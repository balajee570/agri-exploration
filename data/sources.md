# Sources backing `data/crops.json`

Agronomic norms (temperature ranges, water requirements, growing days, soil pH, yield bands) in `crops.json` are aggregated from publicly available Indian and FAO agricultural extension publications. Treat numeric values as **typical bands**, not absolute thresholds — every crop has variety-level variation and microclimate effects.

## Primary references

- **ICAR (Indian Council of Agricultural Research)** crop production handbooks — https://icar.org.in
- **CRIDA (Central Research Institute for Dryland Agriculture)** contingency plans (district-wise) — http://www.crida.in
- **IIHR (Indian Institute of Horticultural Research)** package of practices — https://iihr.res.in
- **DAC&FW Agriculture Statistics at a Glance** (annual) — https://desagri.gov.in
- **FAO Crop Water Information (Irrigation & Drainage Paper 56)** for water-need bands and ET₀ — https://www.fao.org/land-water/databases-and-software/crop-information/en/
- **MSP / FRP** prices — Department of Agriculture & Farmers Welfare annual MSP notifications. Bands in `price_inr_per_q` reflect MSP for MSP-backed crops and approximate wholesale ranges for others.
- **State Agricultural Universities** — package of practices (e.g. PAU, TNAU, ANGRAU, BAU Sabour for Bihar).

## How to update

1. Edit the relevant record in `data/crops.json` with the new value.
2. Add a one-line note here citing the source.
3. Re-run `pytest tests/` to confirm scoring still behaves monotonically.

## Notes on price bands

Prices in `price_inr_per_q` are indicative wholesale bands (₹/quintal). For MSP-backed crops the lower bound is approximately the MSP. Real mandi prices fluctuate; integrating Agmarknet is v2 work.
