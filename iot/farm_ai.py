"""
Farm AI: Google Gemini suggestions for the Smart Farm.

- Daily brief: what to do today and the next few days (water more / less,
  fertilizer, pests, tank), from the forecast, sensors, crop and settings.
- Crop profile: moisture cutoffs, Kc and feeding interval for any crop name,
  which can be applied as the Custom crop.
- Settings check: suggested changes to cutoffs, tank alert, feed size and stage.
- Ask: free questions about the farm.

Calls the Gemini REST API with urllib (no extra packages) and asks for JSON
output. The API key is read from config/.env (GEMINI_API_KEY, git-ignored) and
can be saved there from the web dashboard. Every call runs in a background
thread; the UIs poll task state. AI output never switches a pump: only the
settings a person taps "Apply" on are changed, and those are range-checked by
hardware_manager.
"""

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent / "config" / ".env"
CACHE_FILE = Path(__file__).resolve().parent / "config" / "ai_cache.json"
API = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-2.5-flash"
BRIEF_MAX_AGE_S = 3 * 60 * 60   # automatic brief refresh
TIMEOUT_S = 60

SYSTEM = (
    "You are the farm assistant for a small community smart farm in Alappuzha, "
    "Kerala, India (hot, humid, two monsoons, acidic sandy or clayey soils). Pump 1 waters the field: in AUTO "
    "it starts below the dry cutoff and stops at the stop cutoff (soil moisture %). Pump 2 applies liquid "
    "fertilizer by hand. A rainwater tank is watched by an ultrasonic sensor. "
    "Give practical, specific advice a student can follow today. Use the forecast, sensors and settings "
    "you are given; do not invent readings. Follow Kerala Agricultural University (KAU) practice; prefer "
    "organic and bio-control options; when you name a fertilizer or chemical give a safe dose and safety "
    "note, and never suggest banned pesticides. Keep every text short: titles under 40 characters, "
    "sentences under 140 characters. Plain text only, no markdown. Never mention the name of the school."
)

# ---------------------------------------------------------------- schemas
_STR = {"type": "STRING"}
_NUM = {"type": "NUMBER"}

BRIEF_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "headline": {"type": "STRING", "description": "One line, under 60 characters, e.g. 'Rainy till Thu: water less'"},
        "summary": {"type": "STRING", "description": "2 short sentences: the situation and the main advice"},
        "water": {"type": "STRING", "description": "Watering plan for today, one sentence"},
        "water_change_pct": {"type": "INTEGER", "description": "Suggested change to today's watering vs normal, -100 to 50"},
        "fertilizer": {"type": "STRING", "description": "Fertilizer plan for today, one sentence"},
        "actions": {
            "type": "ARRAY", "maxItems": 5,
            "items": {"type": "OBJECT", "properties": {
                "title": _STR, "detail": _STR,
                "when": {"type": "STRING", "enum": ["today", "tomorrow", "this week"]},
                "kind": {"type": "STRING", "enum": ["water", "fertilizer", "pest", "tank", "harvest", "general"]},
            }, "required": ["title", "detail", "when", "kind"]},
        },
        "reminders": {
            "type": "ARRAY", "maxItems": 4,
            "items": {"type": "OBJECT", "properties": {"day": _STR, "text": _STR}, "required": ["day", "text"]},
        },
        "warnings": {"type": "ARRAY", "maxItems": 3, "items": _STR},
    },
    "required": ["headline", "summary", "water", "water_change_pct", "fertilizer", "actions", "reminders", "warnings"],
}

CROP_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "name": {"type": "STRING", "description": "Crop name, short"},
        "dry_cutoff": {"type": "NUMBER", "description": "Soil moisture % below which to water, 10-80"},
        "stop_cutoff": {"type": "NUMBER", "description": "Soil moisture % at which to stop watering, 20-95"},
        "kc_early": _NUM, "kc_mid": _NUM, "kc_late": _NUM,
        "feed_days": {"type": "INTEGER", "description": "Days between liquid feeds"},
        "season": {"type": "STRING", "description": "Best planting months in Kerala"},
        "water_need": {"type": "STRING", "description": "Water need, e.g. '500-700 mm per season'"},
        "feeding": {"type": "STRING", "description": "Fertilizer plan, one or two sentences"},
        "pests": {"type": "STRING", "description": "Main pests and a bio-control, one sentence"},
        "tips": {"type": "STRING", "description": "One practical tip"},
    },
    "required": ["name", "dry_cutoff", "stop_cutoff", "kc_early", "kc_mid", "kc_late", "feed_days",
                 "season", "water_need", "feeding", "pests", "tips"],
}

PARAM_KEYS = ["dry_cutoff", "stop_cutoff", "tank_alert_pct", "feed_litres", "fert_manual_max_min", "crop_stage"]
PARAMS_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "STRING", "description": "One sentence overall verdict"},
        "suggestions": {
            "type": "ARRAY", "maxItems": 4,
            "items": {"type": "OBJECT", "properties": {
                "key": {"type": "STRING", "enum": PARAM_KEYS},
                "value": {"type": "STRING", "description": "New value: a number, or early/mid/late for crop_stage"},
                "reason": _STR,
            }, "required": ["key", "value", "reason"]},
        },
    },
    "required": ["summary", "suggestions"],
}

ASK_SCHEMA = {
    "type": "OBJECT",
    "properties": {"answer": {"type": "STRING", "description": "Answer in at most 4 short sentences"}},
    "required": ["answer"],
}

PARAM_NAMES = {"dry_cutoff": "Pump 1 starts below", "stop_cutoff": "Pump 1 stops at",
               "tank_alert_pct": "Rain tank alert", "feed_litres": "Fertilizer per feed",
               "fert_manual_max_min": "Pump 2 auto-off", "crop_stage": "Crop stage"}


# ------------------------------------------------------------------ key
def read_env():
    out = {}
    try:
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return out


def save_env_value(key, value):
    """Sets KEY=value in config/.env, keeping every other line."""
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    lines = [ln for ln in lines if not re.match(rf"\s*{re.escape(key)}\s*=", ln)]
    if value:
        if not any(ln.strip() == "# Farm AI (Google Gemini)" for ln in lines):
            lines += ["", "# Farm AI (Google Gemini)"]
        lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n")
    try:
        os.chmod(ENV_FILE, 0o600)
    except OSError:
        pass


class AIError(Exception):
    pass


# --------------------------------------------------------------- client
class GeminiClient:
    def __init__(self):
        self.model_override = None   # set when the default model is not available

    @property
    def api_key(self):
        return os.environ.get("GEMINI_API_KEY") or read_env().get("GEMINI_API_KEY", "")

    @property
    def model(self):
        return self.model_override or read_env().get("GEMINI_MODEL") or DEFAULT_MODEL

    def _request(self, url, body=None):
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read().decode())["error"]["message"]
            except Exception:
                msg = e.reason
            raise AIError(f"{e.code}: {msg}"[:160]) from None
        except urllib.error.URLError as e:
            raise AIError(f"No internet ({e.reason})"[:160]) from None

    def _pick_model(self):
        """Newest Flash model that supports generateContent."""
        data = self._request(f"{API}/models?pageSize=200")
        names = [m["name"].split("/")[-1] for m in data.get("models", [])
                 if "generateContent" in m.get("supportedGenerationMethods", [])]
        flash = [n for n in names if "flash" in n and not re.search(r"lite|image|tts|audio|live|exp|preview", n)]
        pool = flash or [n for n in names if "flash" in n] or names
        if not pool:
            raise AIError("No Gemini model available for this key")

        def ver(n):
            m = re.search(r"(\d+(?:\.\d+)?)", n)
            return float(m.group(1)) if m else 0.0
        return sorted(pool, key=ver)[-1]

    def _generate_retry(self, body):
        """Retries busy / rate-limited replies (503, 429, 500) after 3 s and 10 s."""
        for wait in (3, 10, None):
            try:
                return self._request(f"{API}/models/{self.model}:generateContent", body)
            except AIError as e:
                if wait is None or not str(e)[:3] in ("503", "429", "500"):
                    raise
                time.sleep(wait)

    def generate(self, prompt, schema, temperature=0.4):
        if not self.api_key:
            raise AIError("No API key. Add GEMINI_API_KEY in the web dashboard (Device tab).")
        body = {
            "systemInstruction": {"parts": [{"text": SYSTEM}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature, "responseMimeType": "application/json",
                                 "responseSchema": schema},
        }
        try:
            data = self._generate_retry(body)
        except AIError as e:
            if not str(e).startswith("404"):
                raise
            self.model_override = self._pick_model()
            print(f"[FarmAI] Model not found, using {self.model_override}", flush=True)
            data = self._request(f"{API}/models/{self.model}:generateContent", body)
        try:
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
            return json.loads(text)
        except (KeyError, IndexError, ValueError):
            reason = (data.get("promptFeedback") or {}).get("blockReason") or \
                     (data.get("candidates") or [{}])[0].get("finishReason", "empty reply")
            raise AIError(f"Gemini gave no usable answer ({reason})") from None


# ------------------------------------------------------------- service
class FarmAI:
    TASKS = ("brief", "crop", "params", "ask")

    def __init__(self, hardware, weather, crop_presets):
        self.hw, self.weather, self.presets = hardware, weather, crop_presets
        self.client = GeminiClient()
        self.lock = threading.Lock()
        self.tasks = {k: {"status": "idle", "result": None, "error": "", "time": None, "input": None}
                      for k in self.TASKS}
        self._load_cache()
        threading.Thread(target=self._auto_loop, daemon=True).start()

    # ---- state
    def _load_cache(self):
        try:
            cached = json.loads(CACHE_FILE.read_text())
            for k in self.TASKS:
                if k in cached:
                    self.tasks[k].update(cached[k], status="ok" if cached[k].get("result") else "idle")
        except Exception:
            pass

    def _save_cache(self):
        try:
            with self.lock:
                data = {k: {"result": t["result"], "time": t["time"], "epoch": t.get("epoch"), "input": t["input"]}
                        for k, t in self.tasks.items() if t["result"]}
            CACHE_FILE.write_text(json.dumps(data))
        except Exception as e:
            print(f"[FarmAI] Could not write cache: {e}")

    def status(self):
        key = self.client.api_key
        with self.lock:
            tasks = json.loads(json.dumps(self.tasks))
        return {"configured": bool(key), "key_hint": f"…{key[-4:]}" if len(key) > 8 else "",
                "model": self.client.model, "tasks": tasks}

    def set_key(self, key):
        key = (key or "").strip()
        if key and (len(key) < 10 or len(key) > 300 or re.search(r"\s|=|#", key)):
            raise AIError("That does not look like an API key (check for spaces or a cut-off paste)")
        save_env_value("GEMINI_API_KEY", key)
        os.environ.pop("GEMINI_API_KEY", None)
        self.client.model_override = None
        if key:
            self.start("brief", force=True)

    def _run(self, name, fn, inp=None):
        with self.lock:
            t = self.tasks[name]
            if t["status"] == "busy":
                return False
            t.update(status="busy", error="", input=inp)

        def work():
            try:
                res = fn()
                with self.lock:
                    self.tasks[name].update(status="ok", result=res, time=time.strftime("%d %b %H:%M"),
                                            epoch=time.time())
                self._save_cache()
                print(f"[FarmAI] {name} done", flush=True)
            except Exception as e:
                with self.lock:
                    self.tasks[name].update(status="error", error=str(e)[:200])
                print(f"[FarmAI] {name} failed: {e}", flush=True)
        threading.Thread(target=work, daemon=True).start()
        return True

    def start(self, name, force=False, text=None):
        if name == "brief":
            return self._run("brief", self._brief)
        if name == "crop":
            crop = (text or "").strip()[:60] or self._crop_name()
            return self._run("crop", lambda: self._crop(crop), crop)
        if name == "params":
            return self._run("params", self._params)
        if name == "ask":
            q = (text or "").strip()[:300]
            if not q:
                return False
            return self._run("ask", lambda: self._ask(q), q)
        return False

    def _auto_loop(self):
        """Refreshes the daily brief every few hours and on a new day, when a key is set."""
        time.sleep(20)
        while True:
            try:
                t = self.tasks["brief"]
                epoch = t.get("epoch") or 0
                stale = time.time() - epoch > BRIEF_MAX_AGE_S or \
                    time.strftime("%Y-%m-%d", time.localtime(epoch)) != time.strftime("%Y-%m-%d")
                if self.client.api_key and stale and t["status"] != "busy" and 5 <= time.localtime().tm_hour < 22:
                    self.start("brief")
            except Exception as e:
                print(f"[FarmAI] auto refresh: {e}")
            time.sleep(300)

    # ---- context
    def _crop_name(self):
        t = self.hw.get_telemetry()
        return t["crop_name"].split(" / ")[0]

    def context(self):
        t = self.hw.get_telemetry()
        w = self.weather.get()
        adv = self.hw.get_advice()
        today = date.today()
        ctx = {
            "today": today.strftime("%A %d %B %Y"),
            "crop": t["crop_name"], "crop_stage": adv["stage_name"],
            "moisture_cutoffs_pct": {"pump1_starts_below": t["dry_cutoff"], "pump1_stops_at": t["stop_cutoff"]},
            "pump1_mode": t["pump_mode"],
            "sensors": {"soil_moisture_pct": t["soil_moisture"], "air_temp_c": t["temperature_c"],
                        "air_humidity_pct": t["humidity"], "raining_now": t["rain"],
                        "air_reading_source": t["temperature_source"],
                        "data_source": "simulator" if t["simulator_mode"] else
                        ("live" if t["hardware_connected"] else "offline")},
            "rain_tank": {"level_pct": t["tank"]["level"], "litres": t["tank"]["litres"],
                          "capacity_l": t["tank"]["capacity_l"], "full_alert": t["tank"]["alert"]},
            "farm": t["farm"], "pump2_auto_off_min": t["fert_manual_max_min"],
            "used_today": t["usage"],
            "rule_based_advice": {"water": adv["water"]["title"] + ". " + adv["water"]["text"],
                                  "fertilizer": adv["fert"]["title"] + ". " + adv["fert"]["text"]},
        }
        if w.get("ok"):
            ctx["weather_now"] = {k: w["current"][k] for k in ("temp", "humidity", "wind", "label")}
            ctx["forecast_days"] = [{k: d.get(k) for k in ("day", "date", "label", "max", "min", "rain_chance",
                                                            "rain_mm", "et0")} for d in w["daily"]]
            ctx["next_hours"] = [{k: h[k] for k in ("time", "temp", "rain_chance", "label")} for h in w["hourly"][:12]]
        else:
            ctx["weather"] = "forecast unavailable"
        return ctx

    # ---- tasks
    def _brief(self):
        prompt = ("Farm data (JSON):\n" + json.dumps(self.context(), indent=1) +
                  "\n\nWrite today's farm brief. Mention the weekday and the weather for the next days, "
                  "say whether to water more or less than normal and why, what fertilizer (if any) to give and "
                  "when, any pest or disease risk from the weather, and whether to release rain tank water. "
                  "Add reminders for the coming days.")
        return self.client.generate(prompt, BRIEF_SCHEMA)

    def _crop(self, crop):
        prompt = (f"Crop: {crop}\nFarm data (JSON):\n" + json.dumps(self.context(), indent=1) +
                  "\n\nGive a growing profile for this crop on this farm: soil moisture cutoffs for a capacitive "
                  "soil sensor (0 % dry air, 100 % in water), FAO-56 Kc for early / mid / late stage, days "
                  "between liquid feeds, best season in Kerala, water need, feeding plan, pests and a tip.")
        res = self.client.generate(prompt, CROP_SCHEMA, temperature=0.2)
        res["dry_cutoff"] = max(5.0, min(80.0, float(res["dry_cutoff"])))
        res["stop_cutoff"] = max(res["dry_cutoff"] + 5, min(95.0, float(res["stop_cutoff"])))
        res["feed_days"] = max(3, min(60, int(res["feed_days"])))
        for k in ("kc_early", "kc_mid", "kc_late"):
            res[k] = round(max(0.1, min(1.5, float(res[k]))), 2)
        return res

    def _params(self):
        prompt = ("Farm data (JSON):\n" + json.dumps(self.context(), indent=1) +
                  "\n\nCheck these settings for this crop, stage, season and weather. Suggest only changes "
                  "that clearly help (an empty list is fine). Keys: dry_cutoff and stop_cutoff (soil %), "
                  "tank_alert_pct (50-100), feed_litres (litres of fertilizer solution per feed), "
                  "fert_manual_max_min (pump 2 auto-off minutes), crop_stage (early/mid/late).")
        res = self.client.generate(prompt, PARAMS_SCHEMA, temperature=0.2)
        res["suggestions"] = [s for s in res.get("suggestions", []) if s.get("key") in PARAM_KEYS]
        for s in res["suggestions"]:
            s["name"] = PARAM_NAMES[s["key"]]
            s["applied"] = False
        return res

    def _ask(self, question):
        prompt = ("Farm data (JSON):\n" + json.dumps(self.context(), indent=1) + f"\n\nQuestion: {question}")
        return self.client.generate(prompt, ASK_SCHEMA, temperature=0.5)

    # ---- apply
    def apply_crop(self):
        res = self.tasks["crop"]["result"]
        if not res:
            raise AIError("No crop profile to apply")
        self.hw.set_custom_profile(res["name"], res["dry_cutoff"], res["stop_cutoff"],
                                   (res["kc_early"], res["kc_mid"], res["kc_late"]), res["feed_days"])
        return res["name"]

    def apply_param(self, index):
        res = self.tasks["params"]["result"]
        if not res or not 0 <= index < len(res["suggestions"]):
            raise AIError("No such suggestion")
        s = res["suggestions"][index]
        key, val = s["key"], str(s["value"]).strip().lower()
        if key == "crop_stage":
            if val not in ("early", "mid", "late"):
                raise AIError(f"Bad stage: {val}")
            self.hw.set_farm_settings(crop_stage=val)
        else:
            m = re.search(r"-?\d+(?:\.\d+)?", val)
            if not m:
                raise AIError(f"Bad value: {val}")
            num = float(m.group())
            if key == "dry_cutoff":
                self.hw.set_cutoffs(num, max(self.hw.soil_target_moisture, num + 5))
            elif key == "stop_cutoff":
                self.hw.set_cutoffs(self.hw.soil_dry_threshold, num)
            else:
                self.hw.set_farm_settings(**{key: num})
        with self.lock:
            s["applied"] = True
        self._save_cache()
        return s


def _make():
    from hardware_manager import hardware, CROP_PRESETS
    from weather import weather
    return FarmAI(hardware, weather, CROP_PRESETS)


# Singleton shared by the touchscreen and the web server
ai = _make()
