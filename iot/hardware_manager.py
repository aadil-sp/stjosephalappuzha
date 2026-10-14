"""
Hardware Manager for IoT Smart Agriculture & Irrigation System
Coordinates temperature, humidity, soil moisture readings, water pump relay control,
crop profiles, device diagnostics, and configurable cutoff thresholds.
"""

import time
import json
import math
import random
import threading
import subprocess
from pathlib import Path
from typing import Dict, Any

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
        self.real_water_level = 0
        self.last_hardware_packet_time = 0.0

        # Simulator Mode variables (controlled via UI sliders only when explicitly enabled)
        self.simulator_mode = False
        self.sim_temp = 28.0
        self.sim_humidity = 64.0
        self.sim_soil_moisture = 42.0

        self.pump_on = False
        self.pump_mode = "AUTO"  # "AUTO" or "MANUAL"

        # Crop selection & Cutoff Percentages
        self.selected_crop = "tomato"
        self.soil_dry_threshold = 35.0
        self.soil_target_moisture = 65.0
        self.load_settings()

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
                    "sim_soil_moisture": self.sim_soil_moisture
                }, f, indent=2)
            print(f"[Hardware] Saved settings to {SETTINGS_FILE}")
        except Exception as e:
            print(f"[Hardware] Error saving settings: {e}")
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

    def set_cutoffs(self, dry_cutoff: float, stop_cutoff: float):
        """Updates cutoff percentages safely."""
        with self.lock:
            self.soil_dry_threshold = max(5.0, min(80.0, float(dry_cutoff)))
            self.soil_target_moisture = max(self.soil_dry_threshold + 5.0, min(95.0, float(stop_cutoff)))
            # If values differ from preset, mark as custom
            curr_preset = CROP_PRESETS.get(self.selected_crop)
            if curr_preset and (self.soil_dry_threshold != curr_preset["dry_cutoff"] or self.soil_target_moisture != curr_preset["stop_cutoff"]):
                self.selected_crop = "custom"
        self.save_settings()
        self._send_serial_cmd(f"CUTOFF:{self.soil_dry_threshold}:{self.soil_target_moisture}\n")

    def adjust_dry_cutoff(self, delta: float) -> float:
        with self.lock:
            val = self.soil_dry_threshold + delta
            self.soil_dry_threshold = max(10.0, min(self.soil_target_moisture - 5.0, val))
            self.selected_crop = "custom"
            cur = self.soil_dry_threshold
        self.save_settings()
        self._send_serial_cmd(f"CUTOFF:{self.soil_dry_threshold}:{self.soil_target_moisture}\n")
        return cur

    def adjust_stop_cutoff(self, delta: float) -> float:
        with self.lock:
            val = self.soil_target_moisture + delta
            self.soil_target_moisture = max(self.soil_dry_threshold + 5.0, min(95.0, val))
            self.selected_crop = "custom"
            cur = self.soil_target_moisture
        self.save_settings()
        self._send_serial_cmd(f"CUTOFF:{self.soil_dry_threshold}:{self.soil_target_moisture}\n")
        self._check_auto_irrigation()
        return cur

    def set_simulator_mode(self, enabled: bool) -> bool:
        """Toggles manual simulator mode. When enabled, slider values override physical inputs."""
        with self.lock:
            self.simulator_mode = bool(enabled)
        self.save_settings()
        self._check_auto_irrigation()
        print(f"[Hardware] Simulator Mode -> {'ENABLED' if self.simulator_mode else 'DISABLED'}")
        return self.simulator_mode

    def toggle_simulator_mode(self) -> bool:
        return self.set_simulator_mode(not self.simulator_mode)

    def set_simulated_sensors(self, temp: float = None, humidity: float = None, soil_moisture: float = None):
        """Sets slider values for simulation. When simulator_mode is active, outputs update immediately."""
        with self.lock:
            if temp is not None:
                self.sim_temp = round(float(temp), 1)
            if humidity is not None:
                self.sim_humidity = round(float(humidity), 1)
            if soil_moisture is not None:
                self.sim_soil_moisture = round(float(soil_moisture), 1)

        self.save_settings()
        self._check_auto_irrigation()

    def _check_auto_irrigation(self):
        """Triggers real-time auto-irrigation evaluation when thresholds or moisture change."""
        with self.lock:
            if self.pump_mode != "AUTO":
                return

            if self.simulator_mode:
                soil = self.sim_soil_moisture
            elif self.is_hardware_online and self.real_soil_moisture is not None:
                soil = self.real_soil_moisture
            else:
                soil = None

            if soil is None:
                return

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

    def _send_serial_cmd(self, cmd_str: str):
        """Sends command to Arduino Mega via USB serial if connected."""
        if self.serial_conn and self.arduino_connected:
            with self.serial_lock:
                try:
                    self.serial_conn.write(cmd_str.encode('utf-8'))
                    self.serial_conn.flush()
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

        return {
            "cpu_temp": temp_str,
            "ram_usage": ram_str,
            "disk_usage": disk_str,
            "uptime": uptime_str,
            "lcd_driver": "ADS7846 6-Point Affine",
            "gpio_relay": "GPIO 17 (Pin 11)",
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

            pump = self.pump_on
            mode = self.pump_mode
            dry_cut = round(self.soil_dry_threshold, 1)
            stop_cut = round(self.soil_target_moisture, 1)
            crop_key = self.selected_crop

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
            "temperature_f": temp_f,
            "humidity": hum,
            "soil_moisture": soil,
            "soil_condition": condition,
            "soil_color": condition_color,
            "pump_status": "ON" if pump else "OFF",
            "pump_on": pump,
            "pump_mode": mode,
            "dry_cutoff": dry_cut,
            "stop_cutoff": stop_cut,
            "selected_crop": crop_key,
            "crop_name": crop_info["name"],
            "crop_icon": crop_info["icon"],
            "crop_desc": crop_info["desc"],
            "arduino_mega_online": hw_online,
            "hardware_connected": hw_online,
            "hardware_status": status_label,
            "simulator_mode": sim_mode,
            "sim_temp": self.sim_temp,
            "sim_humidity": self.sim_humidity,
            "sim_soil_moisture": self.sim_soil_moisture,
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
                        self._send_serial_cmd(f"CUTOFF:{self.soil_dry_threshold}:{self.soil_target_moisture}\n")
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
                        if "temp" in data:
                            self.real_temperature_c = float(data["temp"])
                        if "humidity" in data:
                            self.real_humidity = float(data["humidity"])
                        if "soil" in data:
                            self.real_soil_moisture = float(data["soil"])
                        if "rain" in data:
                            self.real_rain = int(data["rain"])
                        if "light" in data:
                            self.real_light = int(data["light"])
                        if "water_level" in data:
                            self.real_water_level = int(data["water_level"])
                        if "pump" in data and self.pump_mode == "AUTO":
                            self.pump_on = bool(data["pump"])
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
        while self.running:
            time.sleep(1.0)
            self._check_auto_irrigation()


# Singleton hardware manager instance
hardware = HardwareManager()
