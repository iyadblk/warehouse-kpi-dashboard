"""Warehouse KPI Dashboard — Streamlit entrypoint."""
from __future__ import annotations

import io
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.generator import generate, append_live_tick
from modules import alerts as alerts_mod
from modules import charts
from modules import kpi_calculator as kpi

DATA_PATH = ROOT / "data" / "sample_data.csv"
STYLE_PATH = ROOT / "assets" / "style.css"
REFRESH_INTERVAL_MS = 60_000


# ------------------------------ Streamlit setup ------------------------------

st.set_page_config(
    page_title="Warehouse KPI Dashboard",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

if STYLE_PATH.exists():
    st.markdown(f"<style>{STYLE_PATH.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

# Session-state defaults
if "data_version" not in st.session_state:
    st.session_state["data_version"] = 0
if "acknowledged_alerts" not in st.session_state:
    st.session_state["acknowledged_alerts"] = {}  # alert_id -> ack timestamp
if "alert_history" not in st.session_state:
    st.session_state["alert_history"] = []  # list of {id, title, severity, acked_at, resolved_at}
if "live_appends" not in st.session_state:
    st.session_state["live_appends"] = 0
if "sidebar_compact" not in st.session_state:
    st.session_state["sidebar_compact"] = False
if "last_refresh" not in st.session_state:
    st.session_state["last_refresh"] = datetime.now()

# Auto-refresh (60s) — append a live tick on each refresh
try:
    from streamlit_autorefresh import st_autorefresh  # type: ignore
    refresh_count = st_autorefresh(interval=REFRESH_INTERVAL_MS, key="auto_refresh")
except Exception:
    refresh_count = 0
    st.markdown(
        f"<meta http-equiv='refresh' content='{REFRESH_INTERVAL_MS // 1000}'>",
        unsafe_allow_html=True,
    )

if refresh_count and refresh_count != st.session_state.get("last_refresh_count"):
    st.session_state["last_refresh_count"] = refresh_count
    try:
        append_live_tick(DATA_PATH)
        st.session_state["live_appends"] += 1
        st.session_state["data_version"] += 1
        st.session_state["last_refresh"] = datetime.now()
    except Exception:
        pass


# ------------------------------ Data loading ---------------------------------

@st.cache_data(show_spinner=False)
def load_dataset(path: Path, version: int) -> pd.DataFrame:
    del version
    if not path.exists():
        generate(days=30, output_path=path)
    df = pd.read_csv(path, parse_dates=["timestamp"])
    return df


def regenerate_dataset() -> None:
    generate(days=30, output_path=DATA_PATH)
    st.session_state["data_version"] += 1
    st.session_state["last_refresh"] = datetime.now()
    load_dataset.clear()


df_all = load_dataset(DATA_PATH, st.session_state["data_version"])

# Inject compact-mode class on the body
if st.session_state["sidebar_compact"]:
    st.markdown(
        "<script>document.body.classList.add('sidebar-compact');</script>"
        "<style>body{} </style>",
        unsafe_allow_html=True,
    )
    st.markdown('<div class="sidebar-compact"></div>', unsafe_allow_html=True)
    # Force CSS by adding parent class
    st.markdown("""
    <style>
        section.main { padding-left: 0 !important; }
    </style>
    <script>
        try { window.parent.document.body.classList.add('sidebar-compact'); } catch (e) {}
    </script>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <script>
        try { window.parent.document.body.classList.remove('sidebar-compact'); } catch (e) {}
    </script>
    """, unsafe_allow_html=True)


# ------------------------------ Sidebar --------------------------------------

with st.sidebar:
    # Toggle row
    tog_col_a, tog_col_b = st.columns([1, 4])
    with tog_col_a:
        if st.button("☰", help="Collapse / expand the sidebar", use_container_width=True):
            st.session_state["sidebar_compact"] = not st.session_state["sidebar_compact"]
            st.rerun()
    with tog_col_b:
        st.markdown("### Filters")

    period_label = st.selectbox(
        "Period", ["7 days", "14 days", "30 days"], index=2, key="period_filter"
    )
    period_days = {"7 days": 7, "14 days": 14, "30 days": 30}[period_label]

    zone_options = ["All"] + sorted(df_all["zone"].dropna().unique().tolist())
    shift_options = ["All", "Morning", "Afternoon", "Night"]
    operator_options = ["All"] + sorted(df_all["operator_name"].dropna().unique().tolist())

    zone_sel = st.selectbox("Zone", zone_options, index=0)
    shift_sel = st.selectbox("Shift", shift_options, index=0)
    operator_sel = st.selectbox("Operator", operator_options, index=0)

    st.markdown("---")
    if st.button("🔄 Refresh data", use_container_width=True):
        regenerate_dataset()
        st.rerun()


# ------------------------------ Filtering ------------------------------------

now = df_all["timestamp"].max()
period_start = now - timedelta(days=period_days)
prev_period_start = period_start - timedelta(days=period_days)

mask = df_all["timestamp"] >= period_start
prev_mask = (df_all["timestamp"] >= prev_period_start) & (df_all["timestamp"] < period_start)

if zone_sel != "All":
    mask &= df_all["zone"] == zone_sel
    prev_mask &= df_all["zone"] == zone_sel
if shift_sel != "All":
    mask &= df_all["shift"] == shift_sel
    prev_mask &= df_all["shift"] == shift_sel
if operator_sel != "All":
    mask &= df_all["operator_name"] == operator_sel
    prev_mask &= df_all["operator_name"] == operator_sel

df = df_all.loc[mask].copy()
df_prev = df_all.loc[prev_mask].copy()


# ------------------------------ Export Excel ---------------------------------

def build_excel_report(current: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        # Sheet 1 — Global KPIs summary
        snapshot = kpi.kpi_snapshot(current)
        summary_rows = [
            ("Picks per hour (avg)", snapshot["picks_per_hour"]),
            ("Error rate (%)", snapshot["error_rate"]),
            ("Stock accuracy (%)", snapshot["stock_accuracy"]),
            ("Order completion rate (%)", snapshot["completion_rate"]),
            ("Pallets processed (total)", snapshot["pallets_total"]),
            ("Order delay rate (%)", round(kpi.order_delay_rate(current), 2)),
            ("Order cancel rate (%)", round(kpi.order_cancel_rate(current), 2)),
            ("Performance score (/100)", kpi.performance_score(current)),
            ("Rows analysed", len(current)),
            ("Report generated", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ]
        pd.DataFrame(summary_rows, columns=["Metric", "Value"]).to_excel(
            writer, sheet_name="Global KPIs", index=False
        )

        # Sheet 2 — Full operator detail
        kpi.operator_summary(current).to_excel(writer, sheet_name="Operator detail", index=False)

        # Sheet 3 — Hourly trends data
        hourly = (
            current.assign(hour=current["timestamp"].dt.floor("h"))
            .groupby("hour", as_index=False)
            .agg(
                picks_per_hour=("picks_completed", "mean"),
                total_picks=("picks_completed", "sum"),
                errors=("picks_errors", "sum"),
                stock_accuracy=("stock_accuracy", "mean"),
                orders=("orders_processed", "sum"),
                reception_pallets=("reception_pallets", "sum"),
                dispatch_pallets=("dispatch_pallets", "sum"),
            )
            .sort_values("hour")
        )
        hourly["picks_per_hour"] = hourly["picks_per_hour"].round(2)
        hourly["stock_accuracy"] = hourly["stock_accuracy"].round(2)
        hourly.to_excel(writer, sheet_name="Hourly trends", index=False)

    buffer.seek(0)
    return buffer.getvalue()


with st.sidebar:
    st.download_button(
        label="📥 Export Excel report",
        data=build_excel_report(df),
        file_name=f"warehouse_report_{datetime.now():%Y-%m-%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    st.markdown("---")
    st.caption(f"Rows: **{len(df):,}**")
    st.caption(f"Auto-refresh: **{REFRESH_INTERVAL_MS // 1000}s**")
    st.caption(f"Live ticks added: **{st.session_state['live_appends']}**")
    if not df.empty:
        st.caption(f"Last observation: **{df['timestamp'].max():%Y-%m-%d %H:%M}**")


# ------------------------------ Header ---------------------------------------

last_updated = st.session_state["last_refresh"].strftime("%H:%M:%S")

st.markdown(f"""
<div class="dashboard-header">
    <div class="dashboard-title">📦 Warehouse KPI Dashboard</div>
    <div class="live-indicator">
        <span class="live-dot"></span>
        Live · last updated {last_updated}
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown(
    f'<div class="dashboard-subtitle">Period: {period_start:%d %b %Y} → {now:%d %b %Y} '
    f'· Zone: {zone_sel} · Shift: {shift_sel} · Operator: {operator_sel}</div>',
    unsafe_allow_html=True,
)


# ------------------------------ Section 1: Metric cards ----------------------

snapshot = kpi.kpi_snapshot(df, df_prev)


def _delta_html(value: float, *, invert: bool = False, suffix: str = "", precision: int = 1) -> str:
    if value == 0:
        return f'<div class="delta flat">▬ {value:+.{precision}f}{suffix}</div>'
    good = value < 0 if invert else value > 0
    arrow = "▲" if value > 0 else "▼"
    cls = "up" if good else "down"
    return f'<div class="delta {cls}">{arrow} {value:+.{precision}f}{suffix}</div>'


def _delta_int_html(value: int) -> str:
    if value == 0:
        return '<div class="delta flat">▬ +0</div>'
    arrow = "▲" if value > 0 else "▼"
    cls = "up" if value > 0 else "down"
    return f'<div class="delta {cls}">{arrow} {value:+,}</div>'


def _render_metric_card(col, label: str, value: str, delta_html: str,
                        spark_values: list[float], spark_color: str):
    with col:
        st.markdown(
            f'<div class="metric-card">'
            f'<div class="label">{label}</div>'
            f'<div class="value">{value}</div>'
            f'{delta_html}'
            f'</div>',
            unsafe_allow_html=True,
        )
        if spark_values:
            st.plotly_chart(
                charts.sparkline(spark_values, color=spark_color, height=55),
                use_container_width=True,
                config={"displayModeBar": False},
            )


metric_cols = st.columns(5)
_render_metric_card(
    metric_cols[0], "Picks/h avg", f"{snapshot['picks_per_hour']:.1f}",
    _delta_html(snapshot["delta_picks"], precision=1),
    kpi.picks_sparkline(df_all), charts.COLOR_INFO,
)
_render_metric_card(
    metric_cols[1], "Error rate", f"{snapshot['error_rate']:.2f}%",
    _delta_html(snapshot["delta_error"], invert=True, suffix="pp", precision=2),
    kpi.error_rate_sparkline(df_all), charts.COLOR_ALERT,
)
_render_metric_card(
    metric_cols[2], "Stock accuracy", f"{snapshot['stock_accuracy']:.2f}%",
    _delta_html(snapshot["delta_accuracy"], suffix="pp", precision=2),
    kpi.accuracy_sparkline(df_all), charts.COLOR_SUCCESS,
)
_render_metric_card(
    metric_cols[3], "Order completion", f"{snapshot['completion_rate']:.1f}%",
    _delta_html(snapshot["delta_completion"], suffix="pp", precision=1),
    kpi.completion_sparkline(df_all), charts.COLOR_SUCCESS,
)
_render_metric_card(
    metric_cols[4], "Pallets processed", f"{snapshot['pallets_total']:,}",
    _delta_int_html(snapshot["delta_pallets"]),
    kpi.pallets_sparkline(df_all), charts.COLOR_INFO,
)


# ------------------------------ Performance score gauge ---------------------

score_col, today_chart_col = st.columns([1, 2])
with score_col:
    st.plotly_chart(charts.performance_gauge(kpi.performance_score(df)), use_container_width=True)
with today_chart_col:
    st.plotly_chart(charts.today_hourly_chart(df_all), use_container_width=True)


# ------------------------------ Today's Progress ----------------------------

st.markdown("### 🎯 Today's Progress")

today_stats = kpi.today_stats(df, full_df=df_all)
target = today_stats["target"]
picks_done = today_stats["picks_completed"]
progress = today_stats["progress_pct"]

if progress >= 80:
    bar_cls = "good"
elif progress >= 50:
    bar_cls = "mid"
else:
    bar_cls = "bad"

eta_text = "—"
if today_stats["eta"] is not None:
    eta_text = today_stats["eta"].strftime("%H:%M")

p1, p2, p3, p4 = st.columns(4)
with p1:
    st.markdown(
        f'<div class="today-card">'
        f'<div class="title">Picks today vs target</div>'
        f'<div class="big">{picks_done:,} / {target:,}</div>'
        f'<div class="progress-shell">'
        f'<div class="progress-fill {bar_cls}" style="width:{min(progress, 100):.1f}%"></div>'
        f'</div>'
        f'<div class="sub">{progress:.1f}% of daily target</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
with p2:
    st.markdown(
        f'<div class="today-card">'
        f'<div class="title">Estimated completion</div>'
        f'<div class="big">{eta_text}</div>'
        f'<div class="sub">Pace: {today_stats["pace"]:.1f} picks/h</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
with p3:
    st.markdown(
        f'<div class="today-card">'
        f'<div class="title">Hours left in shift</div>'
        f'<div class="big">{today_stats["hours_remaining_in_shift"]} h</div>'
        f'<div class="sub">Current shift: {today_stats["current_shift"]}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
with p4:
    st.markdown(
        f'<div class="today-card">'
        f'<div class="title">Active operators (last hr)</div>'
        f'<div class="big">{today_stats["active_operators"]}</div>'
        f'<div class="sub">Total today: {today_stats["picks_completed"]:,} picks</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ------------------------------ Today's Operations --------------------------

st.markdown("### 🔴 Today's Operations")

t1, t2, t3 = st.columns(3)
with t1:
    cs = today_stats["current_shift_picks_per_hour"]
    sa = today_stats["shift_average_picks_per_hour"]
    delta = cs - sa
    delta_html = _delta_html(round(delta, 1), precision=1) if sa else '<div class="delta flat">—</div>'
    st.markdown(
        f'<div class="today-card">'
        f'<div class="title">Current shift performance</div>'
        f'<div class="big">{cs:.1f} picks/h</div>'
        f'<div class="sub">Shift avg ({today_stats["current_shift"]}): {sa:.1f}</div>'
        f'{delta_html}'
        f'</div>',
        unsafe_allow_html=True,
    )
with t2:
    top = today_stats["top_performer"]
    if top:
        st.markdown(
            f'<div class="today-card">'
            f'<div class="title">Top performer today</div>'
            f'<div class="big">{top["operator_name"]}</div>'
            f'<div class="sub">{top["operator_id"]} · {top["picks"]:,} picks</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="today-card"><div class="title">Top performer today</div>'
            '<div class="big">—</div><div class="sub">No data yet</div></div>',
            unsafe_allow_html=True,
        )
with t3:
    worst = today_stats["worst_zone"]
    if worst:
        st.markdown(
            f'<div class="today-card">'
            f'<div class="title">Most problematic zone</div>'
            f'<div class="big">Zone {worst["zone"]}</div>'
            f'<div class="sub">{worst["error_rate"]:.2f}% error rate today</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="today-card"><div class="title">Most problematic zone</div>'
            '<div class="big">—</div><div class="sub">No errors recorded today</div></div>',
            unsafe_allow_html=True,
        )


# ------------------------------ Operator drill-down -------------------------

if operator_sel != "All":
    st.markdown("### 👤 Operator drill-down")
    drill = kpi.operator_drilldown(df, df_all.loc[mask | (df_all["operator_name"] == operator_sel)])
    if drill:
        d1, d2, d3, d4 = st.columns(4)
        with d1:
            st.markdown(
                f'<div class="today-card">'
                f'<div class="title">{drill["operator_id"]}</div>'
                f'<div class="big">{drill["operator_name"]}</div>'
                f'<div class="sub">Attendance: {drill["attendance_pct"]:.1f}%</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with d2:
            delta = drill["picks_per_hour"] - drill["team_picks_per_hour"]
            st.markdown(
                f'<div class="today-card">'
                f'<div class="title">Picks/h vs team</div>'
                f'<div class="big">{drill["picks_per_hour"]:.1f}</div>'
                f'<div class="sub">Team avg: {drill["team_picks_per_hour"]:.1f}</div>'
                f'{_delta_html(round(delta, 1), precision=1)}'
                f'</div>',
                unsafe_allow_html=True,
            )
        with d3:
            delta = drill["error_rate"] - drill["team_error_rate"]
            st.markdown(
                f'<div class="today-card">'
                f'<div class="title">Error rate vs team</div>'
                f'<div class="big">{drill["error_rate"]:.2f}%</div>'
                f'<div class="sub">Team avg: {drill["team_error_rate"]:.2f}%</div>'
                f'{_delta_html(round(delta, 2), invert=True, suffix="pp", precision=2)}'
                f'</div>',
                unsafe_allow_html=True,
            )
        with d4:
            delta = drill["performance_score"] - drill["team_performance_score"]
            st.markdown(
                f'<div class="today-card">'
                f'<div class="title">Performance score</div>'
                f'<div class="big">{drill["performance_score"]:.1f} / 100</div>'
                f'<div class="sub">Team avg: {drill["team_performance_score"]:.1f}</div>'
                f'{_delta_html(round(delta, 1), precision=1)}'
                f'</div>',
                unsafe_allow_html=True,
            )

        s1, s2 = st.columns(2)
        with s1:
            if drill["best_shift"]:
                b = drill["best_shift"]
                st.markdown(
                    f'<div class="today-card">'
                    f'<div class="title">Best shift</div>'
                    f'<div class="big">{b["picks_per_hour"]:.1f} picks/h</div>'
                    f'<div class="sub">{b["shift"]} · {b["day"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        with s2:
            if drill["worst_shift"]:
                w = drill["worst_shift"]
                st.markdown(
                    f'<div class="today-card">'
                    f'<div class="title">Worst shift</div>'
                    f'<div class="big">{w["picks_per_hour"]:.1f} picks/h</div>'
                    f'<div class="sub">{w["shift"]} · {w["day"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        st.plotly_chart(
            charts.operator_trend_chart(drill["trend"], drill["team_picks_per_hour"]),
            use_container_width=True,
        )
    else:
        st.info("No data for the selected operator and filters.")


# ------------------------------ Section 2: Alerts ----------------------------

st.markdown("### 🚨 Active alerts")
acked_ids = set(st.session_state["acknowledged_alerts"].keys())
active_alerts, acked_alerts = alerts_mod.evaluate(df, acknowledged=acked_ids)

# Clean acks for alerts no longer firing — move them to history
current_ids = {a.alert_id for a in active_alerts + acked_alerts}
stale_ids = [aid for aid in list(st.session_state["acknowledged_alerts"]) if aid not in current_ids]
for aid in stale_ids:
    acked_at = st.session_state["acknowledged_alerts"].pop(aid)
    st.session_state["alert_history"].append({
        "id": aid, "title": "Resolved alert", "severity": "—",
        "acked_at": acked_at, "resolved_at": datetime.now(),
    })

if not active_alerts:
    st.markdown(
        '<div class="no-alert">✅ No critical thresholds exceeded for the current filters.</div>',
        unsafe_allow_html=True,
    )
else:
    red_count = sum(1 for a in active_alerts if a.severity == "red")
    orange_count = len(active_alerts) - red_count
    st.caption(f"{red_count} red · {orange_count} orange — sorted by severity score")

    visible = active_alerts[:10]
    for alert in visible:
        c_msg, c_btn = st.columns([5, 1])
        with c_msg:
            st.markdown(
                f'<div class="alert-banner {alert.severity}">'
                f'<div class="alert-body">'
                f'<span class="alert-title">{alert.title}</span>'
                f'{alert.message}'
                f'<span class="severity-badge">Severity {alert.severity_score}/10</span>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with c_btn:
            if st.button("Acknowledge", key=f"ack_{alert.alert_id}", use_container_width=True):
                st.session_state["acknowledged_alerts"][alert.alert_id] = datetime.now()
                st.rerun()

    if len(active_alerts) > 10:
        with st.expander(f"Show {len(active_alerts) - 10} more active alert(s)"):
            for alert in active_alerts[10:]:
                st.markdown(
                    f'<div class="alert-banner {alert.severity}">'
                    f'<div class="alert-body">'
                    f'<span class="alert-title">{alert.title}</span>'
                    f'{alert.message}'
                    f'<span class="severity-badge">Severity {alert.severity_score}/10</span>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )

# Acknowledged + history (last 24h)
with st.expander(f"Acknowledged & resolved (last 24h) — {len(acked_alerts) + len(st.session_state['alert_history'])}"):
    if acked_alerts:
        st.markdown("**Acknowledged (still firing):**")
        for alert in acked_alerts:
            st.markdown(
                f'<div class="alert-banner {alert.severity}" style="opacity:0.7">'
                f'<div class="alert-body">'
                f'<span class="alert-title">{alert.title}</span>'
                f'{alert.message}'
                f'<span class="severity-badge">Severity {alert.severity_score}/10</span>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
    cutoff = datetime.now() - timedelta(hours=24)
    history = [h for h in st.session_state["alert_history"] if h["resolved_at"] >= cutoff]
    if history:
        st.markdown("**Resolved in the last 24h:**")
        for h in history[-20:]:
            st.markdown(
                f"- `{h['id']}` resolved at {h['resolved_at']:%Y-%m-%d %H:%M:%S}"
            )
    if not acked_alerts and not history:
        st.caption("No acknowledged or recently resolved alerts.")


# ------------------------------ Section: Trend charts ----------------------

st.markdown("### 📈 Trends")
row1_left, row1_right = st.columns(2)
with row1_left:
    st.plotly_chart(charts.picks_timeline(df), use_container_width=True)
with row1_right:
    st.plotly_chart(charts.error_rate_per_zone(df), use_container_width=True)

row2_left, row2_right = st.columns(2)
with row2_left:
    st.plotly_chart(charts.top_operators(df), use_container_width=True)
with row2_right:
    st.plotly_chart(charts.productivity_heatmap(df), use_container_width=True)

row3_left, row3_right = st.columns(2)
with row3_left:
    st.plotly_chart(charts.reception_vs_dispatch(df), use_container_width=True)
with row3_right:
    st.plotly_chart(charts.picks_distribution(df), use_container_width=True)

st.plotly_chart(charts.dock_throughput(df), use_container_width=True)


# ------------------------------ Operator table -----------------------------

st.markdown("### 👷 Operator detail")

summary = kpi.operator_summary(df).rename(columns={
    "operator_id": "ID",
    "operator_name": "Operator",
    "picks_per_hour": "Picks/h",
    "total_picks": "Total picks",
    "error_rate": "Error rate (%)",
    "stock_accuracy": "Stock acc. (%)",
    "orders_processed": "Orders",
    "distance_m": "Avg distance (m)",
})

if summary.empty:
    st.info("No operator data for the current filters.")
else:
    max_picks = float(summary["Picks/h"].max() or 1)

    def _color_error(value: float) -> str:
        if value > 3:
            return "background-color: rgba(255,75,75,0.35); color: #fff;"
        if value >= 2:
            return "background-color: rgba(255,165,0,0.30); color: #fff;"
        return "background-color: rgba(0,200,150,0.22); color: #fff;"

    def _color_accuracy(value: float) -> str:
        if value < 96:
            return "background-color: rgba(255,75,75,0.35); color: #fff;"
        if value < 97:
            return "background-color: rgba(255,165,0,0.30); color: #fff;"
        return "background-color: rgba(0,200,150,0.22); color: #fff;"

    styled = (
        summary.style
        .format({
            "Picks/h": "{:.1f}",
            "Total picks": "{:,.0f}",
            "Error rate (%)": "{:.2f}",
            "Stock acc. (%)": "{:.2f}",
            "Orders": "{:,.0f}",
            "Avg distance (m)": "{:.1f}",
        })
        .map(_color_error, subset=["Error rate (%)"])
        .map(_color_accuracy, subset=["Stock acc. (%)"])
        .bar(subset=["Picks/h"], color="#00C896", vmin=0, vmax=max_picks)
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)

st.markdown("---")
st.caption("© Iyad Belkadi — Warehouse KPI Dashboard · Simulated data, auto-refresh every 60s")
