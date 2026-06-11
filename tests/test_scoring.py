"""Property tests for the scoring engine — every input must move the score monotonically."""

from __future__ import annotations

from datetime import date

import pytest

from agri.recommend import crops_by_id, load_crops
from agri.scoring import (
    FitInputs,
    infer_waterlogging_tolerance,
    next_sowing_month,
    score_crop,
    season_fit,
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


def test_water_fit_excess_water_does_not_fail():
    """Munnar regression: heavy rain shouldn't collapse water_fit to zero —
    drainage exists, and waterlogging is handled by a separate penalty."""
    # ~7x annual need (perennial cumulative; or extreme-monsoon for annuals)
    assert water_fit(17500, 1500, 2500) >= 0.4
    # 2x need (Cherrapunji-class monsoon on paddy)
    assert water_fit(5000, 900, 2500) >= 0.4


def test_water_fit_drought_still_punished():
    """Drought is fatal — the relaxed excess curve must not soften scarcity."""
    assert water_fit(100, 900, 2500) < 0.2
    assert water_fit(0, 400, 600) == 0.0


def test_water_fit_excess_monotonic_decay():
    """More excess = lower (or equal) score until the floor."""
    a = water_fit(2500, 1500, 2500)  # perfect
    b = water_fit(4000, 1500, 2500)  # ~60% over
    c = water_fit(10000, 1500, 2500)  # 3x over → floor
    assert a >= b >= c


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


@pytest.mark.parametrize(
    "crop_id, expected",
    [
        ("paddy", "very_high"),
        ("paddy_boro", "very_high"),
        ("tea", "high"),         # smp=high, soil=loam (no clay)
        ("wheat", "medium"),     # smp=medium
        ("cotton", "medium"),    # smp=medium
        ("chickpea", "low"),     # smp=low
    ],
)
def test_infer_tolerance_known_crops(crop_id: str, expected: str) -> None:
    crops = {c["id"]: c for c in load_crops()}
    assert infer_waterlogging_tolerance(crops[crop_id]) == expected


def test_waterlogging_penalty_fires_on_flat_terrain():
    """Chickpea (low tolerance) on flat terrain with heavy rain → significant penalty."""
    crops = {c["id"]: c for c in load_crops()}
    chickpea = crops["chickpea"]
    inputs = FitInputs(
        avg_temp_c=22,
        tmin_window_c=15,
        tmax_window_c=28,
        expected_rain_mm=900,  # >> chickpea water_need_mm[1]=450
        soil_moisture_pct=35,
        soil_temp_c=18,
        sowing_date=date(2025, 11, 1),
        slope_pct=0.5,  # flat
    )
    res = score_crop(chickpea, inputs)
    assert "Waterlogging risk" in res.penalties
    assert res.penalties["Waterlogging risk"] >= 8.0


def test_waterlogging_penalty_absent_on_steep_terrain():
    """Same sensitive crop, same heavy rain — but slope ≥1.5% → no penalty."""
    crops = {c["id"]: c for c in load_crops()}
    chickpea = crops["chickpea"]
    inputs = FitInputs(
        avg_temp_c=22,
        tmin_window_c=15,
        tmax_window_c=28,
        expected_rain_mm=900,
        soil_moisture_pct=35,
        soil_temp_c=18,
        sowing_date=date(2025, 11, 1),
        slope_pct=8.0,  # steep
    )
    res = score_crop(chickpea, inputs)
    assert "Waterlogging risk" not in res.penalties


def test_paddy_no_waterlogging_penalty_in_monsoon():
    """Paddy's very_high tolerance means no penalty even on flat terrain in monsoon."""
    crops = {c["id"]: c for c in load_crops()}
    paddy = crops["paddy"]
    inputs = FitInputs(
        avg_temp_c=28,
        tmin_window_c=24,
        tmax_window_c=32,
        expected_rain_mm=2700,
        soil_moisture_pct=42,
        soil_temp_c=26,
        sowing_date=date(2025, 7, 1),
        slope_pct=0.3,
    )
    res = score_crop(paddy, inputs)
    assert "Waterlogging risk" not in res.penalties
    assert res.score >= 60


# ---- Season reliability ------------------------------------------------------

def test_season_fit_in_window_is_one():
    assert season_fit(date(2026, 5, 25), ["kharif"], [4, 5, 6]) == 1.0


def test_season_fit_one_month_out():
    assert season_fit(date(2026, 5, 25), ["perennial"], [6, 7, 8]) == 0.40


def test_season_fit_two_months_out():
    assert season_fit(date(2026, 5, 25), ["zaid"], [1, 2, 3]) == 0.15


def test_season_fit_far_off_season():
    assert season_fit(date(2026, 7, 1), ["rabi"], [11, 12]) == 0.05


def test_season_fit_empty_months_returns_neutral():
    assert season_fit(date(2026, 5, 25), ["perennial"], []) == 0.5


def test_next_sowing_month_basic():
    # May (5) → next sowing for [6,7,8] is June (6)
    assert next_sowing_month(date(2026, 5, 25), [6, 7, 8]) == 6
    # In-window → returns current month
    assert next_sowing_month(date(2026, 6, 15), [6, 7, 8]) == 6


def test_next_sowing_month_wraps_year():
    # July (7) → next sowing for [11,12] is November
    assert next_sowing_month(date(2026, 7, 1), [11, 12]) == 11


def test_mango_off_window_below_yellow():
    """The bug report: Mango (sowing_months [6,7,8]) sown 25 May should NOT
    appear as a top recommendation."""
    mango = crops_by_id()["mango"]
    inputs = FitInputs(
        avg_temp_c=28, tmin_window_c=22, tmax_window_c=34,
        expected_rain_mm=900, soil_moisture_pct=32,
        soil_temp_c=26, sowing_date=date(2026, 5, 25),
    )
    assert score_crop(mango, inputs).score < 50, (
        f"mango off-window scored {score_crop(mango, inputs).score}"
    )


def test_no_crop_scores_green_far_off_season():
    """'World best' guarantee: no crop ever scores >= 65 when sown ≥3 months
    from its sowing window, even with otherwise-perfect inputs."""
    template = dict(avg_temp_c=24, tmin_window_c=18, tmax_window_c=30,
                    expected_rain_mm=600, soil_moisture_pct=32, soil_temp_c=24)
    for crop in load_crops():
        sowing_months = crop.get("sowing_months") or []
        if not sowing_months:
            continue
        for test_month in range(1, 13):
            if all(min((test_month - sm) % 12, (sm - test_month) % 12) >= 3
                   for sm in sowing_months):
                inputs = FitInputs(sowing_date=date(2026, test_month, 15), **template)
                res = score_crop(crop, inputs)
                assert res.score < 65, (
                    f"{crop['id']} scored {res.score} in month {test_month} "
                    f"(sowing_months={sowing_months})"
                )
                break


# ---- Confidence band --------------------------------------------------------

def test_confidence_band_widens_with_growing_window():
    paddy = crops_by_id()["paddy"]
    near = FitInputs(avg_temp_c=28, tmin_window_c=24, tmax_window_c=32,
                     expected_rain_mm=1400, soil_moisture_pct=40, soil_temp_c=26,
                     sowing_date=date(2026, 7, 1), growing_days=14)
    far = FitInputs(avg_temp_c=28, tmin_window_c=24, tmax_window_c=32,
                    expected_rain_mm=1400, soil_moisture_pct=40, soil_temp_c=26,
                    sowing_date=date(2026, 7, 1), growing_days=180)
    near_r = score_crop(paddy, near)
    far_r = score_crop(paddy, far)
    near_spread = near_r.score_high - near_r.score_low
    far_spread = far_r.score_high - far_r.score_low
    assert far_spread > near_spread


# ---- Aspect modifier --------------------------------------------------------

def test_aspect_bonus_for_highland_perennial():
    coffee = crops_by_id()["coffee"]
    base = FitInputs(avg_temp_c=22, tmin_window_c=16, tmax_window_c=28,
                     expected_rain_mm=2000, soil_moisture_pct=35, soil_temp_c=22,
                     sowing_date=date(2026, 6, 1))
    s_facing = FitInputs(avg_temp_c=22, tmin_window_c=16, tmax_window_c=28,
                         expected_rain_mm=2000, soil_moisture_pct=35, soil_temp_c=22,
                         sowing_date=date(2026, 6, 1), aspect_compass="S")
    n_facing = FitInputs(avg_temp_c=22, tmin_window_c=16, tmax_window_c=28,
                         expected_rain_mm=2000, soil_moisture_pct=35, soil_temp_c=22,
                         sowing_date=date(2026, 6, 1), aspect_compass="N")
    assert score_crop(coffee, n_facing).score >= score_crop(coffee, base).score
    assert score_crop(coffee, s_facing).score <= score_crop(coffee, base).score


# ---- Mandi distance penalty -------------------------------------------------

def test_mandi_distance_penalty_kicks_in_over_50km():
    paddy = crops_by_id()["paddy"]
    near = FitInputs(avg_temp_c=28, tmin_window_c=24, tmax_window_c=32,
                     expected_rain_mm=1400, soil_moisture_pct=40, soil_temp_c=26,
                     sowing_date=date(2026, 7, 1), mandi_distance_km=10)
    far = FitInputs(avg_temp_c=28, tmin_window_c=24, tmax_window_c=32,
                    expected_rain_mm=1400, soil_moisture_pct=40, soil_temp_c=26,
                    sowing_date=date(2026, 7, 1), mandi_distance_km=120)
    assert score_crop(paddy, near).score > score_crop(paddy, far).score


# ---- Pest warnings ----------------------------------------------------------

def test_pest_warnings_present_for_paddy_in_monsoon():
    paddy = crops_by_id()["paddy"]
    inputs = FitInputs(
        avg_temp_c=26, tmin_window_c=23, tmax_window_c=30,
        expected_rain_mm=350, soil_moisture_pct=42, soil_temp_c=27,
        sowing_date=date(2026, 7, 15),
    )
    res = score_crop(paddy, inputs)
    assert len(res.pest_warnings) >= 1


def test_no_pest_warnings_for_perennial_without_rules():
    pomegranate = crops_by_id()["pomegranate"]
    inputs = FitInputs(
        avg_temp_c=25, tmin_window_c=20, tmax_window_c=32,
        expected_rain_mm=700, soil_moisture_pct=28, soil_temp_c=25,
        sowing_date=date(2026, 7, 15),
    )
    res = score_crop(pomegranate, inputs)
    assert res.pest_warnings == []
