"""
Touch Driver for 3.5" (480x320) TFT LCD Resistive Touchscreen (ADS7846 on SPI)
Preserves calibrated 6-parameter affine transformation matrix and translates
raw SPI touch input events into synthetic Qt mouse clicks.
"""

import os
import json
import struct
import threading
from pathlib import Path
from PyQt5.QtCore import QPoint, Qt, QEvent
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import QPushButton

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CALIB_PATH = SCRIPT_DIR / "config" / "touch_calibration.json"
DEFAULT_EVENT_DEVICE = "/dev/input/by-path/platform-fe204000.spi-cs-1-event"


class HardwareTouchInjector(threading.Thread):
    """
    Direct hardware touch event reader for ADS7846 resistive touchscreen on SPI.
    Applies calibrated 6-parameter affine transform to map raw coordinates to 480x320.
    """
    def __init__(self, callback, calib_file=None, event_device=None):
        super().__init__(daemon=True)
        self.callback = callback
        self.running = True
        self.calib_file = Path(calib_file) if calib_file else DEFAULT_CALIB_PATH
        self.event_device = event_device or DEFAULT_EVENT_DEVICE

        # Default fallback affine matrix if file not present
        self.transform = {
            "a": -0.12875132866286174,
            "b": 0.00015372302916662417,
            "c": 509.08178054973115,
            "d": 0.0007860774286883241,
            "e": 0.08632310571523769,
            "f": -19.936530956039377
        }
        self.load_calibration()

    def load_calibration(self):
        if self.calib_file.exists():
            try:
                with open(self.calib_file, "r") as f:
                    data = json.load(f)
                    if "transform" in data:
                        self.transform = data["transform"]
                        print(f"[TouchDriver] Loaded affine matrix: {self.transform}", flush=True)
            except Exception as e:
                print(f"[TouchDriver] Error loading calibration file: {e}. Using fallback defaults.", flush=True)
        else:
            print(f"[TouchDriver] Calibration file not found at {self.calib_file}. Using preset defaults.", flush=True)

    def run(self):
        # Resolve device path
        dev = self.event_device
        if not os.path.exists(dev):
            for fallback in ["/dev/input/event0", "/dev/input/event1", "/dev/input/event4"]:
                if os.path.exists(fallback):
                    dev = fallback
                    break
            else:
                print(f"[TouchDriver] No hardware touch event device found ({dev}). Touch injection disabled.", flush=True)
                return

        print(f"[TouchDriver] Listening for touch input on: {dev}", flush=True)
        try:
            with open(dev, "rb") as f:
                cur_x = None
                cur_y = None
                touch_down = False

                # struct input_event on 64-bit Linux: timeval (16 bytes: qq), type (H), code (H), value (i) = 24 bytes
                event_format = "qqHHi"
                event_size = struct.calcsize(event_format)

                while self.running:
                    data = f.read(event_size)
                    if not data or len(data) < event_size:
                        break

                    sec, usec, ev_type, ev_code, ev_val = struct.unpack(event_format, data)

                    if ev_type == 3:  # EV_ABS
                        if ev_code == 0:  # ABS_X
                            cur_x = ev_val
                        elif ev_code == 1:  # ABS_Y
                            cur_y = ev_val

                    elif ev_type == 1:  # EV_KEY
                        if ev_code == 330:  # BTN_TOUCH
                            if ev_val == 1:
                                touch_down = True
                            elif ev_val == 0 and touch_down:
                                touch_down = False
                                if cur_x is not None and cur_y is not None:
                                    self.process_touch(cur_x, cur_y)
                                    cur_x, cur_y = None, None

        except Exception as e:
            print(f"[TouchDriver] Touch reading error: {e}", flush=True)

    def process_touch(self, raw_x: int, raw_y: int):
        """
        Maps raw resistive touch values to calibrated 480x320 screen coordinates.
        """
        t = self.transform
        screen_x = int(t["a"] * raw_x + t["b"] * raw_y + t["c"])
        screen_y = int(t["d"] * raw_x + t["e"] * raw_y + t["f"])

        # Clamp to 3.5 inch LCD resolution bounds (480 x 320)
        screen_x = max(0, min(479, screen_x))
        screen_y = max(0, min(319, screen_y))

        # Forward calibrated coordinates to UI thread
        self.callback(screen_x, screen_y)


def inject_qt_click(window, x: int, y: int):
    """
    Simulates a crisp touch click on the Qt widget under (x, y).
    """
    pos = QPoint(x, y)
    widget = window.childAt(pos)
    if widget:
        target = widget
        # Traverse up if child label inside QPushButton
        while target and not isinstance(target, QPushButton) and target != window:
            if isinstance(target.parent(), QPushButton):
                target = target.parent()
                break
            target = target.parent()

        if isinstance(target, QPushButton):
            target.animateClick(85)
        else:
            local_pos = widget.mapFromGlobal(window.mapToGlobal(pos))
            press = QMouseEvent(QEvent.MouseButtonPress, local_pos, pos, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
            release = QMouseEvent(QEvent.MouseButtonRelease, local_pos, pos, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
            widget.event(press)
            widget.event(release)
