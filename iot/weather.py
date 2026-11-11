"""
Alappuzha weather from Open-Meteo (free, no API key).

A background thread refreshes the forecast every 15 minutes and caches the last
good result in config/weather_cache.json, so the dashboard still shows the most
recent forecast (marked stale) when the internet is down or after a reboot.
"""

import json
import time
import threading
import urllib.request
from pathlib import Path

LOCATION = "Alappuzha"
LATITUDE, LONGITUDE = 9.4981, 76.3388
CACHE_FILE = Path(__file__).resolve().parent / "config" / "weather_cache.json"
REFRESH_S = 15 * 60
RETRY_S = 60
STALE_S = 3 * 60 * 60

URL = (
    "https://api.open-meteo.com/v1/forecast"
    f"?latitude={LATITUDE}&longitude={LONGITUDE}&timezone=Asia%2FKolkata&forecast_days=5"
    "&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,"
    "wind_speed_10m,precipitation,is_day"
    "&hourly=temperature_2m,precipitation_probability,weather_code,is_day"
    "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
    "precipitation_sum,sunrise,sunset,et0_fao_evapotranspiration"
)

# WMO weather codes -> (label, icon name in icons.py)
_CODES = [
    ((0,), "Clear", "sun"),
    ((1, 2), "Partly cloudy", "cloudsun"),
    ((3,), "Overcast", "cloud"),
    ((45, 48), "Fog", "fog"),
    ((51, 53, 55, 56, 57), "Drizzle", "rain"),
    ((61, 66, 80), "Light rain", "rain"),
    ((63, 81), "Rain", "rain"),
    ((65, 67, 82), "Heavy rain", "rain"),
    ((71, 73, 75, 77, 85, 86), "Snow", "cloud"),
    ((95, 96, 99), "Thunderstorm", "storm"),
]


def describe(code, is_day=1):
    """Returns (label, icon) for a WMO weather code."""
    for codes, text, icon in _CODES:
        if code in codes:
            if icon == "sun" and not is_day:
                return "Clear", "moon"
            return text, icon
    return "--", "cloud"


def _parse(raw):
    cur = raw["current"]
    label, icon = describe(cur["weather_code"], cur.get("is_day", 1))
    out = {
        "location": LOCATION,
        "current": {
            "temp": cur["temperature_2m"],
            "feels": cur["apparent_temperature"],
            "humidity": cur["relative_humidity_2m"],
            "wind": cur["wind_speed_10m"],
            "precip": cur["precipitation"],
            "code": cur["weather_code"],
            "label": label,
            "icon": icon,
        },
        "hourly": [],
        "daily": [],
    }

    # Next 12 hours starting from the current hour
    h = raw["hourly"]
    now_hour = cur["time"][:13]
    start = next((i for i, t in enumerate(h["time"]) if t[:13] >= now_hour), 0)
    for i in range(start, min(start + 12, len(h["time"]))):
        lbl, ic = describe(h["weather_code"][i], h["is_day"][i])
        out["hourly"].append({
            "time": h["time"][i][11:16],
            "temp": h["temperature_2m"][i],
            "rain_chance": h["precipitation_probability"][i],
            "label": lbl,
            "icon": ic,
        })

    d = raw["daily"]
    for i in range(len(d["time"])):
        lbl, ic = describe(d["weather_code"][i])
        out["daily"].append({
            "date": d["time"][i],
            "day": time.strftime("%a", time.strptime(d["time"][i], "%Y-%m-%d")),
            "max": d["temperature_2m_max"][i],
            "min": d["temperature_2m_min"][i],
            "rain_chance": d["precipitation_probability_max"][i],
            "rain_mm": d["precipitation_sum"][i],
            "sunrise": d["sunrise"][i][11:16],
            "sunset": d["sunset"][i][11:16],
            "et0": (d.get("et0_fao_evapotranspiration") or [None] * len(d["time"]))[i],
            "label": lbl,
            "icon": ic,
        })
    return out


class WeatherService:
    def __init__(self):
        self.lock = threading.Lock()
        self.data = None
        self.updated = 0.0
        self.error = ""
        self._wake = threading.Event()
        self._load_cache()
        threading.Thread(target=self._loop, daemon=True).start()

    def _load_cache(self):
        try:
            cached = json.loads(CACHE_FILE.read_text())
            self.data, self.updated = cached["data"], float(cached["updated"])
        except Exception:
            pass

    def _fetch(self):
        req = urllib.request.Request(URL, headers={"User-Agent": "smart-farm"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = _parse(json.loads(resp.read().decode("utf-8")))
        with self.lock:
            self.data, self.updated, self.error = data, time.time(), ""
        try:
            CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            CACHE_FILE.write_text(json.dumps({"updated": self.updated, "data": data}))
        except Exception as e:
            print(f"[Weather] Could not write cache: {e}")

    def _loop(self):
        while True:
            try:
                self._fetch()
                wait = REFRESH_S
            except Exception as e:
                with self.lock:
                    self.error = str(e)[:80]
                print(f"[Weather] Fetch failed: {e}")
                wait = RETRY_S
            self._wake.wait(wait)
            self._wake.clear()

    def refresh(self):
        """Asks the background thread to fetch now."""
        self._wake.set()

    def get(self):
        with self.lock:
            if not self.data:
                return {"ok": False, "location": LOCATION, "error": self.error or "Loading…"}
            age = time.time() - self.updated
            return dict(self.data, ok=True, updated=time.strftime("%H:%M", time.localtime(self.updated)),
                        stale=age > STALE_S, error=self.error)


weather = WeatherService()
