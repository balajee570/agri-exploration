"""Plotly chart builders. Keep them stateless and Streamlit-agnostic."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


GREEN = "#2E7D32"
AMBER = "#F9A825"
RED = "#C62828"
BLUE = "#1565C0"


def forecast_temperature_chart(daily: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=daily["time"],
            y=daily["temperature_2m_max"],
            mode="lines",
            line=dict(color=RED, width=2),
            name="Tmax",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=daily["time"],
            y=daily["temperature_2m_min"],
            mode="lines",
            line=dict(color=BLUE, width=2),
            name="Tmin",
            fill="tonexty",
            fillcolor="rgba(33,150,243,0.08)",
        )
    )
    fig.update_layout(
        margin=dict(l=10, r=10, t=30, b=10),
        height=260,
        title="Temperature forecast (°C)",
        xaxis_title=None,
        yaxis_title="°C",
        legend=dict(orientation="h", y=1.1),
    )
    return fig


def rainfall_bar_chart(daily: pd.DataFrame) -> go.Figure:
    today = pd.Timestamp.today().normalize()
    color = ["#90A4AE" if t < today else GREEN for t in daily["time"]]
    fig = go.Figure(
        go.Bar(
            x=daily["time"],
            y=daily["precipitation_sum"],
            marker_color=color,
            name="Rainfall",
        )
    )
    fig.update_layout(
        margin=dict(l=10, r=10, t=30, b=10),
        height=240,
        title="Daily rainfall (mm) — grey = recent past, green = forecast",
        yaxis_title="mm",
        xaxis_title=None,
        showlegend=False,
    )
    return fig


def water_budget_chart(budget: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=budget["time"], y=budget["rain_mm"], name="Rain", marker_color=BLUE
        )
    )
    fig.add_trace(
        go.Bar(
            x=budget["time"], y=-budget["et0_mm"], name="ET₀ (loss)", marker_color=AMBER
        )
    )
    fig.add_trace(
        go.Scatter(
            x=budget["time"],
            y=budget["cumulative_balance_mm"],
            name="Cumulative balance",
            line=dict(color=GREEN, width=2.5),
            yaxis="y2",
        )
    )
    fig.update_layout(
        barmode="relative",
        height=360,
        margin=dict(l=10, r=10, t=30, b=10),
        title="Daily water balance — rainfall in, ET₀ out, cumulative line",
        yaxis=dict(title="mm/day"),
        yaxis2=dict(title="Cumulative mm", overlaying="y", side="right"),
        legend=dict(orientation="h", y=1.12),
    )
    return fig


def suitability_heatmap(df: pd.DataFrame) -> go.Figure:
    month_cols = [c for c in df.columns if c not in {"crop_id", "name_en"}]
    values = df[month_cols].values
    labels = df["name_en"].tolist()
    fig = px.imshow(
        values,
        x=month_cols,
        y=labels,
        color_continuous_scale=[(0, "#B71C1C"), (0.4, "#FF9800"), (0.7, "#FBC02D"), (1, "#2E7D32")],
        zmin=0,
        zmax=100,
        aspect="auto",
        labels=dict(color="Fit %"),
    )
    fig.update_layout(
        height=max(420, 22 * len(labels)),
        margin=dict(l=10, r=10, t=30, b=10),
        title="Sowing suitability by month (next 12 months)",
    )
    return fig


def soil_moisture_profile(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure(
        go.Bar(
            y=df["depth"],
            x=df["moisture_pct"].fillna(0),
            orientation="h",
            marker_color=BLUE,
            text=[f"{v:.1f}%" if pd.notna(v) else "n/a" for v in df["moisture_pct"]],
            textposition="outside",
        )
    )
    fig.update_layout(
        height=240,
        margin=dict(l=10, r=10, t=30, b=10),
        title="Soil moisture by depth (% volumetric)",
        xaxis=dict(range=[0, 60], title="%"),
        yaxis_title=None,
    )
    return fig


def sowing_window_chart(rows: list[tuple]) -> go.Figure:
    xs = [d.isoformat() for d, _ in rows]
    ys = [r.score for _, r in rows]
    colors = [GREEN if y >= 65 else AMBER if y >= 45 else RED for y in ys]
    fig = go.Figure(go.Bar(x=xs, y=ys, marker_color=colors, text=[f"{y:.0f}" for y in ys], textposition="outside"))
    fig.update_layout(
        height=260,
        margin=dict(l=10, r=10, t=30, b=10),
        title="Sowing-window fit % across the next 90 days",
        yaxis=dict(range=[0, 105]),
    )
    return fig


def compare_radar(by_crop: dict[str, dict[str, float]]) -> go.Figure:
    categories = list(next(iter(by_crop.values())).keys())
    fig = go.Figure()
    palette = ["#2E7D32", "#1565C0", "#F9A825", "#6A1B9A"]
    for i, (name, comps) in enumerate(by_crop.items()):
        fig.add_trace(
            go.Scatterpolar(
                r=[comps[c] for c in categories],
                theta=categories,
                fill="toself",
                name=name,
                line=dict(color=palette[i % len(palette)]),
            )
        )
    fig.update_layout(
        polar=dict(radialaxis=dict(range=[0, 100], visible=True)),
        height=420,
        margin=dict(l=10, r=10, t=30, b=10),
        title="Component-wise comparison",
    )
    return fig
