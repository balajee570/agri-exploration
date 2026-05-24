# 🌾 KrishiCast

**Pan-India crop recommender powered by live weather, multi-depth soil, climate normals, and NASA satellite layers.**

KrishiCast tells you *which crop to sow, when to sow it, and how much water you'll need* — for any farm location in India. Every number is fetched live; nothing is fabricated.

## What it does

- **Pan-India location** — GPS, search (any town/village/district), or click-on-map.
- **Live conditions** — temperature, humidity, wind, multi-depth soil moisture & temperature, last-30-day & 12-month rainfall.
- **Ranked crop recommendations** — ~60 Indian crops (cereals, pulses, oilseeds, vegetables, fruits, spices, fibre, fodder) scored by a transparent fit engine. Tap to see the per-component breakdown.
- **Sowing-window planner** — "sow now" vs "+2 / +4 / +6 / +8 weeks" tabs.
- **12-month sowing calendar** — heatmap of crop × month suitability at your point.
- **Water budget** — daily rainfall vs ET₀, cumulative balance, and per-crop irrigation requirement.
- **Satellite view** — NASA GIBS layers (true color, NDVI, land-surface temp, SMAP root-zone moisture) on an interactive map with farm-boundary drawing.
- **Compare crops** — pick up to 4 crops, see them side-by-side with a component radar.

## Data sources (all live, all key-free)

- **Open-Meteo** — forecast, ERA5 archive, climate normals, multi-depth soil, ET₀.
- **NASA POWER** — daily agromet + 40-year climatology.
- **NASA GIBS** — satellite imagery layers (MODIS, SMAP, IMERG).
- **BigDataCloud** — reverse geocoding (lat/lng → district/state).

No API keys required for any of the above.

## Run locally

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Open http://localhost:8501.

## Run tests

```bash
pytest tests/
```

## Deploy to Streamlit Community Cloud

1. Push this repo to GitHub (`balajee570/agri-exploration`).
2. Go to https://share.streamlit.io → "New app".
3. Select the repo, branch, and `streamlit_app.py` as the entrypoint.
4. Deploy. Subsequent pushes auto-redeploy.

## Architecture

```
streamlit_app.py             # Home — Recommend a crop
pages/
  1_Satellite_View.py        # GIBS layers + farm-boundary drawing
  2_Sowing_Calendar.py       # 12-month suitability heatmap
  3_Water_Budget.py          # rainfall vs ET₀ + irrigation
  4_Compare_Crops.py         # side-by-side picker
agri/
  geo.py                     # search, reverse geocode
  weather.py                 # Open-Meteo (forecast, archive, normals)
  soil.py                    # multi-depth soil extraction
  nasa_power.py              # NASA POWER client
  gibs.py                    # GIBS WMTS URL builders
  season.py                  # Kharif/Rabi/Zaid logic
  scoring.py                 # transparent fit engine
  recommend.py               # ranking + sowing-window scan
  water.py                   # water budget + irrigation
  cache.py                   # Streamlit caching
  viz.py                     # Plotly charts
data/
  crops.json                 # ~60 crops with agronomic norms
  sources.md                 # citations for norms
tests/
  test_scoring.py            # property tests on the scoring math
```

## Scoring engine — how recommendations are computed

For a crop `c`, location `L`, sowing date `d`:

```
fit = 100 * geometric_mean(
    temp_fit,                # piecewise linear over [Tmin, Topt_lo, Topt_hi, Tmax]
    water_fit,               # rainfall + irrigation vs crop water need band
    soil_moisture_fit,       # root-zone moisture vs preference
    soil_temp_fit,           # vs germination minimum
    season_fit,              # Kharif/Rabi/Zaid + month match
) - risk_penalties(heatwave, frost, drought, waterlogging)
```

Every input is a live measurement; weights are explicit and visible. See `agri/scoring.py`.

## Why Streamlit?

- **Server-side Python** dodges browser-CORS issues with NASA POWER & GIBS.
- **Scientific libraries** at hand (pandas, plotly, folium).
- **Free hosting** on Streamlit Community Cloud, auto-deploys from this repo.
- **Engine portable** — `agri/` is plain Python; if/when we outgrow Streamlit, it ports to FastAPI in a day.

## Roadmap (v2 candidates)

- Numeric per-point Sentinel-2 NDVI via Microsoft Planetary Computer STAC.
- Live Agmarknet mandi prices.
- Hindi UI toggle (data already has `name_hi`).
- PDF/WhatsApp share of a farm plan.
- Saved farms & multi-user accounts.
- Pest/disease risk model trained on agromet + observations.
