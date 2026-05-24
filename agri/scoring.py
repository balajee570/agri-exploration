"""Transparent crop-fit scoring. Every weight is explicit; nothing fabricated."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from agri.season import season_for_month


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def temp_fit(t: float, t_min: float, t_opt_lo: float, t_opt_hi: float, t_max: float) -> float:
    """Piecewise-linear: 0 outside [t_min, t_max], 1 inside [t_opt_lo, t_opt_hi]."""
    if t is None or t != t:  # NaN
        return 0.5
    if t <= t_min or t >= t_max:
        return 0.0
    if t_opt_lo <= t <= t_opt_hi:
        return 1.0
    if t < t_opt_lo:
        return _clip((t - t_min) / max(t_opt_lo - t_min, 0.1))
    return _clip((t_max - t) / max(t_max - t_opt_hi, 0.1))


def water_fit(available_mm: float, need_lo: float, need_hi: float, irrigation_mm: float = 0.0) -> float:
    """1 when in [need_lo, need_hi], decays to 0 at half/double those bounds."""
    if available_mm is None or available_mm != available_mm:
        return 0.5
    total = available_mm + irrigation_mm
    if need_lo <= total <= need_hi:
        return 1.0
    if total < need_lo:
        return _clip(total / max(need_lo, 1.0))
    excess = (total - need_hi) / max(need_hi, 1.0)
    return _clip(1.0 - excess)


MOISTURE_TARGETS = {"low": 22.0, "medium": 32.0, "high": 42.0}


def soil_moisture_fit(moisture_pct: float, pref: str) -> float:
    if moisture_pct is None or moisture_pct != moisture_pct:
        return 0.6
    target = MOISTURE_TARGETS.get(pref, 30.0)
    gap = abs(moisture_pct - target)
    return _clip(1.0 - gap / 25.0)


def soil_temp_fit(soil_t_c: float, germ_min_c: float) -> float:
    if soil_t_c is None or soil_t_c != soil_t_c:
        return 0.7
    if soil_t_c >= germ_min_c + 4:
        return 1.0
    if soil_t_c >= germ_min_c:
        return 0.85
    if soil_t_c >= germ_min_c - 3:
        return 0.55
    return 0.2


def season_fit(sowing_date: date, crop_seasons: list[str], sowing_months: list[int]) -> float:
    """How well does the proposed sowing month match the crop's accepted windows?"""
    m = sowing_date.month
    if m in sowing_months:
        return 1.0
    if season_for_month(m) in crop_seasons or "perennial" in crop_seasons:
        return 0.55
    return 0.15


@dataclass
class FitInputs:
    avg_temp_c: float
    tmin_window_c: float
    tmax_window_c: float
    expected_rain_mm: float
    soil_moisture_pct: float
    soil_temp_c: float
    sowing_date: date
    heat_days: int = 0
    frost_days: int = 0
    irrigation_mm: float = 0.0


@dataclass
class FitResult:
    crop_id: str
    score: float
    components: dict[str, float] = field(default_factory=dict)
    penalties: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def score_crop(crop: dict, inputs: FitInputs) -> FitResult:
    """Geometric mean of the five fit components, then risk penalties."""
    t = crop["temp_c"]
    tf = temp_fit(inputs.avg_temp_c, t["min"], t["opt_lo"], t["opt_hi"], t["max"])
    wf = water_fit(
        inputs.expected_rain_mm,
        crop["water_need_mm"][0],
        crop["water_need_mm"][1],
        inputs.irrigation_mm,
    )
    smf = soil_moisture_fit(inputs.soil_moisture_pct, crop["soil_moisture_pref"])
    stf = soil_temp_fit(inputs.soil_temp_c, crop["germination_temp_min_c"])
    sf = season_fit(inputs.sowing_date, crop["seasons"], crop["sowing_months"])

    components = {
        "Temperature fit": tf,
        "Water availability": wf,
        "Soil moisture": smf,
        "Germination temp": stf,
        "Season match": sf,
    }
    floored = [max(c, 0.01) for c in components.values()]
    base = 1.0
    for c in floored:
        base *= c
    base = base ** (1 / len(floored))

    penalties: dict[str, float] = {}
    if inputs.heat_days > 0 and inputs.tmax_window_c > t["max"] - 2:
        pen = min(0.25, 0.04 * inputs.heat_days)
        penalties["Heatwave risk"] = pen
    if inputs.frost_days > 0 and inputs.tmin_window_c < t["min"] + 2:
        pen = min(0.30, 0.06 * inputs.frost_days)
        penalties["Frost risk"] = pen
    if crop["drought_tolerance"] == "low" and inputs.expected_rain_mm < crop["water_need_mm"][0] * 0.4:
        penalties["Drought risk"] = 0.20
    if crop["soil_moisture_pref"] == "low" and inputs.expected_rain_mm > crop["water_need_mm"][1] * 1.5:
        penalties["Waterlogging risk"] = 0.20

    final = max(0.0, base - sum(penalties.values()))

    notes: list[str] = []
    if sf < 0.5:
        notes.append("Off-season sowing — fit reduced.")
    if wf < 0.5 and inputs.irrigation_mm == 0:
        gap = max(0, crop["water_need_mm"][0] - inputs.expected_rain_mm)
        if gap > 0:
            notes.append(f"Likely needs ~{gap:.0f} mm irrigation over the season.")
    if penalties:
        notes.append("Active risk: " + ", ".join(penalties.keys()) + ".")

    return FitResult(
        crop_id=crop["id"],
        score=round(final * 100, 1),
        components={k: round(v * 100, 1) for k, v in components.items()},
        penalties={k: round(v * 100, 1) for k, v in penalties.items()},
        notes=notes,
    )
