"""Tests for the supporting modules: pests, rotation, schemes, varieties, soilgrids."""

from __future__ import annotations

from datetime import date

from agri.pests import PEST_RULES, pest_warnings_for
from agri.rotation import next_season_partners
from agri.schemes import is_msp_crop, is_pmfby_crop, schemes_for
from agri import soilgrids
from agri.soilgrids import (
    SoilGridsUnavailable,
    _parse_layers,
    _texture_to_class,
    _to_profile,
)
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


# ---- soilgrids response parsing & land/water gate ---------------------------

def _layer(name: str, d_factor: float, means: dict[str, float | None]) -> dict:
    return {
        "name": name,
        "unit_measure": {"d_factor": d_factor},
        "depths": [
            {"label": label, "values": {"mean": mean}}
            for label, mean in means.items()
        ],
    }


def _api_response(layers: list[dict]) -> dict:
    return {"properties": {"layers": layers}}


def test_parse_layers_thickness_weighted_mean():
    # phh2o comes back ×10; weights are 5/10/15 over 0-5/5-15/15-30 cm.
    data = _api_response([
        _layer("phh2o", 10, {"0-5cm": 60, "5-15cm": 63, "15-30cm": 66}),
    ])
    raw = _parse_layers(data)
    # (5*60 + 10*63 + 15*66) / 30 / 10 = 6.40
    assert raw["phh2o"] == 6.4
    assert raw["clay"] is None  # absent layer stays None


def test_parse_layers_skips_null_depths():
    data = _api_response([
        _layer("clay", 10, {"0-5cm": None, "5-15cm": 300, "15-30cm": None}),
    ])
    assert _parse_layers(data)["clay"] == 30.0


def test_to_profile_full_schema():
    raw = {"phh2o": 6.2, "clay": 42.0, "sand": 28.0, "soc": 14.0}
    profile = _to_profile(raw)
    assert profile == {
        "ph_h2o": 6.2,
        "clay_pct": 42.0,
        "sand_pct": 28.0,
        "organic_carbon_pct": 1.4,
        "silt_pct": 30.0,
        "soil_class": "clay",
    }


def test_to_profile_all_null_is_none():
    assert _to_profile({"phh2o": None, "clay": None, "sand": None, "soc": None}) is None


def test_has_soil_true_on_land(monkeypatch):
    monkeypatch.setattr(
        soilgrids, "_query_topsoil",
        lambda lat, lng: {"phh2o": 6.5, "clay": None, "sand": None, "soc": None},
    )
    assert soilgrids.has_soil(25.7549, 86.0315) is True


def test_has_soil_false_only_when_api_confirms_no_soil(monkeypatch):
    monkeypatch.setattr(
        soilgrids, "_query_topsoil",
        lambda lat, lng: {"phh2o": None, "clay": None, "sand": None, "soc": None},
    )
    assert soilgrids.has_soil(0.0, -150.0) is False


def test_has_soil_fails_open_when_api_unreachable(monkeypatch):
    def boom(lat, lng):
        raise SoilGridsUnavailable("HTTP 429")

    monkeypatch.setattr(soilgrids, "_query_topsoil", boom)
    assert soilgrids.has_soil(25.7549, 86.0315) is True


def test_fetch_soil_profile_returns_none_when_unreachable(monkeypatch):
    def boom(lat, lng):
        raise SoilGridsUnavailable("timeout")

    monkeypatch.setattr(soilgrids, "_query_topsoil", boom)
    assert soilgrids.fetch_soil_profile(25.7549, 86.0315) is None


_NULL = {"phh2o": None, "clay": None, "sand": None, "soc": None}
_AMRITSAR = (31.6223, 74.8753)


def test_masked_town_centre_falls_back_to_neighbour(monkeypatch):
    # SoilGrids masks built-up cells; the exact pin (a geocoded city centre)
    # is all-null but the cell ~2 km away has farmland values.
    def fake_query(lat, lng):
        if (lat, lng) == _AMRITSAR:
            return dict(_NULL)
        return {"phh2o": 7.8, "clay": 22.0, "sand": 45.0, "soc": 5.0}

    monkeypatch.setattr(soilgrids, "_query_topsoil", fake_query)
    assert soilgrids.has_soil(*_AMRITSAR) is True
    profile = soilgrids.fetch_soil_profile(*_AMRITSAR)
    assert profile is not None and profile["ph_h2o"] == 7.8


def test_masked_centre_skips_failing_probes(monkeypatch):
    calls = []

    def fake_query(lat, lng):
        calls.append((lat, lng))
        if (lat, lng) == _AMRITSAR:
            return dict(_NULL)
        if len(calls) < 4:  # first two probes error out
            raise SoilGridsUnavailable("HTTP 429")
        return {"phh2o": 6.9, "clay": None, "sand": None, "soc": None}

    monkeypatch.setattr(soilgrids, "_query_topsoil", fake_query)
    assert soilgrids.has_soil(*_AMRITSAR) is True


def test_open_ocean_all_probes_null(monkeypatch):
    monkeypatch.setattr(soilgrids, "_query_topsoil", lambda lat, lng: dict(_NULL))
    assert soilgrids.has_soil(0.0, -150.0) is False
    assert soilgrids.fetch_soil_profile(0.0, -150.0) is None


def test_large_city_needs_second_probe_ring(monkeypatch):
    # Urban mask wider than the 2 km ring: only the ~6 km probes reach farmland.
    def fake_query(lat, lng):
        if max(abs(lat - _AMRITSAR[0]), abs(lng - _AMRITSAR[1])) < 0.05:
            return dict(_NULL)
        return {"phh2o": 7.6, "clay": 24.0, "sand": 40.0, "soc": 6.0}

    monkeypatch.setattr(soilgrids, "_query_topsoil", fake_query)
    assert soilgrids.has_soil(*_AMRITSAR) is True
    profile = soilgrids.fetch_soil_profile(*_AMRITSAR)
    assert profile is not None and profile["ph_h2o"] == 7.6
