"""Open-Meteo: live weather, 14-day forecast, ERA5 archive, climate normals."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import httpx
import pandas as pd

from agri.cache import TTL_ARCHIVE, TTL_CLIMATE, TTL_FORECAST, cached

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
_CLIMATE_URL = "https://climate-api.open-meteo.com/v1/climate"


@cached(TTL_FORECAST)
def fetch_forecast(lat: float, lng: float) -> dict[str, Any]:
    """Current + 14-day forecast incl. multi-depth soil moisture/temp and ET₀."""
    params = {
        "latitude": lat,
        "longitude": lng,
        "timezone": "auto",
        "past_days": 30,
        "forecast_days": 14,
        "current": ",".join(
            [
                "temperature_2m",
                "relative_humidity_2m",
                "wind_speed_10m",
                "precipitation",
                "cloud_cover",
                "weather_code",
                "soil_moisture_0_to_1cm",
                "soil_moisture_3_to_9cm",
                "soil_temperature_0cm",
                "soil_temperature_18cm",
            ]
        ),
        "daily": ",".join(
            [
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_sum",
                "et0_fao_evapotranspiration",
                "shortwave_radiation_sum",
                "wind_speed_10m_max",
                "relative_humidity_2m_mean",
            ]
        ),
        "hourly": ",".join(
            [
                "soil_moisture_0_to_1cm",
                "soil_moisture_1_to_3cm",
                "soil_moisture_3_to_9cm",
                "soil_moisture_9_to_27cm",
                "soil_temperature_0cm",
                "soil_temperature_6cm",
                "soil_temperature_18cm",
                "soil_temperature_54cm",
            ]
        ),
    }
    resp = httpx.get(_FORECAST_URL, params=params, timeout=20.0)
    resp.raise_for_status()
    return resp.json()


@cached(TTL_ARCHIVE)
def fetch_archive_year(lat: float, lng: float, end: date | None = None) -> pd.DataFrame:
    """Last 365 days daily rainfall + temp via ERA5."""
    end = end or date.today() - timedelta(days=5)
    start = end - timedelta(days=365)
    params = {
        "latitude": lat,
        "longitude": lng,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min",
        "timezone": "auto",
    }
    resp = httpx.get(_ARCHIVE_URL, params=params, timeout=30.0)
    resp.raise_for_status()
    daily = resp.json().get("daily", {})
    df = pd.DataFrame(daily)
    if not df.empty:
        df["time"] = pd.to_datetime(df["time"])
    return df


@cached(TTL_CLIMATE)
def fetch_climate_normals(lat: float, lng: float) -> pd.DataFrame:
    """1991-2020 monthly normals at the point (CMIP6 ensemble, bias-corrected)."""
    params = {
        "latitude": lat,
        "longitude": lng,
        "start_date": "1991-01-01",
        "end_date": "2020-12-31",
        "models": "MRI_AGCM3_2_S",
        "daily": "temperature_2m_mean,precipitation_sum",
        "timezone": "auto",
    }
    try:
        resp = httpx.get(_CLIMATE_URL, params=params, timeout=30.0)
        resp.raise_for_status()
        daily = resp.json().get("daily", {})
        df = pd.DataFrame(daily)
        if df.empty:
            return df
        df["time"] = pd.to_datetime(df["time"])
        df["month"] = df["time"].dt.month
        normals = df.groupby("month").agg(
            temp_mean_c=("temperature_2m_mean", "mean"),
            precip_mm=("precipitation_sum", "sum"),
        )
        normals["precip_mm"] = normals["precip_mm"] / 30
        return normals.reset_index()
    except httpx.HTTPError:
        return pd.DataFrame()


def daily_forecast_df(forecast_json: dict[str, Any]) -> pd.DataFrame:
    """Pivot the Open-Meteo daily block into a flat DataFrame."""
    daily = forecast_json.get("daily", {})
    df = pd.DataFrame(daily)
    if not df.empty:
        df["time"] = pd.to_datetime(df["time"])
    return df


def hourly_forecast_df(forecast_json: dict[str, Any]) -> pd.DataFrame:
    hourly = forecast_json.get("hourly", {})
    df = pd.DataFrame(hourly)
    if not df.empty:
        df["time"] = pd.to_datetime(df["time"])
    return df


def rainfall_last_n_days(forecast_json: dict[str, Any], n: int) -> float:
    df = daily_forecast_df(forecast_json)
    if df.empty:
        return float("nan")
    today = pd.Timestamp.today().normalize()
    mask = (df["time"] < today) & (df["time"] >= today - pd.Timedelta(days=n))
    return float(df.loc[mask, "precipitation_sum"].sum())


def forecast_window_stats(forecast_json: dict[str, Any], start_offset: int, days: int) -> dict[str, float]:
    """Mean/min/max temp and total precip + ET0 across a future window."""
    df = daily_forecast_df(forecast_json)
    if df.empty:
        return {}
    today = pd.Timestamp.today().normalize()
    start = today + pd.Timedelta(days=start_offset)
    end = start + pd.Timedelta(days=days)
    window = df[(df["time"] >= start) & (df["time"] < end)]
    if window.empty:
        return {}
    return {
        "tmax_mean": float(window["temperature_2m_max"].mean()),
        "tmin_mean": float(window["temperature_2m_min"].mean()),
        "tavg_mean": float((window["temperature_2m_max"] + window["temperature_2m_min"]).mean() / 2),
        "precip_sum_mm": float(window["precipitation_sum"].sum()),
        "et0_sum_mm": float(window.get("et0_fao_evapotranspiration", pd.Series([0])).sum()),
        "heat_days": int((window["temperature_2m_max"] > 38).sum()),
        "frost_days": int((window["temperature_2m_min"] < 2).sum()),
        "days": int(len(window)),
    }
