"""
Hardware Manager for IoT Smart Agriculture & Irrigation System
Coordinates temperature, humidity, soil moisture readings, water pump relay control,
crop profiles, device diagnostics, and configurable cutoff thresholds.

Pump 1 (water) is switched by soil moisture against the crop's cutoffs; pump 2
(fertilizer) is manual and always time-limited. One ultrasonic sensor watches the
rainwater tank and raises a "tank full, release water" alert that stays up until
it is reset. advisor.py turns the weather and crop into daily advice.
"""

import os
import time
import json
import math
import random
import threading
import subprocess
from pathlib import Path
from typing import Dict, Any

from advisor import daily_advice, STAGES, KC, FEED_DAYS
from weather import weather

try:
    from gpiozero import OutputDevice, InputDevice
    GPIO_AVAILABLE = True
except (ImportError, Exception):
    GPIO_AVAILABLE = False

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

SCRIPT_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = SCRIPT_DIR / "config" / "irrigation_settings.json"

CROP_PRESETS = {
    "tomato": {
        "name": "Tomato / Veg",
        "icon": "🍅",
        "dry_cutoff": 35.0,
        "stop_cutoff": 65.0,
        "desc": "Regular drip moisture"
    },
    "paddy": {
        "name": "Paddy / Rice",
        "icon": "🌾",
        "dry_cutoff": 50.0,
        "stop_cutoff": 85.0,
        "desc": "High moisture requirement"
    },
    "chilli": {
        "name": "Chilli / Pepper",
        "icon": "🌶️",
        "dry_cutoff": 25.0,
        "stop_cutoff": 55.0,
        "desc": "Moderate, well-drained"
    },
    "potato": {
        "name": "Potato / Tubers",
        "icon": "🥔",
        "dry_cutoff": 30.0,
        "stop_cutoff": 60.0,
        "desc": "Medium damp soil"
    },
    "corn": {
        "name": "Corn / Maize",
        "icon": "🌽",
        "dry_cutoff": 30.0,
        "stop_cutoff": 65.0,
        "desc": "Standard field watering"
    },
    "arid": {
        "name": "Cactus / Arid",
        "icon": "🌵",
        "dry_cutoff": 15.0,
        "stop_cutoff": 35.0,
        "desc": "Low water requirement"
    },
    "onion": {
        "name": "Onion / Shallot",
        "icon": "🧅",
        "dry_cutoff": 40.0,
        "stop_cutoff": 70.0,
        "desc": "Shallow roots, light frequent watering"
    },
    "custom": {
        "name": "Custom Profile",
        "icon": "⚙️",
        "dry_cutoff": 30.0,
        "stop_cutoff": 65.0,
        "desc": "User defined cutoffs"
    }
}


class HardwareManager:
    PIN_PUMP_RELAY = 17   # Physical Pin 11 - Active HIGH Relay
    PIN_SOIL_SENSOR = 18  # Physical Pin 12
    PIN_DHT_SENSOR = 4    # Physical Pin 7

    def __init__(self, pump_pin: int = PIN_PUMP_RELAY, active_high: bool = True):
        self.lock = threading.Lock()
        self.pump_pin_num = pump_pin
        self.active_high = active_high

        # Real Hardware sensor state (from Arduino Mega)
        self.real_temperature_c = None
        self.real_humidity = None
        self.real_soil_moisture = None
        self.real_rain = 0
        self.real_light = 0
        self.real_water_cm = None      # rain tank: sensor-to-water distance (cm)
        self.last_hardware_packet_time = 0.0

        # Simulator Mode variables (controlled via UI sliders only when explicitly enabled)
        self.simulator_mode = False
        self.sim_temp = 28.0
        self.sim_humidity = 64.0
        self.sim_soil_moisture = 42.0
        self.sim_tank_level = 40.0

        self.pump_on = False
        self.pump_mode = "AUTO"  # "AUTO" or "MANUAL"
        self.fert_pump_on = False
        self._fert_cmd_time = 0.0  # ignore stale fert_pump reports right after a command

        self.fert_manual_max_min = 5.0  # fertilizer pump auto-off
        # Motor driver direction per pump (True = reversed: IN2 / IN4 driven instead of IN1 / IN3)
        self.pump_reverse = {"pump": False, "fert": False}
        self.pump_test = None   # {"input": 1-4, "until": epoch} while a wiring test runs

        # Daily advice inputs
        self.crop_stage = "mid"         # early / mid / late (advisor.STAGES)
        # The Custom crop: name, Kc (early, mid, late) and feed interval. Filled by Farm AI,
        # or copied from the preset when its cutoffs are edited.
        self.custom_profile = None
        self.field_area_m2 = 10.0
        self.water_lpm = 10.0           # pump flow rates, measured with a bucket
        self.fert_lpm = 2.0
        self.feed_litres = 2.0          # fertilizer solution per feed
        self.fert_last_date = None      # YYYY-MM-DD of the last feed
        self.usage_day = time.strftime("%Y-%m-%d")
        self.water_s_today = 0.0
        self.fert_s_today = 0.0
        self._was_running = (False, False)

        # Crop selection & Cutoff Percentages
        self.selected_crop = "tomato"
        self.soil_dry_threshold = 35.0
        self.soil_target_moisture = 65.0

        # Rain tank: sensor-to-water distance when empty / full (cm), surface area (cm2)
        # for litres (1 cm over 1000 cm2 = 1 L) and the full-tank alert
        self.tank_empty_cm = 100.0
        self.tank_full_cm = 10.0
        self.tank_area_cm2 = 10000.0   # e.g. 1 m x 1 m tank
        self.tank_alert_pct = 90.0
        self.tank_alert = False
        self.tank_alert_since = None
        self.tank_armed = True
        self.tank_last_released = None
        self.load_settings()
        self.sim_fert_off_at = 0.0  # when pump 2's current run ends

        # Physical GPIO relay device
        self.relay_device = None
        if GPIO_AVAILABLE:
            try:
                self.relay_device = OutputDevice(self.pump_pin_num, active_high=self.active_high, initial_value=False)
                print(f"[Hardware] Initialized GPIO {self.pump_pin_num} for Pump Relay (active_high={active_high})")
            except Exception as e:
                print(f"[Hardware] Could not initialize physical GPIO {self.pump_pin_num}: {e}. Running in simulation mode.")
                self.relay_device = None

        # Background threads flag
        self.running = True

        # Arduino Mega Serial Link
        self.serial_conn = None
        self.arduino_connected = False
        self.serial_lock = threading.Lock()
        if SERIAL_AVAILABLE:
            self.serial_thread = threading.Thread(target=self._serial_loop, daemon=True)
            self.serial_thread.start()

        # Background watchdog & auto-irrigation thread
        self.worker_thread = threading.Thread(target=self._loop, daemon=True)
        self.worker_thread.start()

    @property
    def is_hardware_online(self) -> bool:
        return self.arduino_connected and ((time.time() - self.last_hardware_packet_time) < 3.5)

    def load_settings(self):
        """Loads saved cutoff percentages, crop profile, and simulator state from JSON config."""
        if SETTINGS_FILE.exists():
            try:
                with open(SETTINGS_FILE, "r") as f:
                    data = json.load(f)
                    self.selected_crop = data.get("selected_crop", "tomato")
                    self.soil_dry_threshold = float(data.get("dry_cutoff", 35.0))
                    self.soil_target_moisture = float(data.get("stop_cutoff", 65.0))
                    self.pump_mode = data.get("pump_mode", "AUTO")
                    self.simulator_mode = bool(data.get("simulator_mode", False))
                    self.sim_temp = float(data.get("sim_temp", 28.0))
                    self.sim_humidity = float(data.get("sim_humidity", 64.0))
                    self.sim_soil_moisture = float(data.get("sim_soil_moisture", 42.0))
                    self.tank_empty_cm = float(data.get("tank_empty_cm", 100.0))
                    self.tank_full_cm = float(data.get("tank_full_cm", 10.0))
                    self.tank_area_cm2 = float(data.get("tank_area_cm2", data.get("water_area_cm2", 10000.0)))
                    self.tank_alert_pct = float(data.get("tank_alert_pct", 90.0))
                    self.tank_alert = bool(data.get("tank_alert", False))
                    self.tank_alert_since = data.get("tank_alert_since")
                    self.tank_armed = bool(data.get("tank_armed", True))
                    self.tank_last_released = data.get("tank_last_released")
                    self.sim_tank_level = float(data.get("sim_tank_level", 40.0))
                    self.fert_manual_max_min = float(data.get("fert_manual_max_min", 5.0))
                    self.crop_stage = data.get("crop_stage", "mid")
                    self.pump_reverse.update(data.get("pump_reverse", {}))
                    self.custom_profile = data.get("custom_profile")
                    self.field_area_m2 = float(data.get("field_area_m2", 10.0))
                    self.water_lpm = float(data.get("water_lpm", 10.0))
                    self.fert_lpm = float(data.get("fert_lpm", 2.0))
                    self.feed_litres = float(data.get("feed_litres", 2.0))
                    self.fert_last_date = data.get("fert_last_date")
                    usage = data.get("usage", {})
                    if usage.get("day") == time.strftime("%Y-%m-%d"):
                        self.water_s_today = float(usage.get("water_s", 0))
                        self.fert_s_today = float(usage.get("fert_s", 0))
                    print(f"[Hardware] Loaded settings: Simulator={self.simulator_mode}, Crop={self.selected_crop}, Dry Cutoff={self.soil_dry_threshold}%, Stop Cutoff={self.soil_target_moisture}%")
            except Exception as e:
                print(f"[Hardware] Error loading settings file: {e}")

    def save_settings(self):
        """Persists cutoff percentages, crop, and simulator state to JSON config."""
        try:
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(SETTINGS_FILE, "w") as f:
                json.dump({
                    "selected_crop": self.selected_crop,
                    "dry_cutoff": self.soil_dry_threshold,
                    "stop_cutoff": self.soil_target_moisture,
                    "pump_mode": self.pump_mode,
                    "simulator_mode": self.simulator_mode,
                    "sim_temp": self.sim_temp,
                    "sim_humidity": self.sim_humidity,
                    "sim_soil_moisture": self.sim_soil_moisture,
            "sim_tank_level": self.sim_tank_level,
                    "tank_empty_cm": self.tank_empty_cm,
                    "tank_full_cm": self.tank_full_cm,
                    "tank_area_cm2": self.tank_area_cm2,
                    "tank_alert_pct": self.tank_alert_pct,
                    "tank_alert": self.tank_alert,
                    "tank_alert_since": self.tank_alert_since,
                    "tank_armed": self.tank_armed,
                    "tank_last_released": self.tank_last_released,
                    "sim_tank_level": self.sim_tank_level,
                    "fert_manual_max_min": self.fert_manual_max_min,
                    "crop_stage": self.crop_stage,
                    "pump_reverse": self.pump_reverse,
                    "custom_profile": self.custom_profile,
                    "field_area_m2": self.field_area_m2,
                    "water_lpm": self.water_lpm,
                    "fert_lpm": self.fert_lpm,
                    "feed_litres": self.feed_litres,
                    "fert_last_date": self.fert_last_date,
                    "usage": {"day": self.usage_day, "water_s": round(self.water_s_today),
                              "fert_s": round(self.fert_s_today)}
                }, f, indent=2)
            print(f"[Hardware] Saved settings to {SETTINGS_FILE}")
        except Exception as e:
            print(f"[Hardware] Error saving settings: {e}")

    def set_crop(self, crop_key: str):
        """Selects a crop preset and automatically updates recommended cutoffs."""
        with self.lock:
            if crop_key in CROP_PRESETS:
                self.selected_crop = crop_key
                preset = CROP_PRESETS[crop_key]
                if crop_key != "custom":
                    self.soil_dry_threshold = preset["dry_cutoff"]
                    self.soil_target_moisture = preset["stop_cutoff"]
                print(f"[Hardware] Crop changed to {preset['name']} (Cutoffs: {self.soil_dry_threshold}% - {self.soil_target_moisture}%)")
        self.save_settings()
        self._send_serial_cmd(f"CUTOFF:{self.soil_dry_threshold}:{self.soil_target_moisture}\n")

    def _to_custom(self):
        """Switches to the Custom crop after a cutoff edit, keeping the old crop's Kc and feeding."""
        if self.selected_crop != "custom":
            prev = self.selected_crop
            self.custom_profile = {"name": f"{CROP_PRESETS[prev]['name'].split(' / ')[0]} (custom)",
                                   "kc": list(KC.get(prev, KC["custom"])), "feed_days": FEED_DAYS.get(prev, 10)}
            self.selected_crop = "custom"

    def set_custom_profile(self, name: str, dry_cutoff: float, stop_cutoff: float, kc, feed_days: int):
        """Applies a crop profile (from Farm AI) as the Custom crop."""
        with self.lock:
            self.custom_profile = {"name": str(name)[:30], "kc": [float(k) for k in kc], "feed_days": int(feed_days)}
            self.selected_crop = "custom"
        self.set_cutoffs(dry_cutoff, stop_cutoff)

    def crop_display_name(self) -> str:
        if self.selected_crop == "custom" and self.custom_profile:
            return self.custom_profile["name"]
        return CROP_PRESETS.get(self.selected_crop, CROP_PRESETS["custom"])["name"]

    def set_cutoffs(self, dry_cutoff: float, stop_cutoff: float):
        """Updates cutoff percentages safely."""
        with self.lock:
            self.soil_dry_threshold = max(5.0, min(80.0, float(dry_cutoff)))
            self.soil_target_moisture = max(self.soil_dry_threshold + 5.0, min(95.0, float(stop_cutoff)))
            # If values differ from preset, mark as custom
            curr_preset = CROP_PRESETS.get(self.selected_crop)
            if curr_preset and (self.soil_dry_threshold != curr_preset["dry_cutoff"] or self.soil_target_moisture != curr_preset["stop_cutoff"]):
                self._to_custom()
        self.save_settings()
        self._send_serial_cmd(f"CUTOFF:{self.soil_dry_threshold}:{self.soil_target_moisture}\n")

    def adjust_dry_cutoff(self, delta: float) -> float:
        with self.lock:
            val = self.soil_dry_threshold + delta
            self.soil_dry_threshold = max(10.0, min(self.soil_target_moisture - 5.0, val))
            self._to_custom()
            cur = self.soil_dry_threshold
        self.save_settings()
        self._send_serial_cmd(f"CUTOFF:{self.soil_dry_threshold}:{self.soil_target_moisture}\n")
        return cur

    def adjust_stop_cutoff(self, delta: float) -> float:
        with self.lock:
            val = self.soil_target_moisture + delta
            self.soil_target_moisture = max(self.soil_dry_threshold + 5.0, min(95.0, val))
            self._to_custom()
            cur = self.soil_target_moisture
        self.save_settings()
        self._send_serial_cmd(f"CUTOFF:{self.soil_dry_threshold}:{self.soil_target_moisture}\n")
        self._check_auto_irrigation()
        return cur

    # ------------------------------------------------------------ rain tank
    def set_tank_calibration(self, empty_cm: float = None, full_cm: float = None, area_cm2: float = None):
        """Sets the ultrasonic distances (cm) that mean an empty and a full rain tank,
        and optionally the water surface area (cm2) used to show litres."""
        with self.lock:
            empty = self.tank_empty_cm if empty_cm is None else float(empty_cm)
            full = self.tank_full_cm if full_cm is None else float(full_cm)
            area = self.tank_area_cm2 if area_cm2 is None else float(area_cm2)
            # Sensors cannot measure closer than ~2-20 cm (blind zone) or beyond ~4.5 m
            full = max(2.0, min(400.0, full))
            empty = max(full + 5.0, min(450.0, empty))
            area = max(50.0, min(500000.0, area))
            self.tank_empty_cm, self.tank_full_cm, self.tank_area_cm2 = round(empty, 1), round(full, 1), round(area)
        self.save_settings()
        self._send_serial_cmd(f"TANK:{self.tank_empty_cm}:{self.tank_full_cm}\n")
        return self.tank_empty_cm, self.tank_full_cm

    def mark_tank(self, which: str):
        """Uses the current ultrasonic reading as the 'empty' or 'full' distance."""
        cm = self.real_water_cm
        if cm is None or not self.is_hardware_online:
            return None
        if which == "empty":
            return self.set_tank_calibration(empty_cm=cm)
        return self.set_tank_calibration(full_cm=cm)

    def _tank_state(self) -> Dict[str, Any]:
        empty, full, area = self.tank_empty_cm, self.tank_full_cm, self.tank_area_cm2
        if self.simulator_mode:
            cm = empty - self.sim_tank_level / 100.0 * (empty - full)
        elif self.is_hardware_online:
            cm = self.real_water_cm
        else:
            cm = None
        out = {"cm": None, "level": None, "litres": None, "capacity_l": round((empty - full) * area / 1000.0, 1),
               "empty_cm": empty, "full_cm": full, "area_cm2": area, "alert_pct": self.tank_alert_pct,
               "alert": self.tank_alert, "alert_since": self.tank_alert_since,
               "last_released": self.tank_last_released}
        if cm is not None:
            out["cm"] = round(cm, 1)
            out["level"] = int(max(0, min(100, (empty - cm) * 100.0 / (empty - full))))
            out["litres"] = round(max(0.0, empty - cm) * area / 1000.0, 1)
        return out

    def _check_tank_alert(self):
        """Latches a 'tank full, release water' alert. It stays up until reset_tank(),
        and can only fire again once the level has dropped 10 % below the alert level."""
        level = self._tank_state()["level"]
        if level is None:
            return
        with self.lock:
            if self.tank_armed and level >= self.tank_alert_pct:
                self.tank_alert, self.tank_armed = True, False
                self.tank_alert_since = time.strftime("%d %b %H:%M")
                print(f"[Tank] Rain tank full ({level}%): release water", flush=True)
            elif not self.tank_armed and not self.tank_alert and level < self.tank_alert_pct - 10:
                self.tank_armed = True

    def reset_tank(self):
        """Clears the full-tank alert after the water has been released."""
        with self.lock:
            self.tank_alert = False
            self.tank_alert_since = None
            self.tank_last_released = time.strftime("%d %b %H:%M")
        self.save_settings()

    def set_farm_settings(self, **kw):
        """Field size, pump flow rates, feed size, crop stage, tank alert level, fertilizer auto-off."""
        limits = {"field_area_m2": (0.5, 100000.0), "water_lpm": (0.1, 500.0), "fert_lpm": (0.05, 100.0),
                  "feed_litres": (0.1, 500.0), "tank_alert_pct": (50.0, 100.0), "fert_manual_max_min": (1.0, 60.0)}
        with self.lock:
            for key, (lo, hi) in limits.items():
                if kw.get(key) is not None:
                    setattr(self, key, round(max(lo, min(hi, float(kw[key]))), 2))
            if kw.get("crop_stage") in STAGES:
                self.crop_stage = kw["crop_stage"]
        self.save_settings()

    # ------------------------------------------------------------- fertilizer
    def set_fert_pump(self, on: bool, minutes: float = None):
        """Pump 2 (fertilizer), manual. Always time-limited: `minutes`, or the auto-off limit."""
        limit = self.fert_manual_max_min * 60
        seconds = int(max(1, min(limit, minutes * 60))) if minutes else int(limit)
        with self.lock:
            self.fert_pump_on = on
            self._fert_cmd_time = time.time()
            self.sim_fert_off_at = time.time() + seconds if on else 0.0
        self._send_serial_cmd(f"FERT:ON:{seconds}\n" if on else "FERT:OFF\n")
        print(f"[Hardware] Fertilizer Pump -> {'ON for %d s' % seconds if on else 'OFF'}", flush=True)
        return self.fert_pump_on

    def toggle_fert_pump(self) -> bool:
        return self.set_fert_pump(not self.fert_pump_on)

    def _track_usage(self, dt: float):
        """Counts today's pump run time. A fertilizer run of 20 s or more counts as today's feed."""
        today = time.strftime("%Y-%m-%d")
        changed = False
        with self.lock:
            if self.usage_day != today:
                self.usage_day, self.water_s_today, self.fert_s_today = today, 0.0, 0.0
                changed = True
            if self.pump_on:
                self.water_s_today += dt
            if self.fert_pump_on:
                self.fert_s_today += dt
                if self.fert_s_today >= 20 and self.fert_last_date != today:
                    self.fert_last_date = today
                    changed = True
            # Save when a pump stops so the counters survive a restart
            stopped = (self._was_running[0] and not self.pump_on) or (self._was_running[1] and not self.fert_pump_on)
            self._was_running = (self.pump_on, self.fert_pump_on)
        if changed or stopped:
            self.save_settings()

    def get_advice(self) -> Dict[str, Any]:
        t = self.get_telemetry()
        return daily_advice(
            crop=self.selected_crop, crop_name=self.crop_display_name(), stage=self.crop_stage, weather=weather.get(),
            soil=t["soil_moisture"], dry_cut=self.soil_dry_threshold, stop_cut=self.soil_target_moisture,
            tank_level=t["tank"]["level"], tank_alert_pct=self.tank_alert_pct, field_m2=self.field_area_m2,
            water_lpm=self.water_lpm, fert_lpm=self.fert_lpm, feed_litres=self.feed_litres,
            fert_last_date=self.fert_last_date, water_s_today=self.water_s_today, fert_s_today=self.fert_s_today,
            custom=self.custom_profile if self.selected_crop == "custom" else None)

    def _simulate(self):
        """Simulator: watering slowly raises the soil moisture; pump 2 stops on its timer."""
        if not self.simulator_mode:
            return
        with self.lock:
            if self.pump_on:
                self.sim_soil_moisture = min(100.0, self.sim_soil_moisture + 0.2)
            if self.fert_pump_on and self.sim_fert_off_at and time.time() > self.sim_fert_off_at:
                self.fert_pump_on = False

    def set_simulator_mode(self, enabled: bool) -> bool:
        """Toggles manual simulator mode. When enabled, slider values override physical inputs."""
        with self.lock:
            self.simulator_mode = bool(enabled)
        self.save_settings()
        self._sync_arduino()
        self._check_auto_irrigation()
        print(f"[Hardware] Simulator Mode -> {'ENABLED' if self.simulator_mode else 'DISABLED'}")
        return self.simulator_mode

    def toggle_simulator_mode(self) -> bool:
        return self.set_simulator_mode(not self.simulator_mode)

    def set_simulated_sensors(self, temp: float = None, humidity: float = None, soil_moisture: float = None,
                              tank_level: float = None):
        """Sets slider values for simulation. When simulator_mode is active, outputs update immediately."""
        with self.lock:
            if temp is not None:
                self.sim_temp = round(float(temp), 1)
            if humidity is not None:
                self.sim_humidity = round(float(humidity), 1)
            if soil_moisture is not None:
                self.sim_soil_moisture = round(float(soil_moisture), 1)
            if tank_level is not None:
                self.sim_tank_level = round(max(0.0, min(100.0, float(tank_level))), 1)

        self.save_settings()
        self._check_auto_irrigation()

    def _check_auto_irrigation(self):
        """Triggers real-time auto-irrigation evaluation when thresholds or moisture change."""
        with self.lock:
            if self.pump_mode != "AUTO":
                return

            # With real sensors the Arduino runs the cutoff logic itself (so irrigation
            # keeps working if the Pi goes down) and its pump state is mirrored in
            # _serial_loop. The Pi only drives the pump against simulated soil values.
            if not self.simulator_mode:
                return
            soil = self.sim_soil_moisture

            if soil < self.soil_dry_threshold and not self.pump_on:
                print(f"[Auto-Irrigation] Soil ({soil:.1f}% < {self.soil_dry_threshold}%). Starting pump!")
                self.pump_on = True
                if self.relay_device:
                    try:
                        self.relay_device.on()
                    except Exception as e:
                        print(f"[Hardware] Relay on error: {e}")
                self._send_serial_cmd("PUMP:ON\n")
            elif soil >= self.soil_target_moisture and self.pump_on:
                print(f"[Auto-Irrigation] Soil reached target ({soil:.1f}% >= {self.soil_target_moisture}%). Stopping pump.")
                self.pump_on = False
                if self.relay_device:
                    try:
                        self.relay_device.off()
                    except Exception as e:
                        print(f"[Hardware] Relay off error: {e}")
                self._send_serial_cmd("PUMP:OFF\n")

    def _sync_arduino(self):
        """Pushes cutoffs and control mode to the Arduino. Its own AUTO logic is only
        enabled when the Pi is in AUTO and not simulating; otherwise the Pi drives the pump."""
        self._last_sync = time.time()
        arduino_auto = self.pump_mode == "AUTO" and not self.simulator_mode
        for pump, rev in self.pump_reverse.items():
            self._send_serial_cmd(f"DIR:{pump.upper()}:{'REV' if rev else 'FWD'}\n")
        self._send_serial_cmd(f"CUTOFF:{self.soil_dry_threshold}:{self.soil_target_moisture}\n")
        self._send_serial_cmd(f"TANK:{self.tank_empty_cm}:{self.tank_full_cm}\n")
        self._send_serial_cmd("MODE:AUTO\n" if arduino_auto else "MODE:MANUAL\n")
        if not arduino_auto:
            self._send_serial_cmd("PUMP:ON\n" if self.pump_on else "PUMP:OFF\n")
        if not self.fert_pump_on:
            self._send_serial_cmd("FERT:OFF\n")

    def _check_arduino_state(self, data):
        """Re-sends our settings when the Mega reports a different mode or cutoffs
        (a lost command, or a manual PUMP command in AUTO), at most every 5 s."""
        want_auto = self.pump_mode == "AUTO" and not self.simulator_mode
        try:
            ok = ((data["mode"] == "AUTO") == want_auto and
                  abs(float(data["dry_cutoff"]) - self.soil_dry_threshold) < 0.1 and
                  abs(float(data["stop_cutoff"]) - self.soil_target_moisture) < 0.1)
        except (KeyError, TypeError, ValueError):
            return
        if not ok and time.time() - getattr(self, "_last_sync", 0) > 5:
            print(f"[Hardware] Arduino out of sync (mode {data.get('mode')}, cutoffs "
                  f"{data.get('dry_cutoff')}/{data.get('stop_cutoff')}): re-sending settings", flush=True)
            self._sync_arduino()

    def set_pump_direction(self, pump: str, reverse: bool):
        """pump: "pump" (1, water) or "fert" (2). Stored here and in the Mega's EEPROM."""
        if pump not in self.pump_reverse:
            return
        with self.lock:
            self.pump_reverse[pump] = bool(reverse)
        self.save_settings()
        self._send_serial_cmd(f"DIR:{pump.upper()}:{'REV' if reverse else 'FWD'}\n")
        print(f"[Hardware] {pump} motor direction -> {'reversed' if reverse else 'forward'}", flush=True)

    TEST_S = 5

    def test_driver_input(self, n: int):
        """Wiring test: only motor-driver input n (1-4) HIGH for 5 s, everything else LOW.
        IN1 / IN2 = pump 1 (D5 / D7), IN3 / IN4 = pump 2 (D6 / D8). Switches to MANUAL."""
        if n not in (1, 2, 3, 4):
            return
        pump, reverse = ("pump" if n <= 2 else "fert"), n in (2, 4)
        with self.lock:
            self.pump_mode = "MANUAL"
            self.pump_on = n <= 2
            self.fert_pump_on = n > 2
            self._fert_cmd_time = time.time()
            self.pump_test = {"input": n, "until": time.time() + self.TEST_S}
        self.save_settings()
        for cmd in ("MODE:MANUAL", "PUMP:OFF", "FERT:OFF", f"DIR:{pump.upper()}:{'REV' if reverse else 'FWD'}",
                    f"{'PUMP' if pump == 'pump' else 'FERT'}:ON:{self.TEST_S}"):
            self._send_serial_cmd(cmd + "\n")
        print(f"[Hardware] Wiring test: IN{n} HIGH for {self.TEST_S} s", flush=True)
        threading.Timer(self.TEST_S + 0.5, self._end_test, args=(n,)).start()

    def _end_test(self, n):
        with self.lock:
            if not self.pump_test or self.pump_test["input"] != n:
                return
            self.pump_test = None
            self.pump_on = self.fert_pump_on = False
        self._send_serial_cmd("PUMP:OFF\nFERT:OFF\n")
        for pump, rev in self.pump_reverse.items():
            self._send_serial_cmd(f"DIR:{pump.upper()}:{'REV' if rev else 'FWD'}\n")

    def _send_serial_cmd(self, cmd_str: str):
        """Sends command(s) to the Arduino Mega via USB serial if connected. Lines are
        paced 15 ms apart so a burst never overflows the Mega's 64-byte receive buffer."""
        if self.serial_conn:
            with self.serial_lock:
                try:
                    for line in cmd_str.strip().splitlines():
                        self.serial_conn.write((line + "\n").encode('utf-8'))
                        self.serial_conn.flush()
                        time.sleep(0.015)
                except Exception as e:
                    print(f"[Serial] Error writing to Arduino: {e}")

    def set_pump(self, state: bool):
        with self.lock:
            self.pump_on = state
            if self.relay_device:
                try:
                    if self.pump_on:
                        self.relay_device.on()
                    else:
                        self.relay_device.off()
                except Exception as e:
                    print(f"[Hardware] Error driving relay GPIO: {e}")
            status = "ON" if self.pump_on else "OFF"
            print(f"[Hardware] Water Pump -> {status}", flush=True)

        self._send_serial_cmd(f"PUMP:{status}\n")

    def toggle_pump(self) -> bool:
        with self.lock:
            self.pump_mode = "MANUAL"
            new_state = not self.pump_on
        self.set_pump(new_state)
        self.save_settings()
        return new_state

    def toggle_mode(self) -> str:
        with self.lock:
            self.pump_mode = "MANUAL" if self.pump_mode == "AUTO" else "AUTO"
            current_mode = self.pump_mode
        self.save_settings()
        self._sync_arduino()
        print(f"[Hardware] Irrigation Mode -> {current_mode}", flush=True)
        return current_mode

    def get_system_diagnostics(self) -> Dict[str, Any]:
        """Collects real-time device stats (CPU temp, RAM, Disk, Uptime)."""
        temp_str = "N/A"
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                temp_raw = int(f.read().strip())
                temp_str = f"{temp_raw / 1000.0:.1f} °C"
        except Exception:
            pass

        ram_str = "N/A"
        disk_str = "N/A"
        if PSUTIL_AVAILABLE:
            try:
                mem = psutil.virtual_memory()
                ram_str = f"{mem.used // (1024*1024)}M / {mem.total // (1024*1024)}M ({mem.percent}%)"
                disk = psutil.disk_usage('/')
                disk_str = f"{disk.used // (1024*1024*1024)}G / {disk.total // (1024*1024*1024)}G ({disk.percent}%)"
            except Exception:
                pass

        uptime_str = "N/A"
        try:
            res = subprocess.run(["uptime", "-p"], capture_output=True, text=True, timeout=2)
            if res.returncode == 0:
                uptime_str = res.stdout.strip().replace("up ", "")
        except Exception:
            pass

        ip_str = "N/A"
        try:
            res = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=2)
            if res.returncode == 0 and res.stdout.strip():
                ip_str = res.stdout.split()[0]
        except Exception:
            pass

        return {
            "ip_address": ip_str,
            "cpu_temp": temp_str,
            "ram_usage": ram_str,
            "disk_usage": disk_str,
            "uptime": uptime_str,
            "lcd_driver": "ADS7846 6-Point Affine",
            "gpio_relay": "Motor driver: pump 1 D5/D7, pump 2 D6/D8",
            "arduino_mega": "Connected (/dev/ttyACM0 @ 115200)" if self.arduino_connected else "Standby / Simulated"
        }

    def get_telemetry(self) -> Dict[str, Any]:
        """Returns snapshot of live telemetry, crop info, thresholds, and real connection status."""
        with self.lock:
            hw_online = self.is_hardware_online
            sim_mode = self.simulator_mode

            if sim_mode:
                temp_c = round(self.sim_temp, 1)
                temp_f = round((temp_c * 9.0 / 5.0) + 32.0, 1)
                hum = round(self.sim_humidity, 1)
                soil = round(self.sim_soil_moisture, 1)
                status_label = "SIMULATOR"
            elif hw_online:
                temp_c = round(self.real_temperature_c, 1) if self.real_temperature_c is not None else None
                temp_f = round((temp_c * 9.0 / 5.0) + 32.0, 1) if temp_c is not None else None
                hum = round(self.real_humidity, 1) if self.real_humidity is not None else None
                soil = round(self.real_soil_moisture, 1) if self.real_soil_moisture is not None else None
                status_label = "ONLINE"
            else:
                # Real mode and hardware not connected
                temp_c = None
                temp_f = None
                hum = None
                soil = None
                status_label = "NOT_CONNECTED"

            # Extra field sensors are only meaningful with live hardware
            rain = self.real_rain if hw_online and not sim_mode else None
            light = self.real_light if hw_online and not sim_mode else None
            tank = self._tank_state()

            pump = self.pump_on
            mode = self.pump_mode
            dry_cut = round(self.soil_dry_threshold, 1)
            stop_cut = round(self.soil_target_moisture, 1)
            crop_key = self.selected_crop

        # No DHT reading (sensor down or Arduino offline): use the Alappuzha weather
        # station instead, marked with source "weather" so every screen labels it
        temp_src = "simulator" if sim_mode else ("sensor" if temp_c is not None else None)
        hum_src = "simulator" if sim_mode else ("sensor" if hum is not None else None)
        if not sim_mode and (temp_c is None or hum is None):
            w = weather.get()
            if w.get("ok") and not w.get("stale"):
                if temp_c is None:
                    temp_c, temp_src = round(float(w["current"]["temp"]), 1), "weather"
                    temp_f = round(temp_c * 9.0 / 5.0 + 32.0, 1)
                if hum is None:
                    hum, hum_src = round(float(w["current"]["humidity"]), 1), "weather"

        crop_info = CROP_PRESETS.get(crop_key, CROP_PRESETS["custom"])

        if not sim_mode and not hw_online:
            condition = "NOT CONNECTED"
            condition_color = "#ef4444"
        elif soil is not None:
            if soil < dry_cut:
                condition = "DRY (PUMP NEEDED)"
                condition_color = "#ef4444"
            elif soil > stop_cut:
                condition = "SATURATED / WET"
                condition_color = "#38bdf8"
            else:
                condition = "OPTIMAL MOISTURE"
                condition_color = "#10b981"
        else:
            condition = "NOT CONNECTED"
            condition_color = "#ef4444"

        return {
            "temperature_c": temp_c,
            "temperature_source": temp_src,
            "temperature_f": temp_f,
            "humidity": hum,
            "humidity_source": hum_src,
            "soil_moisture": soil,
            "rain": rain,
            "light": light,
            "water_level": tank["level"],
            "water_cm": tank["cm"],
            "tank": tank,
            "fert_pump_on": self.fert_pump_on,
            "pump_reverse": dict(self.pump_reverse),
            "pump_test": {"input": self.pump_test["input"],
                          "left": max(0, int(self.pump_test["until"] - time.time() + 0.99))} if self.pump_test else None,
            "fert_off_in": max(0, int(self.sim_fert_off_at - time.time())) if self.fert_pump_on and self.sim_fert_off_at else None,
            "fert_manual_max_min": self.fert_manual_max_min,
            "farm": {"crop_stage": self.crop_stage, "field_area_m2": self.field_area_m2,
                     "water_lpm": self.water_lpm, "fert_lpm": self.fert_lpm, "feed_litres": self.feed_litres,
                     "fert_last_date": self.fert_last_date},
            "usage": {"water_s": round(self.water_s_today), "fert_s": round(self.fert_s_today),
                      "water_l": round(self.water_s_today / 60.0 * self.water_lpm),
                      "fert_l": round(self.fert_s_today / 60.0 * self.fert_lpm, 1)},
            "soil_condition": condition,
            "soil_color": condition_color,
            "pump_status": "ON" if pump else "OFF",
            "pump_on": pump,
            "pump_mode": mode,
            "dry_cutoff": dry_cut,
            "stop_cutoff": stop_cut,
            "selected_crop": crop_key,
            "crop_name": self.crop_display_name(),
            "crop_icon": crop_info["icon"],
            "crop_desc": crop_info["desc"],
            "arduino_mega_online": hw_online,
            "hardware_connected": hw_online,
            "hardware_status": status_label,
            "simulator_mode": sim_mode,
            "sim_temp": self.sim_temp,
            "sim_humidity": self.sim_humidity,
            "sim_soil_moisture": self.sim_soil_moisture,
            "sim_tank_level": self.sim_tank_level,
            "timestamp": time.strftime("%H:%M:%S")
        }

    def _serial_loop(self):
        """Monitors USB serial connection with Arduino Mega 2560."""
        target_ports = ["/dev/ttyACM0", "/dev/ttyUSB0", "COM3", "COM4"]
        while self.running:
            if not self.serial_conn:
                for port in target_ports:
                    try:
                        s = serial.Serial(port, 115200, timeout=1.5)
                        time.sleep(2.0)  # Allow Arduino reset on connect
                        self.serial_conn = s
                        print(f"[Hardware] Successfully connected to Arduino Mega on {port} @ 115200 baud")
                        self._sync_arduino()
                        break
                    except Exception:
                        pass
                if not self.serial_conn:
                    self.arduino_connected = False
                    time.sleep(2.0)
                    continue

            try:
                line = self.serial_conn.readline().decode('utf-8', errors='ignore').strip()
                if "{" in line and "}" in line:
                    s_idx = line.find("{")
                    e_idx = line.rfind("}") + 1
                    data = json.loads(line[s_idx:e_idx])
                    with self.lock:
                        self.last_hardware_packet_time = time.time()
                        self.arduino_connected = True
                        # temp/humidity arrive as null when the DHT sensor is not responding
                        if "temp" in data:
                            self.real_temperature_c = float(data["temp"]) if data["temp"] is not None else None
                        if "humidity" in data:
                            self.real_humidity = float(data["humidity"]) if data["humidity"] is not None else None
                        if "soil" in data:
                            self.real_soil_moisture = float(data["soil"])
                        if "rain" in data:
                            self.real_rain = int(data["rain"])
                        if "light" in data:
                            self.real_light = int(data["light"])
                        # Rain tank; null when the ultrasonic sensor gets no echo
                        if "water_cm" in data:
                            self.real_water_cm = float(data["water_cm"]) if data["water_cm"] is not None else None
                        # The Arduino owns the fertilizer pump timer, so it reports when it switched off
                        if ("fert_pump" in data and not self.simulator_mode
                                and time.time() - self._fert_cmd_time > 2.0):
                            self.fert_pump_on = bool(data["fert_pump"])
                        if "pump" in data and self.pump_mode == "AUTO" and not self.simulator_mode:
                            self.pump_on = bool(data["pump"])
                            if self.relay_device:
                                try:
                                    self.relay_device.value = self.pump_on
                                except Exception as e:
                                    print(f"[Hardware] Relay mirror error: {e}")
                    # Arduino rebooted (boots in AUTO with default cutoffs): re-push our state
                    if data.get("status") == "READY":
                        self._sync_arduino()
                    elif "mode" in data:
                        self._check_arduino_state(data)
                else:
                    if (time.time() - self.last_hardware_packet_time) > 4.0:
                        self.arduino_connected = False
            except Exception as e:
                print(f"[Hardware] Serial connection lost: {e}. Reconnecting...")
                try:
                    self.serial_conn.close()
                except Exception:
                    pass
                self.serial_conn = None
                self.arduino_connected = False
                time.sleep(1.5)

    def _loop(self):
        """Periodic auto-irrigation checker (pure real hardware control, no fake data generation)."""
        last = time.time()
        while self.running:
            time.sleep(0.5)
            now = time.time()
            self._simulate()
            self._track_usage(now - last)
            last = now
            self._check_auto_irrigation()
            self._check_tank_alert()


def run_privileged(args):
    """Fire-and-forget system command (reboot / service restart). The iot-dashboard
    service runs as root; otherwise falls back to non-interactive sudo (needs a sudoers rule)."""
    if os.geteuid() != 0:
        args = ["sudo", "-n"] + list(args)
    try:
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"[System] Failed to run {' '.join(args)}: {e}")


# Singleton hardware manager instance
hardware = HardwareManager()
