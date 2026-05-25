"""Terrain — elevation + local slope from Open-Meteo's key-free Copernicus DEM."""

from __future__ import annotations

import math
from typing import Any

import httpx

from agri.cache import TTL_GEOCODE, cached

_OPEN_METEO_ELEVATION = "https://api.open-meteo.com/v1/elevation"
_DEFAULT_RADIUS_M = 180.0
_M_PER_DEG_LAT = 111_320.0


def _offsets(lat: float, radius_m: float) -> list[tuple[float, float]]:
    """8 compass points (N, NE, E, SE, S, SW, W, NW). Diagonals at r/√2 so all sit on one circle."""
    dlat = radius_m / _M_PER_DEG_LAT
    dlng = radius_m / (_M_PER_DEG_LAT * math.cos(math.radians(lat)) or 1e-6)
    diag = 1.0 / math.sqrt(2.0)
    return [
        (dlat, 0.0),                          # N
        (dlat * diag, dlng * diag),           # NE
        (0.0, dlng),                          # E
        (-dlat * diag, dlng * diag),          # SE
        (-dlat, 0.0),                         # S
        (-dlat * diag, -dlng * diag),         # SW
        (0.0, -dlng),                         # W
        (dlat * diag, -dlng * diag),          # NW
    ]


@cached(TTL_GEOCODE)
def fetch_neighborhood_elevations(
    lat: float, lng: float, radius_m: float = _DEFAULT_RADIUS_M
) -> tuple[float | None, list[float]]:
    """Single batch GET — 9 coords (centre + 8 neighbours). Returns (centre_m, neighbours_m)."""
    lat_r = round(lat, 4)
    lng_r = round(lng, 4)
    lats = [lat_r]
    lngs = [lng_r]
    for dlat, dlng in _offsets(lat_r, radius_m):
        lats.append(round(lat_r + dlat, 6))
        lngs.append(round(lng_r + dlng, 6))
    params = {
        "latitude": ",".join(f"{x}" for x in lats),
        "longitude": ",".join(f"{x}" for x in lngs),
    }
    try:
        resp = httpx.get(_OPEN_METEO_ELEVATION, params=params, timeout=15.0)
        resp.raise_for_status()
        elevs = resp.json().get("elevation", [])
        if not elevs or len(elevs) < 2:
            return None, []
        return float(elevs[0]), [float(e) for e in elevs[1:]]
    except httpx.HTTPError:
        return None, []


def compute_slope_pct(
    centre_m: float | None, neighbours_m: list[float], radius_m: float = _DEFAULT_RADIUS_M
) -> float:
    """Max % grade between centre and any neighbour. Fail-safe → 5.0 (neutral)."""
    if centre_m is None or not neighbours_m:
        return 5.0
    max_diff = max(abs(n - centre_m) for n in neighbours_m)
    return max_diff / radius_m * 100.0


def _drainage_class(slope_pct: float) -> str:
    if slope_pct < 1.0:
        return "flat"
    if slope_pct < 3.0:
        return "gentle"
    if slope_pct < 8.0:
        return "moderate"
    return "steep"


def terrain_summary(lat: float, lng: float) -> dict[str, Any]:
    """Returns {elevation_m, slope_pct, drainage_class}. Fail-safe defaults on API failure."""
    centre, neighbours = fetch_neighborhood_elevations(lat, lng)
    slope = compute_slope_pct(centre, neighbours)
    return {
        "elevation_m": centre,
        "slope_pct": slope,
        "drainage_class": _drainage_class(slope),
    }
