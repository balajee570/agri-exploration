"""Indian crop seasons from calendar date."""

from __future__ import annotations

from datetime import date


def current_season(d: date) -> str:
    """Kharif (Jun-Sep), Rabi (Oct-Mar), Zaid (Apr-May)."""
    return season_for_month(d.month)


def season_for_month(m: int) -> str:
    if 6 <= m <= 9:
        return "kharif"
    if m >= 10 or m <= 3:
        return "rabi"
    return "zaid"


SEASON_LABELS = {
    "kharif": "Kharif (Jun-Oct)",
    "rabi": "Rabi (Oct-Mar)",
    "zaid": "Zaid (Mar-Jun)",
    "perennial": "Perennial",
}


def months_match_season(months: list[int], season: str) -> bool:
    for m in months:
        if season_for_month(m) == season:
            return True
    return False
