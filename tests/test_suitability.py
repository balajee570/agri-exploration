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


def _normals(annual_mean_temp_c: float, annual_rain_mm: float) -> pd.DataFrame:
    """Build a synthetic normals DataFrame matching the shape returned by fetch_climate_normals.

    `precip_mm` here is the monthly total in mm (same units as weather.py produces).
    """
    monthly = annual_rain_mm / 12.0
    return pd.DataFrame(
        {
            "month": list(range(1, 13)),
            "temp_mean_c": [annual_mean_temp_c] * 12,
            "precip_mm": [monthly] * 12,
        }
    )


def test_tea_excluded_in_bihar_plains():
    tea = crops_by_id()["tea"]
    bihar = _normals(annual_mean_temp_c=26.0, annual_rain_mm=1200)
    fit, reason = geographic_fit(tea, elevation_m=50, normals=bihar)
    assert fit == 0.0
    assert "elevation" in reason.lower()


def test_paddy_excluded_at_darjeeling_altitude():
    paddy = crops_by_id()["paddy"]
    darj = _normals(annual_mean_temp_c=11.0, annual_rain_mm=2800)
    fit, reason = geographic_fit(paddy, elevation_m=2100, normals=darj)
    assert fit == 0.0
    assert "elevation" in reason.lower() or "temp" in reason.lower()


def test_paddy_passes_in_bihar():
    paddy = crops_by_id()["paddy"]
    bihar = _normals(annual_mean_temp_c=26.0, annual_rain_mm=1200)
    fit, _ = geographic_fit(paddy, elevation_m=50, normals=bihar)
    assert fit == 1.0


def test_tea_passes_in_darjeeling_hills():
    tea = crops_by_id()["tea"]
    darj = _normals(annual_mean_temp_c=14.0, annual_rain_mm=2800)
    fit, reason = geographic_fit(tea, elevation_m=2100, normals=darj)
    assert fit == 1.0, f"tea should pass in Darjeeling, got: {reason}"


def test_tea_passes_in_mirik_realistic():
    """Live regression: Mirik (Darjeeling district) ~1500 m, ~3500 mm/yr, ~14 °C — tea must pass."""
    tea = crops_by_id()["tea"]
    mirik = _normals(annual_mean_temp_c=14.0, annual_rain_mm=3500)
    fit, reason = geographic_fit(tea, elevation_m=1500, normals=mirik)
    assert fit == 1.0, f"tea should pass in Mirik, got: {reason}"


def test_crop_without_envelope_always_passes():
    wheat = crops_by_id()["wheat"]
    extreme = _normals(annual_mean_temp_c=10.0, annual_rain_mm=50)
    fit, _ = geographic_fit(wheat, elevation_m=2000, normals=extreme)
    assert fit == 1.0


def test_missing_normals_does_not_exclude():
    paddy = crops_by_id()["paddy"]
    fit, _ = geographic_fit(paddy, elevation_m=100, normals=pd.DataFrame())
    assert fit == 1.0


def test_annual_helpers():
    df = _normals(annual_mean_temp_c=20.0, annual_rain_mm=1440)
    assert annual_mean_temp_c(df) == pytest.approx(20.0)
    assert annual_rainfall_mm(df) == pytest.approx(1440.0)
