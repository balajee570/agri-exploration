"""Government-scheme eligibility links for top recommendations.

All schemes are central or pan-India unless `states` is set. Crops list which
specific crops are MSP-backed or PMFBY-covered.
"""

from __future__ import annotations

from typing import TypedDict


class Scheme(TypedDict):
    name: str
    url: str
    blurb: str


_MSP_CROPS = {
    "paddy", "paddy_boro", "wheat", "maize_kharif", "maize_rabi", "sorghum",
    "pearl_millet", "finger_millet", "barley", "chickpea", "pigeon_pea",
    "green_gram", "black_gram", "lentil", "soybean", "groundnut", "mustard",
    "sesame", "sunflower", "safflower", "cotton", "jute",
}

_PMFBY_CROPS = _MSP_CROPS | {
    "potato", "onion_rabi", "onion_kharif", "tomato", "sugarcane", "tobacco",
    "turmeric", "ginger", "chilli", "garlic", "coriander", "cumin",
}


_UNIVERSAL = [
    Scheme(
        name="PM-KISAN",
        url="https://pmkisan.gov.in",
        blurb="₹6 000/year income support for landholding farmers.",
    ),
    Scheme(
        name="eNAM",
        url="https://enam.gov.in",
        blurb="Sell produce on the National Agriculture Market.",
    ),
    Scheme(
        name="Soil Health Card",
        url="https://soilhealth.dac.gov.in",
        blurb="Free soil testing and fertiliser advice.",
    ),
    Scheme(
        name="Kisan Credit Card",
        url="https://www.myscheme.gov.in/schemes/kcc",
        blurb="Short-term crop loan at 4% effective interest.",
    ),
]

_STATE_PORTALS: dict[str, Scheme] = {
    "Karnataka": Scheme(name="Karnataka Raitha Samparka Kendra",
                        url="https://raitamitra.karnataka.gov.in",
                        blurb="State farmer-services portal."),
    "Maharashtra": Scheme(name="MahaDBT", url="https://mahadbtmahait.gov.in",
                          blurb="State direct-benefit transfers."),
    "Tamil Nadu": Scheme(name="TN Uzhavan", url="https://tnreginet.gov.in",
                         blurb="Farmer registration and benefits."),
    "Punjab": Scheme(name="Punjab Agri Portal",
                     url="https://agripb.gov.in",
                     blurb="State agriculture services."),
    "Haryana": Scheme(name="Meri Fasal Mera Byora",
                      url="https://fasal.haryana.gov.in",
                      blurb="Crop registration for procurement."),
    "Uttar Pradesh": Scheme(name="UP Agriculture Department",
                            url="https://upagriculture.com",
                            blurb="State scheme portal."),
    "Madhya Pradesh": Scheme(name="MP Farmer Welfare",
                             url="https://mpkrishi.mp.gov.in",
                             blurb="State scheme portal."),
    "Gujarat": Scheme(name="iKhedut", url="https://ikhedut.gujarat.gov.in",
                      blurb="Single-window scheme application."),
    "Telangana": Scheme(name="Rythu Bandhu",
                        url="https://rythubandhu.telangana.gov.in",
                        blurb="₹5 000/acre/season investment support."),
    "Andhra Pradesh": Scheme(name="YSR Rythu Bharosa",
                             url="https://ysrrythubharosa.ap.gov.in",
                             blurb="Income support + insurance."),
    "Kerala": Scheme(name="Aashraya Farmer Welfare",
                     url="https://keralaagriculture.gov.in",
                     blurb="State farmer welfare."),
    "Odisha": Scheme(name="KALIA",
                     url="https://kalia.odisha.gov.in",
                     blurb="Livelihood and income augmentation."),
    "West Bengal": Scheme(name="Krishak Bandhu",
                          url="https://krishakbandhu.net",
                          blurb="State income support."),
    "Rajasthan": Scheme(name="Rajasthan Kisan Portal",
                        url="https://rajkisan.rajasthan.gov.in",
                        blurb="State scheme portal."),
    "Bihar": Scheme(name="DBT Agriculture Bihar",
                    url="https://dbtagriculture.bihar.gov.in",
                    blurb="Direct-benefit transfers."),
}


def schemes_for(crop_id: str, state: str | None) -> list[Scheme]:
    """All applicable schemes for this crop + state."""
    out: list[Scheme] = []
    if crop_id in _MSP_CROPS:
        out.append(Scheme(
            name="MSP procurement",
            url="https://farmer.gov.in/mspstatements.aspx",
            blurb="This crop is on the central Minimum Support Price list.",
        ))
    if crop_id in _PMFBY_CROPS:
        out.append(Scheme(
            name="PMFBY (crop insurance)",
            url="https://pmfby.gov.in",
            blurb="Eligible for Pradhan Mantri Fasal Bima Yojana.",
        ))
    out.extend(_UNIVERSAL)
    if state and state in _STATE_PORTALS:
        out.append(_STATE_PORTALS[state])
    return out


def is_msp_crop(crop_id: str) -> bool:
    return crop_id in _MSP_CROPS


def is_pmfby_crop(crop_id: str) -> bool:
    return crop_id in _PMFBY_CROPS
