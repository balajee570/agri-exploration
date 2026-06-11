"""Crop rotation planner — what to sow next season after your current crop."""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from agri.geo import Place
from agri.i18n import language_selector
from agri.recommend import crops_by_id, rank_for_date
from agri.rotation import next_season_partners
from agri.weather import fetch_climate_normals, fetch_forecast

st.set_page_config(page_title="Rotation Planner · KrishiCast", page_icon="🔄", layout="wide")
language_selector()
st.title("🔄 Crop Rotation Planner")
st.markdown(
    "Pick this season's crop. We'll suggest 3–4 follow-up crops for the next "
    "season at your location, with climate scores for the next likely sowing window."
)

if "place" not in st.session_state:
    st.warning("Pick a location on the home page first.")
    st.stop()

place: Place = st.session_state.place
st.caption(f"📍 {place.label}")
irrigated = st.session_state.get("irrigated", False)
st.caption(f"💧 Irrigation: {'ON' if irrigated else 'OFF'} (toggle on the home page)")

crops = crops_by_id()
options = sorted(crops.values(), key=lambda c: c["name_en"])
labels = [f"{c['name_en']} ({c['category']})" for c in options]
choice = st.selectbox("This season's crop", labels)
current = options[labels.index(choice)]
partners = next_season_partners(current["id"])

if not partners:
    st.info(f"No structured rotation partner data for {current['name_en']} yet. "
            "Perennials and tree crops typically don't follow a seasonal rotation.")
    st.stop()

st.markdown(f"### After **{current['name_en']}**, consider sowing:")

# Score each partner for the next obvious sowing date (next month after current's
# growing days end, capped at 1 year ahead).
today = date.today()
current_duration = int(sum(current["growing_days"]) / 2)
target_date = today + timedelta(days=max(30, current_duration))
st.caption(f"Scoring partners for sowing around **{target_date.strftime('%d %b %Y')}** "
           f"(after the ~{current_duration}-day {current['name_en']} cycle).")

forecast = fetch_forecast(place.lat, place.lng)
normals = fetch_climate_normals(place.lat, place.lng)

# Run rank_for_date once and pluck partner scores from it
results = rank_for_date(place.lat, place.lng, target_date,
                        top_n=60, forecast_json=forecast, normals=normals,
                        irrigated=irrigated)
by_id = {r.crop_id: r for r in results}

cols = st.columns(min(len(partners), 4))
for col, pid in zip(cols, partners):
    crop = crops.get(pid)
    if not crop:
        continue
    res = by_id.get(pid)
    with col.container(border=True):
        st.markdown(f"#### {crop['name_en']}")
        st.caption(crop.get("category", "").title() + " · " +
                   ", ".join(crop.get("seasons", [])))
        if res:
            badge = "🟢" if res.score >= 65 else "🟡" if res.score >= 45 else "🔴"
            st.metric("Climate score", f"{badge} {res.score:.0f}/100")
            sowing_lo, sowing_hi = crop["water_need_mm"]
            st.caption(f"Water need: {sowing_lo}–{sowing_hi} mm · "
                       f"{int(sum(crop['growing_days'])/2)} days")
        else:
            st.caption("Not climate-suitable at this location.")
        if crop.get("notes"):
            st.caption(f"_{crop['notes']}_")

st.caption(
    "Rotation logic encodes N-fixation (legume after cereal), pest-cycle breaks "
    "(family rotation), and heavy/light feeder pairing. Partners are ranked by "
    "agronomic fit, not displayed score."
)
