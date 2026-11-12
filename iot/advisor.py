"""
Daily farm advice: how much to water and whether to fertilize today, from the
Alappuzha forecast and the selected crop.

Water uses the FAO-56 method from docs/CROP_CARE_GUIDE.md:
    crop water (mm/day) = ET0 x Kc,  1 mm on 1 m2 = 1 litre
minus the rain expected today. Fertilizer follows a simple feeding interval per
crop and is postponed when heavy rain would wash it off. These are rules of
thumb for a school farm, not a prescription.
"""

import time
from datetime import date

# FAO-56 crop coefficient (Kc) for the early, mid and late growth stages
KC = {
    "tomato": (0.6, 1.15, 0.8),
    "onion": (0.7, 1.05, 0.75),
    "paddy": (1.05, 1.2, 0.9),
    "chilli": (0.6, 1.05, 0.9),
    "potato": (0.5, 1.15, 0.75),
    "corn": (0.3, 1.2, 0.6),
    "arid": (0.25, 0.35, 0.25),
    "custom": (0.7, 1.0, 0.8),
}
STAGES = {"early": 0, "mid": 1, "late": 2}
STAGE_NAMES = {"early": "Young plants", "mid": "Flowering / fruiting", "late": "Near harvest"}

# Days between liquid feeds
FEED_DAYS = {"tomato": 7, "chilli": 7, "onion": 10, "potato": 10, "corn": 10,
             "paddy": 14, "arid": 30, "custom": 10}

HEAVY_RAIN_MM = 10.0    # fertilizer washes off
WET_DAY_MM = 5.0        # ...and so does a likely (>= 70 %) rain of this much
RAIN_CHANCE_POSTPONE = 70
DRIP_EFFICIENCY = 0.9


def _season_et0(month):
    """Typical Alappuzha ET0 (mm/day) when the forecast has none."""
    if 6 <= month <= 11:
        return 3.5   # monsoons
    if month == 12 or month <= 2:
        return 4.5   # winter
    return 5.5       # summer


def _effective_rain(mm):
    """Light showers mostly evaporate; about 80 % of the rest reaches the roots."""
    return max(0.0, 0.8 * mm - 1.0)


def _fmt_min(minutes):
    if minutes < 1:
        return f"{max(1, round(minutes * 60))} s"
    m = int(minutes)
    s = round((minutes - m) * 60)
    return f"{m} min {s} s" if s else f"{m} min"


def _next_dry_day(daily):
    for d in daily[1:]:
        if d.get("rain_mm", 0) < WET_DAY_MM and (d.get("rain_chance") or 0) < 60:
            return d["day"]
    return None


def daily_advice(crop, crop_name, stage, weather, soil, dry_cut, stop_cut, tank_level,
                 tank_alert_pct, field_m2, water_lpm, fert_lpm, feed_litres,
                 fert_last_date, water_s_today, fert_s_today, custom=None):
    today = date.today()
    days = weather.get("daily") if weather.get("ok") else None
    w0 = days[0] if days and days[0].get("date") == today.isoformat() else None

    et0 = w0.get("et0") if w0 else None
    et0_src = "forecast"
    if et0 is None:
        et0, et0_src = _season_et0(today.month), "season average"
    rain_mm = w0["rain_mm"] if w0 else 0.0
    rain_chance = (w0["rain_chance"] or 0) if w0 else 0
    tmax = w0["max"] if w0 else None

    kcs = custom["kc"] if custom else KC.get(crop, KC["custom"])
    kc = kcs[STAGES.get(stage, 1)]
    need_mm = et0 * kc
    rain_eff = _effective_rain(rain_mm)
    net_mm = max(0.0, need_mm - rain_eff)
    litres = net_mm * field_m2 / DRIP_EFFICIENCY
    minutes = litres / water_lpm if water_lpm > 0 else 0
    done_l = water_s_today / 60.0 * water_lpm

    # ---- water
    if net_mm < 0.5:
        water = {"action": "skip", "title": "No watering today",
                 "text": f"{rain_mm:.0f} mm of rain is expected, enough for the crop's {need_mm:.1f} mm."}
    else:
        title = f"About {litres:.0f} L today"
        text = f"≈ {_fmt_min(minutes)} of pump 1. Crop uses {need_mm:.1f} mm"
        text += f", rain gives {rain_eff:.1f} mm." if rain_eff > 0 else ", no useful rain expected."
        water = {"action": "light" if rain_eff > 0 else "water", "title": title, "text": text}
    if soil is not None and soil >= stop_cut:
        water["note"] = f"Soil is already wet ({soil:.0f} %), so pump 1 will wait."
    elif soil is not None and soil < dry_cut:
        water["note"] = f"Soil is dry ({soil:.0f} %): pump 1 starts in AUTO."
    water.update(litres=round(litres), minutes=round(minutes, 1), need_mm=round(need_mm, 1),
                 rain_mm=rain_mm, et0=round(et0, 1), et0_src=et0_src, kc=kc,
                 done_litres=round(done_l))

    # ---- fertilizer
    interval = custom["feed_days"] if custom else FEED_DAYS.get(crop, 10)
    since = None
    if fert_last_date:
        try:
            since = (today - date.fromisoformat(fert_last_date)).days
        except ValueError:
            pass
    fminutes = feed_litres / fert_lpm if fert_lpm > 0 else 0
    heavy = rain_mm >= HEAVY_RAIN_MM or (rain_chance >= RAIN_CHANCE_POSTPONE and rain_mm >= WET_DAY_MM)
    if since == 0:
        fert = {"action": "done", "title": "Fertilizer given today",
                "text": f"Next feed in {interval} days."}
    elif since is not None and since < interval:
        left = interval - since
        fert = {"action": "wait", "title": f"Not due ({left} day{'s' if left != 1 else ''} left)",
                "text": f"Last fed {since} day{'s' if since != 1 else ''} ago; {crop_name} is fed every {interval} days."}
    elif heavy:
        nxt = _next_dry_day(days or [])
        fert = {"action": "postpone", "title": "Postpone fertilizer",
                "text": f"Rain ({rain_mm:.0f} mm, {rain_chance}% chance) would wash it away."
                        + (f" Try {nxt}." if nxt else "")}
    else:
        fert = {"action": "apply", "title": f"Give {feed_litres:g} L today",
                "text": f"Run pump 2 for ≈ {_fmt_min(fminutes)}, early morning or after 4 pm."}
        if soil is not None and soil < dry_cut:
            fert["note"] = "Water first: fertilizer on dry soil can burn the roots."
    fert.update(litres=feed_litres, minutes=round(fminutes, 1), interval=interval, since=since,
                run_s=round(fminutes * 60), done_s=round(fert_s_today))

    # ---- extra tips
    tips = []
    if tank_level is not None and tank_level >= tank_alert_pct - 15 and rain_mm >= HEAVY_RAIN_MM:
        tips.append(f"Rain tank is {tank_level} % and {rain_mm:.0f} mm of rain is due: release some water today.")
    if tmax is not None and tmax >= 33:
        tips.append(f"Hot day ({tmax:.0f} °C): water early, mulch the beds.")
    if rain_mm >= HEAVY_RAIN_MM and crop != "paddy":
        tips.append("Check that beds drain well after the rain.")
    if crop == "paddy" and stage != "late":
        tips.append("Paddy: keep 2–5 cm of standing water in the field.")

    return {
        "date": today.isoformat(),
        "day": today.strftime("%a %d %b"),
        "crop": crop, "crop_name": crop_name,
        "stage": stage, "stage_name": STAGE_NAMES.get(stage, stage),
        "weather_ok": bool(w0),
        "weather": {"label": w0["label"], "icon": w0["icon"], "max": tmax, "min": w0["min"],
                    "rain_mm": rain_mm, "rain_chance": rain_chance} if w0 else None,
        "water": water, "fert": fert, "tips": tips,
        "updated": time.strftime("%H:%M"),
    }
