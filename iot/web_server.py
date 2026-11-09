"""
FastAPI web server for the Smart Farm dashboard.
Serves the browser dashboard (dashboard/index.html) and the REST API used by it:
live telemetry, crop profiles, cutoffs, pump control, simulator, Wi-Fi and device actions.
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from pathlib import Path
from hardware_manager import hardware, CROP_PRESETS, run_privileged
from icons import svg_symbols
import wifi_manager

DASHBOARD_HTML = Path(__file__).resolve().parent / "dashboard" / "index.html"

web_app = FastAPI(title="Smart Farm IoT Hub")


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


class TankCalibration(BaseModel):
    height_cm: float = None    # sensor to tank floor (= distance when empty)
    full_gap_cm: float = None  # sensor to water surface when full


class TankMark(BaseModel):
    which: str  # "empty" or "full"


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
        soil_moisture=req.soil_moisture
    )
    return JSONResponse({
        "status": "success",
        "simulator_mode": hardware.simulator_mode,
        "temperature": hardware.sim_temp,
        "humidity": hardware.sim_humidity,
        "soil_moisture": hardware.sim_soil_moisture
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


@web_app.post("/api/tank/calibrate")
def calibrate_tank(req: TankCalibration):
    empty, full = hardware.set_tank_calibration(empty_cm=req.height_cm, full_cm=req.full_gap_cm)
    return JSONResponse({"status": "success", "height_cm": empty, "full_gap_cm": full})


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
