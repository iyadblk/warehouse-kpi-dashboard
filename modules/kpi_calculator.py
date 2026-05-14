"""KPI computation for the warehouse dataset."""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

DAILY_TARGET_PER_OPERATOR = 1200


def _safe_div(num: float, den: float) -> float:
    return float(num / den) if den else 0.0


# --------------------------- Core KPIs ---------------------------------------

def picks_per_hour_global(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    return float(df["picks_completed"].mean())


def picks_per_hour_by_operator(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["operator_id", "operator_name", "picks_per_hour"])
    grouped = (
        df.groupby(["operator_id", "operator_name"], as_index=False)["picks_completed"]
        .mean()
        .rename(columns={"picks_completed": "picks_per_hour"})
        .sort_values("picks_per_hour", ascending=False)
    )
    grouped["picks_per_hour"] = grouped["picks_per_hour"].round(1)
    return grouped


def picks_per_hour_by_zone(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["zone", "picks_per_hour"])
    grouped = (
        df.groupby("zone", as_index=False)["picks_completed"]
        .mean()
        .rename(columns={"picks_completed": "picks_per_hour"})
    )
    grouped["picks_per_hour"] = grouped["picks_per_hour"].round(1)
    return grouped


def picks_per_hour_by_shift(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["shift", "picks_per_hour"])
    grouped = (
        df.groupby("shift", as_index=False)["picks_completed"]
        .mean()
        .rename(columns={"picks_completed": "picks_per_hour"})
    )
    grouped["picks_per_hour"] = grouped["picks_per_hour"].round(1)
    return grouped


def error_rate_global(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    return _safe_div(df["picks_errors"].sum(), df["picks_completed"].sum()) * 100


def error_rate_by_operator(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["operator_id", "operator_name", "error_rate"])
    grouped = df.groupby(["operator_id", "operator_name"], as_index=False).agg(
        errors=("picks_errors", "sum"),
        picks=("picks_completed", "sum"),
    )
    grouped["error_rate"] = (grouped["errors"] / grouped["picks"].clip(lower=1)) * 100
    grouped["error_rate"] = grouped["error_rate"].round(2)
    return grouped[["operator_id", "operator_name", "error_rate"]].sort_values(
        "error_rate", ascending=False
    )


def error_rate_by_zone(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["zone", "error_rate"])
    grouped = df.groupby("zone", as_index=False).agg(
        errors=("picks_errors", "sum"),
        picks=("picks_completed", "sum"),
    )
    grouped["error_rate"] = (grouped["errors"] / grouped["picks"].clip(lower=1)) * 100
    grouped["error_rate"] = grouped["error_rate"].round(2)
    return grouped[["zone", "error_rate"]]


def stock_accuracy_mean(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    return float(df["stock_accuracy"].mean())


def order_completion_rate(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    return _safe_div((df["order_status"] == "Completed").sum(), len(df)) * 100


def order_delay_rate(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    return _safe_div((df["order_status"] == "Delayed").sum(), len(df)) * 100


def order_cancel_rate(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    return _safe_div((df["order_status"] == "Cancelled").sum(), len(df)) * 100


def avg_distance_per_operator(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["operator_id", "operator_name", "distance_m"])
    grouped = (
        df.groupby(["operator_id", "operator_name"], as_index=False)["distance_m"]
        .mean()
        .sort_values("distance_m", ascending=False)
    )
    grouped["distance_m"] = grouped["distance_m"].round(1)
    return grouped


def pallets_reception_vs_dispatch(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["date", "reception_pallets", "dispatch_pallets"])
    daily = (
        df.assign(date=df["timestamp"].dt.date)
        .groupby("date", as_index=False)[["reception_pallets", "dispatch_pallets"]]
        .sum()
    )
    daily["date"] = pd.to_datetime(daily["date"])
    return daily


def pallets_totals(df: pd.DataFrame) -> tuple[int, int]:
    if df.empty:
        return 0, 0
    return int(df["reception_pallets"].sum()), int(df["dispatch_pallets"].sum())


def dock_performance(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["dock_id", "reception_pallets", "dispatch_pallets", "throughput"])
    grouped = df.groupby("dock_id", as_index=False).agg(
        reception_pallets=("reception_pallets", "sum"),
        dispatch_pallets=("dispatch_pallets", "sum"),
        picks_completed=("picks_completed", "sum"),
    )
    grouped["throughput"] = grouped["reception_pallets"] + grouped["dispatch_pallets"]
    return grouped.sort_values("throughput", ascending=False)


def operator_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=[
            "operator_id", "operator_name", "picks_per_hour", "total_picks",
            "error_rate", "stock_accuracy", "orders_processed", "distance_m",
        ])
    grouped = df.groupby(["operator_id", "operator_name"], as_index=False).agg(
        picks_per_hour=("picks_completed", "mean"),
        total_picks=("picks_completed", "sum"),
        errors=("picks_errors", "sum"),
        stock_accuracy=("stock_accuracy", "mean"),
        orders_processed=("orders_processed", "sum"),
        distance_m=("distance_m", "mean"),
    )
    grouped["error_rate"] = (grouped["errors"] / grouped["total_picks"].clip(lower=1)) * 100
    grouped["picks_per_hour"] = grouped["picks_per_hour"].round(1)
    grouped["error_rate"] = grouped["error_rate"].round(2)
    grouped["stock_accuracy"] = grouped["stock_accuracy"].round(2)
    grouped["distance_m"] = grouped["distance_m"].round(1)
    return grouped[[
        "operator_id", "operator_name", "picks_per_hour", "total_picks",
        "error_rate", "stock_accuracy", "orders_processed", "distance_m",
    ]].sort_values("picks_per_hour", ascending=False)


def zone_shift_heatmap(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    pivot = df.pivot_table(
        index="zone", columns="shift", values="picks_completed", aggfunc="mean"
    ).round(1)
    shift_order = [s for s in ["Morning", "Afternoon", "Night"] if s in pivot.columns]
    return pivot[shift_order]


def hourly_picks_timeline(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["timestamp", "picks_per_hour"])
    daily = (
        df.assign(date=df["timestamp"].dt.floor("D"))
        .groupby("date", as_index=False)["picks_completed"]
        .mean()
        .rename(columns={"date": "timestamp", "picks_completed": "picks_per_hour"})
    )
    daily["picks_per_hour"] = daily["picks_per_hour"].round(2)
    return daily


def kpi_snapshot(df: pd.DataFrame, prev_df: pd.DataFrame | None = None) -> dict:
    snapshot = {
        "picks_per_hour": round(picks_per_hour_global(df), 1),
        "error_rate": round(error_rate_global(df), 2),
        "stock_accuracy": round(stock_accuracy_mean(df), 2),
        "completion_rate": round(order_completion_rate(df), 1),
        "pallets_total": int(df["reception_pallets"].sum() + df["dispatch_pallets"].sum()) if not df.empty else 0,
    }
    if prev_df is not None and not prev_df.empty:
        snapshot["delta_picks"] = round(snapshot["picks_per_hour"] - picks_per_hour_global(prev_df), 1)
        snapshot["delta_error"] = round(snapshot["error_rate"] - error_rate_global(prev_df), 2)
        snapshot["delta_accuracy"] = round(snapshot["stock_accuracy"] - stock_accuracy_mean(prev_df), 2)
        snapshot["delta_completion"] = round(snapshot["completion_rate"] - order_completion_rate(prev_df), 1)
        prev_pallets = int(prev_df["reception_pallets"].sum() + prev_df["dispatch_pallets"].sum())
        snapshot["delta_pallets"] = snapshot["pallets_total"] - prev_pallets
    else:
        snapshot.update({"delta_picks": 0.0, "delta_error": 0.0, "delta_accuracy": 0.0,
                         "delta_completion": 0.0, "delta_pallets": 0})
    return snapshot


# --------------------------- Composite score ---------------------------------

def performance_score(df: pd.DataFrame) -> float:
    """Weighted composite score (0-100): 40% picks/h, 30% accuracy, 20% (low) errors, 10% completion."""
    if df.empty:
        return 0.0
    picks = picks_per_hour_global(df)
    accuracy = stock_accuracy_mean(df)
    errors = error_rate_global(df)
    completion = order_completion_rate(df)

    picks_score = float(np.clip(picks / 70.0 * 100, 0, 100))            # 70 picks/h = 100
    accuracy_score = float(np.clip((accuracy - 90) / 10.0 * 100, 0, 100))  # 90-100% range
    error_score = float(np.clip((5 - errors) / 5.0 * 100, 0, 100))       # 0% err = 100, 5% = 0
    completion_score = float(np.clip(completion, 0, 100))

    return round(
        picks_score * 0.40
        + accuracy_score * 0.30
        + error_score * 0.20
        + completion_score * 0.10,
        1,
    )


# --------------------------- Sparkline -------------------------------------

def picks_sparkline(df: pd.DataFrame, days: int = 7) -> list[float]:
    if df.empty:
        return []
    end = df["timestamp"].max().floor("D")
    start = end - timedelta(days=days - 1)
    window = df[df["timestamp"] >= start]
    if window.empty:
        return []
    daily = (
        window.assign(d=window["timestamp"].dt.floor("D"))
        .groupby("d")["picks_completed"].mean()
        .sort_index()
    )
    return [round(v, 2) for v in daily.tolist()]


def error_rate_sparkline(df: pd.DataFrame, days: int = 7) -> list[float]:
    if df.empty:
        return []
    end = df["timestamp"].max().floor("D")
    start = end - timedelta(days=days - 1)
    window = df[df["timestamp"] >= start]
    if window.empty:
        return []
    daily = (
        window.assign(d=window["timestamp"].dt.floor("D"))
        .groupby("d")
        .apply(lambda g: (g["picks_errors"].sum() / max(g["picks_completed"].sum(), 1)) * 100)
        .sort_index()
    )
    return [round(float(v), 2) for v in daily.tolist()]


def accuracy_sparkline(df: pd.DataFrame, days: int = 7) -> list[float]:
    if df.empty:
        return []
    end = df["timestamp"].max().floor("D")
    start = end - timedelta(days=days - 1)
    window = df[df["timestamp"] >= start]
    if window.empty:
        return []
    daily = (
        window.assign(d=window["timestamp"].dt.floor("D"))
        .groupby("d")["stock_accuracy"].mean()
        .sort_index()
    )
    return [round(v, 2) for v in daily.tolist()]


def completion_sparkline(df: pd.DataFrame, days: int = 7) -> list[float]:
    if df.empty:
        return []
    end = df["timestamp"].max().floor("D")
    start = end - timedelta(days=days - 1)
    window = df[df["timestamp"] >= start]
    if window.empty:
        return []
    daily = (
        window.assign(d=window["timestamp"].dt.floor("D"))
        .groupby("d")
        .apply(lambda g: (g["order_status"].eq("Completed").sum() / max(len(g), 1)) * 100)
        .sort_index()
    )
    return [round(float(v), 2) for v in daily.tolist()]


def pallets_sparkline(df: pd.DataFrame, days: int = 7) -> list[float]:
    if df.empty:
        return []
    end = df["timestamp"].max().floor("D")
    start = end - timedelta(days=days - 1)
    window = df[df["timestamp"] >= start]
    if window.empty:
        return []
    daily = (
        window.assign(d=window["timestamp"].dt.floor("D"))
        .groupby("d")
        .apply(lambda g: int(g["reception_pallets"].sum() + g["dispatch_pallets"].sum()))
        .sort_index()
    )
    return [float(v) for v in daily.tolist()]


# --------------------------- Today's view -----------------------------------

def _today_bounds(df: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp]:
    last_ts = df["timestamp"].max()
    day_start = last_ts.normalize()
    day_end = day_start + pd.Timedelta(days=1)
    return day_start, day_end


def today_slice(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    start, end = _today_bounds(df)
    return df[(df["timestamp"] >= start) & (df["timestamp"] < end)].copy()


def today_stats(df: pd.DataFrame, full_df: pd.DataFrame | None = None) -> dict:
    """Live stats for the latest day in the dataset."""
    today = today_slice(df)
    if today.empty:
        return {
            "picks_completed": 0, "target": DAILY_TARGET_PER_OPERATOR,
            "progress_pct": 0.0, "eta": None, "hours_remaining_in_shift": 0,
            "active_operators": 0, "current_shift": "—",
            "current_shift_picks_per_hour": 0.0, "shift_average_picks_per_hour": 0.0,
            "top_performer": None, "worst_zone": None,
        }

    n_operators = int(today["operator_id"].nunique())
    picks_completed = int(today["picks_completed"].sum())
    target = DAILY_TARGET_PER_OPERATOR * max(n_operators, 1)
    progress_pct = round(_safe_div(picks_completed, target) * 100, 1)

    last_ts = today["timestamp"].max()
    elapsed_hours = max((last_ts - today["timestamp"].min()).total_seconds() / 3600, 1)
    pace = picks_completed / elapsed_hours
    remaining = max(target - picks_completed, 0)
    eta_hours = remaining / pace if pace > 0 else None
    eta = (last_ts + pd.Timedelta(hours=eta_hours)) if eta_hours is not None else None

    # Hours remaining in current shift
    hour = int(last_ts.hour)
    from data.generator import SHIFT_PROFILES, shift_for_hour  # local import to avoid cycle
    current_shift = shift_for_hour(hour)
    profile = SHIFT_PROFILES[current_shift]
    shift_start = profile["start_hour"]
    elapsed_in_shift = (hour - shift_start) % 24
    hours_remaining = max(profile["length"] - elapsed_in_shift, 0)

    # Active operators: those with rows in the last hour
    last_hour_cutoff = last_ts - pd.Timedelta(hours=1)
    active = int(today.loc[today["timestamp"] >= last_hour_cutoff, "operator_id"].nunique())

    current_shift_df = today[today["shift"] == current_shift]
    current_shift_picks_h = float(current_shift_df["picks_completed"].mean()) if not current_shift_df.empty else 0.0

    # Reference: average picks/h for this shift across the full history
    ref_df = full_df if full_df is not None else df
    ref_shift = ref_df[ref_df["shift"] == current_shift]
    shift_avg = float(ref_shift["picks_completed"].mean()) if not ref_shift.empty else 0.0

    op_picks = (
        today.groupby(["operator_id", "operator_name"])["picks_completed"].sum()
        .reset_index().sort_values("picks_completed", ascending=False)
    )
    top_performer = None
    if not op_picks.empty:
        top = op_picks.iloc[0]
        top_performer = {
            "operator_id": top["operator_id"],
            "operator_name": top["operator_name"],
            "picks": int(top["picks_completed"]),
        }

    zone_err = today.groupby("zone").agg(
        errors=("picks_errors", "sum"),
        picks=("picks_completed", "sum"),
    )
    zone_err["error_rate"] = (zone_err["errors"] / zone_err["picks"].clip(lower=1)) * 100
    worst_zone = None
    if not zone_err.empty:
        worst = zone_err.sort_values("error_rate", ascending=False).iloc[0]
        worst_zone = {"zone": worst.name, "error_rate": round(float(worst["error_rate"]), 2)}

    return {
        "picks_completed": picks_completed,
        "target": target,
        "progress_pct": progress_pct,
        "eta": eta,
        "hours_remaining_in_shift": hours_remaining,
        "active_operators": active,
        "current_shift": current_shift,
        "current_shift_picks_per_hour": round(current_shift_picks_h, 1),
        "shift_average_picks_per_hour": round(shift_avg, 1),
        "top_performer": top_performer,
        "worst_zone": worst_zone,
        "pace": round(pace, 1),
    }


def today_hourly_timeline(df: pd.DataFrame) -> pd.DataFrame:
    today = today_slice(df)
    if today.empty:
        return pd.DataFrame(columns=["hour", "picks_per_hour"])
    hourly = (
        today.assign(hour=today["timestamp"].dt.floor("h"))
        .groupby("hour", as_index=False)["picks_completed"].mean()
        .rename(columns={"picks_completed": "picks_per_hour"})
    )
    hourly["picks_per_hour"] = hourly["picks_per_hour"].round(1)
    return hourly


# --------------------------- Operator drill-down ----------------------------

def operator_drilldown(df_op: pd.DataFrame, team_df: pd.DataFrame) -> dict:
    """All stats for the operator slice vs the team baseline."""
    if df_op.empty:
        return {}

    op_name = df_op["operator_name"].iloc[0]
    op_id = df_op["operator_id"].iloc[0]

    op_picks = picks_per_hour_global(df_op)
    op_errors = error_rate_global(df_op)
    op_accuracy = stock_accuracy_mean(df_op)
    op_completion = order_completion_rate(df_op)
    op_score = performance_score(df_op)

    # Team baseline excludes the operator itself
    team_baseline = team_df[team_df["operator_id"] != op_id]
    team_picks = picks_per_hour_global(team_baseline)
    team_errors = error_rate_global(team_baseline)
    team_accuracy = stock_accuracy_mean(team_baseline)
    team_completion = order_completion_rate(team_baseline)
    team_score = performance_score(team_baseline)

    # Best / worst shift (using shift_for_day, i.e. concrete shift instances)
    per_shift_day = (
        df_op.assign(day=df_op["timestamp"].dt.date)
        .groupby(["day", "shift"], as_index=False)["picks_completed"]
        .mean()
    )
    best_shift = worst_shift = None
    if not per_shift_day.empty:
        b = per_shift_day.sort_values("picks_completed", ascending=False).iloc[0]
        w = per_shift_day.sort_values("picks_completed", ascending=True).iloc[0]
        best_shift = {"day": str(b["day"]), "shift": b["shift"], "picks_per_hour": round(b["picks_completed"], 1)}
        worst_shift = {"day": str(w["day"]), "shift": w["shift"], "picks_per_hour": round(w["picks_completed"], 1)}

    # Consistency / attendance score: share of days the operator worked, normalised
    total_days = max(df_op["timestamp"].dt.date.nunique(), 1)
    period_days = max(
        (df_op["timestamp"].max().normalize() - df_op["timestamp"].min().normalize()).days + 1,
        1,
    )
    attendance = round(total_days / period_days * 100, 1)

    # Personal trend (daily picks/h)
    trend = (
        df_op.assign(date=df_op["timestamp"].dt.floor("D"))
        .groupby("date", as_index=False)["picks_completed"].mean()
        .rename(columns={"picks_completed": "picks_per_hour"})
    )
    trend["picks_per_hour"] = trend["picks_per_hour"].round(2)

    return {
        "operator_id": op_id,
        "operator_name": op_name,
        "picks_per_hour": round(op_picks, 1),
        "error_rate": round(op_errors, 2),
        "stock_accuracy": round(op_accuracy, 2),
        "completion_rate": round(op_completion, 1),
        "performance_score": op_score,
        "team_picks_per_hour": round(team_picks, 1),
        "team_error_rate": round(team_errors, 2),
        "team_stock_accuracy": round(team_accuracy, 2),
        "team_completion_rate": round(team_completion, 1),
        "team_performance_score": team_score,
        "best_shift": best_shift,
        "worst_shift": worst_shift,
        "attendance_pct": attendance,
        "trend": trend,
    }
