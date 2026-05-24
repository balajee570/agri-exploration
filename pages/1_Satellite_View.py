"""Satellite View — NASA GIBS layers with date scrubbing and farm-boundary drawing."""

from __future__ import annotations

from datetime import date, timedelta

import folium
import streamlit as st
from folium.plugins import Draw, MeasureControl
from streamlit_folium import st_folium

from agri.geo import Place, place_from_coords
from agri.gibs import LAYERS, best_recent_day

st.set_page_config(page_title="Satellite View · KrishiCast", page_icon="🛰️", layout="wide")
st.title("🛰️ Satellite View")
st.markdown(
    "All layers come from **NASA EOSDIS GIBS** — public, key-free, updated daily. "
    "Toggle layers in the top-right map control. Draw a polygon to mark your farm and read its area."
)

if "place" not in st.session_state:
    st.warning("Pick a location on the home page first.")
    st.stop()

place: Place = st.session_state.place
st.caption(f"📍 {place.label} · {place.lat:.4f}, {place.lng:.4f}")

today = date.today()
c1, c2 = st.columns([2, 5])
with c1:
    chosen_day = st.date_input(
        "Imagery date",
        value=today - timedelta(days=1),
        min_value=date(2015, 1, 1),
        max_value=today,
        help="MODIS daily layers have 1-2 day latency; 8-day NDVI composites snap to 8-day cycles.",
    )
    layer_options = {key: lyr.label for key, lyr in LAYERS.items()}
    selected_base = st.selectbox(
        "Base layer",
        options=list(layer_options.keys()),
        format_func=lambda k: layer_options[k],
        index=list(layer_options.keys()).index("true_color_terra"),
    )
    overlays = st.multiselect(
        "Overlay layers",
        options=[k for k in layer_options if k != selected_base],
        default=["ndvi_terra_8day"],
        format_func=lambda k: layer_options[k],
    )
    overlay_opacity = st.slider("Overlay opacity", 0.1, 1.0, 0.6, 0.05)

with c2:
    base = LAYERS[selected_base]
    fmap = folium.Map(
        location=[place.lat, place.lng],
        zoom_start=11,
        tiles="OpenStreetMap",
        control_scale=True,
    )
    folium.TileLayer(
        tiles=base.tile_url(best_recent_day(base, chosen_day)),
        attr=base.attribution,
        name=base.label,
        max_zoom=base.max_zoom,
        overlay=False,
        control=True,
    ).add_to(fmap)
    for key in overlays:
        lyr = LAYERS[key]
        folium.TileLayer(
            tiles=lyr.tile_url(best_recent_day(lyr, chosen_day)),
            attr=lyr.attribution,
            name=lyr.label,
            max_zoom=lyr.max_zoom,
            overlay=True,
            control=True,
            opacity=overlay_opacity,
        ).add_to(fmap)
    folium.Marker(
        [place.lat, place.lng],
        tooltip=place.label,
        icon=folium.Icon(color="green", icon="leaf", prefix="fa"),
    ).add_to(fmap)
    Draw(
        draw_options={
            "polyline": False,
            "polygon": {"shapeOptions": {"color": "#2E7D32", "weight": 3}},
            "rectangle": True,
            "circle": False,
            "marker": False,
            "circlemarker": False,
        },
        edit_options={"edit": True, "remove": True},
    ).add_to(fmap)
    MeasureControl(primary_length_unit="meters", primary_area_unit="hectares").add_to(fmap)
    folium.LayerControl(collapsed=False).add_to(fmap)
    drawn = st_folium(
        fmap,
        height=620,
        use_container_width=True,
        returned_objects=["all_drawings", "last_clicked"],
        key="sat_view_map",
    )
    clicked = (drawn or {}).get("last_clicked")
    if clicked and clicked.get("lat") is not None and clicked.get("lng") is not None:
        new_lat, new_lng = float(clicked["lat"]), float(clicked["lng"])
        if abs(new_lat - place.lat) > 1e-4 or abs(new_lng - place.lng) > 1e-4:
            st.session_state.place = place_from_coords(new_lat, new_lng)
            st.rerun()

st.divider()
st.markdown("#### Drawn area")

def _polygon_area_m2(coords: list[list[float]]) -> float:
    if len(coords) < 3:
        return 0.0
    import math
    R = 6378137.0
    total = 0.0
    for i in range(len(coords)):
        x1, y1 = coords[i]
        x2, y2 = coords[(i + 1) % len(coords)]
        total += math.radians(x2 - x1) * (2 + math.sin(math.radians(y1)) + math.sin(math.radians(y2)))
    return abs(total * R * R / 2.0)

if drawn and drawn.get("all_drawings"):
    for shape in drawn["all_drawings"]:
        geom = shape.get("geometry", {})
        if geom.get("type") == "Polygon":
            ring = geom["coordinates"][0]
            area_m2 = _polygon_area_m2(ring)
            acres = area_m2 / 4046.86
            hectares = area_m2 / 10_000
            st.success(
                f"Farm area: **{acres:.2f} acres** ({hectares:.2f} ha · {area_m2:,.0f} m²) — "
                f"draw a new polygon to update."
            )
            break
else:
    st.info("Draw a polygon around your farm using the pencil tool on the map (top-left).")

with st.expander("ℹ️ What each layer shows"):
    for key, lyr in LAYERS.items():
        st.markdown(f"**{lyr.label}** — {lyr.description}")
