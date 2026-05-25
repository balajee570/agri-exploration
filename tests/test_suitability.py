"""Geographic-suitability filter — verifies hard exclusion of crops outside their envelope."""

from __future__ import annotations

import pandas as pd
import pytest

from agri.recommend import crops_by_id
from agri.suitability import (
    annual_mean_temp_c,
    annual_rainfall_mm,
    geographic_fit,
)


def _normals(monthly_temp_c: float, monthly_rain_mm_daily_avg: float) -> pd.DataFrame:
    """Build a synthetic normals DataFrame matching the shape returned by fetch_climate_normals."""
    return pd.DataFrame(
        {
            "month": list(range(1, 13)),
            "temp_mean_c": [monthly_temp_c] * 12,
            "precip_mm": [monthly_rain_mm_daily_avg] * 12,  # daily avg per month
        }
    )


def test_tea_excluded_in_bihar_plains():
    tea = crops_by_id()["tea"]
    bihar = _normals(monthly_temp_c=26.0, monthly_rain_mm_daily_avg=1200 / 12 / 30)
    fit, reason = geographic_fit(tea, elevation_m=50, normals=bihar)
    assert fit == 0.0
    assert "elevation" in reason.lower()


def test_paddy_excluded_at_darjeeling_altitude():
    paddy = crops_by_id()["paddy"]
    darj = _normals(monthly_temp_c=11.0, monthly_rain_mm_daily_avg=2800 / 12 / 30)
    fit, reason = geographic_fit(paddy, elevation_m=2100, normals=darj)
    assert fit == 0.0
    assert "elevation" in reason.lower() or "temp" in reason.lower()


def test_paddy_passes_in_bihar():
    paddy = crops_by_id()["paddy"]
    bihar = _normals(monthly_temp_c=26.0, monthly_rain_mm_daily_avg=1200 / 12 / 30)
    fit, _ = geographic_fit(paddy, elevation_m=50, normals=bihar)
    assert fit == 1.0


def test_tea_passes_in_darjeeling_hills():
    tea = crops_by_id()["tea"]
    darj = _normals(monthly_temp_c=14.0, monthly_rain_mm_daily_avg=2800 / 12 / 30)
    fit, _ = geographic_fit(tea, elevation_m=2100, normals=darj)
    assert fit == 1.0


def test_crop_without_envelope_always_passes():
    wheat = crops_by_id()["wheat"]
    extreme = _normals(monthly_temp_c=10.0, monthly_rain_mm_daily_avg=50 / 12 / 30)
    fit, _ = geographic_fit(wheat, elevation_m=2000, normals=extreme)
    assert fit == 1.0


def test_missing_normals_does_not_exclude():
    paddy = crops_by_id()["paddy"]
    fit, _ = geographic_fit(paddy, elevation_m=100, normals=pd.DataFrame())
    assert fit == 1.0


def test_annual_helpers():
    df = _normals(monthly_temp_c=20.0, monthly_rain_mm_daily_avg=4.0)
    assert annual_mean_temp_c(df) == pytest.approx(20.0)
    # 4 mm/day-avg × 30 days × 12 months = 1440 mm/yr
    assert annual_rainfall_mm(df) == pytest.approx(1440.0)
