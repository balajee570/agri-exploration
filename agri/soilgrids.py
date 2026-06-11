"""ISRIC SoilGrids 250 m — per-location soil pH, texture, and organic carbon.

Free, no key. https://rest.isric.org/soilgrids/v2.0/properties/query
Cached for 30 days (soil doesn't change on human timescales).

The returned dict's `soil_class` field maps the USDA texture triangle into one
of the catalog's existing `soil_types` strings so `geographic_fit` can do
direct set-membership comparison.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from agri.cache import cached

_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
_TTL = 30 * 24 * 60 * 60  # 30 days
_logger = logging.getLogger(__name__)


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


@cached(_TTL)
def fetch_soil_profile(lat: float, lng: float) -> dict[str, Any] | None:
    """Returns soil profile dict or None on failure / no-soil (e.g. open water).

    Schema:
      {"ph_h2o": 6.2, "sand_pct": 28, "clay_pct": 42, "silt_pct": 30,
       "organic_carbon_pct": 1.4, "soil_class": "clay_loam"}
    """
    params = {
        "lat": f"{lat:.4f}",
        "lon": f"{lng:.4f}",
        "property": ["phh2o", "clay", "sand", "soc"],
        "depth": "0-30cm",
        "value": "mean",
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.get(_URL, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        _logger.warning("SoilGrids fetch failed at (%s, %s): %s", lat, lng, e)
        return None

    layers = (data.get("properties") or {}).get("layers") or []
    if not layers:
        return None

    out: dict[str, Any] = {}
    for layer in layers:
        name = layer.get("name")
        depths = layer.get("depths") or []
        if not depths:
            continue
        mean = (depths[0].get("values") or {}).get("mean")
        if mean is None:
            continue
        d_factor = float((layer.get("unit_measure") or {}).get("d_factor") or 1.0)
        scaled = mean / d_factor
        if name == "phh2o":
            out["ph_h2o"] = round(scaled, 2)
        elif name == "clay":
            out["clay_pct"] = round(scaled, 1)
        elif name == "sand":
            out["sand_pct"] = round(scaled, 1)
        elif name == "soc":
            # SoilGrids SOC is in g/kg; convert to %
            out["organic_carbon_pct"] = round(scaled / 10.0, 2)

    if "sand_pct" in out and "clay_pct" in out:
        out["silt_pct"] = round(100.0 - out["sand_pct"] - out["clay_pct"], 1)
        out["soil_class"] = _texture_to_class(out["sand_pct"], out["clay_pct"])

    if not out:
        return None
    return out


def has_soil(lat: float, lng: float) -> bool:
    """Land-or-ocean sanity check. False ≈ open water / glacier / no soil layer."""
    profile = fetch_soil_profile(lat, lng)
    return profile is not None and "ph_h2o" in profile
