"""Crop rotation planner — suggests follow-up crops for the next season.

Rotation principles encoded:
- Legumes follow cereals (N fixation)
- Cereals follow legumes / cucurbits
- Different families break pest / disease cycles
- Light feeders follow heavy feeders
"""

from __future__ import annotations

# Each value is an ordered list of preferred follow-up crop_ids for the next season.
ROTATION_PARTNERS: dict[str, list[str]] = {
    "paddy": ["wheat", "lentil", "mustard", "chickpea", "berseem", "potato"],
    "paddy_boro": ["green_gram", "sesame", "groundnut", "soybean"],
    "wheat": ["green_gram", "soybean", "maize_kharif", "cotton", "pigeon_pea"],
    "maize_kharif": ["wheat", "chickpea", "mustard", "lentil", "potato"],
    "maize_rabi": ["green_gram", "sesame", "fodder_maize"],
    "sorghum": ["chickpea", "wheat", "safflower", "linseed"],
    "pearl_millet": ["mustard", "chickpea", "wheat"],
    "finger_millet": ["chickpea", "field_pea", "wheat", "mustard"],
    "barley": ["green_gram", "sesame", "soybean"],
    "chickpea": ["paddy", "cotton", "maize_kharif", "sorghum", "pearl_millet"],
    "pigeon_pea": ["wheat", "barley", "mustard", "sorghum"],
    "green_gram": ["wheat", "mustard", "cotton", "maize_rabi"],
    "black_gram": ["wheat", "mustard", "maize_rabi"],
    "lentil": ["maize_kharif", "soybean", "paddy", "cotton"],
    "field_pea": ["maize_kharif", "groundnut", "soybean"],
    "soybean": ["wheat", "chickpea", "potato", "mustard"],
    "groundnut": ["wheat", "mustard", "chickpea", "sorghum"],
    "mustard": ["green_gram", "sesame", "paddy", "cotton"],
    "sesame": ["wheat", "mustard", "chickpea"],
    "sunflower": ["wheat", "mustard", "chickpea"],
    "safflower": ["pearl_millet", "sorghum"],
    "linseed": ["maize_kharif", "green_gram"],
    "cotton": ["chickpea", "wheat", "groundnut", "sorghum", "pigeon_pea"],
    "jute": ["paddy", "lentil", "mustard"],
    "sugarcane": ["wheat", "mustard", "berseem"],  # ratoon, then break
    "tobacco": ["green_gram", "sorghum"],
    "potato": ["green_gram", "groundnut", "soybean", "okra"],
    "onion_rabi": ["green_gram", "okra", "tomato"],
    "onion_kharif": ["wheat", "chickpea", "mustard"],
    "tomato": ["onion_rabi", "garlic", "cabbage", "green_gram"],
    "brinjal": ["wheat", "mustard", "green_gram"],
    "okra": ["chickpea", "potato", "mustard"],
    "cabbage": ["green_gram", "tomato", "onion_kharif"],
    "cauliflower": ["green_gram", "tomato", "okra"],
    "chilli": ["onion_rabi", "garlic", "okra"],
    "turmeric": ["maize_rabi", "chickpea", "groundnut"],
    "ginger": ["maize_rabi", "groundnut"],
    "coriander": ["green_gram", "okra"],
    "cumin": ["pearl_millet", "sesame"],
    "fenugreek": ["okra", "tomato"],
    "garlic": ["green_gram", "tomato", "okra"],
    "watermelon": ["maize_kharif", "cotton", "chickpea"],
    "muskmelon": ["maize_kharif", "cotton", "chickpea"],
    "cucumber": ["wheat", "chickpea", "tomato"],
    "bottle_gourd": ["wheat", "mustard"],
    "carrot": ["green_gram", "okra"],
    "beetroot": ["green_gram", "okra"],
    "strawberry": ["maize_kharif", "groundnut"],
    "marigold": ["wheat", "chickpea"],
    # Perennials — rotation N/A; suggest intercrop partners instead.
    "tea": [],
    "coffee": ["black_pepper", "cardamom"],
    "cardamom": ["black_pepper"],
    "black_pepper": ["cardamom", "coffee"],
    "nutmeg": ["cinnamon", "clove"],
    "clove": ["nutmeg", "cinnamon"],
    "cinnamon": ["clove", "nutmeg"],
    "passion_fruit": [],
    "apple": [],
    "mango": [],
    "banana": ["turmeric", "ginger"],
    "papaya": ["maize_kharif", "groundnut"],
    "guava": [],
    "citrus": [],
    "pomegranate": [],
    "rose": [],
    "jasmine": [],
    "fodder_maize": ["berseem", "wheat"],
    "berseem": ["maize_kharif", "cotton"],
}


def next_season_partners(crop_id: str) -> list[str]:
    """Returns up to 4 ordered next-season crop ids. Empty for crops with no fit."""
    return ROTATION_PARTNERS.get(crop_id, [])[:4]
