"""Sowing Calendar — 12-month suitability heatmap for every crop at this location."""

from __future__ import annotations

import streamlit as st

from agri.geo import Place
from agri.i18n import crop_name, language_selector
from agri.recommend import load_crops, monthly_suitability_matrix
from agri.viz import suitability_heatmap

st.set_page_config(page_title="Sowing Calendar · KrishiCast", page_icon="📅", layout="wide")
language_selector()
st.title("📅 Sowing Calendar")
st.markdown(
    "How well does each crop fit each month at **your** location? "
    "Cells are scored using live forecast for the next 14 days and climate normals beyond — same engine as the home page."
)

if "place" not in st.session_state:
    st.warning("Pick a location on the home page first.")
    st.stop()

place: Place = st.session_state.place
st.caption(f"📍 {place.label}")

crops = load_crops()
categories = sorted({c["category"] for c in crops})
chosen_cats = st.multiselect(
    "Filter by category",
    options=categories,
    default=categories,
    format_func=lambda c: c.title(),
)
min_score = st.slider("Hide crops whose best month scores below", 0, 90, 30, 5)

with st.spinner("Computing 12-month suitability — this can take 10-20 s the first time…"):
    df = monthly_suitability_matrix(place.lat, place.lng)

crop_meta = {c["id"]: c for c in crops}
df["category"] = df["crop_id"].map(lambda cid: crop_meta[cid]["category"])
df = df[df["category"].isin(chosen_cats)]

month_cols = [c for c in df.columns if c not in {"crop_id", "name_en", "category"}]
df["best"] = df[month_cols].max(axis=1)
df = df[df["best"] >= min_score].drop(columns=["best"]).sort_values("name_en")
df["name_en"] = df.apply(lambda row: crop_name(crop_meta[row["crop_id"]]), axis=1)

if df.empty:
    st.info("No crops match the current filters.")
    st.stop()

st.plotly_chart(suitability_heatmap(df.drop(columns=["category"])), use_container_width=True)

st.markdown("#### Top sowing picks for each upcoming month")
peaks = []
for month in month_cols:
    top = df.sort_values(month, ascending=False).head(3)
    peaks.append({
        "month": month,
        "1st": f"{top.iloc[0]['name_en']} ({top.iloc[0][month]:.0f})",
        "2nd": f"{top.iloc[1]['name_en']} ({top.iloc[1][month]:.0f})" if len(top) > 1 else "",
        "3rd": f"{top.iloc[2]['name_en']} ({top.iloc[2][month]:.0f})" if len(top) > 2 else "",
    })

import pandas as pd
st.dataframe(pd.DataFrame(peaks), use_container_width=True, hide_index=True)
