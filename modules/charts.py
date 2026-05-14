"""Plotly chart builders for the warehouse dashboard (English, dark theme)."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from . import kpi_calculator as kpi

COLOR_SUCCESS = "#00C896"
COLOR_ALERT = "#FF4B4B"
COLOR_WARNING = "#FFA500"
COLOR_INFO = "#4B9FFF"
COLOR_MUTED = "#888888"
BG_DARK = "#0b0b0b"
PANEL_DARK = "#1a1a1a"


def _apply_layout(fig: go.Figure, title: str, *, height: int | None = None) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, font=dict(color="#f0f0f0", size=15)),
        plot_bgcolor=PANEL_DARK,
        paper_bgcolor=PANEL_DARK,
        font=dict(color="#dcdcdc", family="Inter, system-ui, sans-serif"),
        margin=dict(l=40, r=20, t=50, b=40),
        xaxis=dict(gridcolor="#2a2a2a", zerolinecolor="#2a2a2a"),
        yaxis=dict(gridcolor="#2a2a2a", zerolinecolor="#2a2a2a"),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    if height:
        fig.update_layout(height=height)
    return fig


def picks_timeline(df: pd.DataFrame) -> go.Figure:
    data = kpi.hourly_picks_timeline(df)
    fig = go.Figure()
    if not data.empty:
        fig.add_trace(go.Scatter(
            x=data["timestamp"], y=data["picks_per_hour"],
            mode="lines+markers",
            line=dict(color=COLOR_INFO, width=2.5),
            marker=dict(size=6, color=COLOR_SUCCESS),
            fill="tozeroy", fillcolor="rgba(75, 159, 255, 0.12)",
            hovertemplate="%{x|%d %b}<br>%{y:.1f} picks/h<extra></extra>",
        ))
        fig.update_yaxes(title="Picks/h")
    return _apply_layout(fig, "Picks/hour — daily trend")


def error_rate_per_zone(df: pd.DataFrame) -> go.Figure:
    data = kpi.error_rate_by_zone(df)
    fig = go.Figure()
    if not data.empty:
        colors = [
            COLOR_ALERT if r > 3 else (COLOR_WARNING if r >= 2 else COLOR_SUCCESS)
            for r in data["error_rate"]
        ]
        fig.add_trace(go.Bar(
            x=data["zone"], y=data["error_rate"],
            marker_color=colors,
            text=[f"{v:.2f}%" for v in data["error_rate"]],
            textposition="outside",
            hovertemplate="Zone %{x}<br>%{y:.2f}%<extra></extra>",
        ))
        fig.update_yaxes(title="Error rate (%)")
        fig.update_xaxes(title="Zone")
    return _apply_layout(fig, "Error rate by zone")


def top_operators(df: pd.DataFrame, top_n: int = 10) -> go.Figure:
    data = kpi.picks_per_hour_by_operator(df).head(top_n).iloc[::-1]
    fig = go.Figure()
    if not data.empty:
        fig.add_trace(go.Bar(
            y=data["operator_name"], x=data["picks_per_hour"],
            orientation="h", marker_color=COLOR_SUCCESS,
            text=[f"{v:.1f}" for v in data["picks_per_hour"]],
            textposition="outside",
            hovertemplate="%{y}<br>%{x:.1f} picks/h<extra></extra>",
        ))
        fig.update_xaxes(title="Picks/hour")
    return _apply_layout(fig, f"Top {top_n} operators (picks/h)")


def productivity_heatmap(df: pd.DataFrame) -> go.Figure:
    """Aggressive 5-band colour scale for Zone x Shift heatmap."""
    pivot = kpi.zone_shift_heatmap(df)
    fig = go.Figure()
    if not pivot.empty:
        colorscale = [
            [0.00, "#FF4B4B"],   # <30 red
            [0.20, "#FF4B4B"],
            [0.21, "#FFA500"],   # 30-40 orange
            [0.40, "#FFA500"],
            [0.41, "#F4D35E"],   # 40-50 yellow
            [0.60, "#F4D35E"],
            [0.61, "#00C896"],   # 50-60 green
            [0.80, "#00C896"],
            [0.81, "#007F5F"],   # >60 dark green
            [1.00, "#007F5F"],
        ]
        fig.add_trace(go.Heatmap(
            z=pivot.values,
            x=list(pivot.columns),
            y=list(pivot.index),
            zmin=20, zmax=70,
            colorscale=colorscale,
            colorbar=dict(title="picks/h", tickfont=dict(color="#dcdcdc")),
            text=[[f"{v:.1f}" for v in row] for row in pivot.values],
            texttemplate="%{text}",
            hovertemplate="Zone %{y} / %{x}<br>%{z:.1f} picks/h<extra></extra>",
        ))
        fig.update_xaxes(title="Shift")
        fig.update_yaxes(title="Zone")
    return _apply_layout(fig, "Productivity heatmap — Zone × Shift")


def reception_vs_dispatch(df: pd.DataFrame) -> go.Figure:
    data = kpi.pallets_reception_vs_dispatch(df)
    fig = go.Figure()
    if not data.empty:
        fig.add_trace(go.Scatter(
            x=data["date"], y=data["reception_pallets"],
            name="Reception", mode="lines",
            line=dict(color=COLOR_INFO, width=2),
            fill="tozeroy", fillcolor="rgba(75, 159, 255, 0.22)",
        ))
        fig.add_trace(go.Scatter(
            x=data["date"], y=data["dispatch_pallets"],
            name="Dispatch", mode="lines",
            line=dict(color=COLOR_SUCCESS, width=2),
            fill="tozeroy", fillcolor="rgba(0, 200, 150, 0.22)",
        ))
        fig.update_yaxes(title="Pallets")
    return _apply_layout(fig, "Reception vs dispatch (pallets/day)")


def picks_distribution(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if not df.empty:
        fig.add_trace(go.Histogram(
            x=df["picks_completed"], nbinsx=30,
            marker_color=COLOR_INFO,
            marker_line_color="#0b0b0b", marker_line_width=1,
            hovertemplate="%{x} picks<br>%{y} observations<extra></extra>",
        ))
        fig.update_xaxes(title="Picks per hour")
        fig.update_yaxes(title="Observations")
    return _apply_layout(fig, "Picks/hour distribution")


def dock_throughput(df: pd.DataFrame) -> go.Figure:
    data = kpi.dock_performance(df)
    fig = go.Figure()
    if not data.empty:
        fig.add_trace(go.Bar(x=data["dock_id"], y=data["reception_pallets"],
                             name="Reception", marker_color=COLOR_INFO))
        fig.add_trace(go.Bar(x=data["dock_id"], y=data["dispatch_pallets"],
                             name="Dispatch", marker_color=COLOR_SUCCESS))
        fig.update_layout(barmode="stack")
        fig.update_yaxes(title="Pallets")
    return _apply_layout(fig, "Dock performance")


def sparkline(values: list[float], *, color: str = COLOR_INFO, height: int = 60) -> go.Figure:
    fig = go.Figure()
    if values:
        fig.add_trace(go.Scatter(
            x=list(range(len(values))),
            y=values,
            mode="lines",
            line=dict(color=color, width=2),
            fill="tozeroy",
            fillcolor="rgba(75, 159, 255, 0.18)" if color == COLOR_INFO else "rgba(0, 200, 150, 0.18)",
            hoverinfo="skip",
        ))
    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=4, b=4),
        plot_bgcolor=PANEL_DARK,
        paper_bgcolor=PANEL_DARK,
        showlegend=False,
        xaxis=dict(visible=False, fixedrange=True),
        yaxis=dict(visible=False, fixedrange=True),
    )
    return fig


def performance_gauge(score: float) -> go.Figure:
    if score >= 80:
        bar_color = COLOR_SUCCESS
    elif score >= 60:
        bar_color = "#F4D35E"
    elif score >= 40:
        bar_color = COLOR_WARNING
    else:
        bar_color = COLOR_ALERT

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number=dict(font=dict(color="#ffffff", size=42), suffix=" / 100"),
        gauge=dict(
            axis=dict(range=[0, 100], tickcolor="#888", tickfont=dict(color="#bbb")),
            bar=dict(color=bar_color, thickness=0.32),
            bgcolor=PANEL_DARK,
            borderwidth=0,
            steps=[
                {"range": [0, 40], "color": "rgba(255,75,75,0.22)"},
                {"range": [40, 60], "color": "rgba(255,165,0,0.22)"},
                {"range": [60, 80], "color": "rgba(244,211,94,0.22)"},
                {"range": [80, 100], "color": "rgba(0,200,150,0.22)"},
            ],
            threshold=dict(line=dict(color="#ffffff", width=2), thickness=0.75, value=score),
        ),
    ))
    fig.update_layout(
        height=240,
        margin=dict(l=20, r=20, t=30, b=10),
        paper_bgcolor=PANEL_DARK,
        font=dict(color="#dcdcdc"),
        title=dict(text="Performance score", font=dict(color="#f0f0f0", size=15)),
    )
    return fig


def today_hourly_chart(df: pd.DataFrame) -> go.Figure:
    data = kpi.today_hourly_timeline(df)
    fig = go.Figure()
    if not data.empty:
        fig.add_trace(go.Scatter(
            x=data["hour"], y=data["picks_per_hour"],
            mode="lines+markers",
            line=dict(color=COLOR_SUCCESS, width=2.5),
            marker=dict(size=7, color=COLOR_INFO),
            fill="tozeroy", fillcolor="rgba(0, 200, 150, 0.15)",
            hovertemplate="%{x|%H:%M}<br>%{y:.1f} picks/h<extra></extra>",
        ))
        fig.update_yaxes(title="Picks/h")
        fig.update_xaxes(title="Hour")
    return _apply_layout(fig, "Today — picks/hour by hour", height=320)


def operator_trend_chart(trend: pd.DataFrame, team_avg: float) -> go.Figure:
    fig = go.Figure()
    if not trend.empty:
        fig.add_trace(go.Scatter(
            x=trend["date"], y=trend["picks_per_hour"],
            mode="lines+markers", name="Operator",
            line=dict(color=COLOR_SUCCESS, width=2.5),
            marker=dict(size=6, color=COLOR_INFO),
        ))
        fig.add_hline(
            y=team_avg, line_dash="dash", line_color=COLOR_MUTED,
            annotation_text=f"Team avg {team_avg:.1f}",
            annotation_position="top right",
            annotation_font_color="#bbb",
        )
        fig.update_yaxes(title="Picks/h")
    return _apply_layout(fig, "Personal trend vs team average", height=320)
