"""Recommendation pipeline: load crops, score them, search sowing windows."""

from __future__ import annotations

import json
from datetime import date, timedelta
from functools import lru_cache
from typing import Any

import pandas as pd

from agri import DATA_DIR
from agri.scoring import FitInputs, FitResult, score_crop
from agri.weather import (
    daily_forecast_df,
    fetch_climate_normals,
    fetch_forecast,
    forecast_window_stats,
)
from agri.soil import root_zone_moisture_pct, root_zone_temp_c
from agri.suitability import geographic_fit
from agri.terrain import terrain_summary


@lru_cache(maxsize=1)
def load_crops() -> list[dict[str, Any]]:
    path = DATA_DIR / "crops.json"
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def crops_by_id() -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in load_crops()}


def _expected_rain_for_window(
    forecast_json: dict, normals: pd.DataFrame, sowing: date, days: int
) -> float:
    """Forecast for the part we have, climate normals for the rest."""
    df = daily_forecast_df(forecast_json)
    today = pd.Timestamp.today().normalize()
    end = pd.Timestamp(sowing) + pd.Timedelta(days=days)
    rain = 0.0
    if not df.empty:
        cut = df[(df["time"] >= pd.Timestamp(sowing)) & (df["time"] < end)]
        rain += float(cut["precipitation_sum"].sum())
        latest_forecast_end = df["time"].max()
    else:
        latest_forecast_end = today

    if pd.Timestamp(sowing) + pd.Timedelta(days=days) > latest_forecast_end and not normals.empty:
        nm = normals.set_index("month")["precip_mm"].to_dict() if "precip_mm" in normals else {}
        cursor = max(pd.Timestamp(sowing), latest_forecast_end + pd.Timedelta(days=1))
        while cursor < end:
            month_rain = float(nm.get(cursor.month, 0.0)) if nm else 0.0
            rain += month_rain
            cursor += pd.Timedelta(days=30)
    return rain


def build_inputs_for_window(
    lat: float,
    lng: float,
    sowing_date: date,
    growing_days: int,
    forecast_json: dict,
    normals: pd.DataFrame,
) -> FitInputs:
    offset = (sowing_date - date.today()).days
    if offset < 0:
        offset = 0
    early = forecast_window_stats(forecast_json, offset, min(14, growing_days))
    full = forecast_window_stats(forecast_json, offset, min(growing_days, 14))
    tavg = early.get("tavg_mean") or full.get("tavg_mean") or 25.0
    tmin = early.get("tmin_mean") or 18.0
    tmax = early.get("tmax_mean") or 32.0
    heat_days = full.get("heat_days", 0)
    frost_days = full.get("frost_days", 0)
    expected_rain = _expected_rain_for_window(forecast_json, normals, sowing_date, growing_days)
    sm = root_zone_moisture_pct(forecast_json)
    st = root_zone_temp_c(forecast_json)
    slope = terrain_summary(lat, lng).get("slope_pct", 5.0)
    return FitInputs(
        avg_temp_c=tavg,
        tmin_window_c=tmin,
        tmax_window_c=tmax,
        expected_rain_mm=expected_rain,
        soil_moisture_pct=sm,
        soil_temp_c=st,
        sowing_date=sowing_date,
        heat_days=heat_days,
        frost_days=frost_days,
        slope_pct=slope,
    )


def rank_for_date(
    lat: float,
    lng: float,
    sowing_date: date,
    top_n: int = 12,
    forecast_json: dict | None = None,
    normals: pd.DataFrame | None = None,
) -> list[FitResult]:
    if forecast_json is None:
        forecast_json = fetch_forecast(lat, lng)
    if normals is None:
        normals = fetch_climate_normals(lat, lng)
    elev = terrain_summary(lat, lng).get("elevation_m")
    crops = load_crops()
    results: list[FitResult] = []
    for crop in crops:
        if geographic_fit(crop, elev, normals)[0] < 0.1:
            continue
        gd = int(sum(crop["growing_days"]) / 2)
        inputs = build_inputs_for_window(lat, lng, sowing_date, gd, forecast_json, normals)
        results.append(score_crop(crop, inputs))
    results.sort(key=lambda r: r.score, reverse=True)
    return results[:top_n]


def sowing_window_scan(
    lat: float,
    lng: float,
    crop_id: str,
    start: date | None = None,
    horizon_days: int = 90,
    step_days: int = 14,
) -> list[tuple[date, FitResult]]:
    """Score a single crop across the next N weeks of possible sowing dates."""
    forecast_json = fetch_forecast(lat, lng)
    normals = fetch_climate_normals(lat, lng)
    crop = crops_by_id().get(crop_id)
    if crop is None:
        return []
    start = start or date.today()
    gd = int(sum(crop["growing_days"]) / 2)
    out: list[tuple[date, FitResult]] = []
    for offset in range(0, horizon_days + 1, step_days):
        d = start + timedelta(days=offset)
        inputs = build_inputs_for_window(lat, lng, d, gd, forecast_json, normals)
        out.append((d, score_crop(crop, inputs)))
    return out


def monthly_suitability_matrix(
    lat: float,
    lng: float,
    forecast_json: dict | None = None,
    normals: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """12-month suitability heatmap data (rows=crops, cols=months)."""
    if forecast_json is None:
        forecast_json = fetch_forecast(lat, lng)
    if normals is None:
        normals = fetch_climate_normals(lat, lng)
    elev = terrain_summary(lat, lng).get("elevation_m")
    crops = load_crops()
    today = date.today()
    months: list[date] = []
    for i in range(12):
        d = date(today.year + (today.month + i - 1) // 12, ((today.month - 1 + i) % 12) + 1, 15)
        months.append(d)
    rows = []
    for crop in crops:
        if geographic_fit(crop, elev, normals)[0] < 0.1:
            continue
        gd = int(sum(crop["growing_days"]) / 2)
        row: dict[str, Any] = {"crop_id": crop["id"], "name_en": crop["name_en"]}
        for d in months:
            inputs = build_inputs_for_window(lat, lng, d, gd, forecast_json, normals)
            row[d.strftime("%b %Y")] = score_crop(crop, inputs).score
        rows.append(row)
    return pd.DataFrame(rows)


def income_estimate_inr_per_acre(crop: dict[str, Any]) -> tuple[int, int]:
    """Rough income band (₹/acre) from yield × price bands. Labeled estimate in UI."""
    yields = crop.get("yield_q_per_acre", [0, 0])
    prices = crop.get("price_inr_per_q", [0, 0])
    lo = int(yields[0] * prices[0])
    hi = int(yields[1] * prices[1])
    return lo, hi
