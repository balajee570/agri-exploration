"""Sarvam-based regional rerank for the climate-suitable top-N.

Climate engine answers "can this crop survive here?" — this layer answers
"is it traditionally grown / commercially sensible here?" using sarvam-105b's
Indian agriculture priors. Returns a dict keyed by crop_id with a regional
score 0..100 and a one-sentence reason.

Cached per (state, ISO-week, crop-set hash) for 7 days so a district only
hits sarvam once per week. Any failure → empty dict → UI falls back to the
climate ranking unchanged.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from agri.ai_client import call_ai
from agri.cache import TTL_GEOCODE, cached


@dataclass(frozen=True)
class RegionalRank:
    crop_id: str
    score: float
    reason: str


_SYSTEM = (
    "You are an expert in Indian agriculture, specifically regional cropping "
    "patterns at the district level. Given climate-suitable crops, you re-rank "
    "by REGIONAL appropriateness for a specific Indian district: traditional "
    "cropping pattern, soil prevalence, mandi access, pest pressure, and "
    "commercial viability for small farmers. Respond ONLY with valid JSON. "
    "No prose outside the JSON. Be concise — your token budget is tight."
)


def _build_prompt(
    state: str, district: str, month_name: str, season: str,
    climate_ranked: list[tuple[str, float]],
) -> str:
    items = "\n".join(f"- {cid} (climate {score:.0f})" for cid, score in climate_ranked)
    return (
        f"District: {district}\nState: {state}\nSowing month: {month_name}\n"
        f"Season: {season}\n\nClimate-suitable crops:\n{items}\n\n"
        "Re-rank by regional fit for THIS district. For each crop output a "
        "0-100 regional score and a 5-15 word reason. Crops weakly grown here "
        "should score low (e.g. cotton in Bihar → 25). Crops central to local "
        "tradition score high (e.g. paddy in Bihar → 95). Use this exact JSON:\n"
        '{"ranked":[{"id":"<crop_id>","score":<0-100>,"why":"<reason>"}]}'
    )


def _parse(raw: str) -> dict[str, RegionalRank]:
    if not raw:
        return {}
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {}
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}
    out: dict[str, RegionalRank] = {}
    for row in obj.get("ranked", []) or []:
        cid = row.get("id")
        if not isinstance(cid, str):
            continue
        try:
            score = float(row.get("score", 0))
        except (TypeError, ValueError):
            continue
        reason = str(row.get("why", "")).strip()
        out[cid] = RegionalRank(crop_id=cid, score=max(0.0, min(100.0, score)), reason=reason)
    return out


def _crop_set_hash(crop_ids: list[str]) -> str:
    return hashlib.md5(",".join(sorted(crop_ids)).encode()).hexdigest()[:10]


@cached(TTL_GEOCODE)
def _cached_rerank(
    state: str, district: str, iso_year_week: str, season: str,
    month_name: str, crop_set_key: str, crop_list_payload: str,
) -> dict[str, dict[str, Any]]:
    """Cache hits on (state, ISO-week, crop_set). Returns a plain dict for hashing."""
    climate_ranked = json.loads(crop_list_payload)
    prompt = _build_prompt(state, district, month_name, season, climate_ranked)
    raw = call_ai(prompt, system=_SYSTEM, max_tokens=2048)
    parsed = _parse(raw)
    return {cid: {"score": r.score, "reason": r.reason} for cid, r in parsed.items()}


def rerank(
    state: str | None, district: str | None, sowing_date: date, season: str,
    climate_ranked: list[tuple[str, float]],
) -> dict[str, RegionalRank]:
    """Top-level: takes climate top-N as (crop_id, climate_score). Returns regional rankings."""
    if not state or not climate_ranked:
        return {}
    iso = sowing_date.isocalendar()
    iso_year_week = f"{iso[0]}-W{iso[1]:02d}"
    crop_ids = [cid for cid, _ in climate_ranked]
    key = _crop_set_hash(crop_ids)
    payload = json.dumps(climate_ranked)
    raw = _cached_rerank(
        state=state,
        district=district or state,
        iso_year_week=iso_year_week,
        season=season,
        month_name=sowing_date.strftime("%B"),
        crop_set_key=key,
        crop_list_payload=payload,
    )
    return {cid: RegionalRank(cid, v["score"], v["reason"]) for cid, v in raw.items()}
