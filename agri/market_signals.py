"""Live mandi-price and pest-alert lookups via Tavily web search.

Two bounded queries per district per day:
  1. "{state} mandi prices today {crop1}, {crop2}, {crop3}" — returns 3-5 result
     snippets which we surface as captions; we do NOT try to parse exact ₹ values.
  2. "{state} {season} crop pest outbreak this week" — same pattern.

Cached per (state, ISO-date) for 12 hours. Failure → empty results, no UI change.
The panel only renders if at least one bucket has results.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from agri.cache import cached

_TTL = 12 * 60 * 60  # 12 h


try:
    import streamlit as st
except ImportError:
    st = None  # type: ignore


def _api_key() -> str:
    if st is None:
        return ""
    try:
        return str(st.secrets.get("TAVILY_API_KEY", ""))
    except Exception:
        return ""


def _client() -> Any | None:
    key = _api_key()
    if not key:
        return None
    try:
        from tavily import TavilyClient  # type: ignore
    except ImportError:
        return None
    try:
        return TavilyClient(api_key=key)
    except Exception:
        return None


@dataclass(frozen=True)
class Signal:
    title: str
    snippet: str
    url: str


def _search(query: str, max_results: int = 4) -> list[Signal]:
    client = _client()
    if client is None:
        return []
    try:
        resp = client.search(query=query, max_results=max_results, search_depth="basic")
    except Exception:
        return []
    out: list[Signal] = []
    for r in (resp or {}).get("results", []) or []:
        out.append(Signal(
            title=str(r.get("title", "")).strip(),
            snippet=str(r.get("content", ""))[:280].strip(),
            url=str(r.get("url", "")),
        ))
    return out


@cached(_TTL)
def mandi_signals(state: str, today_iso: str, top_crops_csv: str) -> list[dict[str, str]]:
    if not state or not top_crops_csv:
        return []
    q = f"{state} mandi price today {top_crops_csv}"
    return [s.__dict__ for s in _search(q, max_results=4)]


@cached(_TTL)
def pest_signals(state: str, season: str, today_iso: str) -> list[dict[str, str]]:
    if not state:
        return []
    q = f"{state} {season} crop pest outbreak advisory this week"
    return [s.__dict__ for s in _search(q, max_results=3)]


def fetch_all(state: str | None, season: str, top_crop_ids: list[str]) -> dict[str, list[Signal]]:
    """One-shot helper: returns {'mandi': [...], 'pest': [...]} for UI."""
    if not state:
        return {"mandi": [], "pest": []}
    today_iso = date.today().isoformat()
    top_csv = ", ".join(top_crop_ids[:3])
    return {
        "mandi": [Signal(**d) for d in mandi_signals(state, today_iso, top_csv)],
        "pest": [Signal(**d) for d in pest_signals(state, season, today_iso)],
    }
