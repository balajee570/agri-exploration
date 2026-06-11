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
    """Fail-safe: a crop record missing elevation_m / slope_max_pct must not be filtered."""
    bare_crop = {"id": "synthetic", "name_en": "Synthetic", "temp_c": {}}
    extreme = _normals(annual_mean_temp_c=10.0, annual_rain_mm=50)
    fit, _ = geographic_fit(bare_crop, elevation_m=2000, normals=extreme, slope_pct=45)
    assert fit == 1.0


def test_missing_normals_does_not_exclude():
    paddy = crops_by_id()["paddy"]
    fit, _ = geographic_fit(paddy, elevation_m=100, normals=pd.DataFrame())
    assert fit == 1.0


def test_paddy_excluded_on_steep_slope():
    """Munnar regression: paddy on a 29% slope must be excluded even within elevation range."""
    paddy = crops_by_id()["paddy"]
    fit, reason = geographic_fit(paddy, elevation_m=500, normals=None, slope_pct=29)
    assert fit == 0.0
    assert "slope" in reason.lower()


def test_tea_passes_on_steep_highland_slope():
    """Tea plantations on 40% slope must NOT be excluded (slope_max_pct ≥ 40)."""
    tea = crops_by_id()["tea"]
    fit, reason = geographic_fit(tea, elevation_m=1500, normals=None, slope_pct=40)
    assert fit == 1.0, f"tea should tolerate steep highland slope, got: {reason}"


def test_cotton_excluded_at_munnar():
    """Canonical failing case: cotton at Munnar (1470 m, 29 % slope) must be excluded."""
    cotton = crops_by_id()["cotton"]
    fit, reason = geographic_fit(cotton, elevation_m=1470, normals=None, slope_pct=29)
    assert fit == 0.0
    assert "elevation" in reason.lower() or "slope" in reason.lower()


def test_slope_check_skipped_when_slope_is_none():
    """Backwards-compat: calling without slope_pct keeps old behaviour."""
    paddy = crops_by_id()["paddy"]
    fit, _ = geographic_fit(paddy, elevation_m=500, normals=None)
    assert fit == 1.0


def test_annual_helpers():
    df = _normals(annual_mean_temp_c=20.0, annual_rain_mm=1440)
    assert annual_mean_temp_c(df) == pytest.approx(20.0)
    assert annual_rainfall_mm(df) == pytest.approx(1440.0)


# ---- Soil pH gate -----------------------------------------------------------

def test_tea_excluded_on_alkaline_soil():
    """Tea wants pH 4.5–5.5; pH 8.5 must reject."""
    tea = crops_by_id()["tea"]
    fit, reason = geographic_fit(
        tea, elevation_m=1500, normals=None, slope_pct=20,
        soil={"ph_h2o": 8.5, "soil_class": "loam"},
    )
    assert fit == 0.0
    assert "ph" in reason.lower()


def test_chickpea_passes_on_neutral_soil():
    """Chickpea's pH 6.0–8.0 → 7.0 should pass cleanly."""
    chickpea = crops_by_id()["chickpea"]
    fit, _ = geographic_fit(
        chickpea, elevation_m=200, normals=None, slope_pct=2,
        soil={"ph_h2o": 7.0, "soil_class": "loam"},
    )
    assert fit == 1.0


def test_missing_soil_data_is_fail_safe():
    """No soil dict → skip soil check entirely, do not block."""
    tea = crops_by_id()["tea"]
    fit, _ = geographic_fit(tea, elevation_m=1500, normals=None,
                            slope_pct=20, soil=None)
    assert fit == 1.0


def test_soil_ph_within_buffer_passes():
    """1.0 unit either side of the catalog band is tolerated (250m pixel imprecision)."""
    coffee = crops_by_id()["coffee"]   # soil_ph [6.0, 6.5]
    fit, _ = geographic_fit(
        coffee, elevation_m=1000, normals=None, slope_pct=15,
        soil={"ph_h2o": 5.2, "soil_class": "loam"},  # within 1.0 unit of 6.0
    )
    assert fit == 1.0
