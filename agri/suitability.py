"""Geographic suitability filter — excludes crops that fundamentally don't fit a location.

Tea doesn't grow in Bihar plains (50 m, hot lowlands). Paddy can't survive at Darjeeling's
2100 m. Each crop optionally declares `elevation_m` and `annual_rain_mm` envelopes; existing
`temp_c.min/max` is also used. Crops without envelopes pass through unchanged — fail-safe.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from agri.terrain import terrain_summary


def annual_rainfall_mm(normals: pd.DataFrame) -> float | None:
    """Sum of monthly daily-avg precip × 30 ≈ annual total."""
    if normals is None or normals.empty or "precip_mm" not in normals.columns:
        return None
    return float(normals["precip_mm"].sum() * 30.0)


def annual_mean_temp_c(normals: pd.DataFrame) -> float | None:
    if normals is None or normals.empty or "temp_mean_c" not in normals.columns:
        return None
    return float(normals["temp_mean_c"].mean())


def geographic_fit(
    crop: dict[str, Any], elevation_m: float | None, normals: pd.DataFrame | None
) -> tuple[float, str]:
    """Returns (fit, reason). fit < 0.1 means exclude from recommendations.

    Checks only the envelopes the crop actually declares. Generous buffers
    (elev ±200 m, rain ×0.5/×2, temp ±5-8 °C) prevent false exclusions on borderline plots.
    """
    if elevation_m is not None:
        env = crop.get("elevation_m")
        if env and isinstance(env, list) and len(env) == 2:
            lo, hi = env
            if elevation_m < lo - 200:
                return 0.0, f"needs elevation ≥{lo} m, here {elevation_m:.0f} m"
            if elevation_m > hi + 200:
                return 0.0, f"needs elevation ≤{hi} m, here {elevation_m:.0f} m"

    annual_rain = annual_rainfall_mm(normals)
    if annual_rain is not None:
        env = crop.get("annual_rain_mm")
        if env and isinstance(env, list) and len(env) == 2:
            lo, hi = env
            if annual_rain < lo * 0.5:
                return 0.0, f"needs ≥{lo} mm/yr rainfall, here only ~{annual_rain:.0f} mm"
            if annual_rain > hi * 2:
                return 0.0, f"needs ≤{hi} mm/yr rainfall, here ~{annual_rain:.0f} mm"

    annual_temp = annual_mean_temp_c(normals)
    if annual_temp is not None:
        tc = crop.get("temp_c") or {}
        tmin = tc.get("min")
        tmax = tc.get("max")
        if tmin is not None and annual_temp < tmin - 8:
            return 0.0, f"avg annual temp {annual_temp:.0f}°C too cold for {tmin}-{tmax}°C crop"
        if tmax is not None and annual_temp > tmax + 5:
            return 0.0, f"avg annual temp {annual_temp:.0f}°C too hot for {tmin}-{tmax}°C crop"

    return 1.0, ""


def excluded_for_location(
    lat: float, lng: float, normals: pd.DataFrame | None, elevation_m: float | None = None
) -> list[tuple[dict[str, Any], str]]:
    """List of (crop, reason) for crops that fail the hard geographic filter at this point."""
    from agri.recommend import load_crops  # lazy: avoids circular import

    if elevation_m is None:
        elevation_m = terrain_summary(lat, lng).get("elevation_m")
    out: list[tuple[dict[str, Any], str]] = []
    for crop in load_crops():
        fit, reason = geographic_fit(crop, elevation_m, normals)
        if fit < 0.1:
            out.append((crop, reason))
    return out
