"""Water budget: rainfall vs ET₀ and irrigation requirement estimates."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd

from agri.weather import daily_forecast_df, fetch_climate_normals, fetch_forecast


def water_budget_series(
    lat: float, lng: float, horizon_days: int = 90
) -> pd.DataFrame:
    """Daily rainfall and ET₀ — actuals where we have them, normals after."""
    fc = fetch_forecast(lat, lng)
    df = daily_forecast_df(fc)
    today = pd.Timestamp.today().normalize()
    if df.empty:
        return pd.DataFrame()
    history_and_forecast = df[["time", "precipitation_sum", "et0_fao_evapotranspiration"]].copy()
    history_and_forecast = history_and_forecast.rename(
        columns={
            "precipitation_sum": "rain_mm",
            "et0_fao_evapotranspiration": "et0_mm",
        }
    )
    history_and_forecast["source"] = history_and_forecast["time"].apply(
        lambda t: "forecast" if t >= today else "actual"
    )

    forecast_end = history_and_forecast["time"].max()
    target_end = today + pd.Timedelta(days=horizon_days)
    if forecast_end < target_end:
        normals = fetch_climate_normals(lat, lng)
        if not normals.empty:
            nm_rain = normals.set_index("month")["precip_mm"].to_dict()
            cur_et0 = float(history_and_forecast["et0_mm"].tail(7).mean() or 4.5)
            extra_rows = []
            cursor = forecast_end + pd.Timedelta(days=1)
            while cursor <= target_end:
                m_rain = float(nm_rain.get(cursor.month, 0.0))
                extra_rows.append(
                    {
                        "time": cursor,
                        "rain_mm": m_rain,
                        "et0_mm": cur_et0,
                        "source": "climate_normal",
                    }
                )
                cursor += pd.Timedelta(days=1)
            history_and_forecast = pd.concat(
                [history_and_forecast, pd.DataFrame(extra_rows)], ignore_index=True
            )
    history_and_forecast["balance_mm"] = (
        history_and_forecast["rain_mm"].fillna(0) - history_and_forecast["et0_mm"].fillna(0)
    )
    history_and_forecast["cumulative_balance_mm"] = history_and_forecast["balance_mm"].cumsum()
    return history_and_forecast


def irrigation_need_mm(
    rain_mm_during_growth: float,
    et0_mm_during_growth: float,
    crop: dict[str, Any],
    kc_effective: float = 0.95,
) -> dict[str, float]:
    """Crop water demand vs expected rain → irrigation shortfall.

    kc_effective approximates the season-averaged FAO crop coefficient.
    """
    etc_mm = et0_mm_during_growth * kc_effective
    crop_min, crop_max = crop["water_need_mm"]
    demand_mm = max(etc_mm, crop_min)
    shortfall = max(0.0, demand_mm - rain_mm_during_growth)
    excess = max(0.0, rain_mm_during_growth - crop_max)
    return {
        "etc_mm": round(etc_mm, 1),
        "rain_mm": round(rain_mm_during_growth, 1),
        "demand_mm": round(demand_mm, 1),
        "shortfall_mm": round(shortfall, 1),
        "excess_mm": round(excess, 1),
        "litres_per_acre": round(shortfall * 4046.86, 0),
    }
