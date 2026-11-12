#!/usr/bin/env python3
"""
Smart Farm touchscreen dashboard for the 3.5" (480x320) ADS7846 LCD on Raspberry Pi 4.

Tablet-style shell: a status bar (time, page title, link status), the page area,
and a navigation bar with Back, Home and Apps. Home is the farm dashboard
(Alappuzha weather, soil gauge, field sensors, today's advice, rain tank and both
pumps). Apps open from the app drawer: Today, Farm AI (Gemini brief, crop
profiles, settings check, questions), Water (pump 1), Fertilizer (pump 2), Rain tank, Weather, Crops, Simulator, Wi-Fi, Settings, Device and Wiring.
A full rain tank pops up an alert on every page until it is reset.

The resistive touch driver only delivers taps, so every control is a large
button, +/- stepper or number pad; nothing relies on dragging or scrolling.
"""

import os
import sys
import html
import math
import time
import socket
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QFrame, QGridLayout, QDialog
)
from PyQt5.QtCore import Qt, QTimer, QSize, QRectF, QPointF, QPoint, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QPainter, QPen, QFontMetricsF, QPainterPath

from hardware_manager import hardware, CROP_PRESETS, run_privileged
from touch_driver import HardwareTouchInjector, inject_qt_click
from keyboard_dialog import get_text_input
from icons import qt_pixmap, qt_icon
from weather import weather
from farm_ai import ai as farm_ai
import app_access
import wifi_manager

# ---------------------------------------------------------------------------
# Palette: dark "field instrument" theme (shared with the web dashboard)
# ---------------------------------------------------------------------------
C = {
    "bg": "#0f1410",
    "surface": "#172019",
    "raised": "#1f2a21",
    "line": "#2c3a2e",
    "text": "#eef3ea",
    "muted": "#93a394",
    "dim": "#5f6e60",
    "leaf": "#8fd16a",
    "leaf_bg": "#22331c",
    "water": "#4cb8e0",
    "sun": "#f4b04a",
    "tank": "#3fc1b0",
    "fert": "#c38fe0",
    "light": "#f5d76e",
    "alert": "#ef5d50",
    "alert_bg": "#3a1a17",
}

CROP_COLORS = {
    "tomato": "#ef6a5a", "paddy": "#e9c46a", "chilli": "#e4572e", "potato": "#c89f6b",
    "corn": "#f2c14e", "arid": "#8fd16a", "onion": "#c77dba", "custom": "#93a394",
}

# App drawer: key, name, icon, tile colour
APPS = [
    ("today", "Today", "calendar", "#3d8f5a"),
    ("ai", "Farm AI", "sparkle", "#b8487e"),
    ("water", "Water", "drop", "#2f86c9"),
    ("fert", "Fertilizer", "flask", "#9a5cc0"),
    ("tanks", "Rain tank", "tank", "#1d9488"),
    ("weather", "Weather", "cloudsun", "#d98a1f"),
    ("crops", "Crops", "sprout", "#4a9a40"),
    ("sim", "Simulator", "sliders", "#c95e34"),
    ("wifi", "Wi-Fi", "wifi", "#3a6fcc"),
    ("settings", "Settings", "gear", "#5f6d61"),
    ("device", "Device", "chip", "#5560ad"),
    ("wiring", "Wiring", "plug", "#a84b4b"),
]
TITLES = dict([("home", "Home"), ("apps", "Apps")] + [(k, n) for k, n, _, _ in APPS])

FONT = "DejaVu Sans"

THEME = f"""
QWidget {{
    background-color: {C['bg']};
    color: {C['text']};
}}
QLabel {{ background: transparent; }}
QWidget#Clear {{ background: transparent; }}
QWidget#Bar {{ background-color: {C['surface']}; }}
QWidget#Drawer {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #16281c, stop:1 #0c120e);
}}
QFrame#Card {{
    background-color: {C['surface']};
    border: 1px solid {C['line']};
    border-radius: 12px;
}}
QFrame#Card QLabel {{ background: transparent; border: none; }}
QPushButton {{
    background-color: {C['raised']};
    color: {C['text']};
    border: 1px solid {C['line']};
    border-radius: 10px;
    padding: 0px 8px;
}}
QPushButton:pressed {{ background-color: {C['line']}; }}
QPushButton:disabled {{ color: {C['dim']}; border-color: {C['raised']}; }}
QPushButton[tone="primary"] {{
    background-color: {C['leaf']};
    color: {C['bg']};
    border: 1px solid {C['leaf']};
}}
QPushButton[tone="fert"] {{
    background-color: {C['fert']};
    color: {C['bg']};
    border: 1px solid {C['fert']};
}}
QPushButton[tone="water"] {{
    background-color: {C['water']};
    color: {C['bg']};
    border: 1px solid {C['water']};
}}
QPushButton[tone="selected"] {{
    background-color: {C['leaf_bg']};
    color: {C['leaf']};
    border: 2px solid {C['leaf']};
}}
QPushButton[tone="quiet"] {{
    background-color: transparent;
    color: {C['muted']};
    border: 1px solid {C['line']};
}}
QPushButton[tone="danger"] {{
    background-color: {C['alert_bg']};
    color: {C['alert']};
    border: 1px solid #6b2a24;
}}
QPushButton[tone="danger-armed"] {{
    background-color: {C['alert']};
    color: {C['bg']};
    border: 1px solid {C['alert']};
}}
QPushButton[card="true"] {{
    background-color: {C['surface']};
    border: 1px solid {C['line']};
    border-radius: 12px;
    padding: 0px;
}}
QPushButton[card="true"]:pressed {{ background-color: {C['raised']}; }}
QPushButton[app="true"] {{ background: transparent; border: none; padding: 0px; }}
QPushButton[app="true"]:pressed {{ background-color: rgba(255, 255, 255, 18); border-radius: 14px; }}
QPushButton[navbar="true"] {{
    background-color: transparent;
    color: {C['muted']};
    border: none;
    border-radius: 15px;
}}
QPushButton[navbar="true"]:pressed {{ background-color: {C['raised']}; }}
QPushButton[navhome="true"] {{
    background-color: {C['raised']};
    border: 1px solid {C['line']};
    border-radius: 15px;
}}
QPushButton[row="true"] {{ text-align: left; padding-left: 12px; }}
"""


def px_font(size, bold=False):
    f = QFont(FONT)
    f.setPixelSize(size)
    f.setBold(bold)
    return f


def label(text="", size=13, color=None, bold=False, align=None):
    lbl = QLabel(text)
    lbl.setFont(px_font(size, bold))
    if color:
        lbl.setStyleSheet(f"color: {color};")
    if align is not None:
        lbl.setAlignment(align)
    return lbl


def set_color(lbl, color):
    css = f"color: {color};"
    if lbl.styleSheet() != css:
        lbl.setStyleSheet(css)


def caps(text, color=None):
    """Small uppercase section caption."""
    lbl = label(text.upper(), 11, color or C["muted"], bold=True)
    f = lbl.font()
    f.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)
    lbl.setFont(f)
    return lbl


def icon_label(name, color, size=22):
    lbl = QLabel()
    lbl.setFixedSize(size, size)
    set_icon(lbl, name, color, size)
    return lbl


def set_icon(lbl, name, color, size):
    """Sets a label's icon pixmap only when it changes (avoids repaints every refresh)."""
    key = (name, color, size)
    if getattr(lbl, "_icon_key", None) != key:
        lbl._icon_key = key
        lbl.setPixmap(qt_pixmap(name, color, size))


def set_button_icon(btn, name, color, size):
    key = (name, color, size)
    if getattr(btn, "_icon_key", None) != key:
        btn._icon_key = key
        btn.setIcon(qt_icon(name, color, size))
        btn.setIconSize(QSize(size, size))


def button(text="", icon=None, icon_color=None, icon_size=22, tone=None, h=44, w=None, size=14):
    btn = QPushButton(text)
    btn.setFocusPolicy(Qt.NoFocus)
    btn.setFont(px_font(size, True))
    if icon:
        set_button_icon(btn, icon, icon_color or C["text"], icon_size)
    if tone:
        btn.setProperty("tone", tone)
    btn.setFixedHeight(h)
    if w:
        btn.setFixedWidth(w)
    return btn


def set_tone(widget, tone):
    if widget.property("tone") == tone:
        return
    widget.setProperty("tone", tone)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def card():
    f = QFrame()
    f.setObjectName("Card")
    return f


def card_button():
    """A whole card that can be tapped."""
    b = QPushButton()
    b.setFocusPolicy(Qt.NoFocus)
    b.setProperty("card", True)
    return b


def clear_widget():
    w = QWidget()
    w.setObjectName("Clear")
    return w


def passthrough(*widgets):
    """Child widgets inside buttons must not swallow taps."""
    for w in widgets:
        w.setAttribute(Qt.WA_TransparentForMouseEvents)


def fmt_num(v, decimals=1):
    s = f"{v:.{decimals}f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


# ---------------------------------------------------------------------------
# Custom painted widgets
# ---------------------------------------------------------------------------
class ArcGauge(QWidget):
    """240-degree soil moisture gauge with dry (start) and target (stop) markers."""

    SWEEP = 240.0
    START = 210.0

    def __init__(self):
        super().__init__()
        self.value = None
        self.dry = 35.0
        self.stop = 65.0
        self.color = C["leaf"]
        self.caption = "--"
        self.setMinimumSize(110, 80)

    def set_state(self, value, dry, stop, color, caption):
        state = (value, dry, stop, color, caption)
        if state != (self.value, self.dry, self.stop, self.color, self.caption):
            self.value, self.dry, self.stop, self.color, self.caption = state
            self.update()

    def _point(self, cx, cy, radius, frac):
        a = math.radians(self.START - self.SWEEP * frac)
        return QPointF(cx + radius * math.cos(a), cy - radius * math.sin(a))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        thick = 10.0 if h < 110 else 12.0
        r = min(w / 2.0, (h - 8) / 1.5) - thick / 2 - 6
        cx, cy = w / 2.0, 6 + thick / 2 + r
        rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)

        p.setPen(QPen(QColor(C["raised"]), thick, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(rect, int(self.START * 16), int(-self.SWEEP * 16))

        if self.value is not None:
            frac = max(0.0, min(1.0, self.value / 100.0))
            if frac > 0:
                p.setPen(QPen(QColor(self.color), thick, Qt.SolidLine, Qt.RoundCap))
                p.drawArc(rect, int(self.START * 16), int(-self.SWEEP * 16 * frac))

        # Cutoff markers straddling the track
        for pct, col in ((self.dry, C["sun"]), (self.stop, C["water"])):
            frac = max(0.0, min(1.0, pct / 100.0))
            a = self._point(cx, cy, r - thick / 2 - 3, frac)
            b = self._point(cx, cy, r + thick / 2 + 3, frac)
            # Dark halo keeps the marker visible on a same-coloured value arc
            p.setPen(QPen(QColor(C["surface"]), 7, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(a, b)
            p.setPen(QPen(QColor(col), 3, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(a, b)

        # Value + unit, sized to the gauge
        big = max(16, int(r * 0.62))
        val = "--" if self.value is None else f"{self.value:.0f}"
        f_big, f_unit = px_font(big, True), px_font(max(10, int(big * 0.42)), True)
        tw = QFontMetricsF(f_big).horizontalAdvance(val)
        uw = QFontMetricsF(f_unit).horizontalAdvance("%")
        x0 = cx - (tw + uw + 2) / 2
        base = cy + big * 0.34
        p.setPen(QColor(C["text"]))
        p.setFont(f_big)
        p.drawText(QPointF(x0, base), val)
        p.setPen(QColor(C["muted"]))
        p.setFont(f_unit)
        p.drawText(QPointF(x0 + tw + 2, base), "%")

        # Condition caption in the gauge opening
        p.setPen(QColor(self.color))
        p.setFont(px_font(13 if r > 50 else 11, True))
        p.drawText(QRectF(0, cy + r * 0.52 - 8, w, 18), Qt.AlignCenter, self.caption)
        p.end()


class RangeBar(QWidget):
    """0-100% bar showing the watering band and the current soil reading."""

    def __init__(self):
        super().__init__()
        self.dry, self.stop, self.soil = 35.0, 65.0, None
        self.setFixedHeight(32)

    def set_state(self, dry, stop, soil):
        if (dry, stop, soil) != (self.dry, self.stop, self.soil):
            self.dry, self.stop, self.soil = dry, stop, soil
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width() - 12
        x0, y, bh = 6.0, 7.0, 10.0
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(C["raised"]))
        p.drawRoundedRect(QRectF(x0, y, w, bh), 5, 5)
        p.setBrush(QColor(C["leaf_bg"]))
        p.drawRect(QRectF(x0 + w * self.dry / 100, y, w * (self.stop - self.dry) / 100, bh))
        for pct, col in ((self.dry, C["sun"]), (self.stop, C["water"])):
            p.setBrush(QColor(col))
            p.drawRoundedRect(QRectF(x0 + w * pct / 100 - 2, y - 3, 4, bh + 6), 2, 2)
        if self.soil is not None:
            sx = x0 + w * max(0, min(100, self.soil)) / 100
            p.setBrush(QColor(C["text"]))
            p.drawEllipse(QPointF(sx, y + bh / 2), 6, 6)
        p.setPen(QColor(C["dim"]))
        p.setFont(px_font(11))
        p.drawText(QRectF(x0, y + bh + 3, 40, 14), Qt.AlignLeft, "0%")
        p.drawText(QRectF(x0 + w - 40, y + bh + 3, 40, 14), Qt.AlignRight, "100%")
        if self.soil is not None:
            p.setPen(QColor(C["muted"]))
            p.drawText(QRectF(x0, y + bh + 3, w, 14), Qt.AlignCenter, f"soil now {self.soil:.0f}%")
        p.end()


class TankGlyph(QWidget):
    """Tank drawing filled to the current level; the outline lights up while its pump runs."""

    def __init__(self, color, w, h):
        super().__init__()
        self.color = color
        self.level = None
        self.active = False
        self.setFixedSize(w, h)

    def set_state(self, level, active):
        if (level, active) != (self.level, self.active):
            self.level, self.active = level, active
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        body = QRectF(2, 2, self.width() - 4, self.height() - 4)
        path = QPainterPath()
        path.addRoundedRect(body, 7, 7)
        p.fillPath(path, QColor(C["raised"]))
        if self.level is not None and self.level > 0:
            fill_h = body.height() * self.level / 100.0
            p.save()
            p.setClipPath(path)
            col = QColor(self.color)
            col.setAlpha(210)
            p.fillRect(QRectF(body.left(), body.bottom() - fill_h, body.width(), fill_h), col)
            p.restore()
        # 25 / 50 / 75 % ticks
        p.setPen(QPen(QColor(C["line"]), 1))
        for frac in (0.25, 0.5, 0.75):
            y = body.bottom() - body.height() * frac
            p.drawLine(QPointF(body.right() - 7, y), QPointF(body.right() - 2, y))
        p.setPen(QPen(QColor(self.color if self.active else C["line"]), 2 if self.active else 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(body, 7, 7)
        if self.level is None:
            p.setPen(QColor(C["dim"]))
            p.setFont(px_font(16, True))
            p.drawText(body, Qt.AlignCenter, "?")
        p.end()


class Bar(QWidget):
    """Thin rounded progress bar."""

    def __init__(self, color, h=10):
        super().__init__()
        self.color = color
        self.frac = 0.0
        self.setFixedHeight(h)

    def set_value(self, frac):
        frac = max(0.0, min(1.0, frac))
        if abs(frac - self.frac) > 0.001:
            self.frac = frac
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.height() / 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(C["raised"]))
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), r, r)
        if self.frac > 0:
            p.setBrush(QColor(self.color))
            p.drawRoundedRect(QRectF(0, 0, max(self.height(), self.width() * self.frac), self.height()), r, r)
        p.end()


class Stepper(QFrame):
    """Label + value with large - / + buttons (tap-only friendly)."""

    def __init__(self, icon, title, color, on_step, step, fmt, compact=False):
        super().__init__()
        self.setObjectName("Card")
        self.fmt = fmt
        row = QHBoxLayout(self)
        row.setContentsMargins(8 if compact else 10, 4, 6, 4)
        row.setSpacing(6 if compact else 8)
        row.addWidget(icon_label(icon, color, 22))
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(label(title, 12, C["muted"], bold=True))
        self.val = label("--", 19, C["text"], bold=True)
        col.addWidget(self.val)
        row.addLayout(col, stretch=1)
        minus = button(icon="minus", w=44 if compact else 52, h=40)
        plus = button(icon="plus", w=44 if compact else 52, h=40)
        minus.clicked.connect(lambda: on_step(-step))
        plus.clicked.connect(lambda: on_step(step))
        row.addWidget(minus)
        row.addWidget(plus)
        self.setFixedHeight(52)

    def set_value(self, v):
        self.val.setText(self.fmt.format(v))


class NumPad(QDialog):
    """Tap-only number entry: digits, decimal point and backspace."""

    def __init__(self, parent, title, value, unit, decimals=1, max_value=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        self.setFixedSize(420, 290)
        self.setStyleSheet(f"QDialog {{ background-color: {C['surface']}; border: 2px solid {C['leaf']};"
                           f" border-radius: 14px; }}")
        self.original = value
        self.decimals = decimals
        self.max_value = max_value
        self.text = ""
        self.value = None

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 12, 12, 12)
        root.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(6)
        t = label(title, 14, C["muted"], bold=True)
        t.setWordWrap(True)
        left.addWidget(t)
        self.display = label("", 30, C["text"], bold=True)
        left.addWidget(self.display)
        left.addWidget(label(unit, 13, C["muted"], bold=True))
        self.hint = label("", 11, C["alert"])
        self.hint.setWordWrap(True)
        left.addWidget(self.hint)
        left.addStretch()
        ok = button("OK", icon="check", icon_color=C["bg"], tone="primary", h=46)
        ok.clicked.connect(self.on_ok)
        cancel = button("Cancel", tone="quiet", h=40)
        cancel.clicked.connect(self.reject)
        left.addWidget(ok)
        left.addWidget(cancel)
        root.addLayout(left, stretch=1)

        grid = QGridLayout()
        grid.setSpacing(6)
        keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "." if decimals else "", "0", "del"]
        for i, k in enumerate(keys):
            if not k:
                continue
            if k == "del":
                b = button(icon="backspace", icon_color=C["muted"], h=56, w=64)
            else:
                b = button(k, h=56, w=64, size=20)
            b.clicked.connect(lambda _, key=k: self.on_key(key))
            grid.addWidget(b, i // 3, i % 3)
        root.addLayout(grid)
        self.render()

    def showEvent(self, e):
        super().showEvent(e)
        par = self.parentWidget()
        if par:
            self.move(par.mapToGlobal(QPoint((par.width() - self.width()) // 2,
                                             (par.height() - self.height()) // 2)))

    def on_key(self, k):
        if k == "del":
            self.text = self.text[:-1]
        elif k == ".":
            if "." not in self.text:
                self.text = (self.text or "0") + "."
        else:
            if "." in self.text and len(self.text.split(".")[1]) >= self.decimals:
                return
            if len(self.text) < 7:
                self.text = self.text.lstrip("0") + k if self.text != "0" else k
        self.hint.setText("")
        self.render()

    def render(self):
        if self.text:
            self.display.setText(self.text)
            set_color(self.display, C["text"])
        else:
            self.display.setText(fmt_num(self.original, self.decimals))
            set_color(self.display, C["dim"])

    def on_ok(self):
        try:
            v = float(self.text) if self.text else self.original
        except ValueError:
            v = self.original
        if v <= 0:
            self.hint.setText("Enter a number above 0")
            return
        if self.max_value is not None and v > self.max_value:
            self.hint.setText(f"Maximum is {fmt_num(self.max_value)}")
            return
        self.value = v
        self.accept()


def get_number(parent, title, value, unit, decimals=1, max_value=None):
    dlg = NumPad(parent, title, value, unit, decimals, max_value)
    if dlg.exec_() == QDialog.Accepted:
        return dlg.value
    return None



# ---------------------------------------------------------------------------
# Rain tank card and full-tank alert
# ---------------------------------------------------------------------------
def tank_text(t):
    """(level text, detail text, colour) for the rain tank state dict."""
    if t["level"] is None:
        return "--", "No reading", C["dim"]
    if t["alert"]:
        return f"{t['level']}%", "FULL · release", C["alert"]
    return f"{t['level']}%", f"{fmt_num(t['litres'], 0)} / {fmt_num(t['capacity_l'], 0)} L", C["muted"]


class HomeTankCard(QPushButton):
    """Home screen rain tank: level and litres, red when full. Tap: Rain tank app."""

    def __init__(self, win):
        super().__init__()
        self.setFocusPolicy(Qt.NoFocus)
        self.setProperty("card", True)
        self.clicked.connect(lambda: win.open_page("tanks"))
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 7, 8, 7)
        row.setSpacing(8)
        self.glyph = TankGlyph(C["tank"], 30, 96)
        row.addWidget(self.glyph, alignment=Qt.AlignVCenter)
        col = QVBoxLayout()
        col.setSpacing(1)
        cap = caps("Rain tank")
        col.addWidget(cap)
        self.level = label("--", 24, C["text"], bold=True)
        col.addWidget(self.level)
        self.sub = label("", 11, C["muted"], bold=True)
        self.sub.setWordWrap(True)
        col.addWidget(self.sub)
        col.addStretch()
        row.addLayout(col, stretch=1)
        passthrough(self.glyph, cap, self.level, self.sub)
        self._alert = None

    def refresh(self, t):
        self.glyph.set_state(t["level"], t["alert"])
        lvl, sub, col = tank_text(t)
        self.level.setText(lvl)
        set_color(self.level, C["alert"] if t["alert"] else (C["text"] if t["level"] is not None else C["dim"]))
        self.sub.setText(sub)
        set_color(self.sub, col)
        if self._alert != t["alert"]:
            self._alert = t["alert"]
            self.setStyleSheet(f"QPushButton {{ border: 2px solid {C['alert']}; }}" if t["alert"] else "")


class TankAlert(QWidget):
    """Full-screen scrim with a 'rain tank full' card. Covers the whole window so a
    stray tap cannot hit the page underneath."""

    SNOOZE_S = 30 * 60

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.snooze_until = 0.0
        self.setObjectName("Scrim")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("QWidget#Scrim { background-color: rgba(0, 0, 0, 170); }")
        self.setGeometry(0, 0, 480, 320)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)
        box = QFrame()
        box.setObjectName("AlertBox")
        box.setStyleSheet(f"QFrame#AlertBox {{ background-color: {C['surface']}; border: 2px solid {C['alert']};"
                          f" border-radius: 14px; }}")
        outer.addWidget(box)
        col = QVBoxLayout(box)
        col.setContentsMargins(16, 12, 16, 12)
        col.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(icon_label("bell", C["alert"], 30))
        top.addWidget(label("Rain tank is full", 20, C["alert"], bold=True), stretch=1)
        col.addLayout(top)
        self.msg = label("", 13, C["text"])
        self.msg.setWordWrap(True)
        col.addWidget(self.msg, stretch=1)
        btns = QHBoxLayout()
        btns.setSpacing(10)
        later = button("Later", icon="clock", icon_color=C["muted"], tone="quiet", h=46)
        later.clicked.connect(self.on_later)
        reset = button("Released · Reset", icon="check", icon_color=C["bg"], tone="primary", h=46)
        reset.clicked.connect(self.on_reset)
        btns.addWidget(later, stretch=2)
        btns.addWidget(reset, stretch=3)
        col.addLayout(btns)
        self.hide()

    def on_later(self):
        self.snooze_until = time.time() + self.SNOOZE_S
        self.hide()

    def on_reset(self):
        hardware.reset_tank()
        self.hide()
        self.win.update_telemetry()

    def refresh(self, t):
        if t["alert"] and time.time() >= self.snooze_until:
            lvl = f"{t['level']}%" if t["level"] is not None else "full"
            self.msg.setText(f"Level {lvl} since {t['alert_since']}. Open the tank outlet and release "
                             f"the water, then tap Reset.")
            if not self.isVisible():
                self.show()
                self.raise_()
        elif self.isVisible() and not t["alert"]:
            self.hide()


class AdviceRow(QFrame):
    """One line of today's advice: icon, headline, explanation, optional note."""

    def __init__(self, icon, color, h=70):
        super().__init__()
        self.setObjectName("Card")
        self.setFixedHeight(h)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 5, 8, 5)
        row.setSpacing(10)
        self.icon = icon_label(icon, color, 26)
        row.addWidget(self.icon, alignment=Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(1)
        self.title = label("", 15, C["text"], bold=True)
        self.text = label("", 11, C["muted"])
        self.text.setWordWrap(True)
        col.addWidget(self.title)
        col.addWidget(self.text)
        col.addStretch()
        row.addLayout(col, stretch=1)
        self.side = QVBoxLayout()
        row.addLayout(self.side)

    def set(self, title, text, title_color=None):
        self.title.setText(title)
        set_color(self.title, title_color or C["text"])
        self.text.setText(text)


ADVICE_COLORS = {"water": C["water"], "light": C["water"], "skip": C["leaf"], "apply": C["fert"],
                 "postpone": C["sun"], "wait": C["muted"], "done": C["leaf"]}


# Motor driver input -> Mega pin, as wired (see firmware pump_motor / fert_motor)
DRIVER_PINS = {1: 5, 2: 7, 3: 6, 4: 8}


def self_web_url():
    """Web dashboard address on the local network (no traffic is sent)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
    except OSError:
        ip = "<pi-ip>"
    return f"http://{ip}:8000"


def fmt_secs(s):
    s = int(s)
    return f"{s // 60}:{s % 60:02d}"


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class IoTTouchDashboard(QMainWindow):
    hardware_touch_signal = pyqtSignal(int, int)

    WIFI_PAGE_SIZE = 4
    STATUS_H = 24
    NAV_H = 38
    ADVICE_MAX_AGE = 20

    def __init__(self, fullscreen: bool = False):
        super().__init__()
        self.setWindowTitle("Smart Farm")
        self.setFixedSize(480, 320)

        self.wifi_networks = []
        self.wifi_page = 0
        self.reboot_armed = False
        self.history = []
        self.current = None
        self.wifi_status = None
        self.advice = None
        self.advice_time = 0.0

        root = QWidget()
        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.build_status_bar())
        self.pages = QStackedWidget()
        lay.addWidget(self.pages, stretch=1)
        lay.addWidget(self.build_nav_bar())
        self.setCentralWidget(root)

        self.page_widgets = {}
        builders = {
            "home": self.build_home, "apps": self.build_drawer, "today": self.build_today, "ai": self.build_ai,
            "water": self.build_water, "fert": self.build_fert, "tanks": self.build_tanks,
            "weather": self.build_weather, "crops": self.build_crops, "sim": self.build_sim,
            "wifi": self.build_wifi, "settings": self.build_settings, "device": self.build_device,
            "wiring": self.build_wiring,
        }
        for key, build in builders.items():
            page = QWidget()
            if key == "apps":
                page.setObjectName("Drawer")
                page.setAttribute(Qt.WA_StyledBackground, True)
            build(page)
            self.page_widgets[key] = page
            self.pages.addWidget(page)

        self.tank_alert = TankAlert(self)

        self.hardware_touch_signal.connect(lambda x, y: inject_qt_click(self, x, y))
        self.touch_injector = HardwareTouchInjector(self.hardware_touch_signal.emit)
        self.touch_injector.start()

        self.open_page("home", push=False)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.update_telemetry)
        self.refresh_timer.start(500)
        self.wifi_timer = QTimer(self)
        self.wifi_timer.timeout.connect(self.update_wifi_status)
        self.wifi_timer.start(30000)
        QTimer.singleShot(1500, self.update_wifi_status)
        self.update_telemetry()

        if fullscreen:
            self.showFullScreen()
        else:
            self.show()

    # ------------------------------------------------------------ chrome
    def build_status_bar(self):
        bar = QWidget()
        bar.setObjectName("Bar")
        bar.setAttribute(Qt.WA_StyledBackground, True)
        bar.setFixedHeight(self.STATUS_H)
        row = QHBoxLayout(bar)
        row.setContentsMargins(10, 0, 8, 0)
        row.setSpacing(6)

        left = QHBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(6)
        self.lbl_clock = label("--:--", 13, C["text"], bold=True)
        self.lbl_date = label("", 11, C["muted"])
        left.addWidget(self.lbl_clock)
        left.addWidget(self.lbl_date)
        left.addStretch()
        lw = clear_widget()
        lw.setLayout(left)
        lw.setFixedWidth(136)
        row.addWidget(lw)

        self.lbl_title = label("", 13, C["text"], bold=True, align=Qt.AlignCenter)
        row.addWidget(self.lbl_title, stretch=1)

        right = QHBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(6)
        right.addStretch()
        self.lbl_badge = label("TANK FULL", 10, C["bg"], bold=True)
        self.lbl_badge.setStyleSheet(f"color: {C['bg']}; background: {C['alert']}; border-radius: 8px; padding: 1px 6px;")
        self.lbl_badge.hide()
        right.addWidget(self.lbl_badge)
        self.lbl_status = label("", 10, bold=True)
        right.addWidget(self.lbl_status)
        self.ic_wifi = icon_label("wifi", C["dim"], 16)
        right.addWidget(self.ic_wifi)
        rw = clear_widget()
        rw.setLayout(right)
        rw.setFixedWidth(164)
        row.addWidget(rw)
        return bar
    def build_nav_bar(self):
        bar = QWidget()
        bar.setObjectName("Bar")
        bar.setAttribute(Qt.WA_StyledBackground, True)
        bar.setFixedHeight(self.NAV_H)
        row = QHBoxLayout(bar)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(8)

        self.btn_back = button("Back", icon="back", icon_color=C["muted"], icon_size=18, h=30, w=104, size=13)
        self.btn_back.setProperty("navbar", True)
        self.btn_back.clicked.connect(self.go_back)
        row.addWidget(self.btn_back)
        row.addStretch()
        self.btn_home = button("", icon="home", icon_color=C["text"], icon_size=20, h=30, w=132)
        self.btn_home.setProperty("navhome", True)
        self.btn_home.clicked.connect(self.go_home)
        row.addWidget(self.btn_home)
        row.addStretch()
        self.btn_apps = button("Apps", icon="apps", icon_color=C["muted"], icon_size=18, h=30, w=104, size=13)
        self.btn_apps.setProperty("navbar", True)
        self.btn_apps.clicked.connect(lambda: self.open_page("apps"))
        row.addWidget(self.btn_apps)
        return bar

    def open_page(self, key, push=True):
        if key == self.current:
            return
        if push and self.current:
            self.history = (self.history + [self.current])[-20:]
        self.current = key
        self.pages.setCurrentWidget(self.page_widgets[key])
        self.lbl_title.setText("Smart Farm" if key == "home" else TITLES[key])
        self.disarm_reboot()
        if key == "wifi":
            self.refresh_wifi(rescan=not self.wifi_networks)
        elif key == "device":
            self.refresh_device()
        elif key in ("today", "fert"):
            self.get_advice(force=True)
        elif key == "weather":
            weather.refresh() if not weather.get()["ok"] else None
        self.update_nav()
        self.update_telemetry()

    def go_back(self):
        if self.history:
            self.open_page(self.history.pop(), push=False)

    def go_home(self):
        self.history = []
        self.open_page("home", push=False)

    def update_nav(self):
        can_back = bool(self.history)
        self.btn_back.setEnabled(can_back)
        set_button_icon(self.btn_back, "back", C["muted"] if can_back else C["line"], 18)
        on_apps = self.current == "apps"
        set_button_icon(self.btn_apps, "apps", C["leaf"] if on_apps else C["muted"], 18)
        set_button_icon(self.btn_home, "home", C["leaf"] if self.current == "home" else C["text"], 20)

    @staticmethod
    def page_box(page, spacing=6, margins=(6, 5, 6, 5)):
        box = QVBoxLayout(page)
        box.setContentsMargins(*margins)
        box.setSpacing(spacing)
        return box

    # ------------------------------------------------------------- home
    def build_home(self, page):
        box = self.page_box(page)

        top = QHBoxLayout()
        top.setSpacing(6)

        # Weather (tap: Weather app)
        wc = card_button()
        wc.setFixedSize(178, 124)
        wc.clicked.connect(lambda: self.open_page("weather"))
        w = QVBoxLayout(wc)
        w.setContentsMargins(10, 7, 10, 7)
        w.setSpacing(1)
        r1 = QHBoxLayout()
        r1.addWidget(caps("Alappuzha"))
        r1.addStretch()
        self.home_w_updated = label("", 10, C["dim"])
        r1.addWidget(self.home_w_updated)
        w.addLayout(r1)
        r2 = QHBoxLayout()
        r2.setSpacing(8)
        self.home_w_icon = icon_label("cloud", C["light"], 40)
        self.home_w_temp = label("--°", 32, C["text"], bold=True)
        r2.addWidget(self.home_w_icon)
        r2.addWidget(self.home_w_temp)
        r2.addStretch()
        w.addLayout(r2)
        self.home_w_label = label("Loading…", 13, C["text"], bold=True)
        self.home_w_range = label("", 11, C["muted"])
        self.home_w_rain = label("", 11, C["water"])
        w.addWidget(self.home_w_label)
        w.addWidget(self.home_w_range)
        w.addWidget(self.home_w_rain)
        passthrough(self.home_w_updated, self.home_w_icon, self.home_w_temp, self.home_w_label,
                    self.home_w_range, self.home_w_rain)
        top.addWidget(wc)

        # Soil (tap: Water app)
        sc = card_button()
        sc.setFixedSize(140, 124)
        sc.clicked.connect(lambda: self.open_page("water"))
        s = QVBoxLayout(sc)
        s.setContentsMargins(8, 7, 8, 5)
        s.setSpacing(0)
        cap = caps("Soil")
        s.addWidget(cap)
        self.gauge = ArcGauge()
        s.addWidget(self.gauge, stretch=1)
        self.home_crop = label("", 11, C["muted"], align=Qt.AlignCenter)
        s.addWidget(self.home_crop)
        passthrough(cap, self.gauge, self.home_crop)
        top.addWidget(sc)

        # Field sensors
        fc = card()
        fc.setFixedHeight(124)
        f = QVBoxLayout(fc)
        f.setContentsMargins(10, 7, 8, 7)
        f.setSpacing(3)
        f.addWidget(caps("Field"))
        self.field = {}
        for key, icon, col in (("temp", "thermo", C["sun"]), ("hum", "drop", C["water"]),
                               ("rain", "rain", C["water"]), ("light", "sun", C["light"])):
            r = QHBoxLayout()
            r.setSpacing(6)
            ic = icon_label(icon, col, 18)
            v = label("--", 14, C["text"], bold=True)
            r.addWidget(ic)
            r.addWidget(v, stretch=1)
            f.addLayout(r)
            self.field[key] = (ic, v)
        f.addStretch()
        top.addWidget(fc, stretch=1)
        box.addLayout(top)

        bottom = QHBoxLayout()
        bottom.setSpacing(6)

        # Today's advice (tap: Today app)
        tc = card_button()
        tc.setFixedHeight(118)
        tc.clicked.connect(lambda: self.open_page("today"))
        t = QVBoxLayout(tc)
        t.setContentsMargins(10, 7, 8, 7)
        t.setSpacing(4)
        cap = caps("Today")
        t.addWidget(cap)
        self.home_adv = {}
        for key, icon, col in (("water", "drop", C["water"]), ("fert", "flask", C["fert"])):
            r = QHBoxLayout()
            r.setSpacing(6)
            ic = icon_label(icon, col, 18)
            v = label("…", 13, C["text"], bold=True)
            r.addWidget(ic)
            r.addWidget(v, stretch=1)
            t.addLayout(r)
            self.home_adv[key] = v
            passthrough(ic, v)
        self.home_adv_note = label("", 11, C["muted"])
        self.home_adv_note.setWordWrap(True)
        t.addWidget(self.home_adv_note)
        t.addStretch()
        passthrough(cap, self.home_adv_note)
        bottom.addWidget(tc, stretch=1)

        self.home_tank = HomeTankCard(self)
        self.home_tank.setFixedSize(128, 118)
        bottom.addWidget(self.home_tank)

        pumps = QVBoxLayout()
        pumps.setSpacing(6)
        self.home_p1 = button("", icon="drop", icon_color=C["water"], icon_size=20, h=56, w=100, size=12)
        self.home_p2 = button("", icon="flask", icon_color=C["fert"], icon_size=20, h=56, w=100, size=12)
        self.home_p1.clicked.connect(self.on_pump)
        self.home_p2.clicked.connect(self.on_fert)
        pumps.addWidget(self.home_p1)
        pumps.addWidget(self.home_p2)
        bottom.addLayout(pumps)
        box.addLayout(bottom)
        box.addStretch()

    # ------------------------------------------------------------- today
    def build_today(self, page):
        box = self.page_box(page)
        head = QHBoxLayout()
        head.setSpacing(8)
        self.td_wx_icon = icon_label("cloud", C["muted"], 26)
        head.addWidget(self.td_wx_icon)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.td_title = label("", 14, C["text"], bold=True)
        self.td_sub = label("", 11, C["muted"])
        col.addWidget(self.td_title)
        col.addWidget(self.td_sub)
        head.addLayout(col, stretch=1)
        self.btn_td_crop = button("", icon="sprout", icon_color=C["leaf"], icon_size=16, h=34, size=12)
        self.btn_td_crop.clicked.connect(lambda: self.open_page("crops"))
        head.addWidget(self.btn_td_crop)
        box.addLayout(head)

        self.td_water = AdviceRow("drop", C["water"])
        box.addWidget(self.td_water)
        self.td_fert = AdviceRow("flask", C["fert"])
        self.btn_td_run = button("Run", icon="play", icon_color=C["bg"], icon_size=16, tone="fert", h=40, w=96, size=13)
        self.btn_td_run.clicked.connect(self.on_fert_suggested)
        self.td_fert.side.addWidget(self.btn_td_run, alignment=Qt.AlignVCenter)
        box.addWidget(self.td_fert)
        self.td_tips = label("", 11, C["sun"])
        self.td_tips.setWordWrap(True)
        box.addWidget(self.td_tips, stretch=1, alignment=Qt.AlignTop)

    def get_advice(self, force=False):
        if force or not self.advice or time.time() - self.advice_time > self.ADVICE_MAX_AGE:
            try:
                self.advice = hardware.get_advice()
            except Exception as e:
                print(f"[Advice] {e}")
            self.advice_time = time.time()
        return self.advice

    # ----------------------------------------------------------- farm ai
    AI_VIEWS = [("brief", "Brief"), ("crop", "Crop"), ("params", "Settings"), ("ask", "Ask")]
    AI_QUESTIONS = ["What should I do this week?", "Any pest or disease risk now?",
                    "Is it a good time to fertilize?", "How can I save water?"]
    AI_RUN = {"brief": "Refresh", "crop": "My crop", "params": "Check", "ask": "Type…"}

    def build_ai(self, page):
        self.ai_view = "brief"
        self.ai_page = 0
        box = self.page_box(page, spacing=5)
        head = QHBoxLayout()
        head.setSpacing(5)
        self.ai_tabs = {}
        for key, name in self.AI_VIEWS:
            b = button(name, h=34, size=12)
            b.clicked.connect(lambda _, k=key: self.set_ai_view(k))
            head.addWidget(b, stretch=1)
            self.ai_tabs[key] = b
        self.btn_ai_run = button("", icon="sparkle", icon_color=C["bg"], icon_size=16, tone="primary", h=34, w=104, size=12)
        self.btn_ai_run.clicked.connect(self.on_ai_run)
        head.addWidget(self.btn_ai_run)
        box.addLayout(head)

        self.ai_stack = QStackedWidget()
        # Brief / crop / ask: one rich-text card each
        def text_card():
            c = card()
            lay = QVBoxLayout(c)
            lay.setContentsMargins(10, 6, 10, 6)
            lay.setSpacing(4)
            lbl = QLabel()
            lbl.setTextFormat(Qt.RichText)
            lbl.setWordWrap(True)
            lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            lbl.setFont(px_font(12))
            lay.addWidget(lbl, stretch=1)
            return c, lay, lbl

        brief, bl, self.ai_brief_lbl = text_card()
        pager = QHBoxLayout()
        pager.setSpacing(6)
        self.ai_prev = button(icon="back", w=50, h=30)
        self.ai_next = button(icon="next", w=50, h=30)
        self.ai_pg_lbl = label("", 11, C["muted"], align=Qt.AlignCenter)
        self.ai_prev.clicked.connect(lambda: self.page_ai(-1))
        self.ai_next.clicked.connect(lambda: self.page_ai(1))
        pager.addWidget(self.ai_prev)
        pager.addWidget(self.ai_pg_lbl, stretch=1)
        pager.addWidget(self.ai_next)
        bl.addLayout(pager)
        self.ai_stack.addWidget(brief)

        crop, cl, self.ai_crop_lbl = text_card()
        crow = QHBoxLayout()
        crow.setSpacing(6)
        other = button("Other crop…", icon="sprout", icon_color=C["leaf"], icon_size=16, h=32, size=12)
        other.clicked.connect(self.ask_ai_crop)
        self.btn_ai_crop_apply = button("Use as Custom crop", icon="check", icon_color=C["bg"], icon_size=16,
                                        tone="primary", h=32, size=12)
        self.btn_ai_crop_apply.clicked.connect(self.apply_ai_crop)
        crow.addWidget(other)
        crow.addWidget(self.btn_ai_crop_apply, stretch=1)
        cl.addLayout(crow)
        self.ai_stack.addWidget(crop)

        params = card()
        pl = QVBoxLayout(params)
        pl.setContentsMargins(10, 6, 8, 6)
        pl.setSpacing(4)
        self.ai_params_lbl = label("", 12, C["text"])
        self.ai_params_lbl.setWordWrap(True)
        pl.addWidget(self.ai_params_lbl)
        self.ai_param_rows = []
        for i in range(4):
            r = QHBoxLayout()
            r.setSpacing(6)
            t = QLabel()
            t.setTextFormat(Qt.RichText)
            t.setWordWrap(True)
            t.setFont(px_font(11))
            b = button("Apply", h=34, w=76, size=12)
            b.clicked.connect(lambda _, k=i: self.apply_ai_param(k))
            r.addWidget(t, stretch=1)
            r.addWidget(b)
            pl.addLayout(r)
            self.ai_param_rows.append((t, b))
        pl.addStretch()
        self.ai_stack.addWidget(params)

        ask, al, self.ai_ask_lbl = text_card()
        grid = QGridLayout()
        grid.setSpacing(5)
        for i, q in enumerate(self.AI_QUESTIONS):
            b = button(q, h=32, size=11)
            b.clicked.connect(lambda _, text=q: self.run_ai("ask", text))
            grid.addWidget(b, i // 2, i % 2)
        al.insertLayout(0, grid)
        self.ai_stack.addWidget(ask)
        box.addWidget(self.ai_stack, stretch=1)

    def set_ai_view(self, view):
        self.ai_view = view
        self.update_telemetry()

    def page_ai(self, delta):
        self.ai_page += delta
        self.update_telemetry()

    def run_ai(self, task, text=None):
        farm_ai.start(task, force=True, text=text)
        self.update_telemetry()

    def on_ai_run(self):
        if self.ai_view == "ask":
            q = get_text_input(parent=self, prompt="Ask Farm AI")
            if q:
                self.run_ai("ask", q)
        elif self.ai_view == "crop":
            self.run_ai("crop")
        else:
            if self.ai_view == "brief":
                self.ai_page = 0
            self.run_ai(self.ai_view)

    def ask_ai_crop(self):
        name = get_text_input(parent=self, prompt="Crop name (e.g. banana, okra, ginger)")
        if name:
            self.run_ai("crop", name)

    def apply_ai_crop(self):
        try:
            farm_ai.apply_crop()
            self.get_advice(force=True)
        except Exception as e:
            print(f"[FarmAI] {e}")
        self.update_telemetry()

    def apply_ai_param(self, i):
        try:
            farm_ai.apply_param(i)
            self.get_advice(force=True)
        except Exception as e:
            print(f"[FarmAI] {e}")
        self.update_telemetry()

    @staticmethod
    def _ai_state_html(st, task, idle_text):
        """Busy / error / not-set-up text for a task, or None when there is a result to show."""
        t = st["tasks"][task]
        if not st["configured"]:
            return (f"<span style='color:{C['sun']}'><b>Farm AI needs a Gemini API key.</b></span><br>"
                    f"On a phone or laptop open the web dashboard ({html.escape(self_web_url())}), "
                    "Device tab, and paste the key under <b>Farm AI key</b>.")
        if t["status"] == "busy":
            return f"<span style='color:{C['leaf']}'><b>Thinking…</b></span><br>Asking Gemini, this takes a few seconds."
        if t["status"] == "error" and not t["result"]:
            return f"<span style='color:{C['alert']}'><b>Could not get an answer.</b></span><br>{html.escape(t['error'])}"
        if not t["result"]:
            return idle_text
        return None

    def refresh_ai(self):
        st = farm_ai.status()
        views = [k for k, _ in self.AI_VIEWS]
        self.ai_stack.setCurrentIndex(views.index(self.ai_view))
        for key, b in self.ai_tabs.items():
            set_tone(b, "selected" if key == self.ai_view else None)
        busy = st["tasks"][self.ai_view]["status"] == "busy"
        self.btn_ai_run.setText("…" if busy else self.AI_RUN[self.ai_view])
        self.btn_ai_run.setEnabled(st["configured"] and not busy)
        esc = html.escape

        if self.ai_view == "brief":
            t = st["tasks"]["brief"]
            msg = self._ai_state_html(st, "brief", "Tap <b>Refresh</b> for today's farm brief.")
            pages = [msg] if msg else self._brief_pages(t["result"], t)
            self.ai_page = max(0, min(len(pages) - 1, self.ai_page))
            self.ai_brief_lbl.setText(pages[self.ai_page])
            self.ai_pg_lbl.setText(f"{self.ai_page + 1} / {len(pages)}" if len(pages) > 1 else "")
            self.ai_prev.setEnabled(self.ai_page > 0)
            self.ai_next.setEnabled(self.ai_page < len(pages) - 1)
            self.ai_prev.setVisible(len(pages) > 1)
            self.ai_next.setVisible(len(pages) > 1)
        elif self.ai_view == "crop":
            t = st["tasks"]["crop"]
            msg = self._ai_state_html(st, "crop", "Tap <b>My crop</b> to profile the current crop, "
                                                  "or <b>Other crop…</b> to type any crop name.")
            r = t["result"]
            if msg:
                self.ai_crop_lbl.setText(msg)
            else:
                self.ai_crop_lbl.setText(
                    f"<span style='color:{C['leaf']}; font-size:15px'><b>{esc(r['name'])}</b></span>"
                    f"  <span style='color:{C['dim']}'>{esc(t['time'] or '')}</span><br>"
                    f"<b>Water</b> below {r['dry_cutoff']:.0f}% until {r['stop_cutoff']:.0f}% · Kc "
                    f"{r['kc_early']}/{r['kc_mid']}/{r['kc_late']} · feed every {r['feed_days']} d<br>"
                    f"<span style='color:{C['muted']}'>Season:</span> {esc(r['season'])} · {esc(r['water_need'])}<br>"
                    f"<span style='color:{C['fert']}'>Feed:</span> {esc(r['feeding'])}<br>"
                    f"<span style='color:{C['sun']}'>Pests:</span> {esc(r['pests'])}")
            self.btn_ai_crop_apply.setEnabled(bool(r) and t["status"] != "busy")
        elif self.ai_view == "params":
            t = st["tasks"]["params"]
            msg = self._ai_state_html(st, "params", "Tap <b>Check</b> and Farm AI reviews your cutoffs, "
                                                    "tank alert, feed size and crop stage.")
            r = t["result"]
            self.ai_params_lbl.setTextFormat(Qt.RichText)
            self.ai_params_lbl.setText(msg or (esc(r["summary"]) if r["suggestions"] else
                                               esc(r["summary"]) + "<br><b>No changes needed.</b>"))
            sugg = [] if msg else r["suggestions"]
            for i, (lbl, b) in enumerate(self.ai_param_rows):
                if i < len(sugg):
                    s = sugg[i]
                    lbl.setText(f"<b>{esc(s['name'])} → {esc(str(s['value']))}</b> "
                                f"<span style='color:{C['muted']}'>{esc(s['reason'])}</span>")
                    b.setText("Done" if s["applied"] else "Apply")
                    b.setEnabled(not s["applied"])
                    set_tone(b, None if s["applied"] else "primary")
                    lbl.show()
                    b.show()
                else:
                    lbl.hide()
                    b.hide()
        else:
            t = st["tasks"]["ask"]
            msg = self._ai_state_html(st, "ask", "Tap a question, or <b>Type…</b> to ask your own.")
            self.ai_ask_lbl.setText(msg or f"<span style='color:{C['muted']}'>{esc(t['input'] or '')}</span><br>"
                                           f"{esc(t['result']['answer'])}")

    def _brief_pages(self, r, t):
        esc = html.escape
        kind_col = {"water": C["water"], "fertilizer": C["fert"], "pest": C["alert"], "tank": C["tank"],
                    "harvest": C["sun"], "general": C["leaf"]}
        stale = " (refresh failed)" if t["status"] == "error" else ""
        p1 = (f"<span style='color:{C['leaf']}; font-size:15px'><b>{esc(r['headline'])}</b></span>"
              f"  <span style='color:{C['dim']}'>{esc(t['time'] or '')}{stale}</span><br>{esc(r['summary'])}<br>"
              f"<span style='color:{C['water']}'><b>Water:</b></span> {esc(r['water'])}<br>"
              f"<span style='color:{C['fert']}'><b>Fertilizer:</b></span> {esc(r['fertilizer'])}")
        pages = [p1]
        acts = r.get("actions", [])
        for i in range(0, len(acts), 3):
            pages.append("<br>".join(
                f"<span style='color:{kind_col.get(a['kind'], C['leaf'])}'><b>{esc(a['title'])}</b></span>"
                f" <span style='color:{C['dim']}'>{esc(a['when'])}</span><br>{esc(a['detail'])}" for a in acts[i:i + 3]))
        rem = [f"<b>{esc(x['day'])}:</b> {esc(x['text'])}" for x in r.get("reminders", [])]
        warn = [f"<span style='color:{C['alert']}'>⚠ {esc(w)}</span>" for w in r.get("warnings", [])]
        if rem or warn:
            pages.append((f"<span style='color:{C['muted']}'><b>REMINDERS</b></span><br>" + "<br>".join(rem)
                          if rem else "") + ("<br>" if rem and warn else "") + "<br>".join(warn))
        return pages

    # ------------------------------------------------------------- water
    def build_water(self, page):
        box = self.page_box(page)
        top = QHBoxLayout()
        top.setSpacing(6)
        self.btn_auto = button("AUTO", icon="auto", h=40)
        self.btn_manual = button("MANUAL", icon="hand", h=40)
        self.btn_auto.clicked.connect(lambda: self.set_mode("AUTO"))
        self.btn_manual.clicked.connect(lambda: self.set_mode("MANUAL"))
        top.addWidget(self.btn_auto, stretch=1)
        top.addWidget(self.btn_manual, stretch=1)
        self.btn_water_pump = button("Pump OFF", icon="power", icon_color=C["muted"], icon_size=20, h=40, w=136, size=13)
        self.btn_water_pump.clicked.connect(self.on_pump)
        top.addWidget(self.btn_water_pump)
        box.addLayout(top)
        self.step_dry = Stepper("power", "Pump 1 starts below", C["sun"],
                                lambda d: self.adjust_cutoff("dry", d), 5, "{:.0f} %")
        self.step_stop = Stepper("drop", "Pump 1 stops at", C["water"],
                                 lambda d: self.adjust_cutoff("stop", d), 5, "{:.0f} %")
        box.addWidget(self.step_dry)
        box.addWidget(self.step_stop)
        bar_card = card()
        bc = QVBoxLayout(bar_card)
        bc.setContentsMargins(8, 4, 8, 2)
        bc.setSpacing(0)
        self.range_bar = RangeBar()
        bc.addWidget(self.range_bar)
        box.addWidget(bar_card)
        self.lbl_water_info = label("", 11, C["muted"])
        self.lbl_water_info.setWordWrap(True)
        box.addWidget(self.lbl_water_info)
        box.addStretch()

    def adjust_cutoff(self, which, delta):
        if which == "dry":
            hardware.adjust_dry_cutoff(delta)
        else:
            hardware.adjust_stop_cutoff(delta)
        self.update_telemetry()

    # -------------------------------------------------------- fertilizer
    def build_fert(self, page):
        box = self.page_box(page)
        top = QHBoxLayout()
        top.setSpacing(8)
        self.btn_fert = button("Pump 2 OFF", icon="power", icon_color=C["muted"], icon_size=24, h=64, size=17)
        self.btn_fert.clicked.connect(self.on_fert)
        top.addWidget(self.btn_fert, stretch=1)
        st = card()
        st.setFixedSize(150, 64)
        sc = QVBoxLayout(st)
        sc.setContentsMargins(10, 5, 10, 5)
        sc.setSpacing(0)
        sc.addWidget(caps("Today"))
        self.lbl_fert_today = label("--", 15, C["text"], bold=True)
        self.lbl_fert_last = label("", 11, C["muted"])
        sc.addWidget(self.lbl_fert_today)
        sc.addWidget(self.lbl_fert_last)
        top.addWidget(st)
        box.addLayout(top)

        box.addWidget(caps("Run for"))
        chips = QHBoxLayout()
        chips.setSpacing(6)
        for mins in (0.5, 1, 2, 5):
            b = button(f"{fmt_num(mins)} min" if mins >= 1 else "30 s", icon="play", icon_color=C["fert"],
                       icon_size=14, h=40, size=13)
            b.clicked.connect(lambda _, m=mins: self.run_fert(m))
            chips.addWidget(b)
        box.addLayout(chips)

        self.fert_adv = AdviceRow("calendar", C["fert"], h=66)
        self.btn_fert_sugg = button("Run", icon="play", icon_color=C["bg"], icon_size=16, tone="fert", h=40, w=96, size=13)
        self.btn_fert_sugg.clicked.connect(self.on_fert_suggested)
        self.fert_adv.side.addWidget(self.btn_fert_sugg, alignment=Qt.AlignVCenter)
        box.addWidget(self.fert_adv)
        self.lbl_fert_info = label("", 11, C["dim"])
        self.lbl_fert_info.setWordWrap(True)
        box.addWidget(self.lbl_fert_info)
        box.addStretch()

    def run_fert(self, minutes):
        hardware.set_fert_pump(True, minutes)
        self.update_telemetry()

    def on_fert_suggested(self):
        adv = self.get_advice()
        if adv and adv["fert"]["action"] == "apply":
            hardware.set_fert_pump(True, adv["fert"]["minutes"])
        self.update_telemetry()

    # --------------------------------------------------------- rain tank
    def build_tanks(self, page):
        row = QHBoxLayout(page)
        row.setContentsMargins(6, 5, 6, 5)
        row.setSpacing(6)

        left = card()
        left.setFixedWidth(150)
        lc = QVBoxLayout(left)
        lc.setContentsMargins(10, 7, 10, 8)
        lc.setSpacing(4)
        lc.addWidget(caps("Rain tank"))
        lr = QHBoxLayout()
        lr.setSpacing(8)
        self.tk_glyph = TankGlyph(C["tank"], 40, 96)
        lr.addWidget(self.tk_glyph)
        lcol = QVBoxLayout()
        lcol.setSpacing(1)
        self.tk_level = label("--", 22, C["text"], bold=True)
        self.tk_litres = label("", 11, C["muted"], bold=True)
        self.tk_litres.setWordWrap(True)
        self.tk_dist = label("", 10, C["dim"])
        self.tk_dist.setWordWrap(True)
        lcol.addWidget(self.tk_level)
        lcol.addWidget(self.tk_litres)
        lcol.addWidget(self.tk_dist)
        lcol.addStretch()
        lr.addLayout(lcol, stretch=1)
        lc.addLayout(lr)
        self.tk_state = label("", 11, C["muted"], bold=True)
        self.tk_state.setWordWrap(True)
        lc.addWidget(self.tk_state, stretch=1)
        self.btn_tk_reset = button("Reset", icon="check", icon_color=C["muted"], icon_size=16, h=40, size=13)
        self.btn_tk_reset.clicked.connect(self.on_tank_reset)
        lc.addWidget(self.btn_tk_reset)
        row.addWidget(left)

        right = QVBoxLayout()
        right.setSpacing(6)
        self.step_tank_alert = Stepper("bell", "Alert when full at", C["alert"],
                                       lambda dlt: self.adjust_tank("alert", dlt), 5, "{:.0f} %")
        self.step_tank_height = Stepper("tank", "Height (sensor to floor)", C["tank"],
                                        lambda dlt: self.adjust_tank("height", dlt), 5, "{:.0f} cm")
        self.step_tank_gap = Stepper("drop", "Gap when full", C["water"],
                                     lambda dlt: self.adjust_tank("gap", dlt), 1, "{:.0f} cm")
        right.addWidget(self.step_tank_alert)
        right.addWidget(self.step_tank_height)
        right.addWidget(self.step_tank_gap)
        marks = QHBoxLayout()
        marks.setSpacing(6)
        self.btn_cal_area = button("Area", icon="ruler", icon_color=C["muted"], icon_size=16, h=38, size=12)
        self.btn_cal_area.clicked.connect(self.on_cal_area)
        self.btn_mark_empty = button("Empty now", h=38, size=12)
        self.btn_mark_full = button("Full now", h=38, size=12)
        self.btn_mark_empty.clicked.connect(lambda: self.mark_tank("empty"))
        self.btn_mark_full.clicked.connect(lambda: self.mark_tank("full"))
        marks.addWidget(self.btn_cal_area, stretch=4)
        marks.addWidget(self.btn_mark_empty, stretch=3)
        marks.addWidget(self.btn_mark_full, stretch=3)
        right.addLayout(marks)
        self.lbl_tank_hint = label("Area turns cm into litres: 1 cm over 1000 cm² = 1 L.", 10, C["muted"])
        self.lbl_tank_hint.setWordWrap(True)
        right.addWidget(self.lbl_tank_hint)
        right.addStretch()
        row.addLayout(right, stretch=1)

    def on_tank_reset(self):
        hardware.reset_tank()
        self.update_telemetry()

    def adjust_tank(self, which, delta):
        if which == "alert":
            hardware.set_farm_settings(tank_alert_pct=hardware.tank_alert_pct + delta)
        elif which == "height":
            hardware.set_tank_calibration(empty_cm=hardware.tank_empty_cm + delta)
        else:
            hardware.set_tank_calibration(full_cm=hardware.tank_full_cm + delta)
        self.update_telemetry()

    def on_cal_area(self):
        v = get_number(self, "Tank surface area (length × width, or 0.785 × diameter²)",
                       hardware.tank_area_cm2, "cm²", decimals=0, max_value=500000)
        if v is not None:
            hardware.set_tank_calibration(area_cm2=v)
            self.update_telemetry()

    def mark_tank(self, which):
        if hardware.mark_tank(which) is None:
            self.lbl_tank_hint.setText("No sensor reading. Check the ultrasonic wiring.")
            set_color(self.lbl_tank_hint, C["alert"])
        else:
            self.lbl_tank_hint.setText(f"Saved the current distance as {which}.")
            set_color(self.lbl_tank_hint, C["leaf"])
        self.update_telemetry()

    # --------------------------------------------------------- simulator
    def build_sim(self, page):
        box = self.page_box(page, spacing=5)
        self.btn_sim = button("Simulator OFF", icon="sliders", h=36)
        self.btn_sim.clicked.connect(self.toggle_sim)
        box.addWidget(self.btn_sim)
        grid = QGridLayout()
        grid.setSpacing(5)
        self.step_sim_t = Stepper("thermo", "Temp", C["sun"], lambda d: self.step_sim("temp", d), 1, "{:.0f} °C", True)
        self.step_sim_h = Stepper("drop", "Humidity", C["water"], lambda d: self.step_sim("hum", d), 5, "{:.0f} %", True)
        self.step_sim_s = Stepper("sprout", "Soil", C["leaf"], lambda d: self.step_sim("soil", d), 5, "{:.0f} %", True)
        self.step_sim_k = Stepper("tank", "Rain tank", C["tank"], lambda d: self.step_sim("tank", d), 5, "{:.0f} %", True)
        for i, s in enumerate((self.step_sim_t, self.step_sim_h, self.step_sim_s, self.step_sim_k)):
            grid.addWidget(s, i // 2, i % 2)
        box.addLayout(grid)
        note = label("Fake sensor values for testing. Pump 1 raises soil moisture.", 11, C["muted"])
        note.setWordWrap(True)
        box.addWidget(note)
        box.addStretch()

    def toggle_sim(self):
        hardware.toggle_simulator_mode()
        self.update_telemetry()

    def step_sim(self, kind, delta):
        if kind == "temp":
            hardware.set_simulated_sensors(temp=max(0, min(50, hardware.sim_temp + delta)))
        elif kind == "hum":
            hardware.set_simulated_sensors(humidity=max(0, min(100, hardware.sim_humidity + delta)))
        elif kind == "tank":
            hardware.set_simulated_sensors(tank_level=hardware.sim_tank_level + delta)
        else:
            hardware.set_simulated_sensors(soil_moisture=max(0, min(100, hardware.sim_soil_moisture + delta)))
        self.update_telemetry()

    # ----------------------------------------------------------- weather
    def build_weather(self, page):
        box = self.page_box(page)

        now = card_button()
        now.setFixedHeight(92)
        now.clicked.connect(weather.refresh)
        n = QHBoxLayout(now)
        n.setContentsMargins(12, 6, 12, 6)
        n.setSpacing(10)
        self.wx_icon = icon_label("cloud", C["light"], 52)
        n.addWidget(self.wx_icon)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.wx_temp = label("--°", 32, C["text"], bold=True)
        self.wx_label = label("Loading…", 13, C["text"], bold=True)
        self.wx_feels = label("", 11, C["muted"])
        col.addWidget(self.wx_temp)
        col.addWidget(self.wx_label)
        col.addWidget(self.wx_feels)
        n.addLayout(col, stretch=1)
        stats = QGridLayout()
        stats.setHorizontalSpacing(6)
        stats.setVerticalSpacing(4)
        self.wx_stats = {}
        for i, (key, icon, col_) in enumerate((("hum", "drop", C["water"]), ("wind", "wind", C["muted"]),
                                               ("rise", "sunrise", C["sun"]), ("set", "sunset", C["sun"]))):
            ic = icon_label(icon, col_, 16)
            v = label("--", 12, C["text"], bold=True)
            stats.addWidget(ic, i // 2, (i % 2) * 2)
            stats.addWidget(v, i // 2, (i % 2) * 2 + 1)
            self.wx_stats[key] = v
            passthrough(ic, v)
        n.addLayout(stats)
        passthrough(self.wx_icon, self.wx_temp, self.wx_label, self.wx_feels)
        box.addWidget(now)

        hourly = card()
        hourly.setFixedHeight(74)
        h = QHBoxLayout(hourly)
        h.setContentsMargins(6, 4, 6, 4)
        h.setSpacing(0)
        self.wx_hours = []
        for _ in range(8):
            c = QVBoxLayout()
            c.setSpacing(1)
            t = label("", 10, C["muted"], align=Qt.AlignCenter)
            ic = QLabel()
            ic.setFixedSize(20, 20)
            tp = label("", 12, C["text"], bold=True, align=Qt.AlignCenter)
            rp = label("", 10, C["water"], align=Qt.AlignCenter)
            c.addWidget(t)
            c.addWidget(ic, alignment=Qt.AlignHCenter)
            c.addWidget(tp)
            c.addWidget(rp)
            h.addLayout(c, stretch=1)
            self.wx_hours.append((t, ic, tp, rp))
        box.addWidget(hourly)

        daily = card()
        d = QHBoxLayout(daily)
        d.setContentsMargins(6, 4, 6, 4)
        d.setSpacing(0)
        self.wx_days = []
        for _ in range(5):
            c = QVBoxLayout()
            c.setSpacing(1)
            dn = label("", 12, C["text"], bold=True, align=Qt.AlignCenter)
            ic = QLabel()
            ic.setFixedSize(22, 22)
            tr = label("", 11, C["text"], align=Qt.AlignCenter)
            rp = label("", 10, C["water"], align=Qt.AlignCenter)
            c.addWidget(dn)
            c.addWidget(ic, alignment=Qt.AlignHCenter)
            c.addWidget(tr)
            c.addWidget(rp)
            d.addLayout(c, stretch=1)
            self.wx_days.append((dn, ic, tr, rp))
        box.addWidget(daily, stretch=1)

    # ------------------------------------------------------------- crops
    def build_crops(self, page):
        grid = QGridLayout(page)
        grid.setContentsMargins(6, 5, 6, 5)
        grid.setSpacing(6)
        self.crop_buttons = {}
        for i, (key, preset) in enumerate(CROP_PRESETS.items()):
            b = QPushButton()
            b.setFocusPolicy(Qt.NoFocus)
            b.setFixedHeight(56)
            b.setProperty("row", True)
            inner = QHBoxLayout(b)
            inner.setContentsMargins(10, 4, 8, 4)
            inner.setSpacing(8)
            ic = icon_label("sprout", CROP_COLORS.get(key, C["muted"]), 24)
            txt = QVBoxLayout()
            txt.setSpacing(0)
            name = label(preset["name"].split(" / ")[0], 14, C["text"], bold=True)
            rng = label("Your cutoffs" if key == "custom" else
                        f"{preset['dry_cutoff']:.0f}–{preset['stop_cutoff']:.0f}% moisture", 11, C["muted"])
            txt.addWidget(name)
            txt.addWidget(rng)
            inner.addWidget(ic)
            inner.addLayout(txt, stretch=1)
            passthrough(ic, name, rng)
            b.clicked.connect(lambda _, k=key: self.select_crop(k))
            grid.addWidget(b, i // 2, i % 2)
            self.crop_buttons[key] = b
        grid.setRowStretch(4, 1)

    def select_crop(self, key):
        hardware.set_crop(key)
        self.update_telemetry()

    # ------------------------------------------------------------ drawer
    def build_drawer(self, page):
        box = QVBoxLayout(page)
        box.setContentsMargins(4, 14, 4, 8)
        box.setSpacing(0)
        grid = QGridLayout()
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(12)
        for i, (key, name, icon, color) in enumerate(APPS):
            b = QPushButton()
            b.setFocusPolicy(Qt.NoFocus)
            b.setProperty("app", True)
            b.setFixedSize(76, 96)
            col = QVBoxLayout(b)
            col.setContentsMargins(0, 6, 0, 4)
            col.setSpacing(5)
            tile = QLabel()
            tile.setFixedSize(58, 58)
            tile.setAlignment(Qt.AlignCenter)
            tile.setPixmap(qt_pixmap(icon, "#ffffff", 30, 2.2))
            tile.setStyleSheet(f"background-color: {color}; border-radius: 15px;")
            name_lbl = label(name, 12, C["text"], bold=True, align=Qt.AlignCenter)
            col.addWidget(tile, alignment=Qt.AlignHCenter)
            col.addWidget(name_lbl)
            passthrough(tile, name_lbl)
            b.clicked.connect(lambda _, k=key: self.open_page(k))
            grid.addWidget(b, i // 6, i % 6, alignment=Qt.AlignCenter)
        box.addLayout(grid)
        box.addStretch()
        hint = label("Tap an app. Home returns to the dashboard.", 11, C["dim"], align=Qt.AlignCenter)
        box.addWidget(hint)

    # -------------------------------------------------------------- wifi
    def build_wifi(self, page):
        box = self.page_box(page, spacing=4)
        top = QHBoxLayout()
        top.setSpacing(6)
        self.lbl_wifi = label("Wi-Fi", 13, C["leaf"], bold=True)
        top.addWidget(self.lbl_wifi, stretch=1)
        btn_scan = button(icon="refresh", w=48, h=36)
        btn_scan.clicked.connect(lambda: self.refresh_wifi(rescan=True))
        top.addWidget(btn_scan)
        box.addLayout(top)

        self.wifi_rows = []
        for _ in range(self.WIFI_PAGE_SIZE):
            b = QPushButton()
            b.setFocusPolicy(Qt.NoFocus)
            b.setFixedHeight(40)
            row = QHBoxLayout(b)
            row.setContentsMargins(10, 0, 10, 0)
            row.setSpacing(8)
            ic = QLabel()
            ic.setFixedSize(20, 20)
            name = label("", 13, C["text"], bold=True)
            lock = QLabel()
            lock.setFixedSize(16, 16)
            sig = label("", 12, C["muted"])
            row.addWidget(ic)
            row.addWidget(name, stretch=1)
            row.addWidget(lock)
            row.addWidget(sig)
            passthrough(ic, name, lock, sig)
            b.clicked.connect(lambda _, i=len(self.wifi_rows): self.on_wifi_row(i))
            self.wifi_rows.append((b, ic, name, lock, sig))
            box.addWidget(b)

        pager = QHBoxLayout()
        pager.setSpacing(6)
        self.btn_wifi_prev = button(icon="back", w=56, h=34)
        self.btn_wifi_next = button(icon="next", w=56, h=34)
        self.lbl_wifi_page = label("", 12, C["muted"], align=Qt.AlignCenter)
        self.btn_wifi_prev.clicked.connect(lambda: self.page_wifi(-1))
        self.btn_wifi_next.clicked.connect(lambda: self.page_wifi(1))
        pager.addWidget(self.btn_wifi_prev)
        pager.addWidget(self.lbl_wifi_page, stretch=1)
        pager.addWidget(self.btn_wifi_next)
        box.addStretch()
        box.addLayout(pager)

    def refresh_wifi(self, rescan=False):
        curr = wifi_manager.get_current_wifi()
        self.wifi_status = curr
        if curr["connected"]:
            self.lbl_wifi.setText(f"{curr['ssid']}  ·  {curr['signal']}%")
            set_color(self.lbl_wifi, C["leaf"])
        else:
            self.lbl_wifi.setText("Not connected")
            set_color(self.lbl_wifi, C["alert"])
        if rescan:
            self.lbl_wifi_page.setText("Scanning…")
            QApplication.processEvents()
            self.wifi_networks = wifi_manager.scan_wifi_networks()
            self.wifi_page = 0
        self.render_wifi_page()

    def page_wifi(self, delta):
        pages = max(1, math.ceil(len(self.wifi_networks) / self.WIFI_PAGE_SIZE))
        self.wifi_page = max(0, min(pages - 1, self.wifi_page + delta))
        self.render_wifi_page()

    def render_wifi_page(self):
        pages = max(1, math.ceil(len(self.wifi_networks) / self.WIFI_PAGE_SIZE))
        start = self.wifi_page * self.WIFI_PAGE_SIZE
        chunk = self.wifi_networks[start:start + self.WIFI_PAGE_SIZE]
        for i, (b, ic, name, lock, sig) in enumerate(self.wifi_rows):
            if i < len(chunk):
                net = chunk[i]
                strength = C["leaf"] if net["signal"] >= 60 else C["sun"] if net["signal"] >= 30 else C["alert"]
                set_icon(ic, "wifi", strength, 20)
                name.setText(net["ssid"][:22])
                set_color(name, C["leaf"] if net["active"] else C["text"])
                if net.get("security", "") not in ("", "--"):
                    set_icon(lock, "lock", C["muted"], 16)
                else:
                    lock.clear()
                    lock._icon_key = None
                sig.setText(f"{net['signal']}%")
                set_tone(b, "selected" if net["active"] else None)
                b.show()
            else:
                b.hide()
        self.lbl_wifi_page.setText("No networks found" if not self.wifi_networks else f"{self.wifi_page + 1} / {pages}")
        self.btn_wifi_prev.setEnabled(self.wifi_page > 0)
        self.btn_wifi_next.setEnabled(self.wifi_page < pages - 1)

    def on_wifi_row(self, i):
        idx = self.wifi_page * self.WIFI_PAGE_SIZE + i
        if idx >= len(self.wifi_networks):
            return
        ssid = self.wifi_networks[idx]["ssid"]
        password = get_text_input(parent=self, prompt=f"Password for {ssid}", is_password=True)
        if password is None:
            return
        self.lbl_wifi.setText(f"Connecting to {ssid}…")
        set_color(self.lbl_wifi, C["sun"])
        QApplication.processEvents()
        res = wifi_manager.connect_wifi(ssid, password)
        if not res["success"]:
            self.lbl_wifi.setText(f"Failed: {res['message'][:28]}")
            set_color(self.lbl_wifi, C["alert"])
            return
        self.refresh_wifi(rescan=True)

    def update_wifi_status(self):
        try:
            self.wifi_status = wifi_manager.get_current_wifi()
        except Exception:
            self.wifi_status = None
        ok = bool(self.wifi_status and self.wifi_status.get("connected"))
        set_icon(self.ic_wifi, "wifi", C["leaf"] if ok else C["dim"], 16)

    # ---------------------------------------------------------- settings
    SETTING_TILES = [
        ("field_area_m2", "Field area", "m²", 1, 100000),
        ("feed_litres", "Fertilizer per feed", "L", 2, 500),
        ("water_lpm", "Pump 1 flow", "L/min", 1, 500),
        ("fert_lpm", "Pump 2 flow", "L/min", 2, 100),
        ("fert_manual_max_min", "Pump 2 auto-off", "min", 0, 60),
    ]

    def build_settings(self, page):
        box = self.page_box(page, spacing=5)
        box.addWidget(caps("Crop stage"))
        seg = QHBoxLayout()
        seg.setSpacing(6)
        self.stage_buttons = {}
        for key, name in (("early", "Young plants"), ("mid", "Flowering"), ("late", "Near harvest")):
            b = button(name, h=36, size=13)
            b.clicked.connect(lambda _, k=key: self.set_farm(crop_stage=k))
            seg.addWidget(b)
            self.stage_buttons[key] = b
        box.addLayout(seg)
        grid = QGridLayout()
        grid.setSpacing(6)
        self.setting_tiles = {}
        for i, (key, title, unit, decimals, mx) in enumerate(self.SETTING_TILES):
            b = card_button()
            b.setFixedHeight(50)
            col = QVBoxLayout(b)
            col.setContentsMargins(10, 4, 10, 4)
            col.setSpacing(0)
            t = label(title, 11, C["muted"], bold=True)
            v = label("--", 16, C["text"], bold=True)
            col.addWidget(t)
            col.addWidget(v)
            passthrough(t, v)
            b.clicked.connect(lambda _, k=key: self.edit_setting(k))
            grid.addWidget(b, i // 2, i % 2)
            self.setting_tiles[key] = v
        info = label("Measure a pump's flow by timing how long it takes to fill a 10 L bucket.", 10, C["dim"])
        info.setWordWrap(True)
        grid.addWidget(info, 2, 1)
        box.addLayout(grid)
        box.addStretch()

    def set_farm(self, **kw):
        hardware.set_farm_settings(**kw)
        self.get_advice(force=True)
        self.update_telemetry()

    def edit_setting(self, key):
        _, title, unit, decimals, mx = next(t for t in self.SETTING_TILES if t[0] == key)
        v = get_number(self, title, getattr(hardware, key), unit, decimals=decimals, max_value=mx)
        if v is not None:
            self.set_farm(**{key: v})

    def on_reboot(self):
        # Two taps needed: first arms, second reboots
        if not self.reboot_armed:
            self.reboot_armed = True
            self.btn_reboot.setText("Tap to confirm")
            set_button_icon(self.btn_reboot, "power", C["bg"], 22)
            set_tone(self.btn_reboot, "danger-armed")
            QTimer.singleShot(4000, self.disarm_reboot)
            return
        self.btn_reboot.setText("Rebooting…")
        run_privileged(["reboot"])

    def disarm_reboot(self):
        if getattr(self, "reboot_armed", False):
            self.reboot_armed = False
            self.btn_reboot.setText("Reboot Pi")
            set_button_icon(self.btn_reboot, "power", C["alert"], 22)
            set_tone(self.btn_reboot, "danger")

    # ------------------------------------------------------------ device
    def build_device(self, page):
        box = self.page_box(page)
        info = card()
        grid = QGridLayout(info)
        grid.setContentsMargins(12, 6, 12, 6)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(2)
        self.device_values = {}
        rows = [
            ("ip_address", "wifi", "Address"),
            ("cpu_temp", "thermo", "CPU temp"),
            ("ram_usage", "chip", "Memory"),
            ("disk_usage", "disk", "Storage"),
            ("uptime", "clock", "Uptime"),
            ("arduino_mega", "plug", "Arduino"),
            ("web", "info", "Web app"),
            ("app_key", "lock", "App key"),
        ]
        for r, (key, icon, title) in enumerate(rows):
            grid.addWidget(icon_label(icon, C["muted"], 18), r, 0)
            grid.addWidget(label(title, 12, C["muted"]), r, 1)
            v = label("…", 13, C["text"], bold=True)
            grid.addWidget(v, r, 2)
            self.device_values[key] = v
        grid.setColumnStretch(2, 1)
        box.addWidget(info)
        box.addStretch()
        actions = QHBoxLayout()
        actions.setSpacing(8)
        btn_restart = button("Restart app", icon="refresh", h=42)
        btn_restart.clicked.connect(lambda: run_privileged(["systemctl", "restart", "iot-dashboard.service"]))
        self.btn_reboot = button("Reboot Pi", icon="power", icon_color=C["alert"], tone="danger", h=42)
        self.btn_reboot.clicked.connect(self.on_reboot)
        actions.addWidget(btn_restart)
        actions.addWidget(self.btn_reboot)
        box.addLayout(actions)

    def refresh_device(self):
        diag = hardware.get_system_diagnostics()
        diag["arduino_mega"] = "Connected" if hardware.is_hardware_online else "Not connected"
        diag["ram_usage"] = diag["ram_usage"].split(" (")[0]
        diag["disk_usage"] = diag["disk_usage"].split(" (")[0]
        diag["web"] = f"http://{diag['ip_address']}:8000"
        diag["app_key"] = app_access.app_key()
        for key, lbl in self.device_values.items():
            lbl.setText(str(diag.get(key, "N/A")))

    # ------------------------------------------------------------ wiring
    def build_wiring(self, page):
        box = self.page_box(page)
        pins = card()
        grid = QGridLayout(pins)
        grid.setContentsMargins(10, 3, 10, 3)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(0)
        rows = [
            ("sprout", C["leaf"], "Soil moisture", "A0"),
            ("rain", C["water"], "Rain sensor", "A1"),
            ("sun", C["light"], "Light (LDR)", "A2"),
            ("thermo", C["sun"], "DHT11 / DHT22", "D2"),
            ("power", C["water"], "Pump 1 driver IN1 / IN2", "D5 / D7"),
            ("power", C["fert"], "Pump 2 driver IN3 / IN4", "D6 / D8"),
            ("tank", C["tank"], "Rain tank TRIG / ECHO", "D9 / D10"),
            ("chip", C["muted"], "Status LED", "D13"),
        ]
        for r, (icon, col, name, pin) in enumerate(rows):
            grid.addWidget(icon_label(icon, col, 18), r, 0)
            grid.addWidget(label(name, 12, C["text"]), r, 1)
            grid.addWidget(label(pin, 13, C["leaf"], bold=True, align=Qt.AlignRight | Qt.AlignVCenter), r, 2)
        grid.setColumnStretch(1, 1)
        box.addWidget(pins)
        relays = QHBoxLayout()
        relays.setSpacing(6)
        self.relay_buttons = {}
        for key, name in (("pump", "Pump 1"), ("fert", "Pump 2")):
            b = button("", icon="power", icon_color=C["water"] if key == "pump" else C["fert"], icon_size=16, h=36, size=12)
            b.clicked.connect(lambda _, k=key: self.toggle_relay(k))
            relays.addWidget(b)
            self.relay_buttons[key] = (b, name)
        box.addLayout(relays)
        tests = QHBoxLayout()
        tests.setSpacing(6)
        self.test_buttons = {}
        for n in (1, 2, 3, 4):
            b = button(f"Test IN{n}", h=34, size=12)
            b.clicked.connect(lambda _, k=n: self.run_input_test(k))
            tests.addWidget(b)
            self.test_buttons[n] = b
        box.addLayout(tests)
        self.lbl_test = label("", 11, C["muted"])
        self.lbl_test.setWordWrap(True)
        box.addWidget(self.lbl_test)
        box.addStretch()

    def run_input_test(self, n):
        hardware.test_driver_input(n)
        self.update_telemetry()

    def toggle_relay(self, key):
        hardware.set_pump_direction(key, not hardware.pump_reverse[key])
        self.update_telemetry()

    # ----------------------------------------------------------- actions
    def on_pump(self):
        hardware.toggle_pump()
        self.update_telemetry()

    def on_fert(self):
        hardware.toggle_fert_pump()
        self.update_telemetry()

    def set_mode(self, mode):
        if hardware.pump_mode != mode:
            hardware.toggle_mode()
        self.update_telemetry()

    def style_pump(self, btn, on, tone, icon, text, size):
        btn.setText(text)
        set_tone(btn, tone if on else None)
        set_button_icon(btn, "power" if on else icon, C["bg"] if on else C[tone], size)

    # --------------------------------------------------------- telemetry
    def update_telemetry(self):
        d = hardware.get_telemetry()
        sim, online = d["simulator_mode"], d["hardware_connected"]
        page = self.current

        # Status bar
        self.lbl_clock.setText(time.strftime("%H:%M"))
        self.lbl_date.setText(time.strftime("%a %d %b"))
        if sim:
            status, col, bg = "SIM", C["sun"], "#3a2c12"
        elif online:
            status, col, bg = "ONLINE", C["leaf"], C["leaf_bg"]
        else:
            status, col, bg = "OFFLINE", C["alert"], C["alert_bg"]
        self.lbl_status.setText(f"● {status}")
        css = f"color: {col}; background: {bg}; border-radius: 8px; padding: 1px 6px;"
        if self.lbl_status.styleSheet() != css:
            self.lbl_status.setStyleSheet(css)
        self.lbl_badge.setVisible(bool(d["tank"]["alert"]))
        self.tank_alert.refresh(d["tank"])

        soil, dry, stop = d["soil_moisture"], d["dry_cutoff"], d["stop_cutoff"]

        if page == "home":
            self.refresh_home(d, sim, online)
        elif page == "today":
            self.refresh_today(d)
        elif page == "ai":
            self.refresh_ai()
        elif page == "water":
            on, auto = d["pump_on"], d["pump_mode"] == "AUTO"
            self.style_pump(self.btn_water_pump, on, "water", "power", "Pump ON" if on else "Pump OFF", 20)
            set_tone(self.btn_auto, "selected" if auto else None)
            set_tone(self.btn_manual, None if auto else "selected")
            set_button_icon(self.btn_auto, "auto", C["leaf"] if auto else C["muted"], 22)
            set_button_icon(self.btn_manual, "hand", C["muted"] if auto else C["leaf"], 22)
            self.step_dry.set_value(dry)
            self.step_stop.set_value(stop)
            self.range_bar.set_state(dry, stop, soil)
            u = d["usage"]
            text = (f"AUTO: soil moisture switches pump 1. " if auto else "MANUAL: pump 1 only runs when you switch it. ")
            text += f"Today: {fmt_secs(u['water_s'])} run, about {u['water_l']} L."
            self.lbl_water_info.setText(text)
        elif page == "fert":
            self.refresh_fert(d)
        elif page == "tanks":
            self.refresh_tanks(d, sim, online)
        elif page == "weather":
            self.refresh_weather()
        elif page == "crops":
            for key, b in self.crop_buttons.items():
                set_tone(b, "selected" if key == d["selected_crop"] else None)
        elif page == "wiring":
            for key, (b, name) in self.relay_buttons.items():
                b.setText(f"{name}: {'Reversed' if d['pump_reverse'][key] else 'Forward'}")
            test = d["pump_test"]
            for n, b in self.test_buttons.items():
                set_tone(b, "primary" if test and test["input"] == n else None)
            if test:
                n = test["input"]
                outs = "OUT1 / OUT2 (pump 1)" if n <= 2 else "OUT3 / OUT4 (pump 2)"
                self.lbl_test.setText(f"IN{n} (D{DRIVER_PINS[n]}) HIGH for {test['left']} s, all other inputs LOW: "
                                      f"{outs} should run.")
                set_color(self.lbl_test, C["leaf"])
            else:
                self.lbl_test.setText("Test: one input HIGH for 5 s. IN1 / IN2 should spin pump 1 (opposite "
                                      "ways), IN3 / IN4 pump 2.")
                set_color(self.lbl_test, C["muted"])
        elif page == "sim":
            self.btn_sim.setText("Simulator ON" if sim else "Simulator OFF")
            set_button_icon(self.btn_sim, "sliders", C["bg"] if sim else C["muted"], 22)
            set_tone(self.btn_sim, "primary" if sim else None)
            self.step_sim_t.set_value(d["sim_temp"])
            self.step_sim_h.set_value(d["sim_humidity"])
            self.step_sim_s.set_value(d["sim_soil_moisture"])
            self.step_sim_k.set_value(d["sim_tank_level"])
        elif page == "settings":
            farm = d["farm"]
            for key, b in self.stage_buttons.items():
                set_tone(b, "selected" if key == farm["crop_stage"] else None)
            for key, title, unit, decimals, _ in self.SETTING_TILES:
                v = d["fert_manual_max_min"] if key == "fert_manual_max_min" else farm[key]
                self.setting_tiles[key].setText(f"{fmt_num(v, max(decimals, 1))} {unit}")

    def refresh_home(self, d, sim, online):
        soil, dry, stop = d["soil_moisture"], d["dry_cutoff"], d["stop_cutoff"]
        if soil is None:
            caption, gcol = "No signal", C["dim"]
        elif soil < dry:
            caption, gcol = "Too dry", C["sun"]
        elif soil > stop:
            caption, gcol = "Wet", C["water"]
        else:
            caption, gcol = "Good", C["leaf"]
        self.gauge.set_state(soil, dry, stop, gcol, caption)
        crop = d["crop_name"].split(" / ")[0].replace("Custom Profile", "Custom")[:14]
        self.home_crop.setText(f"{crop} {dry:.0f}–{stop:.0f}%")

        no_sensor = "No sensor" if online and not sim else ("Live only" if sim else "Offline")
        t, h = d["temperature_c"], d["humidity"]
        t_wx, h_wx = d["temperature_source"] == "weather", d["humidity_source"] == "weather"
        self._field("temp", (f"{t:.0f} °C weather" if t_wx else f"{t:.1f} °C") if t is not None else no_sensor,
                    t is not None, t_wx)
        self._field("hum", (f"{h:.0f} % weather" if h_wx else f"{h:.0f} % air") if h is not None else no_sensor,
                    h is not None, h_wx)
        rain, light = d.get("rain"), d.get("light")
        self._field("rain", ("Raining" if rain else "Dry") if rain is not None else no_sensor, rain is not None)
        self._field("light", f"Light {light}%" if light is not None else no_sensor, light is not None)

        self.home_tank.refresh(d["tank"])
        on1, on2 = d["pump_on"], d["fert_pump_on"]
        self.style_pump(self.home_p1, on1, "water", "drop", f"Pump 1\n{'ON' if on1 else d['pump_mode']}", 20)
        self.style_pump(self.home_p2, on2, "fert", "flask",
                        f"Pump 2\n{fmt_secs(d['fert_off_in']) if on2 and d['fert_off_in'] is not None else ('ON' if on2 else 'OFF')}", 20)

        adv = self.get_advice()
        if adv:
            wa, fe = adv["water"], adv["fert"]
            self.home_adv["water"].setText(wa["title"])
            set_color(self.home_adv["water"], ADVICE_COLORS.get(wa["action"], C["text"]))
            self.home_adv["fert"].setText(fe["title"])
            set_color(self.home_adv["fert"], ADVICE_COLORS.get(fe["action"], C["text"]))
            brief = farm_ai.tasks["brief"]["result"]
            if brief:
                note, col = f"✦ {brief['headline']}", C["leaf"]
            elif adv["tips"]:
                note, col = adv["tips"][0], C["sun"]
            else:
                note, col = f"{adv['crop_name'].split(' / ')[0]} · {adv['stage_name']}", C["muted"]
            self.home_adv_note.setText(note)
            set_color(self.home_adv_note, col)

        w = weather.get()
        if w["ok"]:
            cur, today = w["current"], w["daily"][0] if w["daily"] else None
            set_icon(self.home_w_icon, cur["icon"], self._wx_color(cur["icon"]), 40)
            self.home_w_temp.setText(f"{cur['temp']:.0f}°")
            self.home_w_label.setText(cur["label"])
            self.home_w_updated.setText(("old " if w["stale"] else "") + w["updated"])
            set_color(self.home_w_updated, C["sun"] if w["stale"] else C["dim"])
            if today:
                self.home_w_range.setText(f"H {today['max']:.0f}°  L {today['min']:.0f}°  ·  {cur['humidity']}%")
                self.home_w_rain.setText(f"Rain {today['rain_chance']}%  ·  {today['rain_mm']:.0f} mm today")
        else:
            self.home_w_label.setText("No forecast yet")
            self.home_w_range.setText("Needs internet")
            self.home_w_rain.setText("")

    def refresh_today(self, d):
        adv = self.get_advice()
        if not adv:
            return
        crop = adv["crop_name"].split(" / ")[0]
        self.btn_td_crop.setText(crop)
        wx = adv["weather"]
        if wx:
            set_icon(self.td_wx_icon, wx["icon"], self._wx_color(wx["icon"]), 26)
            self.td_title.setText(f"{adv['day']} · {wx['label']}, {wx['max']:.0f}°")
            self.td_sub.setText(f"Rain {wx['rain_chance']}%, {wx['rain_mm']:.0f} mm  ·  {adv['stage_name']}")
        else:
            set_icon(self.td_wx_icon, "cloud", C["dim"], 26)
            self.td_title.setText(f"{adv['day']} · no forecast")
            self.td_sub.setText(f"Using season averages  ·  {adv['stage_name']}")
        wa, fe = adv["water"], adv["fert"]
        wtext = wa["text"] + (f" {wa['note']}" if wa.get("note") else "")
        self.td_water.set(wa["title"], wtext, ADVICE_COLORS.get(wa["action"]))
        self.fill_fert_advice(self.td_fert, self.btn_td_run, fe, d)
        self.td_tips.setText("\n".join(adv["tips"]))

    def fill_fert_advice(self, row, btn, fe, d):
        text = fe["text"] + (f" {fe['note']}" if fe.get("note") else "")
        row.set(fe["title"], text, ADVICE_COLORS.get(fe["action"]))
        show = fe["action"] == "apply"
        btn.setVisible(show)
        if show:
            btn.setText(fmt_secs(fe["run_s"]))
            btn.setEnabled(not d["fert_pump_on"])

    def refresh_fert(self, d):
        on = d["fert_pump_on"]
        left = d["fert_off_in"]
        text = (f"Pump 2 ON · {fmt_secs(left)}" if left is not None else "Pump 2 ON") if on else "Pump 2 OFF"
        self.style_pump(self.btn_fert, on, "fert", "power", text, 24)
        u, farm = d["usage"], d["farm"]
        self.lbl_fert_today.setText(f"{fmt_secs(u['fert_s'])} · {fmt_num(u['fert_l'])} L")
        last = farm["fert_last_date"]
        if last:
            days = (time.mktime(time.strptime(time.strftime("%Y-%m-%d"), "%Y-%m-%d"))
                    - time.mktime(time.strptime(last, "%Y-%m-%d"))) / 86400
            self.lbl_fert_last.setText("Fed today" if days < 1 else f"Last fed {days:.0f} d ago")
        else:
            self.lbl_fert_last.setText("No feed recorded")
        adv = self.get_advice()
        if adv:
            self.fill_fert_advice(self.fert_adv, self.btn_fert_sugg, adv["fert"], d)
        self.lbl_fert_info.setText(f"Manual pump. Stops by itself after the run time "
                                   f"(at most {d['fert_manual_max_min']:.0f} min, set in Settings).")

    def refresh_tanks(self, d, sim, online):
        t = d["tank"]
        self.tk_glyph.set_state(t["level"], t["alert"])
        lvl, sub, col = tank_text(t)
        self.tk_level.setText(lvl)
        set_color(self.tk_level, C["alert"] if t["alert"] else (C["text"] if t["level"] is not None else C["dim"]))
        if t["level"] is not None:
            self.tk_litres.setText(f"{fmt_num(t['litres'], 0)} of {fmt_num(t['capacity_l'], 0)} L")
            self.tk_dist.setText(f"{t['cm']:.0f} cm to water")
        else:
            self.tk_litres.setText("No reading")
            self.tk_dist.setText("Check the sensor" if online and not sim else "Offline")
        if t["alert"]:
            self.tk_state.setText(f"FULL since {t['alert_since']}. Release the water, then Reset.")
            set_color(self.tk_state, C["alert"])
        else:
            self.tk_state.setText(f"OK. Last released {t['last_released']}." if t["last_released"]
                                  else f"Alerts at {t['alert_pct']:.0f}%.")
            set_color(self.tk_state, C["muted"])
        self.btn_tk_reset.setEnabled(bool(t["alert"]))
        set_tone(self.btn_tk_reset, "primary" if t["alert"] else None)
        set_button_icon(self.btn_tk_reset, "check", C["bg"] if t["alert"] else C["dim"], 16)
        self.step_tank_alert.set_value(t["alert_pct"])
        self.step_tank_height.set_value(t["empty_cm"])
        self.step_tank_gap.set_value(t["full_cm"])
        self.btn_cal_area.setText(f"{fmt_num(t['area_cm2'], 0)} cm²")

    def _field(self, key, text, ok, from_weather=False):
        """from_weather: the value is the weather station's, shown in muted colour."""
        ic, v = self.field[key]
        v.setText(text)
        set_color(v, C["muted"] if from_weather else (C["text"] if ok else C["dim"]))

    @staticmethod
    def _wx_color(icon):
        return {"sun": C["light"], "moon": C["muted"], "cloudsun": C["light"], "rain": C["water"],
                "storm": C["sun"], "fog": C["muted"], "cloud": C["muted"]}.get(icon, C["muted"])

    def refresh_weather(self):
        w = weather.get()
        if not w["ok"]:
            self.wx_label.setText("No forecast yet")
            self.wx_feels.setText(w.get("error") or "Needs internet")
            return
        cur = w["current"]
        set_icon(self.wx_icon, cur["icon"], self._wx_color(cur["icon"]), 52)
        self.wx_temp.setText(f"{cur['temp']:.0f}°C")
        self.wx_label.setText(f"{cur['label']} · Alappuzha")
        self.wx_feels.setText(f"Feels {cur['feels']:.0f}°  ·  Updated {w['updated']}" + ("  (old)" if w["stale"] else ""))
        today = w["daily"][0] if w["daily"] else {}
        self.wx_stats["hum"].setText(f"{cur['humidity']}%")
        self.wx_stats["wind"].setText(f"{cur['wind']:.0f} km/h")
        self.wx_stats["rise"].setText(today.get("sunrise", "--"))
        self.wx_stats["set"].setText(today.get("sunset", "--"))
        hours = w["hourly"][::max(1, len(w["hourly"]) // 8)][:8] if len(w["hourly"]) > 8 else w["hourly"]
        for i, (t, ic, tp, rp) in enumerate(self.wx_hours):
            if i < len(hours):
                hr = hours[i]
                t.setText("Now" if i == 0 else hr["time"])
                set_icon(ic, hr["icon"], self._wx_color(hr["icon"]), 20)
                tp.setText(f"{hr['temp']:.0f}°")
                rp.setText(f"{hr['rain_chance']}%" if hr["rain_chance"] is not None else "")
        for i, (dn, ic, tr, rp) in enumerate(self.wx_days):
            if i < len(w["daily"]):
                day = w["daily"][i]
                dn.setText("Today" if i == 0 else day["day"])
                set_icon(ic, day["icon"], self._wx_color(day["icon"]), 22)
                tr.setText(f"{day['max']:.0f}° / {day['min']:.0f}°")
                rp.setText(f"Rain {day['rain_chance']}%")


def main():
    fullscreen = "--fullscreen" in sys.argv
    os.environ["QT_QPA_FB_DISABLE_INPUT"] = "1"  # only touch_driver may deliver taps (see main.py)
    app = QApplication(sys.argv)
    app.setFont(px_font(13))
    app.setStyleSheet(THEME)
    IoTTouchDashboard(fullscreen=fullscreen)
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
