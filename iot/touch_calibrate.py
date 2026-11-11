#!/usr/bin/env python3
"""
Touch calibration test for the 3.5" (480x320) ADS7846 resistive LCD.

16 points (4 x 4 grid, default) or 5 points (corners + centre, --points 5).
Taps go through the same ghost-touch filter as the dashboard (touch_driver.
filter_tap); rejected touches are counted and reported. For every target it
records the raw ADS7846 reading, then fits a new 6-parameter affine matrix (least squares) and
shows, per point, how far off the CURRENT calibration lands versus the new fit.
After that, tap anywhere to see where touches land, then tap Save new or
Keep current. Nothing is written unless Save new is tapped.

Run with the dashboard stopped (it owns the LCD and the touch device):
    sudo systemctl stop iot-dashboard
    sudo QT_QPA_PLATFORM=linuxfb:fb=/dev/fb1 python3 touch_calibrate.py [--points 16|5]
    sudo systemctl start iot-dashboard

Results are also written to /tmp/touch_cal_result.json.
"""

import os
import sys
import json
import math
import time
import threading
from pathlib import Path

from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtCore import Qt, QTimer, QRectF, QPointF, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPen, QFont

from touch_driver import HardwareTouchInjector, DEFAULT_CALIB_PATH, DEFAULT_EVENT_DEVICE, read_taps

W, H = 480, 320
INSET = 30
POINTS = 5 if "--points" in sys.argv and sys.argv[sys.argv.index("--points") + 1] == "5" else 16
if POINTS == 5:
    TARGETS = [(INSET, INSET), (W - INSET, INSET), (W - INSET, H - INSET), (INSET, H - INSET), (W // 2, H // 2)]
    NAMES = ["top-left", "top-right", "bottom-right", "bottom-left", "centre"]
else:
    # 4 x 4 grid, row by row
    XS = [INSET, 170, 310, W - INSET]
    YS = [INSET, 117, 203, H - INSET]
    TARGETS = [(x, y) for y in YS for x in XS]
    NAMES = [f"r{r + 1}c{c + 1}" for r in range(4) for c in range(4)]
RESULT_FILE = Path("/tmp/touch_cal_result.json")
IDLE_TIMEOUT_S = 240

BG, TEXT, MUTED, LEAF, SUN, ALERT, WATER = "#0f1410", "#eef3ea", "#93a394", "#8fd16a", "#f4b04a", "#ef5d50", "#4cb8e0"


def apply(t, rx, ry):
    return t["a"] * rx + t["b"] * ry + t["c"], t["d"] * rx + t["e"] * ry + t["f"]


def solve3(m, v):
    """Solves a 3x3 linear system with Cramer's rule."""
    def det(a):
        return (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
                - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
                + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
    d = det(m)
    if abs(d) < 1e-9:
        raise ValueError("points are collinear")
    out = []
    for i in range(3):
        mi = [row[:] for row in m]
        for r in range(3):
            mi[r][i] = v[r]
        out.append(det(mi) / d)
    return out


def fit_affine(raw, screen):
    """Least-squares fit of screen = A * [rx, ry, 1] from point pairs."""
    m = [[0.0] * 3 for _ in range(3)]
    vx, vy = [0.0] * 3, [0.0] * 3
    for (rx, ry), (sx, sy) in zip(raw, screen):
        row = (rx, ry, 1.0)
        for i in range(3):
            for j in range(3):
                m[i][j] += row[i] * row[j]
            vx[i] += row[i] * sx
            vy[i] += row[i] * sy
    a, b, c = solve3(m, vx)
    d, e, f = solve3(m, vy)
    return {"a": a, "b": b, "c": c, "d": d, "e": e, "f": f}


class RawTouchReader(threading.Thread):
    """Filtered raw taps from the ADS7846 (median point, ghost touches rejected)."""

    def __init__(self, on_tap, on_reject, device):
        super().__init__(daemon=True)
        self.on_tap, self.on_reject, self.device = on_tap, on_reject, device

    def run(self):
        read_taps(self.device, lambda x, y, info: self.on_tap(int(x), int(y), info["samples"], info["spread_raw"]),
                  self.on_reject)


class CalibrationScreen(QWidget):
    tapped = pyqtSignal(int, int, int, int)
    rejected = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setFixedSize(W, H)
        self.current = HardwareTouchInjector(lambda *_: None).transform
        self.step = 0
        self.raw = []
        self.spreads = []
        self.rejects = []
        self.new = None
        self.errors_old, self.errors_new = [], []
        self.test_points = []
        self.phase = "collect"     # collect -> results -> done
        self.status = ""
        self.last_activity = time.time()
        self.tapped.connect(self.on_tap)
        self.rejected.connect(self.on_reject)

        dev = DEFAULT_EVENT_DEVICE if os.path.exists(DEFAULT_EVENT_DEVICE) else "/dev/input/event0"
        RawTouchReader(self.tapped.emit, self.rejected.emit, dev).start()
        t = QTimer(self)
        t.timeout.connect(self.check_idle)
        t.start(1000)

    # ------------------------------------------------------------ flow
    def check_idle(self):
        if time.time() - self.last_activity > IDLE_TIMEOUT_S:
            self.finish(saved=False, reason="timeout")

    def on_reject(self, reason):
        self.rejects.append({"phase": self.phase, "step": self.step, "reason": reason})
        if self.phase == "collect":
            self.status = f"Ignored a touch ({reason}). Press firmly and hold."
            self.update()

    def on_tap(self, rx, ry, samples, spread):
        self.last_activity = time.time()
        if self.phase == "collect":
            self.raw.append((rx, ry))
            self.spreads.append(spread)
            self.step += 1
            self.status = ""
            if self.step == len(TARGETS):
                self.compute()
            self.update()
        elif self.phase == "results":
            x, y = apply(self.new, rx, ry)
            if self.save_rect().contains(QPointF(x, y)):
                self.finish(saved=True)
            elif self.keep_rect().contains(QPointF(x, y)):
                self.finish(saved=False)
            else:
                ox, oy = apply(self.current, rx, ry)
                self.test_points = (self.test_points + [((x, y), (ox, oy))])[-6:]
                self.update()

    def compute(self):
        try:
            self.new = fit_affine(self.raw, TARGETS)
        except ValueError:
            self.raw, self.spreads, self.step = [], [], 0
            self.status = "Points were not spread out. Starting again."
            return
        for (rx, ry), (tx, ty) in zip(self.raw, TARGETS):
            ox, oy = apply(self.current, rx, ry)
            nx, ny = apply(self.new, rx, ry)
            self.errors_old.append(math.hypot(ox - tx, oy - ty))
            self.errors_new.append(math.hypot(nx - tx, ny - ty))
        self.phase = "results"
        self.write_result(saved=False, reason="pending")

    def write_result(self, saved, reason):
        res = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "outcome": reason,
            "saved": saved,
            "points": POINTS,
            "rejected_touches": self.rejects,
            "targets": [{"name": n, "screen": list(t), "raw": list(r), "spread_raw": sp,
                         "error_current_px": round(eo, 1), "error_new_px": round(en, 1)}
                        for n, t, r, sp, eo, en in zip(NAMES, TARGETS, self.raw, self.spreads,
                                                       self.errors_old, self.errors_new)],
            "current_transform": self.current,
            "new_transform": self.new,
        }
        if self.errors_old:
            res["current_avg_px"] = round(sum(self.errors_old) / len(self.errors_old), 1)
            res["current_max_px"] = round(max(self.errors_old), 1)
            res["new_avg_px"] = round(sum(self.errors_new) / len(self.errors_new), 1)
            res["new_max_px"] = round(max(self.errors_new), 1)
        RESULT_FILE.write_text(json.dumps(res, indent=2))

    def finish(self, saved, reason=None):
        if saved:
            path = Path(DEFAULT_CALIB_PATH)
            data = {}
            try:
                data = json.loads(path.read_text())
            except Exception:
                pass
            if path.exists():
                path.with_suffix(".json.bak").write_text(path.read_text())
            data["transform"] = self.new
            data["calibrated"] = time.strftime("%Y-%m-%d %H:%M:%S")
            data["points"] = POINTS
            path.write_text(json.dumps(data, indent=2))
        self.write_result(saved=saved, reason=reason or ("saved" if saved else "kept"))
        self.phase = "done"
        self.status = "Saved new calibration." if saved else ("Timed out, nothing saved." if reason == "timeout"
                                                              else "Kept the current calibration.")
        self.update()
        QTimer.singleShot(2500, QApplication.instance().quit)

    # ---------------------------------------------------------- drawing
    # Buttons sit in the band between grid rows 2 and 3 (y 117 / 203)
    def save_rect(self):
        return QRectF(250, 138, 210, 44)

    def keep_rect(self):
        return QRectF(20, 138, 210, 44)

    def text(self, p, rect, s, size, color, bold=False, align=Qt.AlignCenter):
        f = QFont("DejaVu Sans")
        f.setPixelSize(size)
        f.setBold(bold)
        p.setFont(f)
        p.setPen(QColor(color))
        p.drawText(rect, align | Qt.TextWordWrap, s)

    def cross(self, p, x, y, color, r=14, w=2):
        p.setPen(QPen(QColor(color), w))
        p.drawLine(QPointF(x - r, y), QPointF(x + r, y))
        p.drawLine(QPointF(x, y - r), QPointF(x, y + r))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(BG))
        if self.phase == "collect":
            # Text lives in the bands between target rows so it never covers a target
            self.text(p, QRectF(0, 140, W, 22), f"Touch calibration · point {min(self.step + 1, POINTS)} of {POINTS}",
                      17, TEXT, True)
            self.text(p, QRectF(0, 162, W, 18), "Press the centre of the green target firmly and hold half a second",
                      11, MUTED)
            if self.status:
                self.text(p, QRectF(0, 225, W, 18), self.status, 12, SUN, True)
            for i, (x, y) in enumerate(TARGETS):
                if i < self.step:
                    self.cross(p, x, y, MUTED, 8, 2)
            if self.step < len(TARGETS):
                x, y = TARGETS[self.step]
                p.setPen(QPen(QColor(LEAF), 2))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(x, y), 16, 16)
                p.drawEllipse(QPointF(x, y), 6, 6)
                self.cross(p, x, y, LEAF, 22, 2)
            self.text(p, QRectF(0, 64, W, 18), f"Ignored touches: {len(self.rejects)}  ·  exits after 4 min idle",
                      11, "#5f6e60")
            return

        # Results
        avg_o = sum(self.errors_old) / len(self.errors_old)
        avg_n = sum(self.errors_new) / len(self.errors_new)
        col = LEAF if max(self.errors_old) <= 8 else SUN if max(self.errors_old) <= 15 else ALERT
        self.text(p, QRectF(0, 50, W, 20), f"{POINTS}-point test · current avg {avg_o:.1f} px, worst "
                  f"{max(self.errors_old):.1f} px", 13, col, True)
        self.text(p, QRectF(0, 70, W, 18), f"New fit avg {avg_n:.1f} px, worst {max(self.errors_new):.1f} px"
                  f"  ·  ignored touches {len(self.rejects)}", 12, LEAF, True)
        for i, (x, y) in enumerate(TARGETS):
            self.cross(p, x, y, MUTED, 10, 1)
            ox, oy = apply(self.current, *self.raw[i])
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(ALERT))
            p.drawEllipse(QPointF(ox, oy), 4, 4)
            p.setBrush(QColor(LEAF))
            nx, ny = apply(self.new, *self.raw[i])
            p.drawEllipse(QPointF(nx, ny), 3, 3)
            e = self.errors_old[i]
            ecol = LEAF if e <= 8 else SUN if e <= 15 else ALERT
            lx = x - 44 if x > W / 2 else x + 10
            self.text(p, QRectF(lx, y + 4, 36, 14), f"{e:.0f}", 11, ecol, True,
                      Qt.AlignRight if x > W / 2 else Qt.AlignLeft)
        self.text(p, QRectF(0, 92, W, 16), "Numbers: current error in px · red = current, green = new fit", 11, MUTED)
        self.text(p, QRectF(0, 184, W, 16), "Tap anywhere to test (blue = new, red = current)", 11, MUTED)
        for (nx, ny), (ox, oy) in self.test_points:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(ALERT))
            p.drawEllipse(QPointF(ox, oy), 3, 3)
            self.cross(p, nx, ny, WATER, 9, 2)

        for rect, label, fill, fg in ((self.keep_rect(), "Keep current", "#1f2a21", TEXT),
                                      (self.save_rect(), "Save new", LEAF, BG)):
            p.setPen(QPen(QColor("#2c3a2e"), 1))
            p.setBrush(QColor(fill))
            p.drawRoundedRect(rect, 10, 10)
            self.text(p, rect, label, 15, fg, True)
        if self.phase == "done":
            p.fillRect(self.rect(), QColor(15, 20, 16, 230))
            self.text(p, QRectF(0, 140, W, 40), self.status, 18, LEAF, True)


def main():
    os.environ["QT_QPA_FB_DISABLE_INPUT"] = "1"  # raw taps come from RawTouchReader only
    app = QApplication(sys.argv)
    w = CalibrationScreen()
    w.showFullScreen()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
