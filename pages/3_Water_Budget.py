"""Water Budget — rainfall vs ET₀ and per-crop irrigation requirement."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from agri.geo import Place
from agri.i18n import crop_name, language_selector
from agri.recommend import load_crops
from agri.viz import water_budget_chart
from agri.water import irrigation_need_mm, water_budget_series

st.set_page_config(page_title="Water Budget · KrishiCast", page_icon="💧", layout="wide")
language_selector()
st.title("💧 Water Budget")
st.markdown(
    "Daily rainfall in, evapotranspiration out — and the resulting balance. "
    "Use this to plan irrigation. Past data is actual, future is forecast then climate-normal."
)

if "place" not in st.session_state:
    st.warning("Pick a location on the home page first.")
    st.stop()

place: Place = st.session_state.place
st.caption(f"📍 {place.label}")

horizon = st.slider("Plan horizon (days)", 30, 180, 90, 15)

with st.spinner("Building water-budget…"):
    budget = water_budget_series(place.lat, place.lng, horizon_days=horizon)

if budget.empty:
    st.error("Water-budget data temporarily unavailable.")
    st.stop()

st.plotly_chart(water_budget_chart(budget), use_container_width=True)

tot_rain = float(budget["rain_mm"].sum())
tot_et0 = float(budget["et0_mm"].sum())
deficit = tot_et0 - tot_rain
c1, c2, c3 = st.columns(3)
c1.metric("Total rainfall (window)", f"{tot_rain:.0f} mm")
c2.metric("Total ET₀ (window)", f"{tot_et0:.0f} mm")
c3.metric(
    "Net balance",
    f"{tot_rain - tot_et0:+.0f} mm",
    delta=f"{'surplus' if deficit < 0 else 'deficit'}",
)

st.divider()
st.markdown("### 🚿 Irrigation requirement per crop")
st.caption(
    "We sum forecast/normal rainfall and ET₀ across each crop's typical growing duration "
    "starting from today, then estimate shortfall using a season-averaged crop coefficient."
)

crops = load_crops()
ids = st.multiselect(
    "Pick crops you're considering",
    options=[c["id"] for c in crops],
    default=["paddy", "wheat", "maize_kharif", "chickpea", "tomato"],
    format_func=lambda i: crop_name(next(c for c in crops if c["id"] == i)),
)

rows = []
for cid in ids:
    crop = next(c for c in crops if c["id"] == cid)
    gd = int(sum(crop["growing_days"]) / 2)
    window = budget.head(gd)
    res = irrigation_need_mm(
        rain_mm_during_growth=float(window["rain_mm"].sum()),
        et0_mm_during_growth=float(window["et0_mm"].sum()),
        crop=crop,
    )
    rows.append(
        {
            "Crop": crop_name(crop),
            "Days": gd,
            "Rain expected (mm)": res["rain_mm"],
            "Crop water demand (mm)": res["demand_mm"],
            "Shortfall (mm)": res["shortfall_mm"],
            "Excess (mm)": res["excess_mm"],
            "Irrigation (litres/acre)": int(res["litres_per_acre"]),
        }
    )

if rows:
    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, use_container_width=True)

st.caption(
    "ET₀ is FAO-56 Penman-Monteith from Open-Meteo. Crop water demand uses an averaged "
    "Kc; for precise scheduling use stage-wise Kc."
)
