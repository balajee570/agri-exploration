"""NASA POWER: server-side agromet (no key, no CORS issue since we're server-side)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import httpx
import pandas as pd

from agri.cache import TTL_POWER, cached

_DAILY_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
_CLIMATOLOGY_URL = "https://power.larc.nasa.gov/api/temporal/climatology/point"

_AGROMET_PARAMS = [
    "T2M",
    "T2M_MAX",
    "T2M_MIN",
    "RH2M",
    "WS2M",
    "PRECTOTCORR",
    "ALLSKY_SFC_SW_DWN",
    "EVPTRNS",
]


@cached(TTL_POWER)
def fetch_daily(lat: float, lng: float, days: int = 30) -> pd.DataFrame:
    """Last N days of NASA POWER daily agromet."""
    end = date.today() - timedelta(days=3)
    start = end - timedelta(days=days)
    params = {
        "parameters": ",".join(_AGROMET_PARAMS),
        "community": "AG",
        "longitude": lng,
        "latitude": lat,
        "start": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
        "format": "JSON",
    }
    try:
        resp = httpx.get(_DAILY_URL, params=params, timeout=30.0)
        resp.raise_for_status()
        payload = resp.json()
    except httpx.HTTPError:
        return pd.DataFrame()
    series = payload.get("properties", {}).get("parameter", {})
    if not series:
        return pd.DataFrame()
    df = pd.DataFrame(series)
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df = df.replace(-999, pd.NA).dropna(how="all")
    return df


@cached(TTL_POWER)
def fetch_climatology(lat: float, lng: float) -> pd.DataFrame:
    """40-year monthly climatology (Jan-Dec) for the point."""
    params = {
        "parameters": ",".join(["T2M", "T2M_MAX", "T2M_MIN", "PRECTOTCORR", "EVPTRNS"]),
        "community": "AG",
        "longitude": lng,
        "latitude": lat,
        "format": "JSON",
    }
    try:
        resp = httpx.get(_CLIMATOLOGY_URL, params=params, timeout=30.0)
        resp.raise_for_status()
        payload = resp.json()
    except httpx.HTTPError:
        return pd.DataFrame()
    series = payload.get("properties", {}).get("parameter", {})
    if not series:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    month_map = {
        "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
        "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
    }
    months_seen: set[int] = set()
    for param, by_month in series.items():
        for key, value in by_month.items():
            m = month_map.get(key)
            if m is None:
                continue
            months_seen.add(m)
    for m in sorted(months_seen):
        row = {"month": m}
        for param, by_month in series.items():
            month_key = [k for k, v in month_map.items() if v == m][0]
            row[param] = by_month.get(month_key)
        rows.append(row)
    df = pd.DataFrame(rows)
    return df
