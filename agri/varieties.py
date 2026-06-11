"""District / state-level variety recommendations.

Hand-curated from publicly available ICAR-AICRP "Notified Varieties" tables and
state agricultural-university recommendations. Static JSON so we don't depend
on scraping PDFs at runtime.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from agri import DATA_DIR


@lru_cache(maxsize=1)
def _load() -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Schema: {crop_id: {state: [{name, duration_days, notes}]}}"""
    path = DATA_DIR / "varieties.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def recommend_varieties(crop_id: str, state: str | None) -> list[dict[str, Any]]:
    """Returns the curated variety list for this crop in this state. Empty if absent."""
    table = _load().get(crop_id) or {}
    if state and state in table:
        return table[state]
    return table.get("__default__") or []
