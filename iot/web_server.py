"""
FastAPI web server for the Smart Farm dashboard.
Serves the browser dashboard (dashboard/index.html) and the REST API used by it:
live telemetry, crop profiles, cutoffs, water and fertilizer pumps, rain tank
alert and calibration, daily advice, Farm AI (Gemini), Alappuzha weather,
simulator, Wi-Fi and device actions.
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
from hardware_manager import hardware, CROP_PRESETS, run_privileged
from icons import svg_symbols
from weather import weather
from farm_ai import ai, AIError
import app_access
import wifi_manager

DASHBOARD_HTML = Path(__file__).resolve().parent / "dashboard" / "index.html"

web_app = FastAPI(title="Smart Farm IoT Hub")


@web_app.middleware("http")
async def require_app_key(request: Request, call_next):
    # Local network: open. Internet (tunnel) and the Android app: X-Farm-Key required
    host = request.client.host if request.client else ""
    if app_access.needs_key(host, request.headers) and not app_access.key_ok(request.headers.get("x-farm-key")):
        return JSONResponse({"status": "error", "message": "Access key required"}, status_code=401)
    return await call_next(request)


class CutoffSettings(BaseModel):
    dry_cutoff: float
    stop_cutoff: float


class CropSelection(BaseModel):
    crop_key: str


class SimulatorSettings(BaseModel):
    enabled: bool = None
    temperature: float = None
    humidity: float = None
    soil_moisture: float = None
    tank_level: float = None


class TankCalibration(BaseModel):
    height_cm: float = None    # sensor to tank floor (= distance when empty)
    full_gap_cm: float = None  # sensor to water surface when full
    area_cm2: float = None     # water surface area, converts cm to litres


class TankMark(BaseModel):
    which: str  # "empty" or "full"


class PumpState(BaseModel):
    on: bool
    minutes: float = None  # run time; defaults to the auto-off limit


class PumpDirection(BaseModel):
    pump: str          # "pump" (pump 1) or "fert" (pump 2)
    reverse: bool


class FarmSettings(BaseModel):
    crop_stage: str = None
    field_area_m2: float = None
    water_lpm: float = None
    fert_lpm: float = None
    feed_litres: float = None
    tank_alert_pct: float = None
    fert_manual_max_min: float = None


class AIKey(BaseModel):
    key: str = ""


class AIRequest(BaseModel):
    text: Optional[str] = None


class AIApply(BaseModel):
    index: int = 0


class WifiConnectionRequest(BaseModel):
    ssid: str
    password: str = ""


@web_app.get("/", response_class=HTMLResponse)
def index():
    # Read per request so dashboard edits show up without restarting the service
    return DASHBOARD_HTML.read_text(encoding="utf-8").replace("<!--ICONS-->", svg_symbols())


@web_app.get("/api/telemetry")
def get_telemetry():
    return JSONResponse(hardware.get_telemetry())


@web_app.post("/api/simulator/toggle")
def toggle_simulator():
    new_state = hardware.toggle_simulator_mode()
    return JSONResponse({"simulator_mode": new_state})


@web_app.post("/api/simulator/set")
def set_simulator_sensors(req: SimulatorSettings):
    if req.enabled is not None:
        hardware.set_simulator_mode(req.enabled)
    hardware.set_simulated_sensors(
        temp=req.temperature,
        humidity=req.humidity,
        soil_moisture=req.soil_moisture,
        tank_level=req.tank_level
    )
    return JSONResponse({
        "status": "success",
        "simulator_mode": hardware.simulator_mode,
        "temperature": hardware.sim_temp,
        "humidity": hardware.sim_humidity,
        "soil_moisture": hardware.sim_soil_moisture,
        "tank_level": hardware.sim_tank_level
    })


@web_app.post("/api/pump/toggle")
def toggle_pump():
    new_state = hardware.toggle_pump()
    return JSONResponse({"pump_on": new_state, "pump_status": "ON" if new_state else "OFF"})


@web_app.post("/api/pump/mode")
def toggle_mode():
    new_mode = hardware.toggle_mode()
    return JSONResponse({"mode": new_mode})


@web_app.post("/api/settings/cutoffs")
def set_cutoffs(settings: CutoffSettings):
    hardware.set_cutoffs(settings.dry_cutoff, settings.stop_cutoff)
    return JSONResponse({
        "status": "success",
        "dry_cutoff": hardware.soil_dry_threshold,
        "stop_cutoff": hardware.soil_target_moisture
    })


@web_app.post("/api/fert/toggle")
def toggle_fert_pump():
    return JSONResponse({"fert_pump_on": hardware.toggle_fert_pump()})


@web_app.post("/api/fert/set")
def set_fert_pump(req: PumpState):
    return JSONResponse({"fert_pump_on": hardware.set_fert_pump(req.on, req.minutes)})


@web_app.post("/api/settings/farm")
def set_farm_settings(req: FarmSettings):
    hardware.set_farm_settings(**req.dict())
    return JSONResponse(hardware.get_telemetry()["farm"])


@web_app.post("/api/settings/direction")
def set_direction(req: PumpDirection):
    if req.pump not in ("pump", "fert"):
        return JSONResponse({"status": "error", "message": "pump must be 'pump' or 'fert'"}, status_code=400)
    hardware.set_pump_direction(req.pump, req.reverse)
    return JSONResponse({"pump_reverse": hardware.pump_reverse})


@web_app.post("/api/test/input/{n}")
def test_input(n: int):
    if n not in (1, 2, 3, 4):
        return JSONResponse({"status": "error", "message": "input must be 1-4"}, status_code=400)
    hardware.test_driver_input(n)
    return JSONResponse({"status": "testing", "input": n})


@web_app.get("/api/advice")
def get_advice():
    return JSONResponse(hardware.get_advice())


@web_app.get("/api/ai/status")
def ai_status():
    return JSONResponse(ai.status())


@web_app.post("/api/ai/key")
def ai_key(req: AIKey):
    # Write-only: the key is never sent back, only its last 4 characters
    try:
        ai.set_key(req.key)
    except AIError as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=400)
    return JSONResponse(ai.status())


@web_app.post("/api/ai/{task}")
def ai_start(task: str, req: AIRequest = None):
    if task not in ai.TASKS:
        return JSONResponse({"status": "error", "message": "Unknown task"}, status_code=404)
    ai.start(task, force=True, text=req.text if req else None)
    return JSONResponse(ai.status())


@web_app.post("/api/ai/apply/{what}")
def ai_apply(what: str, req: AIApply = None):
    try:
        if what == "crop":
            ai.apply_crop()
        elif what == "param":
            ai.apply_param(req.index if req else 0)
        else:
            return JSONResponse({"status": "error", "message": "Unknown"}, status_code=404)
    except AIError as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=400)
    return JSONResponse(ai.status())


@web_app.get("/api/weather")
def get_weather():
    return JSONResponse(weather.get())


@web_app.post("/api/weather/refresh")
def refresh_weather():
    weather.refresh()
    return JSONResponse({"status": "refreshing"})


@web_app.post("/api/tank/reset")
def reset_tank():
    hardware.reset_tank()
    return JSONResponse(hardware.get_telemetry()["tank"])


@web_app.post("/api/tank/calibrate")
def calibrate_tank(req: TankCalibration):
    empty, full = hardware.set_tank_calibration(empty_cm=req.height_cm, full_cm=req.full_gap_cm,
                                                area_cm2=req.area_cm2)
    return JSONResponse({"status": "success", "height_cm": empty, "full_gap_cm": full,
                         "area_cm2": hardware.tank_area_cm2})


@web_app.post("/api/tank/mark")
def mark_tank(req: TankMark):
    if req.which not in ("empty", "full"):
        return JSONResponse({"status": "error", "message": "which must be 'empty' or 'full'"}, status_code=400)
    res = hardware.mark_tank(req.which)
    if res is None:
        return JSONResponse({"status": "error", "message": "No ultrasonic reading from the Arduino"}, status_code=409)
    return JSONResponse({"status": "success", "height_cm": res[0], "full_gap_cm": res[1]})


@web_app.get("/api/crops")
def get_crops():
    return JSONResponse(CROP_PRESETS)


@web_app.post("/api/crops/select")
def select_crop(req: CropSelection):
    hardware.set_crop(req.crop_key)
    return JSONResponse({
        "status": "success",
        "selected_crop": hardware.selected_crop,
        "dry_cutoff": hardware.soil_dry_threshold,
        "stop_cutoff": hardware.soil_target_moisture
    })


@web_app.get("/api/wifi/scan")
def get_wifi_scan():
    curr = wifi_manager.get_current_wifi()
    networks = wifi_manager.scan_wifi_networks()
    return JSONResponse({"current": curr, "networks": networks})


@web_app.post("/api/wifi/connect")
def connect_to_wifi(req: WifiConnectionRequest):
    res = wifi_manager.connect_wifi(req.ssid, req.password)
    return JSONResponse(res)


@web_app.get("/api/system/diagnostics")
def get_system_diagnostics():
    return JSONResponse(hardware.get_system_diagnostics())


@web_app.post("/api/system/restart-gui")
def api_restart_gui():
    run_privileged(["systemctl", "restart", "iot-dashboard.service"])
    return JSONResponse({"status": "restarting"})


@web_app.post("/api/system/reboot")
def api_reboot_pi():
    run_privileged(["reboot"])
    return JSONResponse({"status": "rebooting"})
