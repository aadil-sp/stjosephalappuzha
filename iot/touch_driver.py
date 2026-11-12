"""
Touch Driver for 3.5" (480x320) TFT LCD Resistive Touchscreen (ADS7846 on SPI)
Preserves calibrated 6-parameter affine transformation matrix and translates
raw SPI touch input events into synthetic Qt mouse clicks.

Resistive panels report garbage while the finger lands and lifts, and the kernel
overlay does no debouncing, so every tap is filtered (filter_tap): too-short
presses are ignored as ghost touches, the lift-off samples are dropped, and the
tap position is the median of the remaining samples with outliers removed.
"""

import os
import json
import struct
import time
import threading
from pathlib import Path
from PyQt5.QtCore import QPoint, Qt, QEvent
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import QAbstractButton, QApplication

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CALIB_PATH = SCRIPT_DIR / "config" / "touch_calibration.json"
DEFAULT_EVENT_DEVICE = "/dev/input/by-path/platform-fe204000.spi-cs-1-event"

MIN_SAMPLES = 3          # fewer samples than this = ghost touch
LIFT_OFF_SAMPLES = 2     # last samples before release are unreliable
OUTLIER_RAW = 150        # ~19 px on this panel (about 7.8 raw units per pixel)
DEBOUNCE_S = 0.15        # ignore a new press this soon after the last tap


def _median(v):
    v = sorted(v)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def filter_tap(samples):
    """Reduces the raw (x, y) samples of one press to a single point.
    Returns ((raw_x, raw_y), info) or (None, reason)."""
    n = len(samples)
    if n < MIN_SAMPLES:
        return None, f"ghost ({n} samples)"
    pts = samples[:-LIFT_OFF_SAMPLES] if n > MIN_SAMPLES + LIFT_OFF_SAMPLES else samples
    mx, my = _median([p[0] for p in pts]), _median([p[1] for p in pts])
    kept = [p for p in pts if abs(p[0] - mx) <= OUTLIER_RAW and abs(p[1] - my) <= OUTLIER_RAW]
    if len(kept) < 2:
        return None, f"unstable ({n} samples)"
    rx, ry = _median([p[0] for p in kept]), _median([p[1] for p in kept])
    spread = max(max(abs(p[0] - rx), abs(p[1] - ry)) for p in kept)
    return (rx, ry), {"samples": n, "kept": len(kept), "spread_raw": round(spread)}


def read_taps(device, on_tap, on_reject=None):
    """Blocking loop over the evdev device: calls on_tap(rx, ry, info) for each
    filtered tap and on_reject(reason) for each rejected one."""
    fmt = "qqHHi"  # 64-bit struct input_event: timeval (qq), type (H), code (H), value (i)
    size = struct.calcsize(fmt)
    samples, down, cx, cy = [], False, None, None
    last_tap = 0.0
    with open(device, "rb") as f:
        while True:
            data = f.read(size)
            if len(data) < size:
                return
            _, _, typ, code, val = struct.unpack(fmt, data)
            if typ == 3 and code == 0:        # ABS_X
                cx = val
            elif typ == 3 and code == 1:      # ABS_Y
                cy = val
            elif typ == 0:                    # SYN_REPORT: one complete sample
                if down and cx is not None and cy is not None:
                    samples.append((cx, cy))
            elif typ == 1 and code == 330:    # BTN_TOUCH
                if val == 1:
                    down, samples = True, []
                elif down:
                    down = False
                    point, info = filter_tap(samples)
                    now = time.time()
                    if point and now - last_tap < DEBOUNCE_S:
                        point, info = None, "bounce"
                    if point:
                        last_tap = now
                        on_tap(point[0], point[1], info)
                    elif on_reject:
                        on_reject(info)


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
            read_taps(dev, lambda x, y, info: self.process_touch(x, y),
                      lambda reason: print(f"[TouchDriver] Ignored touch: {reason}", flush=True))
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
    Taps go to an open modal dialog (e.g. the on-screen keyboard) when there is one.
    """
    global_pos = window.mapToGlobal(QPoint(x, y))
    top = QApplication.activeModalWidget() or window
    pos = top.mapFromGlobal(global_pos)
    widget = top.childAt(pos)
    if widget:
        target = widget
        # Traverse up if child label inside a button
        while target and not isinstance(target, QAbstractButton) and target != top:
            target = target.parent()

        if isinstance(target, QAbstractButton):
            if target.isEnabled():
                target.animateClick(85)
        else:
            local_pos = widget.mapFromGlobal(global_pos)
            press = QMouseEvent(QEvent.MouseButtonPress, local_pos, global_pos, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
            release = QMouseEvent(QEvent.MouseButtonRelease, local_pos, global_pos, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
            widget.event(press)
            widget.event(release)
