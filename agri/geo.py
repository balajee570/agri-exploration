"""Location: geocoding (place → lat/lng) and reverse geocoding (lat/lng → district)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from agri.cache import TTL_GEOCODE, cached


@dataclass(frozen=True)
class Place:
    name: str
    lat: float
    lng: float
    state: str | None
    district: str | None
    elevation_m: float | None
    country: str = "India"

    @property
    def label(self) -> str:
        parts = [self.name]
        if self.district and self.district != self.name:
            parts.append(self.district)
        if self.state:
            parts.append(self.state)
        return ", ".join(parts)


_OPEN_METEO_GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
_BDC_REVERSE = "https://api.bigdatacloud.net/data/reverse-geocode-client"


@cached(TTL_GEOCODE)
def search_india(query: str, limit: int = 8) -> list[Place]:
    """Pan-India place search via Open-Meteo geocoding."""
    query = query.strip()
    if not query:
        return []
    try:
        resp = httpx.get(
            _OPEN_METEO_GEOCODE,
            params={
                "name": query,
                "count": limit,
                "language": "en",
                "format": "json",
                "countryCode": "IN",
            },
            timeout=10.0,
        )
        resp.raise_for_status()
    except httpx.HTTPError:
        return []

    out: list[Place] = []
    for r in resp.json().get("results", []) or []:
        out.append(
            Place(
                name=r.get("name", query),
                lat=float(r["latitude"]),
                lng=float(r["longitude"]),
                state=r.get("admin1"),
                district=r.get("admin2") or r.get("admin3"),
                elevation_m=r.get("elevation"),
            )
        )
    return out


@cached(TTL_GEOCODE)
def reverse_geocode(lat: float, lng: float) -> dict[str, Any]:
    """lat/lng → district/state. BigDataCloud public endpoint (no key)."""
    try:
        resp = httpx.get(
            _BDC_REVERSE,
            params={"latitude": lat, "longitude": lng, "localityLanguage": "en"},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPError:
        return {}
    return {
        "state": data.get("principalSubdivision"),
        "district": data.get("localityInfo", {}).get("administrative", [{}])[-2].get("name")
        if data.get("localityInfo", {}).get("administrative")
        else data.get("city") or data.get("locality"),
        "locality": data.get("locality") or data.get("city"),
        "country": data.get("countryName"),
        "country_code": data.get("countryCode"),
    }


def place_from_coords(lat: float, lng: float) -> Place:
    info = reverse_geocode(lat, lng)
    return Place(
        name=info.get("locality") or info.get("district") or f"{lat:.3f}, {lng:.3f}",
        lat=lat,
        lng=lng,
        state=info.get("state"),
        district=info.get("district"),
        elevation_m=None,
        country=info.get("country") or "India",
    )


def climate_zone(lat: float, lng: float) -> str:
    """Coarse Indian climate-zone bucket from latitude. Used as a tiebreaker only."""
    if lat >= 28:
        return "north"
    if lat >= 23:
        return "central"
    if lat >= 17:
        return "south_central"
    return "south"


_OVERPASS = "https://overpass-api.de/api/interpreter"


@cached(TTL_GEOCODE)
def nearest_mandi(lat: float, lng: float) -> dict[str, Any] | None:
    """Closest OpenStreetMap `amenity=marketplace` within 100 km. None if absent.

    Returns {distance_km, name, lat, lng}.
    """
    radius_m = 100_000
    query = (
        f"[out:json][timeout:25];"
        f"(node['amenity'='marketplace'](around:{radius_m},{lat},{lng});"
        f"way['amenity'='marketplace'](around:{radius_m},{lat},{lng}););"
        f"out center 30;"
    )
    try:
        resp = httpx.post(_OVERPASS, data=query.encode("utf-8"), timeout=20.0,
                          headers={"User-Agent": "KrishiCast/1.0 (open-source)"})
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
    except httpx.HTTPError:
        return None

    import math as _math
    def _dist_km(la1, lo1, la2, lo2):
        R = 6371.0
        p1, p2 = _math.radians(la1), _math.radians(la2)
        dp = _math.radians(la2 - la1)
        dl = _math.radians(lo2 - lo1)
        a = _math.sin(dp / 2) ** 2 + _math.cos(p1) * _math.cos(p2) * _math.sin(dl / 2) ** 2
        return 2 * R * _math.asin(_math.sqrt(a))

    best = None
    for el in elements:
        plat = el.get("lat") or (el.get("center") or {}).get("lat")
        plng = el.get("lon") or (el.get("center") or {}).get("lon")
        if plat is None or plng is None:
            continue
        d = _dist_km(lat, lng, plat, plng)
        name = (el.get("tags") or {}).get("name") or "marketplace"
        if best is None or d < best["distance_km"]:
            best = {"distance_km": round(d, 1), "name": name,
                    "lat": plat, "lng": plng}
    return best


def is_on_land(lat: float, lng: float) -> bool:
    """Coarse land/water check via SoilGrids existence.

    True if a soil profile is available at this point; False otherwise.
    Used to short-circuit recommendations for points in open water.
    """
    from agri.soilgrids import has_soil
    return has_soil(lat, lng)
