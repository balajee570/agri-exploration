"""AgMarknet wholesale price snapshot for a crop in a state.

AgMarknet's public dashboard exposes a JSON endpoint that returns recent modal
prices per commodity per state. Free, no key, occasional schema drift — we
fail soft and silently omit the price line when anything goes wrong.

The crop ids in `data/crops.json` are mapped to AgMarknet commodity names with
a small lookup so we stay decoupled from upstream slug changes.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from agri.cache import cached

_logger = logging.getLogger(__name__)
_TTL = 24 * 60 * 60  # 24 h

_URL = "https://agmarknet.gov.in/SearchCmmMkt.aspx"

# Map our crop_id → AgMarknet commodity name
COMMODITY_NAME: dict[str, str] = {
    "paddy": "Paddy(Dhan)(Common)",
    "paddy_boro": "Paddy(Dhan)(Common)",
    "wheat": "Wheat",
    "maize_kharif": "Maize",
    "maize_rabi": "Maize",
    "sorghum": "Jowar(Sorghum)",
    "pearl_millet": "Bajra(Pearl Millet/Cumbu)",
    "finger_millet": "Ragi (Finger Millet)",
    "barley": "Barley(Jau)",
    "chickpea": "Bengal Gram(Gram)(Whole)",
    "pigeon_pea": "Arhar (Tur/Red Gram)(Whole)",
    "green_gram": "Green Gram (Moong)(Whole)",
    "black_gram": "Black Gram (Urd Beans)(Whole)",
    "lentil": "Masur Dal",
    "soybean": "Soyabean",
    "groundnut": "Groundnut",
    "mustard": "Mustard",
    "sesame": "Sesamum(Sesame,Gingelly,Til)",
    "sunflower": "Sunflower",
    "cotton": "Cotton",
    "jute": "Jute",
    "sugarcane": "Sugarcane",
    "potato": "Potato",
    "onion_rabi": "Onion",
    "onion_kharif": "Onion",
    "tomato": "Tomato",
    "brinjal": "Brinjal",
    "okra": "Bhindi(Ladies Finger)",
    "cabbage": "Cabbage",
    "cauliflower": "Cauliflower",
    "chilli": "Green Chilli",
    "turmeric": "Turmeric",
    "ginger": "Ginger(Green)",
    "garlic": "Garlic",
    "coriander": "Coriander(Leaves)",
    "banana": "Banana",
    "mango": "Mango",
    "papaya": "Papaya",
    "guava": "Guava",
    "watermelon": "Water Melon",
    "muskmelon": "Karbuja(Musk Melon)",
}


@cached(_TTL)
def latest_price_strip(crop_id: str, state: str | None) -> str | None:
    """Returns a one-line price strip like '₹2 350/q at Lucknow (12 May)' or None.

    Uses the public agmarknet HTML search; parses the modal-price column.
    Silent failure on any error — the UI just omits the strip.
    """
    if not state:
        return None
    commodity = COMMODITY_NAME.get(crop_id)
    if not commodity:
        return None
    params = {
        "Tx_Commodity": commodity,
        "Tx_State": state,
        "Tx_District": "",
        "Tx_Market": "",
        "DateFrom": "",
        "DateTo": "",
        "Fr_Date": "",
        "To_Date": "",
        "Tx_Trend": "0",
        "Tx_CommodityHead": commodity,
        "Tx_StateHead": state,
        "Tx_DistrictHead": "",
        "Tx_MarketHead": "",
    }
    try:
        with httpx.Client(timeout=12.0, follow_redirects=True) as client:
            r = client.get(_URL, params=params,
                           headers={"User-Agent": "Mozilla/5.0 (KrishiCast / open-source)"})
            r.raise_for_status()
            html = r.text
    except Exception as e:
        _logger.info("AgMarknet fetch failed (%s, %s): %s", crop_id, state, e)
        return None

    # Best-effort extraction: AgMarknet returns an HTML table with a "Modal Price (Rs./Quintal)"
    # column. We grab the first numeric row.
    import re
    # Try a row pattern: <td>market</td>...<td>modal_price</td><td>date</td>
    rows = re.findall(
        r"<tr[^>]*>\s*<td[^>]*>\s*\d+\s*</td>\s*<td[^>]*>([^<]+)</td>"  # market
        r".*?<td[^>]*>\s*([\d,]+)\s*</td>"  # modal price
        r"\s*<td[^>]*>([^<]+)</td>\s*</tr>",  # date
        html, re.S
    )
    if not rows:
        return None
    market, modal_price, date_str = rows[0]
    modal_price = modal_price.replace(",", "").strip()
    if not modal_price.isdigit():
        return None
    return f"₹{int(modal_price):,}/q at {market.strip()} ({date_str.strip()})"
