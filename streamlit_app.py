"""KrishiCast — pan-India crop recommender powered by live weather + satellite data."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from agri import DATA_DIR
from agri.geo import Place, nearest_mandi, place_from_coords, search_india
from agri.gibs import LAYERS, best_recent_day
from agri.i18n import crop_name, current_lang, language_selector
from agri.market_signals import fetch_all as fetch_market_signals
from agri.mandi_prices import latest_price_strip
from agri.recommend import (
    best_sowing_date,
    crops_by_id,
    income_estimate_inr_per_acre,
    rank_for_date,
)
from agri.regional_priors import rerank as regional_rerank
from agri.rotation import next_season_partners
from agri.schemes import schemes_for
from agri.season import SEASON_LABELS, SEASON_LABELS_HI, current_season
from agri.soil import current_soil_profile, root_zone_moisture_pct, root_zone_temp_c
from agri.soilgrids import fetch_soil_profile, has_soil
from agri.suitability import excluded_for_location
from agri.terrain import terrain_summary
from agri.varieties import recommend_varieties
from agri.viz import (
    forecast_temperature_chart,
    rainfall_bar_chart,
    score_ring,
    soil_moisture_profile,
)
from agri.weather import (
    daily_forecast_df,
    fetch_archive_year,
    fetch_climate_normals,
    fetch_forecast,
    rainfall_last_n_days,
)

_logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="KrishiCast · Crop recommender for India",
    page_icon="🌾",
    layout="wide",
)


# ---- Custom CSS for the polished look ----------------------------------------
_CUSTOM_CSS = """
<style>
  /* Hero banner */
  .krishicast-hero {
    background: linear-gradient(135deg, #2E7D32 0%, #558B2F 50%, #8D6E63 100%);
    border-radius: 14px;
    padding: 22px 28px;
    color: #FAFAF7;
    margin-bottom: 18px;
    box-shadow: 0 4px 14px rgba(46,125,50,0.18);
  }
  .krishicast-hero h1 { margin: 0; font-size: 1.85rem; letter-spacing: -0.02em; }
  .krishicast-hero .pill {
    display: inline-block; background: rgba(255,255,255,0.18);
    padding: 4px 12px; border-radius: 999px; font-size: 0.92rem; margin-right: 8px;
    backdrop-filter: blur(4px);
  }
  .krishicast-hero .sub { opacity: 0.9; font-size: 0.95rem; margin-top: 6px; }

  /* Card chrome */
  .crop-card {
    border: 1px solid #E0E0DC; border-radius: 14px; padding: 14px 16px;
    background: #FFFFFF; box-shadow: 0 1px 4px rgba(0,0,0,0.04);
  }
  .crop-card h3 { margin: 0 0 6px 0; font-size: 1.18rem; }
  .badge {
    display: inline-block; padding: 2px 9px; border-radius: 999px;
    font-size: 0.78rem; margin-right: 4px; margin-bottom: 4px;
  }
  .badge-green { background: #E8F5E9; color: #2E7D32; }
  .badge-amber { background: #FFF8E1; color: #B27B00; }
  .badge-red   { background: #FFEBEE; color: #C62828; }
  .badge-blue  { background: #E3F2FD; color: #1565C0; }
  .badge-earth { background: #EFEBE9; color: #6D4C41; }

  .scheme-chip {
    display: inline-block; padding: 3px 9px; border-radius: 6px;
    font-size: 0.78rem; margin-right: 5px; margin-bottom: 4px;
    background: #E8F5E9; color: #2E7D32; text-decoration: none;
  }
  .scheme-chip:hover { background: #C8E6C9; }

  .live-strip {
    background: #F7F6F1; border-radius: 12px; padding: 12px 18px;
    border: 1px solid #E5E2D6;
    display: flex; flex-wrap: wrap; gap: 24px; align-items: center;
  }
  .live-strip .item { min-width: 100px; }
  .live-strip .item .lbl { font-size: 0.78rem; color: #666; }
  .live-strip .item .val { font-size: 1.1rem; font-weight: 600; color: #1B1B1B; }

  .pest-warn {
    background: #FFF3E0; border-left: 4px solid #F57C00;
    padding: 8px 12px; margin: 6px 0; border-radius: 6px; font-size: 0.85rem;
  }

  .footer {
    text-align: center; color: #888; font-size: 0.78rem; padding: 16px 0;
  }
</style>
"""


def _init_state() -> None:
    if "place" not in st.session_state:
        st.session_state.place = Place(
            name="Patna", lat=25.6, lng=85.1, state="Bihar",
            district="Patna", elevation_m=53,
        )
    if "sowing_date" not in st.session_state:
        st.session_state.sowing_date = date.today()
    if "irrigated" not in st.session_state:
        st.session_state.irrigated = False


# ---- Header -----------------------------------------------------------------

def _hero(place: Place, sowing_date: date) -> None:
    season = current_season(sowing_date)
    _slabels = SEASON_LABELS_HI if current_lang() == "hi" else SEASON_LABELS
    terr = terrain_summary(place.lat, place.lng)
    elev_m = terr.get("elevation_m")
    slope = terr.get("slope_pct") or 0.0
    aspect = terr.get("aspect")
    parts = []
    if elev_m is not None:
        parts.append(f"⛰️ {elev_m:.0f} m")
    parts.append(f"📐 {slope:.1f}% slope")
    if aspect:
        parts.append(f"🧭 faces {aspect}")
    terrain_pill = " · ".join(parts)
    st.markdown(f"""
    <div class="krishicast-hero">
      <h1>🌾 KrishiCast</h1>
      <div class="sub">
        <span class="pill">📍 {place.label}</span>
        <span class="pill">{terrain_pill}</span>
        <span class="pill">📅 {sowing_date.strftime('%a, %d %b %Y')}</span>
        <span class="pill">🪴 {_slabels[season]}</span>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ---- Location picker --------------------------------------------------------

def _location_strip() -> Place:
    st.markdown("### 📍 Where is your farm?")
    q = st.text_input(
        "Search any town, district or village in India",
        key="search_input",
        placeholder="Patna, Hoshangabad village, Anantapur, Tezpur…",
        label_visibility="collapsed",
    )

    if q:
        results = search_india(q, limit=6)
        if results:
            labels = [r.label for r in results]
            choice = st.radio("Pick a match", labels, horizontal=False, key="search_pick")
            picked = results[labels.index(choice)]
            if st.button("Use this location", type="primary"):
                st.session_state.place = picked
                st.rerun()
        else:
            st.caption("No match. Try a nearby larger town.")

    place: Place = st.session_state.place
    sub = f"**{place.label}** · {place.lat:.4f}°, {place.lng:.4f}°"
    if place.elevation_m:
        sub += f" · {place.elevation_m:.0f} m"
    st.caption(sub)
    st.caption("💡 Tip: click anywhere on the satellite map below to drop a pin.")
    return place


# ---- Live conditions strip --------------------------------------------------

def _conditions_strip(place: Place, forecast: dict) -> None:
    current = forecast.get("current", {})
    rain_30 = rainfall_last_n_days(forecast, 30)
    sm = root_zone_moisture_pct(forecast)
    st_c = root_zone_temp_c(forecast)

    soil = fetch_soil_profile(place.lat, place.lng)

    items = [
        ("Temp now", f"{current.get('temperature_2m', '—')} °C", "🌡️"),
        ("Humidity", f"{current.get('relative_humidity_2m', '—')} %", "💧"),
        ("Wind", f"{current.get('wind_speed_10m', '—')} km/h", "💨"),
        ("Root-zone moisture", f"{sm:.1f}%" if pd.notna(sm) else "—", "🌱"),
        ("Root-zone temp", f"{st_c:.1f} °C" if pd.notna(st_c) else "—", "🌡️"),
        ("Rainfall (30 d)", f"{rain_30:.0f} mm" if pd.notna(rain_30) else "—", "🌧️"),
    ]
    if soil and "ph_h2o" in soil:
        items.append(("Soil pH (0-30 cm)", f"{soil['ph_h2o']:.1f}", "🧪"))
    if soil and "soil_class" in soil:
        items.append(("Soil texture", soil["soil_class"].replace("_", " "), "🟤"))

    html_items = "".join(
        f'<div class="item"><div class="lbl">{ico} {lbl}</div>'
        f'<div class="val">{val}</div></div>'
        for lbl, val, ico in items
    )
    st.markdown(f'<div class="live-strip">{html_items}</div>', unsafe_allow_html=True)


# ---- Recommendation card ----------------------------------------------------

def _next_window_caption(crop: dict, sowing_date: date,
                        best: tuple[date, "object"] | None) -> tuple[str, str]:
    """Returns (caption, badge_class). Badge class is one of badge-green/amber/red."""
    if best is None:
        return ("", "badge-earth")
    best_date, best_res = best
    days_ahead = (best_date - sowing_date).days
    if abs(days_ahead) <= 7:
        return (f"🗓 Now is the best window (projected {best_res.score:.0f}/100)", "badge-green")
    if days_ahead > 0:
        if days_ahead <= 35:
            return (f"🗓 Best date: {best_date.strftime('%d %b')} "
                    f"(in {days_ahead} days · projected {best_res.score:.0f})", "badge-amber")
        return (f"🗓 Best date: {best_date.strftime('%d %b %Y')} "
                f"(projected {best_res.score:.0f})", "badge-red")
    # best_date was earlier than chosen — window has just passed; next year
    return (f"🗓 Window already passed — next: {best_date.strftime('%d %b %Y')} "
            f"(projected {best_res.score:.0f})", "badge-red")


def _render_crop_card(res, crop: dict, place: Place, sowing_date: date,
                     irrigated: bool, idx: int, panel_key: str) -> None:
    with st.container(border=True):
        # Cards already sit two column-levels deep (page split → card grid),
        # which is Streamlit's nesting limit — the header must stack, not
        # open a third st.columns.
        st.markdown(f"<h3>{crop_name(crop)}</h3>", unsafe_allow_html=True)
        badges = [
            f'<span class="badge badge-earth">{crop["category"].title()}</span>',
            f'<span class="badge badge-blue">{int(sum(crop["growing_days"])/2)} d to harvest</span>',
            f'<span class="badge badge-amber">{crop["water_need_mm"][0]}–{crop["water_need_mm"][1]} mm water</span>',
        ]
        st.markdown(" ".join(badges), unsafe_allow_html=True)

        st.plotly_chart(score_ring(res.score, res.score_low, res.score_high),
                        use_container_width=True,
                        key=f"ring_{panel_key}_{res.crop_id}_{idx}")
        st.caption(f"Confidence: {res.score_low:.0f}–{res.score_high:.0f}")

        lo, hi = income_estimate_inr_per_acre(crop, irrigated=irrigated)
        if lo and hi:
            label = "Est. income (irrigated)" if irrigated and crop.get("irrigated_yield_q_per_acre") else "Est. income"
            st.caption(f"{label}: **₹{lo/1000:.0f}k – ₹{hi/1000:.0f}k**/acre")

        # Best sowing date
        try:
            best = best_sowing_date(place.lat, place.lng, res.crop_id, irrigated=irrigated)
        except Exception:
            best = None
        caption, badge_class = _next_window_caption(crop, sowing_date, best)
        if caption:
            st.markdown(f'<span class="badge {badge_class}">{caption}</span>',
                        unsafe_allow_html=True)

        # Pest warnings
        for w in res.pest_warnings:
            st.markdown(f'<div class="pest-warn">{w}</div>', unsafe_allow_html=True)

        # Mandi price strip
        try:
            price = latest_price_strip(res.crop_id, place.state)
        except Exception:
            price = None
        if price:
            st.caption(f"💰 Latest mandi price: **{price}**")

        # Variety recommendation
        varieties = recommend_varieties(res.crop_id, place.state)
        if varieties:
            v_names = " · ".join(f"**{v['name']}**" for v in varieties[:2])
            st.caption(f"🌱 Recommended varieties for {place.state or 'your area'}: {v_names}")

        # Schemes
        schemes = schemes_for(res.crop_id, place.state)[:4]
        if schemes:
            chips = " ".join(
                f'<a class="scheme-chip" href="{s["url"]}" target="_blank">{s["name"]}</a>'
                for s in schemes
            )
            st.markdown(f"<div style='margin-top:4px;'>🏛 {chips}</div>",
                        unsafe_allow_html=True)

        # Rotation hint
        partners = next_season_partners(res.crop_id)
        if partners:
            crops_by = crops_by_id()
            names = ", ".join(crops_by.get(p, {}).get("name_en", p) for p in partners[:3])
            st.caption(f"🔄 After {crop['name_en']}, try: {names}")

        # Why this score?
        with st.expander("Why this score?"):
            for k, v in res.components.items():
                st.progress(min(int(v), 100), text=f"{k}: {v:.0f}/100")
            if res.penalties:
                st.warning("Risk penalties: " + ", ".join(
                    f"{k} (-{v:.0f})" for k, v in res.penalties.items()
                ))
            for note in res.notes:
                st.caption("• " + note)
            if crop.get("notes"):
                st.caption(f"_{crop['notes']}_")

        # Variety + scheme details + feedback in a second expander
        with st.expander("Varieties · Schemes · Feedback"):
            if varieties:
                st.markdown("**Recommended varieties**")
                for v in varieties[:4]:
                    duration = f" · {v['duration_days']} days" if v.get("duration_days") else ""
                    st.markdown(f"- **{v['name']}**{duration} — {v.get('notes', '')}")
            if schemes:
                st.markdown("**Eligible schemes**")
                for s in schemes:
                    st.markdown(f"- [{s['name']}]({s['url']}) — {s['blurb']}")
            # Feedback
            fb_key = f"fb_{panel_key}_{res.crop_id}_{idx}_{sowing_date}"
            if st.button("👎 This recommendation didn't work for me",
                         key=fb_key, use_container_width=True):
                _append_feedback(place=place, sowing_date=sowing_date,
                                 crop_id=res.crop_id, score=res.score)
                st.success("Logged. Thank you!")


# ---- Recommendation panel ---------------------------------------------------

def _recommendation_panel(place: Place, sowing_date: date,
                          forecast: dict, normals: pd.DataFrame,
                          irrigated: bool, panel_key: str = "main") -> None:
    st.markdown(f"### 🌱 Best crops to sow around **{sowing_date.strftime('%d %b %Y')}**")
    if irrigated:
        st.caption("💧 Irrigation assumed — yields and water-fit reflect supplemental watering.")
    else:
        st.caption("☔ Rain-fed assumption — toggle irrigation in the sidebar to see irrigated yields.")

    results = rank_for_date(
        place.lat, place.lng, sowing_date,
        top_n=12, forecast_json=forecast, normals=normals,
        irrigated=irrigated,
    )
    crops = crops_by_id()
    if not results:
        st.warning("Could not score crops — live data unavailable. Try again in a few seconds.")
        return

    # Nearest mandi caption
    try:
        nm = nearest_mandi(place.lat, place.lng)
    except Exception:
        nm = None
    if nm:
        st.caption(f"🛒 Nearest mandi (OSM): **{nm['name']}**, {nm['distance_km']:.1f} km away.")

    chunks = [results[i : i + 3] for i in range(0, len(results), 3)]
    for chunk_idx, chunk in enumerate(chunks):
        cols = st.columns(len(chunk))
        for col_idx, (col, res) in enumerate(zip(cols, chunk)):
            crop = crops[res.crop_id]
            with col:
                _render_crop_card(res, crop, place, sowing_date, irrigated,
                                 idx=chunk_idx * 3 + col_idx, panel_key=panel_key)

    excluded = excluded_for_location(place.lat, place.lng, normals)
    if excluded:
        with st.expander(f"ℹ️ {len(excluded)} crops not suitable for this location"):
            for crop, reason in excluded:
                st.caption(f"• **{crop_name(crop)}** — {reason}")

    _market_panel(place=place, sowing_date=sowing_date, results=results)


# ---- AI farming intelligence ------------------------------------------------

def _build_crop_payload(results, regional, crops) -> list[dict]:
    out = []
    for r in results:
        crop = crops.get(r.crop_id, {})
        reg = regional.get(r.crop_id) if regional else None
        out.append({
            "id": r.crop_id,
            "name": crop.get("name_en", r.crop_id),
            "climate": r.score,
            "regional": reg.score if reg else None,
            "reason": reg.reason if reg else "",
            "sowing_months": crop.get("sowing_months", []),
        })
    return out


def _build_counter_payload(results, regional, crops) -> list[dict]:
    if not regional:
        return []
    top_3_ids = {r.crop_id for r in results[:3]}
    climate_high = sorted(results, key=lambda r: r.score, reverse=True)
    out: list[dict] = []
    for r in climate_high:
        if r.crop_id in top_3_ids:
            continue
        reg = regional.get(r.crop_id)
        if not reg:
            continue
        if r.score - reg.score < 30:
            continue
        crop = crops.get(r.crop_id, {})
        out.append({
            "id": r.crop_id,
            "name": crop.get("name_en", r.crop_id),
            "climate": r.score,
            "regional": reg.score,
            "reason": reg.reason,
        })
        if len(out) >= 3:
            break
    return out


def _market_panel(place: Place, sowing_date: date, results: list) -> None:
    crops = crops_by_id()
    season = current_season(sowing_date)
    terr = terrain_summary(place.lat, place.lng)
    regional = regional_rerank(
        state=place.state, district=place.district,
        sowing_date=sowing_date, season=season,
        climate_ranked=[(r.crop_id, r.score) for r in results],
        elevation_m=terr.get("elevation_m"),
        slope_pct=terr.get("slope_pct"),
    )
    top_crops_payload = _build_crop_payload(results[:3], regional, crops)
    counter_crops_payload = _build_counter_payload(results, regional, crops)
    bundle = fetch_market_signals(place.state, season, sowing_date,
                                  top_crops_payload, counter_crops_payload)
    summary = bundle.get("summary_md", "")
    links = bundle.get("links", [])
    label = "🌾 Farming intelligence (AI-synthesized) & marketplaces"
    with st.expander(label, expanded=False):
        if summary:
            st.markdown(summary)
        elif regional:
            st.caption("_AI farming-intelligence synthesis returned empty — marketplace directory below._")
        else:
            st.info(
                "💡 AI farming intelligence unavailable — configure `SARVAM_API_KEY` "
                "in Streamlit secrets to enable."
            )
        if links:
            st.markdown("**🛒 Buy & sell platforms**")
            for ml in links:
                st.markdown(f"- [{ml.name}]({ml.url}) — {ml.purpose}")


# ---- Share / later windows / map -------------------------------------------

def _share_panel(place: Place, sowing_date: date, forecast: dict,
                 normals: pd.DataFrame, irrigated: bool) -> None:
    st.markdown("### 📲 Share this plan")
    results = rank_for_date(
        place.lat, place.lng, sowing_date,
        top_n=12, forecast_json=forecast, normals=normals,
        irrigated=irrigated,
    )
    if not results:
        return
    top3 = results[:3]
    crops = crops_by_id()
    lines = [
        f"🌾 KrishiCast farm plan — {place.label}",
        f"📅 Sowing around {sowing_date.strftime('%d %b %Y')}"
        + (" · 💧 Irrigated" if irrigated else " · ☔ Rain-fed"),
        "",
        "Top crop recommendations:",
    ]
    for i, res in enumerate(top3, 1):
        crop = crops[res.crop_id]
        lo, hi = income_estimate_inr_per_acre(crop, irrigated=irrigated)
        lines += [
            f"{i}. {crop['name_en']}  —  Score: {res.score:.0f}/100",
            f"   {int(sum(crop['growing_days'])/2)} days · "
            f"Water need: {crop['water_need_mm'][0]}–{crop['water_need_mm'][1]} mm",
        ]
        if lo and hi:
            lines.append(f"   Est. income: ₹{lo/1000:.0f}k–₹{hi/1000:.0f}k/acre")
        for w in res.pest_warnings[:1]:
            lines.append(f"   {w}")
    lines += ["", "Generated by KrishiCast (krishicast.streamlit.app)"]
    st.code("\n".join(lines), language=None)
    st.caption("Tap the copy icon (top-right of the box) to copy, then paste into WhatsApp or SMS.")


def _later_windows(place: Place, forecast: dict, normals: pd.DataFrame,
                   irrigated: bool) -> None:
    st.markdown("### ⏭️ Better to sow later?")
    tabs = st.tabs(["+2 weeks", "+4 weeks", "+6 weeks", "+8 weeks"])
    for tab, weeks in zip(tabs, [2, 4, 6, 8]):
        with tab:
            future = date.today().fromordinal(date.today().toordinal() + weeks * 7)
            _recommendation_panel(place, future, forecast, normals, irrigated,
                                  panel_key=f"wk{weeks}")


def _mini_map(place: Place) -> None:
    st.markdown("### 🛰️ Your farm — satellite snapshot")
    layer = LAYERS["true_color_terra"]
    ndvi = LAYERS["ndvi_terra_8day"]
    fmap = folium.Map(
        location=[place.lat, place.lng],
        zoom_start=10,
        tiles="OpenStreetMap",
        control_scale=True,
    )
    folium.TileLayer(
        tiles=layer.tile_url(best_recent_day(layer)), attr=layer.attribution,
        name=layer.label, max_zoom=layer.max_zoom, overlay=False, control=True,
    ).add_to(fmap)
    folium.TileLayer(
        tiles=ndvi.tile_url(best_recent_day(ndvi)), attr=ndvi.attribution,
        name=ndvi.label, max_zoom=ndvi.max_zoom, overlay=True, control=True, opacity=0.6,
    ).add_to(fmap)
    folium.Marker([place.lat, place.lng], tooltip=place.label,
                  icon=folium.Icon(color="green", icon="leaf", prefix="fa")).add_to(fmap)
    folium.LayerControl(collapsed=False).add_to(fmap)
    out = st_folium(fmap, height=380, use_container_width=True,
                    returned_objects=["last_clicked"], key="home_mini_map")
    clicked = (out or {}).get("last_clicked")
    if clicked and clicked.get("lat") is not None and clicked.get("lng") is not None:
        new_lat, new_lng = float(clicked["lat"]), float(clicked["lng"])
        moved = abs(new_lat - place.lat) > 1e-4 or abs(new_lng - place.lng) > 1e-4
        if moved:
            st.session_state.place = place_from_coords(new_lat, new_lng)
            st.rerun()
    st.caption("Click the map to drop a pin. NDVI overlay shows vegetation health.")


# ---- Feedback log -----------------------------------------------------------

_FEEDBACK_PATH = DATA_DIR / "feedback.jsonl"


def _append_feedback(*, place: Place, sowing_date: date,
                     crop_id: str, score: float) -> None:
    entry = {
        "ts": date.today().isoformat(),
        "place": place.label,
        "lat": place.lat,
        "lng": place.lng,
        "sowing_date": sowing_date.isoformat(),
        "crop_id": crop_id,
        "score": score,
    }
    try:
        with _FEEDBACK_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        _logger.warning("Feedback write failed: %s", e)


# ---- Main -------------------------------------------------------------------

def main() -> None:
    _init_state()
    st.markdown(_CUSTOM_CSS, unsafe_allow_html=True)
    language_selector()

    place = _location_strip()

    # Ocean check — short-circuit if pin is in water
    if not has_soil(place.lat, place.lng):
        st.error(
            "🌊 No soil profile is available at this point — it appears to be open water, "
            "glacier, or otherwise non-arable terrain. Please drop your pin on land."
        )
        return

    sowing_date = st.date_input(
        "When do you plan to sow?",
        value=st.session_state.sowing_date,
        min_value=date.today(),
        key="sowing_date_input",
        help="We'll evaluate every crop for this date.",
    )
    st.session_state.sowing_date = sowing_date

    # Sidebar
    with st.sidebar:
        st.markdown("### 💧 Water")
        irrigated = st.toggle(
            "I have irrigation",
            value=st.session_state.irrigated,
            help="When on, supplemental irrigation is assumed to meet crop water needs. "
                 "Affects water-fit score and switches to irrigated yield bands.",
        )
        st.session_state.irrigated = irrigated

        st.markdown("---")
        st.markdown("### 📊 Data sources")
        st.caption(
            "Open-Meteo (weather, climate normals) · NASA POWER · SoilGrids 250 m (ISRIC) · "
            "OpenStreetMap Overpass · AgMarknet · Sarvam AI · Tavily · NASA GIBS."
        )

    _hero(place, sowing_date)

    try:
        forecast = fetch_forecast(place.lat, place.lng)
        live_ok = True
    except Exception:
        forecast = {}
        live_ok = False
        st.warning(
            "⏳ Live weather is rate-limited — running on climate normals only."
        )
    normals = fetch_climate_normals(place.lat, place.lng)

    if live_ok:
        _conditions_strip(place, forecast)

    st.divider()
    left, right = st.columns([3, 2])
    with left:
        _recommendation_panel(place, sowing_date, forecast, normals, irrigated)
    with right:
        _mini_map(place)
        if live_ok:
            st.markdown("#### Soil moisture (live · 4 depths)")
            st.plotly_chart(soil_moisture_profile(current_soil_profile(forecast)),
                            use_container_width=True)

    st.divider()
    _share_panel(place, sowing_date, forecast, normals, irrigated)

    st.divider()
    _later_windows(place, forecast, normals, irrigated)

    if live_ok:
        st.divider()
        st.markdown("### 📈 Weather forecast — next 14 days")
        daily = daily_forecast_df(forecast)
        if not daily.empty:
            c1, c2 = st.columns(2)
            c1.plotly_chart(forecast_temperature_chart(daily), use_container_width=True)
            c2.plotly_chart(rainfall_bar_chart(daily), use_container_width=True)

    st.divider()
    st.markdown("### 📜 Last 12 months — what actually fell here")
    archive = fetch_archive_year(place.lat, place.lng)
    if not archive.empty:
        monthly = (
            archive.assign(month=archive["time"].dt.to_period("M"))
            .groupby("month")
            .agg(rain_mm=("precipitation_sum", "sum"))
            .reset_index()
        )
        monthly["month_str"] = monthly["month"].astype(str)
        st.bar_chart(monthly.set_index("month_str")["rain_mm"], height=240)
        annual = monthly["rain_mm"].sum()
        st.caption(f"Annual rainfall at this point over the last 365 days: **{annual:.0f} mm**. "
                   f"Source: ERA5 reanalysis via Open-Meteo.")
    else:
        st.info("ERA5 archive temporarily unavailable for this point.")

    st.divider()
    st.markdown(
        '<div class="footer">Built on Open-Meteo · NASA POWER · SoilGrids · '
        'AgMarknet · OpenStreetMap · Sarvam · Tavily · NASA GIBS — '
        'every number is fetched, not invented.</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
