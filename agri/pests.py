"""Curated pest / disease risk rules for the top Indian crops.

Each rule maps a crop_id to a list of risk windows. Triggers are evaluated against
the same forecast statistics the scoring engine already computes (no extra fetches).
Output is human-readable warning strings appended to `FitResult.pest_warnings`.

Rules drawn from ICAR-IIPM and state agri-university advisories — when in doubt,
err on the side of warning the farmer.
"""

from __future__ import annotations

from datetime import date
from typing import Any

# Each rule: {name, months (1-12 list), trigger (callable), advice}
PEST_RULES: dict[str, list[dict[str, Any]]] = {
    "paddy": [
        {"name": "Rice blast",
         "months": [7, 8, 9],
         "trigger": lambda tmin, tmax, rain: 22 <= (tmin + tmax) / 2 <= 28 and rain > 200,
         "advice": "Use blast-resistant variety; avoid excess nitrogen at tillering."},
        {"name": "Brown plant hopper",
         "months": [8, 9, 10],
         "trigger": lambda tmin, tmax, rain: tmin > 22 and rain > 150,
         "advice": "Alternate wetting/drying; monitor with light traps."},
        {"name": "Stem borer",
         "months": [7, 8, 9],
         "trigger": lambda tmin, tmax, rain: 24 <= tmin <= 30,
         "advice": "Pheromone traps; clip yellow leaves; resistant variety if available."},
    ],
    "paddy_boro": [
        {"name": "Rice blast",
         "months": [2, 3, 4],
         "trigger": lambda tmin, tmax, rain: 20 <= (tmin + tmax) / 2 <= 28,
         "advice": "Resistant variety; balanced nitrogen."},
    ],
    "wheat": [
        {"name": "Yellow rust",
         "months": [12, 1, 2, 3],
         "trigger": lambda tmin, tmax, rain: 5 <= tmin <= 15 and rain > 50,
         "advice": "Scout from late tillering; use rust-resistant varieties (HD 3086, DBW 187)."},
        {"name": "Aphid attack",
         "months": [1, 2, 3],
         "trigger": lambda tmin, tmax, rain: 12 <= tmax <= 22,
         "advice": "Ladybird beetles help; spray neem if economic threshold crossed."},
        {"name": "Karnal bunt",
         "months": [2, 3],
         "trigger": lambda tmin, tmax, rain: tmin < 15 and rain > 30,
         "advice": "Avoid late sowing; cool-humid weather at flowering raises risk."},
    ],
    "maize_kharif": [
        {"name": "Fall armyworm",
         "months": [6, 7, 8, 9],
         "trigger": lambda tmin, tmax, rain: tmin > 18,
         "advice": "Scout whorl daily; pheromone traps; spray Bt formulations at threshold."},
        {"name": "Stem borer",
         "months": [7, 8],
         "trigger": lambda tmin, tmax, rain: tmax > 28,
         "advice": "Trichogramma releases; resistant hybrids."},
    ],
    "maize_rabi": [
        {"name": "Fall armyworm",
         "months": [11, 12, 1, 2],
         "trigger": lambda tmin, tmax, rain: tmin > 15,
         "advice": "Pheromone traps; scout regularly."},
    ],
    "cotton": [
        {"name": "Pink bollworm",
         "months": [9, 10, 11],
         "trigger": lambda tmin, tmax, rain: tmin > 20 and rain < 100,
         "advice": "Pheromone traps; Bt cotton confirmation; uproot stubble post-harvest."},
        {"name": "Whitefly",
         "months": [7, 8, 9, 10],
         "trigger": lambda tmin, tmax, rain: tmax > 30 and rain < 80,
         "advice": "Yellow sticky traps; avoid synthetic pyrethroids early."},
        {"name": "Cotton leaf curl virus",
         "months": [7, 8, 9],
         "trigger": lambda tmin, tmax, rain: tmax > 32,
         "advice": "Plant resistant hybrids; rogue infected plants early."},
    ],
    "soybean": [
        {"name": "Stem fly",
         "months": [7, 8],
         "trigger": lambda tmin, tmax, rain: tmin > 22 and rain > 100,
         "advice": "Treat seed with thiamethoxam; remove infested plants."},
        {"name": "Girdle beetle",
         "months": [8, 9],
         "trigger": lambda tmin, tmax, rain: rain > 200,
         "advice": "Hand-collect adults; spray quinalphos at threshold."},
    ],
    "chickpea": [
        {"name": "Pod borer (Helicoverpa)",
         "months": [12, 1, 2],
         "trigger": lambda tmin, tmax, rain: 8 <= tmin <= 18,
         "advice": "Pheromone traps from flowering; NPV spray at egg stage."},
        {"name": "Fusarium wilt",
         "months": [11, 12, 1],
         "trigger": lambda tmin, tmax, rain: tmax > 25,
         "advice": "Sow resistant variety (JG 11, JG 14); avoid waterlogging."},
    ],
    "pigeon_pea": [
        {"name": "Pod borer",
         "months": [10, 11, 12],
         "trigger": lambda tmin, tmax, rain: tmin > 15,
         "advice": "NPV at egg stage; trap crop marigold border."},
    ],
    "groundnut": [
        {"name": "Leaf miner",
         "months": [8, 9, 10],
         "trigger": lambda tmin, tmax, rain: tmax > 30,
         "advice": "Need-based dimethoate spray; avoid blanket sprays."},
        {"name": "Tikka leaf spot",
         "months": [8, 9],
         "trigger": lambda tmin, tmax, rain: rain > 150,
         "advice": "Carbendazim spray; resistant variety (TMV 7, GG 20)."},
    ],
    "mustard": [
        {"name": "Aphid",
         "months": [12, 1, 2],
         "trigger": lambda tmin, tmax, rain: 5 <= tmin <= 15,
         "advice": "Yellow sticky traps; conserve ladybirds; spray at 25-30 aphids/plant."},
        {"name": "Sclerotinia rot",
         "months": [1, 2],
         "trigger": lambda tmin, tmax, rain: rain > 30,
         "advice": "Avoid dense planting; carbendazim if humidity persists."},
    ],
    "sugarcane": [
        {"name": "Early shoot borer",
         "months": [3, 4, 5],
         "trigger": lambda tmin, tmax, rain: tmax > 32,
         "advice": "Light traps; carbofuran at planting; trichogramma releases."},
        {"name": "Red rot",
         "months": [6, 7, 8],
         "trigger": lambda tmin, tmax, rain: rain > 250,
         "advice": "Disease-free setts; resistant variety; ratoon ban for 2 years if infected."},
    ],
    "tomato": [
        {"name": "Early blight",
         "months": [8, 9, 10, 11],
         "trigger": lambda tmin, tmax, rain: rain > 100,
         "advice": "Mancozeb spray; stake plants to improve airflow."},
        {"name": "Fruit borer",
         "months": [9, 10, 11, 12],
         "trigger": lambda tmin, tmax, rain: tmin > 18,
         "advice": "Pheromone traps; NPV; hand-pick larvae."},
    ],
    "potato": [
        {"name": "Late blight",
         "months": [11, 12, 1, 2],
         "trigger": lambda tmin, tmax, rain: 10 <= tmin <= 15 and rain > 30,
         "advice": "Prophylactic mancozeb at canopy closure; resistant cultivar."},
    ],
    "onion_rabi": [
        {"name": "Purple blotch",
         "months": [1, 2, 3],
         "trigger": lambda tmin, tmax, rain: rain > 30,
         "advice": "Mancozeb + sticker; avoid overhead irrigation."},
        {"name": "Thrips",
         "months": [12, 1, 2, 3],
         "trigger": lambda tmin, tmax, rain: tmax > 22,
         "advice": "Blue sticky traps; fipronil at threshold."},
    ],
    "onion_kharif": [
        {"name": "Purple blotch",
         "months": [8, 9, 10],
         "trigger": lambda tmin, tmax, rain: rain > 100,
         "advice": "Mancozeb spray; avoid waterlogging."},
    ],
    "chilli": [
        {"name": "Thrips",
         "months": [10, 11, 12, 1],
         "trigger": lambda tmin, tmax, rain: tmax > 25,
         "advice": "Blue traps; spinosad spray; mulch to deter."},
        {"name": "Fruit rot",
         "months": [8, 9, 10],
         "trigger": lambda tmin, tmax, rain: rain > 150,
         "advice": "Drip irrigation; copper oxychloride spray."},
    ],
    "banana": [
        {"name": "Panama wilt",
         "months": list(range(1, 13)),
         "trigger": lambda tmin, tmax, rain: tmax > 28,
         "advice": "Use TC plants; sanitize tools; avoid susceptible cultivar (Rasthali) in infected fields."},
        {"name": "Sigatoka leaf spot",
         "months": [7, 8, 9, 10],
         "trigger": lambda tmin, tmax, rain: rain > 200,
         "advice": "Remove infected leaves; spray propiconazole."},
    ],
    "mango": [
        {"name": "Mango hopper",
         "months": [2, 3, 4],
         "trigger": lambda tmin, tmax, rain: tmax > 30,
         "advice": "Imidacloprid spray at flowering; sticky bands."},
        {"name": "Powdery mildew",
         "months": [2, 3],
         "trigger": lambda tmin, tmax, rain: tmin < 18,
         "advice": "Wettable sulfur at panicle emergence."},
    ],
    "tea": [
        {"name": "Helopeltis (mosquito bug)",
         "months": [4, 5, 6, 7],
         "trigger": lambda tmin, tmax, rain: rain > 200,
         "advice": "Quinalphos spray; conserve spider predators."},
    ],
    "coffee": [
        {"name": "Coffee berry borer",
         "months": [10, 11, 12],
         "trigger": lambda tmin, tmax, rain: tmin > 18,
         "advice": "Strip-pick ripe cherries; sanitize fallen berries; Beauveria spray."},
        {"name": "White stem borer",
         "months": [4, 5],
         "trigger": lambda tmin, tmax, rain: tmax > 30,
         "advice": "Tracing & scraping; lime swab; shade management."},
    ],
    "cardamom": [
        {"name": "Thrips",
         "months": [3, 4, 5],
         "trigger": lambda tmin, tmax, rain: tmax > 28,
         "advice": "Sticky traps; spinosad; remove dry leaf debris."},
    ],
    "black_pepper": [
        {"name": "Quick wilt (Phytophthora)",
         "months": [6, 7, 8, 9],
         "trigger": lambda tmin, tmax, rain: rain > 300,
         "advice": "Improve drainage; potassium phosphonate drench; resistant cultivar (Panniyur 5)."},
    ],
    "watermelon": [
        {"name": "Fruit fly",
         "months": [3, 4, 5],
         "trigger": lambda tmin, tmax, rain: tmax > 32,
         "advice": "Cue lure traps; bait sprays; sanitation."},
    ],
}


def pest_warnings_for(
    crop_id: str, sowing_date: date,
    tmax_window_c: float, tmin_window_c: float, expected_rain_mm: float,
) -> list[str]:
    """Returns short human-readable warning strings for active risks in the window."""
    rules = PEST_RULES.get(crop_id) or []
    out: list[str] = []
    m = sowing_date.month
    for rule in rules:
        if m not in rule["months"]:
            continue
        try:
            triggered = rule["trigger"](tmin_window_c, tmax_window_c, expected_rain_mm)
        except Exception:
            triggered = False
        if not triggered:
            continue
        out.append(f"⚠️ {rule['name']} risk — {rule['advice']}")
    return out
