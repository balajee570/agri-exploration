"""Live market intelligence — Tavily web search synthesized through Sarvam-105B.

Pipeline:
  1. Tavily fetches raw web-search results for mandi prices + pest advisories
     (cached 12 h per state/season).
  2. Sarvam-105B synthesizes those into a concise 3-section Markdown summary:
     mandi prices, advisories, AI recommendation (with explicit
     climate-vs-regional disagreements flagged).
  3. A curated list of universal + state-specific buy/sell marketplaces is
     appended for the farmer.

Failure modes: any step that returns "" or [] silently drops to the next; the
UI either renders what it has or hides the panel entirely.
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


@dataclass(frozen=True)
class MarketLink:
    name: str
    url: str
    purpose: str  # "Buy inputs" / "Sell produce" / "Price discovery" / etc.


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


_SYNTHESIS_SYSTEM = (
    "You are an agriculture market analyst for Indian farmers. Given raw "
    "web-search results for mandi prices and pest/disease advisories, plus "
    "the farmer's top recommended crops, write a CONCISE three-section "
    "Markdown summary. Use ₹/quintal where prices appear in the source. "
    "Mention specific mandi names when present in the source data. "
    "If your domain knowledge contradicts the climate-driven ranking, say so "
    "explicitly (e.g. 'Cotton scores high on weather but Bihar's procurement "
    "infrastructure favours Gujarat/Maharashtra — focus on Moong instead'). "
    "Output ONLY these three sections, in this exact order, nothing else:\n\n"
    "**📊 Mandi prices**\n[2-3 sentences with actual ₹ values from results]\n\n"
    "**🛡️ Advisories**\n[2-3 sentences on pests/diseases/weather]\n\n"
    "**✅ AI recommendation**\n[3-4 sentences justifying the top crops, "
    "weaving in mandi prices and advisories; flag any climate-vs-regional "
    "disagreements explicitly]"
)


def _format_results(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "(none)"
    return "\n".join(
        f"- {r.get('title', '').strip()} — {r.get('snippet', '').strip()}"
        for r in rows[:5]
    )


@cached(_TTL)
def synthesize_market_summary(
    state: str, district: str, season: str,
    top_crops_csv: str, today_iso: str,
) -> str:
    """Returns a 3-section Markdown summary, or "" on any failure.

    Cache key includes the day, so summaries refresh daily but a state+crop
    combination only hits Sarvam once per day.
    """
    if not state or not top_crops_csv:
        return ""
    mandi = mandi_signals(state, today_iso, top_crops_csv)
    pest = pest_signals(state, season, today_iso)
    if not mandi and not pest:
        return ""
    prompt = (
        f"Location: {district or state}, {state}\n"
        f"Sowing season: {season}\n"
        f"Top recommended crops: {top_crops_csv}\n\n"
        f"Mandi search results:\n{_format_results(mandi)}\n\n"
        f"Pest/advisory search results:\n{_format_results(pest)}"
    )
    from agri.ai_client import call_ai
    return call_ai(prompt, system=_SYNTHESIS_SYSTEM, max_tokens=2048)


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
    """Return state-specific portal (if any) plus universal platforms."""
    links: list[MarketLink] = []
    if state and state in _STATE_PORTALS:
        links.append(_STATE_PORTALS[state])
    links.extend(_UNIVERSAL_PLATFORMS)
    return links


def fetch_all(state: str | None, season: str, top_crop_ids: list[str]) -> dict[str, Any]:
    """One-shot helper for the UI.

    Returns {"summary_md": str, "links": list[MarketLink]}.
    summary_md may be "" if Tavily/Sarvam are unavailable;
    links is always non-empty (universal platforms always returned).
    """
    today_iso = date.today().isoformat()
    top_csv = ", ".join(top_crop_ids[:3])
    summary = ""
    if state:
        summary = synthesize_market_summary(state, state, season, top_csv, today_iso)
    return {"summary_md": summary, "links": buy_sell_links(state)}
