"""Compare Crops — pick 2-4 crops, see side-by-side fit, water, income, risks."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from agri.geo import Place
from agri.i18n import crop_name, language_selector
from agri.recommend import (
    build_inputs_for_window,
    crops_by_id,
    income_estimate_inr_per_acre,
    load_crops,
)
from agri.scoring import score_crop
from agri.viz import compare_radar
from agri.weather import fetch_climate_normals, fetch_forecast

st.set_page_config(page_title="Compare Crops · KrishiCast", page_icon="⚖️", layout="wide")
language_selector()
st.title("⚖️ Compare crops")
st.markdown("Pick up to 4 crops and we'll score them side-by-side for your location & sowing date.")

if "place" not in st.session_state:
    st.warning("Pick a location on the home page first.")
    st.stop()

place: Place = st.session_state.place
st.caption(f"📍 {place.label}")

sowing = st.date_input("Sowing date", value=st.session_state.get("sowing_date", date.today()))

crops = load_crops()
picked_ids = st.multiselect(
    "Crops to compare",
    options=[c["id"] for c in crops],
    default=["paddy", "maize_kharif", "soybean", "pigeon_pea"],
    max_selections=4,
    format_func=lambda i: crop_name(next(c for c in crops if c["id"] == i)),
)

if not picked_ids:
    st.info("Select at least one crop.")
    st.stop()

with st.spinner("Scoring…"):
    forecast = fetch_forecast(place.lat, place.lng)
    normals = fetch_climate_normals(place.lat, place.lng)
    cmap = crops_by_id()
    cards = []
    radar_data = {}
    for cid in picked_ids:
        crop = cmap[cid]
        gd = int(sum(crop["growing_days"]) / 2)
        inputs = build_inputs_for_window(place.lat, place.lng, sowing, gd, forecast, normals)
        result = score_crop(crop, inputs)
        lo, hi = income_estimate_inr_per_acre(crop)
        cards.append((crop, result, (lo, hi), gd))
        radar_data[crop_name(crop)] = result.components

cols = st.columns(len(cards))
for col, (crop, res, (lo, hi), gd) in zip(cols, cards):
    with col.container(border=True):
        st.markdown(f"### {crop_name(crop)}")
        st.markdown(
            f"<div style='font-size:2.4rem;font-weight:700;color:#2E7D32;line-height:1;'>"
            f"{res.score:.0f}<span style='font-size:1rem;'> / 100</span></div>",
            unsafe_allow_html=True,
        )
        st.caption(f"{crop['category'].title()} · {gd} days · "
                   f"Water need {crop['water_need_mm'][0]}–{crop['water_need_mm'][1]} mm")
        if lo and hi:
            st.metric("Est. income (₹/acre)", f"₹{lo/1000:.0f}k – ₹{hi/1000:.0f}k", help="Estimate from yield × price bands.")
        for k, v in res.components.items():
            st.progress(min(int(v), 100), text=f"{k}: {v:.0f}")
        if res.penalties:
            st.warning("Risks: " + ", ".join(f"{k}" for k in res.penalties))
        if crop.get("notes"):
            st.caption(crop["notes"])

st.divider()
st.markdown("### 🎯 Component comparison")
st.plotly_chart(compare_radar(radar_data), use_container_width=True)

st.divider()
st.markdown("### 📋 Side-by-side detail")
detail_rows = []
for crop, res, (lo, hi), gd in cards:
    detail_rows.append(
        {
            "Crop": crop_name(crop),
            "Fit score": res.score,
            "Days to harvest": gd,
            "Temp range (°C)": f"{crop['temp_c']['min']}–{crop['temp_c']['max']}",
            "Water need (mm)": f"{crop['water_need_mm'][0]}–{crop['water_need_mm'][1]}",
            "Drought tolerance": crop["drought_tolerance"],
            "Yield (q/acre)": f"{crop['yield_q_per_acre'][0]}–{crop['yield_q_per_acre'][1]}",
            "Price (₹/q)": f"{crop['price_inr_per_q'][0]}–{crop['price_inr_per_q'][1]}",
            "Est. income (₹/acre)": f"₹{lo:,}–₹{hi:,}",
        }
    )
st.dataframe(pd.DataFrame(detail_rows), hide_index=True, use_container_width=True)
