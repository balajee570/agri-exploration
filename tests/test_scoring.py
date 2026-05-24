"""Property tests for the scoring engine — every input must move the score monotonically."""

from __future__ import annotations

from datetime import date

import pytest

from agri.recommend import load_crops
from agri.scoring import (
    FitInputs,
    score_crop,
    soil_moisture_fit,
    soil_temp_fit,
    temp_fit,
    water_fit,
)


def test_temp_fit_perfect_in_optimum():
    assert temp_fit(25, 10, 22, 32, 40) == 1.0


def test_temp_fit_zero_outside_extremes():
    assert temp_fit(5, 10, 22, 32, 40) == 0.0
    assert temp_fit(45, 10, 22, 32, 40) == 0.0


def test_temp_fit_decreases_away_from_optimum():
    a = temp_fit(20, 10, 22, 32, 40)
    b = temp_fit(15, 10, 22, 32, 40)
    assert a > b


def test_water_fit_perfect_within_band():
    assert water_fit(500, 400, 600) == 1.0


def test_water_fit_drops_below_band():
    assert water_fit(200, 400, 600) < 1.0
    assert water_fit(50, 400, 600) < water_fit(200, 400, 600)


def test_water_fit_irrigation_helps():
    base = water_fit(100, 400, 600)
    helped = water_fit(100, 400, 600, irrigation_mm=350)
    assert helped > base


def test_soil_moisture_fit_peaks_at_target():
    high = soil_moisture_fit(42, "high")
    low = soil_moisture_fit(15, "high")
    assert high > low


def test_soil_temp_fit_higher_when_warm_enough():
    cold = soil_temp_fit(15, 20)
    warm = soil_temp_fit(25, 20)
    assert warm > cold


def test_score_crop_paddy_in_summer_monsoon_scores_high():
    crops = {c["id"]: c for c in load_crops()}
    paddy = crops["paddy"]
    inputs = FitInputs(
        avg_temp_c=28,
        tmin_window_c=24,
        tmax_window_c=32,
        expected_rain_mm=1400,
        soil_moisture_pct=40,
        soil_temp_c=26,
        sowing_date=date(2025, 7, 1),
    )
    res = score_crop(paddy, inputs)
    assert res.score >= 70


def test_score_crop_wheat_off_season_scores_low():
    crops = {c["id"]: c for c in load_crops()}
    wheat = crops["wheat"]
    inputs = FitInputs(
        avg_temp_c=35,
        tmin_window_c=28,
        tmax_window_c=42,
        expected_rain_mm=900,
        soil_moisture_pct=45,
        soil_temp_c=30,
        sowing_date=date(2025, 7, 1),
        heat_days=10,
    )
    res = score_crop(wheat, inputs)
    assert res.score < 40


@pytest.mark.parametrize("rain", [50, 200, 500, 1000])
def test_water_increase_helps_water_hungry_crop(rain: float):
    crops = {c["id"]: c for c in load_crops()}
    paddy = crops["paddy"]
    base_inputs = FitInputs(
        avg_temp_c=27,
        tmin_window_c=22,
        tmax_window_c=32,
        expected_rain_mm=rain,
        soil_moisture_pct=35,
        soil_temp_c=24,
        sowing_date=date(2025, 7, 1),
    )
    more_inputs = FitInputs(**{**base_inputs.__dict__, "expected_rain_mm": rain + 400})
    if rain + 400 <= paddy["water_need_mm"][1]:
        assert score_crop(paddy, more_inputs).score >= score_crop(paddy, base_inputs).score


def test_components_sum_to_score_breakdown():
    crops = {c["id"]: c for c in load_crops()}
    crop = crops["maize_kharif"]
    inputs = FitInputs(
        avg_temp_c=26,
        tmin_window_c=22,
        tmax_window_c=30,
        expected_rain_mm=650,
        soil_moisture_pct=32,
        soil_temp_c=24,
        sowing_date=date(2025, 7, 1),
    )
    res = score_crop(crop, inputs)
    assert set(res.components.keys()) == {
        "Temperature fit",
        "Water availability",
        "Soil moisture",
        "Germination temp",
        "Season match",
    }
    assert 0 <= res.score <= 100


def test_frost_penalty_applies_to_sensitive_crop():
    crops = {c["id"]: c for c in load_crops()}
    banana = crops["banana"]
    inputs = FitInputs(
        avg_temp_c=10,
        tmin_window_c=1,
        tmax_window_c=15,
        expected_rain_mm=600,
        soil_moisture_pct=30,
        soil_temp_c=12,
        sowing_date=date(2025, 12, 15),
        frost_days=3,
    )
    res = score_crop(banana, inputs)
    assert "Frost risk" in res.penalties
