"""Transparent crop-fit scoring. Every weight is explicit; nothing fabricated."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from agri.season import season_for_month


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def temp_fit(t: float, t_min: float, t_opt_lo: float, t_opt_hi: float, t_max: float) -> float:
    """Piecewise-linear: 0 outside [t_min, t_max], 1 inside [t_opt_lo, t_opt_hi]."""
    if t is None or t != t:
        return 0.5
    if t <= t_min or t >= t_max:
        return 0.0
    if t_opt_lo <= t <= t_opt_hi:
        return 1.0
    if t < t_opt_lo:
        return _clip((t - t_min) / max(t_opt_lo - t_min, 0.1))
    return _clip((t_max - t) / max(t_max - t_opt_hi, 0.1))


def water_fit(available_mm: float, need_lo: float, need_hi: float, irrigation_mm: float = 0.0) -> float:
    """1 inside [need_lo, need_hi]; drought is fatal but excess decays gently.

    Excess water doesn't kill a crop the way drought does — drainage, terracing
    and the separate waterlogging penalty (score_crop) handle the flooding side.
    """
    if available_mm is None or available_mm != available_mm:
        return 0.5
    total = available_mm + irrigation_mm
    if need_lo <= total <= need_hi:
        return 1.0
    if total < need_lo:
        return _clip(total / max(need_lo, 1.0))
    excess = (total - need_hi) / max(need_hi, 1.0)
    return max(0.4, _clip(1.0 - 0.3 * excess))


MOISTURE_TARGETS = {"low": 22.0, "medium": 32.0, "high": 42.0}
WATERLOG_TOLERANCE_SCORE = {"low": 1.0, "medium": 0.6, "high": 0.25, "very_high": 0.0}

_PADDY_IDS = {"paddy", "paddy_boro"}
_CLAY_SOILS = {"clay", "clay_loam"}
_SANDY_SOILS = {"sandy", "sandy_loam", "loamy_sand"}


def infer_waterlogging_tolerance(crop: dict) -> str:
    soils = set(crop.get("soil_types") or [])
    pref = crop.get("soil_moisture_pref", "medium")
    if crop["id"] in _PADDY_IDS or (pref == "high" and soils & _CLAY_SOILS):
        return "very_high"
    if pref == "high":
        return "high"
    if pref == "low":
        return "low"
    return "medium"


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
    """Calendar distance to nearest sowing month. Steep off-window penalty.

    Used multiplicatively in score_crop (see below). The old 0.55/0.15 step
    function plus a geomean diluted timing to near-irrelevance — Mango sown
    a month before its window scored 88/100. This gates the score by timing.
    """
    if not sowing_months:
        return 0.5
    m = sowing_date.month
    if m in sowing_months:
        return 1.0
    distances = [min((m - sm) % 12, (sm - m) % 12) for sm in sowing_months]
    nearest = min(distances)
    if nearest == 1:
        return 0.40
    if nearest == 2:
        return 0.15
    return 0.05


def next_sowing_month(sowing_date: date, sowing_months: list[int]) -> int | None:
    """Forward-cyclic distance: returns the next month (1-12) in `sowing_months`."""
    if not sowing_months:
        return None
    m = sowing_date.month
    if m in sowing_months:
        return m
    forward = [((sm - m) % 12) or 12 for sm in sowing_months]
    return sowing_months[forward.index(min(forward))]


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
    slope_pct: float = 5.0
    aspect_compass: str | None = None
    mandi_distance_km: float | None = None
    forecast_horizon_days: int = 14
    growing_days: int = 90


@dataclass
class FitResult:
    crop_id: str
    score: float
    components: dict[str, float] = field(default_factory=dict)
    penalties: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    pest_warnings: list[str] = field(default_factory=list)
    score_low: float = 0.0
    score_high: float = 0.0


_HIGHLAND_PERENNIALS = {"tea", "coffee", "cardamom", "apple", "black_pepper",
                        "cinnamon", "nutmeg", "clove"}


def _aspect_bonus(crop_id: str, aspect: str | None) -> float:
    """N-facing slopes are cooler — small positive bias for highland perennials."""
    if not aspect or crop_id not in _HIGHLAND_PERENNIALS:
        return 0.0
    if aspect in ("N", "NE", "NW"):
        return 0.03
    if aspect in ("S", "SE", "SW"):
        return -0.03
    return 0.0


def _mandi_penalty(distance_km: float | None) -> float:
    """Long mandi distance hurts profitability — small penalty, capped."""
    if distance_km is None:
        return 0.0
    if distance_km <= 50:
        return 0.0
    if distance_km <= 100:
        return 0.05
    return 0.10


def _confidence_spread(growing_days: int, forecast_horizon_days: int) -> float:
    """Wider spread for sowing dates / growing windows beyond forecast horizon."""
    if growing_days <= forecast_horizon_days:
        return 0.03
    gap = growing_days - forecast_horizon_days
    return min(0.10, 0.03 + 0.0007 * gap)


def score_crop(crop: dict, inputs: FitInputs) -> FitResult:
    """Climate geomean × season gate, then risk penalties + aspect / mandi modifiers."""
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
    # Climate / soil / water geomean — these describe THIS place.
    climate_components = [tf, wf, smf, stf]
    floored = [max(c, 0.01) for c in climate_components]
    climate_base = 1.0
    for c in floored:
        climate_base *= c
    climate_base = climate_base ** (1 / len(floored))
    # Season is a calendar gate, not an average.
    base = climate_base * sf
    base = max(0.0, min(1.0, base + _aspect_bonus(crop["id"], inputs.aspect_compass)))

    penalties: dict[str, float] = {}
    if inputs.heat_days > 0 and inputs.tmax_window_c > t["max"] - 2:
        pen = min(0.25, 0.04 * inputs.heat_days)
        penalties["Heatwave risk"] = pen
    if inputs.frost_days > 0 and inputs.tmin_window_c < t["min"] + 2:
        pen = min(0.30, 0.06 * inputs.frost_days)
        penalties["Frost risk"] = pen
    if crop["drought_tolerance"] == "low" and inputs.expected_rain_mm < crop["water_need_mm"][0] * 0.4:
        penalties["Drought risk"] = 0.20
    tol = infer_waterlogging_tolerance(crop)
    sens = WATERLOG_TOLERANCE_SCORE.get(tol, 0.6)
    need_hi = crop["water_need_mm"][1]
    if inputs.slope_pct < 1.5 and inputs.expected_rain_mm > need_hi and sens > 0:
        flat_factor = _clip((1.5 - inputs.slope_pct) / 1.5)
        rain_excess = _clip((inputs.expected_rain_mm - need_hi) / max(need_hi, 1.0))
        pen = min(0.30, 0.30 * sens * flat_factor * (0.5 + 0.5 * rain_excess))
        if pen >= 0.02:
            penalties["Waterlogging risk"] = pen
    mandi_pen = _mandi_penalty(inputs.mandi_distance_km)
    if mandi_pen > 0:
        penalties["Mandi distance"] = mandi_pen

    final = max(0.0, base - sum(penalties.values()))

    notes: list[str] = []
    if sf < 1.0:
        nm = next_sowing_month(inputs.sowing_date, crop["sowing_months"])
        if nm is not None:
            label = date(2000, nm, 1).strftime("%B")
            notes.append(f"Off-window — next planting window starts {label}.")
    if wf < 0.5 and inputs.irrigation_mm == 0:
        gap = max(0, crop["water_need_mm"][0] - inputs.expected_rain_mm)
        if gap > 0:
            notes.append(f"Likely needs ~{gap:.0f} mm irrigation over the season.")
    if penalties:
        notes.append("Active risk: " + ", ".join(penalties.keys()) + ".")

    # Pest warnings consume only the sowing date + crop id — no extra fetches.
    pest_warnings: list[str] = []
    try:
        from agri.pests import pest_warnings_for
        pest_warnings = pest_warnings_for(
            crop_id=crop["id"], sowing_date=inputs.sowing_date,
            tmax_window_c=inputs.tmax_window_c, tmin_window_c=inputs.tmin_window_c,
            expected_rain_mm=inputs.expected_rain_mm,
        )
    except Exception:
        pest_warnings = []

    spread = _confidence_spread(inputs.growing_days, inputs.forecast_horizon_days)
    score_pct = round(final * 100, 1)
    return FitResult(
        crop_id=crop["id"],
        score=score_pct,
        components={k: round(v * 100, 1) for k, v in components.items()},
        penalties={k: round(v * 100, 1) for k, v in penalties.items()},
        notes=notes,
        pest_warnings=pest_warnings,
        score_low=round(max(0.0, final - spread) * 100, 1),
        score_high=round(min(1.0, final + spread) * 100, 1),
    )
