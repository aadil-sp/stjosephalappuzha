#!/usr/bin/env python3
"""
Main Application Launcher for Smart IoT Agriculture & Irrigation System
Starts background FastAPI telemetry server (port 8000) and launches
the native PyQt5 3.5" (480x320) resistive touchscreen GUI.
"""

import sys
import os
import threading
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

# Touch input comes only from touch_driver (calibrated + ghost-filtered). Qt's
# linuxfb platform would otherwise also read the ADS7846 through libinput/evdev
# with raw, uncalibrated coordinates, so each tap clicked a second, wrong spot.
os.environ["QT_QPA_FB_DISABLE_INPUT"] = "1"

from PyQt5.QtWidgets import QApplication
from dashboard_app import IoTTouchDashboard, THEME, px_font
from web_server import web_app
import uvicorn


def start_api_server():
    """Runs FastAPI background server on port 8000."""
    try:
        print("[API] Starting background telemetry web server on http://0.0.0.0:8000...", flush=True)
        uvicorn.run(web_app, host="0.0.0.0", port=8000, log_level="warning")
    except Exception as e:
        print(f"[API] Error running web server: {e}", flush=True)


def main():
    fullscreen = "--fullscreen" in sys.argv

    # Start FastAPI server in background thread
    api_thread = threading.Thread(target=start_api_server, daemon=True)
    api_thread.start()

    # Start PyQt5 Touchscreen GUI
    print("[GUI] Launching native 480x320 Touchscreen Dashboard...", flush=True)
    app = QApplication(sys.argv)
    app.setFont(px_font(13))
    app.setStyleSheet(THEME)

    window = IoTTouchDashboard(fullscreen=fullscreen)
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
