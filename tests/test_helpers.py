"""Tests for the supporting modules: pests, rotation, schemes, varieties, soilgrids."""

from __future__ import annotations

from datetime import date

from agri.pests import PEST_RULES, pest_warnings_for
from agri.rotation import next_season_partners
from agri.schemes import is_msp_crop, is_pmfby_crop, schemes_for
from agri.soilgrids import _texture_to_class
from agri.varieties import recommend_varieties


# ---- pests -----------------------------------------------------------------

def test_pest_warnings_paddy_monsoon_humid():
    warnings = pest_warnings_for(
        crop_id="paddy", sowing_date=date(2026, 7, 15),
        tmax_window_c=30, tmin_window_c=24, expected_rain_mm=350,
    )
    assert len(warnings) >= 1
    assert any("blast" in w.lower() or "borer" in w.lower() or "hopper" in w.lower()
               for w in warnings)


def test_pest_warnings_skip_off_month():
    warnings = pest_warnings_for(
        crop_id="paddy", sowing_date=date(2026, 1, 15),
        tmax_window_c=22, tmin_window_c=14, expected_rain_mm=20,
    )
    assert warnings == []


def test_pest_warnings_empty_for_unknown_crop():
    assert pest_warnings_for("nonexistent_crop", date(2026, 7, 15),
                             tmax_window_c=30, tmin_window_c=24,
                             expected_rain_mm=300) == []


def test_top_crops_have_pest_rules():
    """Sanity: the most-grown crops should all have at least one pest rule."""
    must_have = ["paddy", "wheat", "cotton", "soybean", "chickpea", "potato"]
    for cid in must_have:
        assert cid in PEST_RULES, f"{cid} should have pest rules"


# ---- rotation --------------------------------------------------------------

def test_rotation_paddy_offers_legumes():
    partners = next_season_partners("paddy")
    assert "lentil" in partners or "chickpea" in partners or "mustard" in partners


def test_rotation_cotton_offers_legume():
    partners = next_season_partners("cotton")
    assert "chickpea" in partners or "groundnut" in partners


def test_rotation_empty_for_perennials_with_no_fit():
    partners = next_season_partners("apple")
    assert partners == []


def test_rotation_returns_at_most_four():
    assert len(next_season_partners("paddy")) <= 4


def test_rotation_empty_for_unknown_crop():
    assert next_season_partners("nonexistent_crop") == []


# ---- schemes ---------------------------------------------------------------

def test_paddy_is_msp_backed():
    assert is_msp_crop("paddy")
    assert is_pmfby_crop("paddy")


def test_apple_not_msp_backed():
    assert not is_msp_crop("apple")


def test_schemes_for_paddy_in_punjab_includes_state_portal():
    out = schemes_for("paddy", "Punjab")
    names = {s["name"] for s in out}
    assert "MSP procurement" in names
    assert "PMFBY (crop insurance)" in names
    assert "PM-KISAN" in names
    assert any("Punjab" in s["name"] for s in out)


def test_schemes_for_unknown_state_falls_back_to_central():
    out = schemes_for("paddy", "Mars")
    names = {s["name"] for s in out}
    assert "PM-KISAN" in names
    assert "MSP procurement" in names


# ---- varieties -------------------------------------------------------------

def test_varieties_paddy_punjab():
    out = recommend_varieties("paddy", "Punjab")
    assert len(out) >= 1
    assert any("Basmati" in v["name"] or "PR" in v["name"] for v in out)


def test_varieties_unknown_state_falls_back_to_default():
    out = recommend_varieties("paddy", "Mars")
    assert len(out) >= 1  # __default__ entry


def test_varieties_unknown_crop_returns_empty():
    assert recommend_varieties("nonexistent_crop", "Punjab") == []


# ---- soilgrids texture triangle --------------------------------------------

def test_texture_triangle_clay():
    assert _texture_to_class(sand=10, clay=55) == "clay"


def test_texture_triangle_sandy():
    assert _texture_to_class(sand=90, clay=5) == "sandy"


def test_texture_triangle_loam():
    assert _texture_to_class(sand=40, clay=20) == "loam"


def test_texture_triangle_clay_loam():
    assert _texture_to_class(sand=30, clay=35) == "clay_loam"


def test_texture_triangle_sandy_loam():
    assert _texture_to_class(sand=72, clay=10) == "sandy_loam"
