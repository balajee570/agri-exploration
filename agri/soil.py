"""Soil moisture & temp extraction from Open-Meteo's land-surface model."""

from __future__ import annotations

from typing import Any

import pandas as pd

from agri.weather import hourly_forecast_df

_DEPTH_BANDS = [
    ("0-1 cm", "soil_moisture_0_to_1cm", "soil_temperature_0cm"),
    ("1-3 cm", "soil_moisture_1_to_3cm", None),
    ("3-9 cm", "soil_moisture_3_to_9cm", "soil_temperature_6cm"),
    ("9-27 cm", "soil_moisture_9_to_27cm", "soil_temperature_18cm"),
    (">27 cm", None, "soil_temperature_54cm"),
]


def current_soil_profile(forecast_json: dict[str, Any]) -> pd.DataFrame:
    """Latest-available soil moisture (% volumetric) and temp at multiple depths."""
    hourly = hourly_forecast_df(forecast_json)
    if hourly.empty:
        return pd.DataFrame()
    now = pd.Timestamp.now(tz=hourly["time"].dt.tz if hourly["time"].dt.tz else None).floor("h")
    row = hourly.iloc[(hourly["time"] - now).abs().argsort()[:1]]
    out = []
    for label, moist_col, temp_col in _DEPTH_BANDS:
        m = float(row[moist_col].iloc[0]) * 100 if moist_col and moist_col in row else None
        t = float(row[temp_col].iloc[0]) if temp_col and temp_col in row else None
        out.append({"depth": label, "moisture_pct": m, "temp_c": t})
    return pd.DataFrame(out)


def root_zone_moisture_pct(forecast_json: dict[str, Any]) -> float:
    """Average volumetric moisture in 3-27 cm (typical root zone) as a percent."""
    hourly = hourly_forecast_df(forecast_json)
    if hourly.empty:
        return float("nan")
    cols = ["soil_moisture_3_to_9cm", "soil_moisture_9_to_27cm"]
    cols = [c for c in cols if c in hourly.columns]
    if not cols:
        return float("nan")
    now = pd.Timestamp.now(tz=hourly["time"].dt.tz if hourly["time"].dt.tz else None).floor("h")
    row = hourly.iloc[(hourly["time"] - now).abs().argsort()[:1]]
    return float(row[cols].mean(axis=1).iloc[0]) * 100


def root_zone_temp_c(forecast_json: dict[str, Any]) -> float:
    """Soil temperature at ~18 cm (root zone)."""
    hourly = hourly_forecast_df(forecast_json)
    if hourly.empty or "soil_temperature_18cm" not in hourly.columns:
        return float("nan")
    now = pd.Timestamp.now(tz=hourly["time"].dt.tz if hourly["time"].dt.tz else None).floor("h")
    row = hourly.iloc[(hourly["time"] - now).abs().argsort()[:1]]
    return float(row["soil_temperature_18cm"].iloc[0])
