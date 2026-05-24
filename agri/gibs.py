"""NASA GIBS WMTS tile URL builders for folium TileLayer.

GIBS serves tiles publicly with no key. We point folium at the EPSG:3857
("GoogleMapsCompatible_Level9") matrix set so tiles align with web maps.

Reference: https://nasa-gibs.github.io/gibs-api-docs/
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

_BASE = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best"


@dataclass(frozen=True)
class GibsLayer:
    layer_id: str
    label: str
    tile_format: str
    matrix_set: str
    max_zoom: int
    attribution: str = "NASA EOSDIS GIBS"
    description: str = ""

    def tile_url(self, day: date) -> str:
        return (
            f"{_BASE}/{self.layer_id}/default/{day.isoformat()}/"
            f"{self.matrix_set}/{{z}}/{{y}}/{{x}}.{self.tile_format}"
        )


LAYERS: dict[str, GibsLayer] = {
    "true_color_terra": GibsLayer(
        layer_id="MODIS_Terra_CorrectedReflectance_TrueColor",
        label="True Color (Terra)",
        tile_format="jpg",
        matrix_set="GoogleMapsCompatible_Level9",
        max_zoom=9,
        description="Daily true-color imagery from MODIS Terra.",
    ),
    "true_color_aqua": GibsLayer(
        layer_id="MODIS_Aqua_CorrectedReflectance_TrueColor",
        label="True Color (Aqua)",
        tile_format="jpg",
        matrix_set="GoogleMapsCompatible_Level9",
        max_zoom=9,
        description="Daily true-color imagery from MODIS Aqua.",
    ),
    "ndvi_terra_8day": GibsLayer(
        layer_id="MODIS_Terra_NDVI_8Day",
        label="Vegetation Index (NDVI · 8-day)",
        tile_format="png",
        matrix_set="GoogleMapsCompatible_Level9",
        max_zoom=9,
        description="8-day composite vegetation health (MODIS Terra). Greener = denser, healthier canopy.",
    ),
    "lst_day": GibsLayer(
        layer_id="MODIS_Terra_Land_Surface_Temp_Day",
        label="Land Surface Temperature (Day)",
        tile_format="png",
        matrix_set="GoogleMapsCompatible_Level7",
        max_zoom=7,
        description="Daytime land-surface temperature. Useful for spotting heat-stress hot spots.",
    ),
    "smap_root_zone": GibsLayer(
        layer_id="SMAP_L4_Analyzed_Root_Zone_Soil_Moisture",
        label="Root-Zone Soil Moisture (SMAP)",
        tile_format="png",
        matrix_set="GoogleMapsCompatible_Level6",
        max_zoom=6,
        description="Deep soil moisture in the root zone (SMAP, ~9 km).",
    ),
    "precip_imerg": GibsLayer(
        layer_id="IMERG_Precipitation_Rate",
        label="Rainfall rate (IMERG)",
        tile_format="png",
        matrix_set="GoogleMapsCompatible_Level6",
        max_zoom=6,
        description="Near-real-time precipitation rate from NASA IMERG.",
    ),
}


def best_recent_day(layer: GibsLayer, today: date | None = None) -> date:
    """Most recent date the layer is likely to have imagery for.

    MODIS daily lays down with a 1-2 day latency; 8-day composites snap to 8-day
    cycle starts; SMAP root-zone has ~3 day latency. We back off conservatively.
    """
    today = today or date.today()
    if "8Day" in layer.layer_id:
        anchor = date(today.year, 1, 1)
        diff = (today - anchor).days
        cycle_start = anchor + timedelta(days=(diff // 8) * 8)
        if (today - cycle_start).days < 2:
            cycle_start -= timedelta(days=8)
        return cycle_start
    if "SMAP" in layer.layer_id:
        return today - timedelta(days=3)
    return today - timedelta(days=1)
