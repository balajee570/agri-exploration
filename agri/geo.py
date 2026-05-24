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
