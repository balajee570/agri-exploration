"""Farming intelligence — AI-synthesized agronomic reasoning + buy/sell links.

The AI here answers *"what should I grow and why?"* — supported by Tavily
web-search snippets that provide source backing (ICAR, state agri dept,
NAFED schemes, Cotton Corporation regional data, etc.). It does NOT surface
mandi prices: those vary hourly and Tavily snippets are too unreliable for
price quotation.

Two distinct outputs:
  1. A structured Markdown summary with ✅ "Why grow these crops" and
     ❌ "Climate suggests but AI advises against" sections — the second
     section is the explicit counter-narrative for cases where the climate
     engine ranks a crop high but the AI rerank knows it's a bad regional fit
     (e.g. Cotton in Bihar).
  2. A curated list of universal + state-specific marketplaces.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from agri.cache import cached

_TTL = 12 * 60 * 60  # 12 h cache for both Tavily and Sarvam outputs


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


@dataclass(frozen=True)
class MarketLink:
    name: str
    url: str
    purpose: str


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


_FARMING_SYSTEM = (
    "You are an expert in Indian agronomy and regional cropping patterns. "
    "Given a list of recommended crops for a specific Indian location and "
    "supporting web-search snippets, write a CONCISE structured farming "
    "intelligence summary in Markdown. Focus exclusively on agronomic "
    "reasoning — soil suitability, traditional cropping pattern, pest/"
    "disease pressure, processing infrastructure (mandis/ginning/cold-chain), "
    "and government schemes (MSP, PSS, PMFBY). Cite institutions by name "
    "(ICAR, state agri dept, NAFED, Cotton Corporation, etc.) where they "
    "appear in the snippets. NEVER invent specific ₹ prices or yield numbers — "
    "only use what's in the snippets.\n\n"
    "Output ONLY these two sections, in this exact order, nothing else:\n\n"
    "**✅ Why grow these crops here**\n"
    "For each top crop, a 3-4 sentence agronomic paragraph. Format:\n"
    "1. **{Crop name}** — {reasoning covering soil/season fit, agronomic tips, "
    "infrastructure/scheme context}\n"
    "2. **{Crop name}** — {same}\n"
    "3. **{Crop name}** — {same}\n\n"
    "**❌ Climate suggests but AI advises against**\n"
    "For each counter crop listed by the user, write 2-3 sentences explaining "
    "WHY it's a poor regional fit. Be specific: infrastructure gaps, regional "
    "disease/pest patterns, capital requirements, alternative regions where it "
    "thrives. This is critical — the farmer needs an explicit reason NOT to "
    "follow the climate-based suggestion. Format:\n"
    "- **{Crop}** (Climate: X · Regional: Y) — {counter reasoning}"
)


@cached(_TTL)
def _farming_background(state: str, season: str, today_iso: str) -> str:
    """Tavily background — general cropping patterns + agronomic advisories."""
    if not state:
        return ""
    queries = [
        f"best crops to grow {state} {season} season ICAR recommendations traditional",
        f"{state} agriculture department crop advisory {season} cropping pattern",
    ]
    snippets: list[str] = []
    seen: set[str] = set()
    for q in queries:
        for s in _search(q, max_results=4):
            line = f"- {s.title}: {s.snippet}"
            if line not in seen:
                seen.add(line)
                snippets.append(line)
    return "\n".join(snippets[:8])


def _format_crops(crops: list[dict[str, Any]]) -> str:
    if not crops:
        return "(none)"
    lines: list[str] = []
    for c in crops:
        parts = [c.get("name", c.get("id", "?")),
                 f"climate {c.get('climate', 0):.0f}"]
        if c.get("regional") is not None:
            parts.append(f"regional {c['regional']:.0f}")
        line = f"- {parts[0]} ({', '.join(parts[1:])})"
        if c.get("reason"):
            line += f" — {c['reason']}"
        lines.append(line)
    return "\n".join(lines)


@cached(_TTL)
def synthesize_farming_intelligence(
    state: str, district: str, season: str, month_name: str,
    top_crops_json: str, counter_crops_json: str, today_iso: str,
) -> str:
    """Returns Markdown farming-intelligence summary, or "" on any failure.

    Cache key includes the day, so summaries refresh daily but a state+crop
    combination only hits Sarvam once per day.
    """
    if not state or not top_crops_json:
        return ""
    top_crops = json.loads(top_crops_json)
    counter_crops = json.loads(counter_crops_json) if counter_crops_json else []
    if not top_crops:
        return ""

    background = _farming_background(state, season, today_iso)
    counter_section = ""
    if counter_crops:
        counter_section = (
            f"\n\nClimate engine top picks NOT in AI top 3 — write counter-recommendations "
            f"for these:\n{_format_crops(counter_crops)}"
        )
    prompt = (
        f"Location: {district or state}, {state}\n"
        f"Sowing month: {month_name} ({season} season)\n\n"
        f"Top recommended crops (AI-reranked):\n{_format_crops(top_crops)}"
        + counter_section
        + f"\n\nBackground context from web search:\n{background or '(none — rely on your own knowledge)'}"
    )
    from agri.ai_client import call_ai
    return call_ai(prompt, system=_FARMING_SYSTEM, max_tokens=3500)


_UNIVERSAL_PLATFORMS: list[MarketLink] = [
    MarketLink("eNAM", "https://enam.gov.in",
               "Sell produce — National Agriculture Market"),
    MarketLink("AgMarknet", "https://agmarknet.gov.in",
               "Price discovery across Indian mandis"),
    MarketLink("AgriBegri", "https://www.agribegri.com",
               "Buy inputs — seeds, fertilisers, tools"),
    MarketLink("BigHaat", "https://www.bighaat.com",
               "Buy inputs — agri inputs delivered"),
    MarketLink("IndiaMART (Agriculture)",
               "https://dir.indiamart.com/industry/agriculture.html",
               "B2B buy & sell directory"),
]

_STATE_PORTALS: dict[str, MarketLink] = {
    "Bihar": MarketLink("Bihar Mandi Portal",
                        "https://esamadhan.bihar.gov.in/",
                        "State mandi portal"),
    "Karnataka": MarketLink("Karnataka RMS",
                            "https://rms.karnataka.gov.in/",
                            "State mandi portal"),
    "Maharashtra": MarketLink("MahaFPC",
                              "https://mahafpc.in/",
                              "State FPC marketplace"),
    "Punjab": MarketLink("Punjab Mandi Board",
                         "https://mandiboard.punjab.gov.in/",
                         "State mandi board"),
    "Haryana": MarketLink("Haryana Mandi Board",
                          "https://hsamb.gov.in/",
                          "State mandi board"),
    "Madhya Pradesh": MarketLink("MP Mandi Board",
                                  "https://mpmandiboard.gov.in/",
                                  "State mandi board"),
    "Uttar Pradesh": MarketLink("UP Mandi Parishad",
                                 "https://upmandiparishad.in/",
                                 "State mandi parishad"),
    "Tamil Nadu": MarketLink("TN Agri Marketing",
                              "https://tnagrisnet.tn.gov.in/",
                              "State agri marketing portal"),
    "Gujarat": MarketLink("Gujarat APMC",
                           "https://apmcgujarat.com/",
                           "State APMC portal"),
    "Andhra Pradesh": MarketLink("AP Agri Marketing",
                                  "https://apagrisnet.gov.in/",
                                  "State agri marketing portal"),
    "Telangana": MarketLink("TS Agri Marketing",
                             "https://agrimarket.telangana.gov.in/",
                             "State agri marketing portal"),
    "West Bengal": MarketLink("WB Agri Marketing",
                               "https://wbagrimarketingboard.gov.in/",
                               "State agri marketing board"),
    "Rajasthan": MarketLink("Rajasthan Mandi Board",
                             "https://rajkisan.rajasthan.gov.in/",
                             "State agri portal"),
}


def buy_sell_links(state: str | None) -> list[MarketLink]:
    """State-specific portal first (if any), then universal platforms."""
    links: list[MarketLink] = []
    if state and state in _STATE_PORTALS:
        links.append(_STATE_PORTALS[state])
    links.extend(_UNIVERSAL_PLATFORMS)
    return links


def fetch_all(
    state: str | None, season: str, sowing_date: date,
    top_crops: list[dict[str, Any]], counter_crops: list[dict[str, Any]],
) -> dict[str, Any]:
    """One-shot helper for the UI.

    Returns {"summary_md": str, "links": list[MarketLink]}.
    summary_md may be "" if Sarvam is unavailable;
    links is always populated (universal platforms always returned).
    """
    today_iso = date.today().isoformat()
    summary = ""
    if state and top_crops:
        summary = synthesize_farming_intelligence(
            state=state, district=state, season=season,
            month_name=sowing_date.strftime("%B"),
            top_crops_json=json.dumps(top_crops),
            counter_crops_json=json.dumps(counter_crops or []),
            today_iso=today_iso,
        )
    return {"summary_md": summary, "links": buy_sell_links(state)}
