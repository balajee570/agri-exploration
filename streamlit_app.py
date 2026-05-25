"""KrishiCast — pan-India crop recommender powered by live weather + satellite data."""

from __future__ import annotations

from datetime import date

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from agri.geo import Place, place_from_coords, search_india
from agri.gibs import LAYERS, best_recent_day
from agri.i18n import crop_name, current_lang, language_selector
from agri.market_signals import fetch_all as fetch_market_signals
from agri.recommend import (
    crops_by_id,
    income_estimate_inr_per_acre,
    rank_for_date,
)
from agri.regional_priors import rerank as regional_rerank
from agri.season import SEASON_LABELS, SEASON_LABELS_HI, current_season
from agri.soil import current_soil_profile, root_zone_moisture_pct, root_zone_temp_c
from agri.suitability import excluded_for_location
from agri.terrain import terrain_summary
from agri.viz import (
    forecast_temperature_chart,
    rainfall_bar_chart,
    soil_moisture_profile,
)
from agri.weather import (
    daily_forecast_df,
    fetch_archive_year,
    fetch_climate_normals,
    fetch_forecast,
    rainfall_last_n_days,
)

st.set_page_config(
    page_title="KrishiCast · Crop recommender for India",
    page_icon="🌾",
    layout="wide",
)


def _init_state() -> None:
    if "place" not in st.session_state:
        st.session_state.place = Place(
            name="Patna",
            lat=25.6,
            lng=85.1,
            state="Bihar",
            district="Patna",
            elevation_m=53,
        )
    if "sowing_date" not in st.session_state:
        st.session_state.sowing_date = date.today()


def _location_strip() -> Place:
    st.markdown("### 📍 Where is your farm?")
    q = st.text_input(
        "Search any town, district or village in India",
        key="search_input",
        placeholder="Patna, Hoshangabad village, Anantapur, Tezpur… (or click the map below)",
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
    st.caption("💡 Tip: click anywhere on the satellite map below to drop a pin on that location.")
    return place


def _conditions_strip(place: Place, forecast: dict) -> None:
    df = daily_forecast_df(forecast)
    current = forecast.get("current", {})
    rain_30 = rainfall_last_n_days(forecast, 30)
    sm = root_zone_moisture_pct(forecast)
    st_c = root_zone_temp_c(forecast)

    cols = st.columns(6)
    cols[0].metric("Temp now", f"{current.get('temperature_2m', '—')} °C")
    cols[1].metric("Humidity", f"{current.get('relative_humidity_2m', '—')} %")
    cols[2].metric("Wind", f"{current.get('wind_speed_10m', '—')} km/h")
    cols[3].metric("Root-zone soil moisture", f"{sm:.1f}%" if pd.notna(sm) else "—")
    cols[4].metric("Root-zone soil temp", f"{st_c:.1f} °C" if pd.notna(st_c) else "—")
    cols[5].metric("Rainfall (30 d)", f"{rain_30:.0f} mm" if pd.notna(rain_30) else "—")

    terr = terrain_summary(place.lat, place.lng)
    elev_txt = f"{terr['elevation_m']:.0f} m · " if terr.get("elevation_m") is not None else ""
    flood_warn = " — heavy rain may waterlog sensitive crops." if terr["drainage_class"] == "flat" else ""
    st.caption(
        f"⛰️ {elev_txt}Slope: **{terr['slope_pct']:.1f}%** ({terr['drainage_class']}){flood_warn}"
    )

    season = current_season(date.today())
    _slabels = SEASON_LABELS_HI if current_lang() == "hi" else SEASON_LABELS
    st.caption(
        f"📅 Today: **{date.today().strftime('%a, %d %b %Y')}** · "
        f"Season: **{_slabels[season]}** · "
        f"All readings live from Open-Meteo, no API key. "
        f"Forecast: ECMWF/GFS blend. Soil: land-surface model."
    )


def _recommendation_panel(place: Place, sowing_date: date, forecast: dict, normals: pd.DataFrame) -> None:
    st.markdown(f"### 🌱 Best crops to sow around **{sowing_date.strftime('%d %b %Y')}**")
    results = rank_for_date(
        place.lat, place.lng, sowing_date,
        top_n=12, forecast_json=forecast, normals=normals,
    )
    crops = crops_by_id()
    if not results:
        st.warning("Could not score crops — live data unavailable. Try again in a few seconds.")
        return

    chunks = [results[i : i + 3] for i in range(0, len(results), 3)]
    for chunk in chunks:
        cols = st.columns(len(chunk))
        for col, res in zip(cols, chunk):
            crop = crops[res.crop_id]
            badge = "🟢" if res.score >= 65 else "🟡" if res.score >= 45 else "🔴"
            lo, hi = income_estimate_inr_per_acre(crop)
            with col.container(border=True):
                st.markdown(f"#### {badge} {crop_name(crop)}")
                st.markdown(
                    f"<div style='font-size:2.1rem;font-weight:700;color:#2E7D32;line-height:1;'>"
                    f"{res.score:.0f}<span style='font-size:1rem;'> / 100</span></div>",
                    unsafe_allow_html=True,
                )
                st.caption(
                    f"{crop['category'].title()} · "
                    f"{int(sum(crop['growing_days'])/2)} days to harvest · "
                    f"Water need: {crop['water_need_mm'][0]}–{crop['water_need_mm'][1]} mm"
                )
                if lo and hi:
                    st.caption(f"Est. income: ₹{lo/1000:.0f}k – ₹{hi/1000:.0f}k per acre *(estimate)*")
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

    excluded = excluded_for_location(place.lat, place.lng, normals)
    if excluded:
        with st.expander(f"ℹ️ {len(excluded)} crops not suitable for this region"):
            for crop, reason in excluded:
                st.caption(f"• **{crop_name(crop)}** — {reason}")

    _market_panel(place=place, sowing_date=sowing_date, results=results)


def _build_crop_payload(results, regional, crops) -> list[dict]:
    """Convert top FitResults into the dict shape the synthesis prompt expects."""
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
        })
    return out


def _build_counter_payload(results, regional, crops) -> list[dict]:
    """Climate-high but AI-low (delta ≥ 30) crops outside the displayed top 3.

    These get the explicit ❌ counter-narrative section in the AI summary —
    the explanation a farmer needs for why NOT to follow the climate-only
    suggestion (Cotton in Bihar being the canonical example).
    """
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
        if r.score - reg.score < 30:  # only flag significant disagreements
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
    regional = regional_rerank(
        state=place.state, district=place.district,
        sowing_date=sowing_date, season=season,
        climate_ranked=[(r.crop_id, r.score) for r in results],
    )
    top_crops_payload = _build_crop_payload(results[:3], regional, crops)
    counter_crops_payload = _build_counter_payload(results, regional, crops)
    bundle = fetch_market_signals(place.state, season, sowing_date, top_crops_payload, counter_crops_payload)
    summary = bundle.get("summary_md", "")
    links = bundle.get("links", [])
    if not summary and not links:
        return
    label = "🌾 Farming intelligence (AI-synthesized) & marketplaces"
    with st.expander(label, expanded=False):
        if summary:
            st.markdown(summary)
        elif regional:
            st.caption(
                "_AI farming-intelligence synthesis returned empty — "
                "showing marketplace directory below._"
            )
        else:
            st.info(
                "💡 **AI farming intelligence unavailable** — configure `SARVAM_API_KEY` in "
                "Streamlit secrets to enable AI-driven regional reasoning and "
                "explicit counter-recommendations for poorly-fitting crops."
            )
        if links:
            st.markdown("**🛒 Buy & sell platforms**")
            for ml in links:
                st.markdown(f"- [{ml.name}]({ml.url}) — {ml.purpose}")


def _share_panel(place: Place, sowing_date: date, forecast: dict, normals: pd.DataFrame) -> None:
    st.markdown("### 📲 Share this plan")
    results = rank_for_date(
        place.lat, place.lng, sowing_date,
        top_n=12, forecast_json=forecast, normals=normals,
    )
    if not results:
        return
    top3 = results[:3]
    crops = crops_by_id()
    lines = [
        f"🌾 KrishiCast farm plan — {place.label}",
        f"📅 Sowing around {sowing_date.strftime('%d %b %Y')}",
        "",
        "Top crop recommendations:",
    ]
    for i, res in enumerate(top3, 1):
        crop = crops[res.crop_id]
        lo, hi = income_estimate_inr_per_acre(crop)
        lines += [
            f"{i}. {crop['name_en']} ({crop.get('name_hi', '')})  —  Score: {res.score:.0f}/100",
            f"   {int(sum(crop['growing_days'])/2)} days · Water need: {crop['water_need_mm'][0]}–{crop['water_need_mm'][1]} mm",
        ]
        if lo and hi:
            lines.append(f"   Est. income: ₹{lo/1000:.0f}k–₹{hi/1000:.0f}k/acre")
    lines += ["", "Generated by KrishiCast (krishicast.streamlit.app)"]
    st.code("\n".join(lines), language=None)
    st.caption("Tap the copy icon (top-right of the box) to copy, then paste into WhatsApp or SMS.")


def _later_windows(place: Place, forecast: dict, normals: pd.DataFrame) -> None:
    st.markdown("### ⏭️ Better to sow later?")
    tabs = st.tabs(["+2 weeks", "+4 weeks", "+6 weeks", "+8 weeks"])
    for tab, weeks in zip(tabs, [2, 4, 6, 8]):
        with tab:
            future = date.today().fromordinal(date.today().toordinal() + weeks * 7)
            _recommendation_panel(place, future, forecast, normals)


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
        tiles=layer.tile_url(best_recent_day(layer)),
        attr=layer.attribution,
        name=layer.label,
        max_zoom=layer.max_zoom,
        overlay=False,
        control=True,
    ).add_to(fmap)
    folium.TileLayer(
        tiles=ndvi.tile_url(best_recent_day(ndvi)),
        attr=ndvi.attribution,
        name=ndvi.label,
        max_zoom=ndvi.max_zoom,
        overlay=True,
        control=True,
        opacity=0.6,
    ).add_to(fmap)
    folium.Marker(
        [place.lat, place.lng],
        tooltip=place.label,
        icon=folium.Icon(color="green", icon="leaf", prefix="fa"),
    ).add_to(fmap)
    folium.LayerControl(collapsed=False).add_to(fmap)
    out = st_folium(
        fmap,
        height=380,
        use_container_width=True,
        returned_objects=["last_clicked"],
        key="home_mini_map",
    )
    clicked = (out or {}).get("last_clicked")
    if clicked and clicked.get("lat") is not None and clicked.get("lng") is not None:
        new_lat, new_lng = float(clicked["lat"]), float(clicked["lng"])
        moved = abs(new_lat - place.lat) > 1e-4 or abs(new_lng - place.lng) > 1e-4
        if moved:
            st.session_state.place = place_from_coords(new_lat, new_lng)
            st.rerun()
    st.caption(
        "Tiles from NASA EOSDIS GIBS (no key). Click anywhere to move your farm pin. "
        "Toggle NDVI to see vegetation health. Use the **Satellite View** page for full layer controls and farm-boundary drawing."
    )


def main() -> None:
    _init_state()
    language_selector()
    st.title("🌾 KrishiCast")
    st.markdown(
        "Pan-India crop recommendations powered by **live weather, multi-depth soil moisture, "
        "12-month rainfall history, climate normals, and NASA satellite layers** — every number is fetched, not invented."
    )

    place = _location_strip()
    sowing_date = st.date_input(
        "When do you plan to sow?",
        value=st.session_state.sowing_date,
        min_value=date.today(),
        key="sowing_date_input",
        help="We'll evaluate every crop for this date and the windows around it.",
    )
    st.session_state.sowing_date = sowing_date

    try:
        forecast = fetch_forecast(place.lat, place.lng)
        live_ok = True
    except Exception:  # noqa: BLE001
        forecast = {}
        live_ok = False
        st.warning(
            "⏳ **Live weather is rate-limited — running on climate normals only.** "
            "Open-Meteo's free tier is shared across all users of the app. "
            "Crop recommendations below are based on 30-year climate normals + "
            "ERA5 archive (no live forecast or soil moisture). Refresh in a minute "
            "or two for the full live experience."
        )
    normals = fetch_climate_normals(place.lat, place.lng)

    if live_ok:
        st.divider()
        _conditions_strip(place, forecast)

    st.divider()
    left, right = st.columns([3, 2])
    with left:
        _recommendation_panel(place, sowing_date, forecast, normals)
    with right:
        _mini_map(place)
        if live_ok:
            st.markdown("#### Soil profile (live)")
            st.plotly_chart(soil_moisture_profile(current_soil_profile(forecast)), use_container_width=True)

    st.divider()
    _share_panel(place, sowing_date, forecast, normals)

    st.divider()
    _later_windows(place, forecast, normals)

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
        st.caption(f"Annual rainfall at this point over the last 365 days: **{annual:.0f} mm**. Source: ERA5 reanalysis via Open-Meteo.")
    else:
        st.info("ERA5 archive temporarily unavailable for this point.")

    st.divider()
    st.caption(
        "Open the **Satellite View**, **Sowing Calendar**, **Water Budget**, and **Compare Crops** pages "
        "in the left sidebar for deeper planning tools."
    )


if __name__ == "__main__":
    main()
