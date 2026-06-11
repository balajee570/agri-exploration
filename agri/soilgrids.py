"""ISRIC SoilGrids 250 m — per-location soil pH, texture, and organic carbon.

Free, no key. https://rest.isric.org/soilgrids/v2.0/properties/query
Cached for 30 days (soil doesn't change on human timescales).

The returned dict's `soil_class` field maps the USDA texture triangle into one
of the catalog's existing `soil_types` strings so `geographic_fit` can do
direct set-membership comparison.

Note on depths: SoilGrids only serves the aggregated "0-30cm" interval for
`ocs`. For phh2o/clay/sand/soc the valid intervals are 0-5cm, 5-15cm and
15-30cm (then deeper), so we query those three and take a thickness-weighted
mean to represent the 0-30 cm root zone.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from agri.cache import cached

_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
_TTL = 30 * 24 * 60 * 60  # 30 days
_PROPERTIES = ["phh2o", "clay", "sand", "soc"]
# Thickness (cm) of each standard topsoil interval, used as weighted-mean weights.
_DEPTH_WEIGHTS = {"0-5cm": 5.0, "5-15cm": 10.0, "15-30cm": 15.0}
_logger = logging.getLogger(__name__)


class SoilGridsUnavailable(RuntimeError):
    """The API could not be reached — says nothing about whether soil exists."""


def _texture_to_class(sand: float, clay: float) -> str:
    """USDA texture triangle → one of the catalog's `soil_types` strings.

    Sand & clay are percentages (0-100). Silt = 100 - sand - clay.
    Returned class is the closest match the catalog vocabulary allows.
    """
    silt = max(0.0, 100.0 - sand - clay)
    if clay >= 40:
        return "clay"
    if clay >= 27 and sand <= 45:
        return "clay_loam"
    if sand >= 85 and clay < 10:
        return "sandy"
    if sand >= 70 and clay < 15:
        return "sandy_loam"
    if 23 <= clay < 40 and sand >= 45:
        return "sandy_clay_loam"
    if 7 <= clay < 27 and silt < 50 and sand < 52:
        return "loam"
    if silt >= 50 and clay < 27:
        return "silty_loam"
    if sand >= 43 and clay < 20:
        return "sandy_loam"
    return "loam"


def _depth_label(depth: dict[str, Any]) -> str:
    label = depth.get("label")
    if label:
        return str(label)
    rng = depth.get("range") or {}
    top, bottom = rng.get("top_depth"), rng.get("bottom_depth")
    if top is None or bottom is None:
        return ""
    return f"{top}-{bottom}{rng.get('unit_depth', 'cm')}"


def _parse_layers(data: dict[str, Any]) -> dict[str, float | None]:
    """Per-property thickness-weighted topsoil mean, scaled to natural units.

    A property maps to None when the API returned no value for it at this
    point — all-None across properties is SoilGrids' ocean/glacier signature.
    """
    out: dict[str, float | None] = {name: None for name in _PROPERTIES}
    layers = (data.get("properties") or {}).get("layers") or []
    for layer in layers:
        name = layer.get("name")
        if name not in out:
            continue
        d_factor = float((layer.get("unit_measure") or {}).get("d_factor") or 1.0)
        num = den = 0.0
        for depth in layer.get("depths") or []:
            weight = _DEPTH_WEIGHTS.get(_depth_label(depth))
            mean = (depth.get("values") or {}).get("mean")
            if weight and mean is not None:
                num += weight * float(mean)
                den += weight
        if den:
            out[name] = (num / den) / d_factor
    return out


@cached(_TTL)
def _query_topsoil(lat: float, lng: float) -> dict[str, float | None]:
    """Raises SoilGridsUnavailable on transport failure so the (long-TTL)
    cache never stores a transient error as if it were a real answer."""
    params = {
        "lat": f"{lat:.4f}",
        "lon": f"{lng:.4f}",
        "property": _PROPERTIES,
        "depth": list(_DEPTH_WEIGHTS),
        "value": "mean",
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(_URL, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        raise SoilGridsUnavailable(str(e)) from e
    return _parse_layers(data)


def _to_profile(raw: dict[str, float | None]) -> dict[str, Any] | None:
    out: dict[str, Any] = {}
    if raw.get("phh2o") is not None:
        out["ph_h2o"] = round(raw["phh2o"], 2)
    if raw.get("clay") is not None:
        out["clay_pct"] = round(raw["clay"], 1)
    if raw.get("sand") is not None:
        out["sand_pct"] = round(raw["sand"], 1)
    if raw.get("soc") is not None:
        # SoilGrids SOC is in g/kg; convert to %
        out["organic_carbon_pct"] = round(raw["soc"] / 10.0, 2)

    if "sand_pct" in out and "clay_pct" in out:
        out["silt_pct"] = round(100.0 - out["sand_pct"] - out["clay_pct"], 1)
        out["soil_class"] = _texture_to_class(out["sand_pct"], out["clay_pct"])

    if not out:
        return None
    return out


def fetch_soil_profile(lat: float, lng: float) -> dict[str, Any] | None:
    """Returns soil profile dict, or None when no data is available
    (open water / glacier, or the API was unreachable).

    Schema:
      {"ph_h2o": 6.2, "sand_pct": 28, "clay_pct": 42, "silt_pct": 30,
       "organic_carbon_pct": 1.4, "soil_class": "clay_loam"}
    """
    try:
        raw = _query_topsoil(lat, lng)
    except SoilGridsUnavailable as e:
        _logger.warning("SoilGrids fetch failed at (%s, %s): %s", lat, lng, e)
        return None
    return _to_profile(raw)


def has_soil(lat: float, lng: float) -> bool:
    """Land-or-ocean sanity check.

    False only when SoilGrids *confirmed* there is no soil layer here (the
    API answered and every property was null). A fetch failure fails open —
    never lock a farmer out because a free API had a bad minute.
    """
    try:
        raw = _query_topsoil(lat, lng)
    except SoilGridsUnavailable as e:
        _logger.warning("SoilGrids unreachable at (%s, %s); assuming land: %s", lat, lng, e)
        return True
    return any(v is not None for v in raw.values())
