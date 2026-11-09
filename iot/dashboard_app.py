#!/usr/bin/env python3
"""
Smart Farm touchscreen dashboard for the 3.5" (480x320) ADS7846 LCD on Raspberry Pi 4.

Home screen: soil moisture gauge with cutoff markers, temperature / humidity /
tank / weather tiles, pump button and AUTO / MANUAL mode switch.
Settings: Crops, Cutoffs, Simulator, Wi-Fi (with on-screen keyboard), Device, Wiring.

The resistive touch driver only delivers taps, so every control is a large
button or +/- stepper; nothing relies on dragging or scrolling.
"""

import sys
import math
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QFrame, QGridLayout
)
from PyQt5.QtCore import Qt, QTimer, QSize, QRectF, QPointF, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QPainter, QPen, QBrush, QFontMetricsF

from hardware_manager import hardware, CROP_PRESETS, run_privileged
from touch_driver import HardwareTouchInjector, inject_qt_click
from keyboard_dialog import get_text_input
from icons import qt_pixmap, qt_icon
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
    "light": "#f5d76e",
    "alert": "#ef5d50",
    "alert_bg": "#3a1a17",
}

CROP_COLORS = {
    "tomato": "#ef6a5a", "paddy": "#e9c46a", "chilli": "#e4572e", "potato": "#c89f6b",
    "corn": "#f2c14e", "arid": "#8fd16a", "onion": "#c77dba", "custom": "#93a394",
}

FONT = "DejaVu Sans"

THEME = f"""
QWidget {{
    background-color: {C['bg']};
    color: {C['text']};
}}
QLabel {{ background: transparent; }}
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
    padding: 0px 10px;
}}
QPushButton:pressed {{ background-color: {C['line']}; }}
QPushButton[tone="primary"] {{
    background-color: {C['leaf']};
    color: {C['bg']};
    border: 1px solid {C['leaf']};
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
QPushButton[nav="true"] {{
    text-align: left;
    padding-left: 10px;
    background-color: transparent;
    color: {C['muted']};
    border: 1px solid transparent;
}}
QPushButton[nav="true"][tone="selected"] {{
    background-color: {C['leaf_bg']};
    color: {C['leaf']};
    border: 1px solid {C['leaf']};
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


def caps(text, color=None):
    """Small uppercase section caption."""
    lbl = label(text.upper(), 11, color or C["muted"], bold=True)
    f = lbl.font()
    f.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)
    lbl.setFont(f)
    return lbl


def icon_label(name, color, size=22):
    lbl = QLabel()
    lbl.setPixmap(qt_pixmap(name, color, size))
    lbl.setFixedSize(size, size)
    return lbl


def button(text="", icon=None, icon_color=None, icon_size=22, tone=None, h=44, w=None):
    btn = QPushButton(text)
    btn.setFocusPolicy(Qt.NoFocus)
    btn.setFont(px_font(14, True))
    if icon:
        btn.setIcon(qt_icon(icon, icon_color or C["text"], icon_size))
        btn.setIconSize(QSize(icon_size, icon_size))
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


def passthrough(*widgets):
    """Child labels inside buttons must not swallow taps."""
    for w in widgets:
        w.setAttribute(Qt.WA_TransparentForMouseEvents)


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
        self.setMinimumSize(150, 120)

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
        thick = 12.0
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
            a = self._point(cx, cy, r - thick / 2 - 4, frac)
            b = self._point(cx, cy, r + thick / 2 + 4, frac)
            # Dark halo keeps the marker visible on a same-coloured value arc
            p.setPen(QPen(QColor(C["surface"]), 7, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(a, b)
            p.setPen(QPen(QColor(col), 3, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(a, b)

        # Value + unit
        val = "--" if self.value is None else f"{self.value:.0f}"
        f_big, f_unit = px_font(36, True), px_font(15, True)
        tw = QFontMetricsF(f_big).horizontalAdvance(val)
        uw = QFontMetricsF(f_unit).horizontalAdvance("%")
        x0 = cx - (tw + uw + 2) / 2
        base = cy + 12
        p.setPen(QColor(C["text"]))
        p.setFont(f_big)
        p.drawText(QPointF(x0, base), val)
        p.setPen(QColor(C["muted"]))
        p.setFont(f_unit)
        p.drawText(QPointF(x0 + tw + 2, base), "%")

        # Condition caption in the gauge opening
        p.setPen(QColor(self.color))
        p.setFont(px_font(13, True))
        p.drawText(QRectF(0, cy + r * 0.5 - 10, w, 22), Qt.AlignCenter, self.caption)
        p.end()


class RangeBar(QWidget):
    """0-100% bar showing the watering band and the current soil reading."""

    def __init__(self):
        super().__init__()
        self.dry, self.stop, self.soil = 35.0, 65.0, None
        self.setFixedHeight(34)

    def set_state(self, dry, stop, soil):
        if (dry, stop, soil) != (self.dry, self.stop, self.soil):
            self.dry, self.stop, self.soil = dry, stop, soil
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width() - 12
        x0, y, bh = 6.0, 8.0, 10.0
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


class Tile(QFrame):
    """Compact sensor tile: icon + caption, big value + unit, status line."""

    def __init__(self, icon, title, color):
        super().__init__()
        self.setObjectName("Card")
        box = QVBoxLayout(self)
        box.setContentsMargins(10, 8, 10, 8)
        box.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(6)
        self.icon = icon_label(icon, color, 20)
        top.addWidget(self.icon)
        top.addWidget(caps(title))
        top.addStretch()
        box.addLayout(top)
        box.addStretch()

        row = QHBoxLayout()
        row.setSpacing(3)
        self.val = label("--", 26, C["text"], bold=True)
        self.unit = label("", 13, C["muted"], bold=True)
        row.addWidget(self.val, alignment=Qt.AlignBottom)
        row.addWidget(self.unit, alignment=Qt.AlignBottom)
        row.addStretch()
        box.addLayout(row)

        self.sub = label("", 12, C["muted"])
        box.addWidget(self.sub)

    def set(self, value, unit="", sub="", sub_color=None, icon=None, icon_color=None):
        self.val.setText(value)
        self.val.setStyleSheet(f"color: {C['text'] if value != '--' else C['dim']};")
        self.unit.setText(unit if value != "--" else "")
        self.sub.setText(sub)
        self.sub.setStyleSheet(f"color: {sub_color or C['muted']};")
        if icon:
            self.icon.setPixmap(qt_pixmap(icon, icon_color, 20))


class Stepper(QFrame):
    """Label + value with large - / + buttons (tap-only friendly)."""

    def __init__(self, icon, title, color, on_step, step, fmt):
        super().__init__()
        self.setObjectName("Card")
        self.fmt = fmt
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 4, 6, 4)
        row.setSpacing(8)
        row.addWidget(icon_label(icon, color, 22))
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(label(title, 12, C["muted"], bold=True))
        self.val = label("--", 20, C["text"], bold=True)
        col.addWidget(self.val)
        row.addLayout(col, stretch=1)
        minus = button(icon="minus", w=54, h=42)
        plus = button(icon="plus", w=54, h=42)
        minus.clicked.connect(lambda: on_step(-step))
        plus.clicked.connect(lambda: on_step(step))
        row.addWidget(minus)
        row.addWidget(plus)

    def set_value(self, v):
        self.val.setText(self.fmt.format(v))


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class IoTTouchDashboard(QMainWindow):
    hardware_touch_signal = pyqtSignal(int, int)

    TABS = [
        ("crops", "Crops", "sprout"),
        ("cutoffs", "Cutoffs", "gauge"),
        ("tank", "Tank", "tank"),
        ("sim", "Simulator", "sliders"),
        ("wifi", "Wi-Fi", "wifi"),
        ("device", "Device", "chip"),
        ("info", "Wiring", "plug"),
    ]
    WIFI_PAGE_SIZE = 4

    def __init__(self, fullscreen: bool = False):
        super().__init__()
        self.setWindowTitle("Smart Farm")
        self.setFixedSize(480, 320)

        self.wifi_networks = []
        self.wifi_page = 0
        self.reboot_armed = False

        self.stack = QStackedWidget(self)
        self.setCentralWidget(self.stack)
        self.page_home = QWidget()
        self.page_settings = QWidget()
        self.build_home()
        self.build_settings()
        self.stack.addWidget(self.page_home)
        self.stack.addWidget(self.page_settings)

        self.hardware_touch_signal.connect(lambda x, y: inject_qt_click(self, x, y))
        self.touch_injector = HardwareTouchInjector(self.hardware_touch_signal.emit)
        self.touch_injector.start()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.update_telemetry)
        self.refresh_timer.start(500)
        self.update_telemetry()

        if fullscreen:
            self.showFullScreen()
        else:
            self.show()

    # ------------------------------------------------------------------ home
    def build_home(self):
        root = QVBoxLayout(self.page_home)
        root.setContentsMargins(8, 6, 8, 8)
        root.setSpacing(8)

        # Header
        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(icon_label("leaf", C["leaf"], 24))
        header.addWidget(label("Smart Farm", 18, C["text"], bold=True))
        header.addStretch()
        self.lbl_status = label("", 12, bold=True)
        header.addWidget(self.lbl_status)
        self.lbl_clock = label("--:--", 15, C["muted"], bold=True)
        header.addWidget(self.lbl_clock)
        btn_settings = button(icon="gear", icon_color=C["text"], icon_size=24, w=48, h=40)
        btn_settings.clicked.connect(lambda: self.open_settings("crops"))
        header.addWidget(btn_settings)
        root.addLayout(header)

        # Body: gauge card + 2x2 tiles
        body = QHBoxLayout()
        body.setSpacing(8)

        gauge_card = card()
        gauge_card.setFixedWidth(196)
        g = QVBoxLayout(gauge_card)
        g.setContentsMargins(8, 8, 8, 6)
        g.setSpacing(0)
        g_top = QHBoxLayout()
        g_top.setSpacing(6)
        g_top.addWidget(icon_label("sprout", C["leaf"], 20))
        g_top.addWidget(caps("Soil moisture"))
        g_top.addStretch()
        g.addLayout(g_top)
        self.gauge = ArcGauge()
        g.addWidget(self.gauge, stretch=1)
        self.btn_crop = button("", tone="quiet", h=30)
        self.btn_crop.setFont(px_font(12, True))
        self.btn_crop.clicked.connect(lambda: self.open_settings("crops"))
        g.addWidget(self.btn_crop)
        body.addWidget(gauge_card)

        grid = QGridLayout()
        grid.setSpacing(8)
        self.tile_temp = Tile("thermo", "Temp", C["sun"])
        self.tile_hum = Tile("drop", "Humidity", C["water"])
        self.tile_tank = Tile("tank", "Tank", C["tank"])
        self.tile_weather = Tile("sun", "Weather", C["light"])
        grid.addWidget(self.tile_temp, 0, 0)
        grid.addWidget(self.tile_hum, 0, 1)
        grid.addWidget(self.tile_tank, 1, 0)
        grid.addWidget(self.tile_weather, 1, 1)
        body.addLayout(grid, stretch=1)
        root.addLayout(body, stretch=1)

        # Controls: pump + mode switch
        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.btn_pump = button("PUMP OFF", icon="power", icon_size=24, h=52, w=196)
        self.btn_pump.setFont(px_font(16, True))
        self.btn_pump.clicked.connect(self.on_pump)
        controls.addWidget(self.btn_pump)

        self.btn_auto = button("AUTO", icon="auto", h=52)
        self.btn_manual = button("MANUAL", icon="hand", h=52)
        self.btn_auto.clicked.connect(lambda: self.set_mode("AUTO"))
        self.btn_manual.clicked.connect(lambda: self.set_mode("MANUAL"))
        controls.addWidget(self.btn_auto, stretch=1)
        controls.addWidget(self.btn_manual, stretch=1)
        root.addLayout(controls)

    # -------------------------------------------------------------- settings
    def build_settings(self):
        root = QVBoxLayout(self.page_settings)
        root.setContentsMargins(8, 6, 8, 8)
        root.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(10)
        btn_back = button("Home", icon="back", h=40, w=100)
        btn_back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        header.addWidget(btn_back)
        self.lbl_settings_title = label("", 18, C["text"], bold=True)
        header.addWidget(self.lbl_settings_title)
        header.addStretch()
        self.lbl_settings_status = label("", 12, bold=True)
        header.addWidget(self.lbl_settings_status)
        root.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(8)

        nav = QVBoxLayout()
        nav.setSpacing(3)
        self.nav_buttons = {}
        for key, title, icon in self.TABS:
            b = button(title, icon=icon, icon_size=18, h=34, w=112)
            b.setFont(px_font(12, True))
            b.setProperty("nav", True)
            b.clicked.connect(lambda _, k=key: self.open_settings(k))
            nav.addWidget(b)
            self.nav_buttons[key] = b
        nav.addStretch()
        body.addLayout(nav)

        self.tab_stack = QStackedWidget()
        self.tab_index = {}
        builders = {
            "crops": self.build_tab_crops, "cutoffs": self.build_tab_cutoffs,
            "tank": self.build_tab_tank,
            "sim": self.build_tab_sim, "wifi": self.build_tab_wifi,
            "device": self.build_tab_device, "info": self.build_tab_info,
        }
        for key, _, _ in self.TABS:
            page = QWidget()
            builders[key](page)
            self.tab_index[key] = self.tab_stack.addWidget(page)
        body.addWidget(self.tab_stack, stretch=1)
        root.addLayout(body, stretch=1)

    def open_settings(self, key):
        self.tab_stack.setCurrentIndex(self.tab_index[key])
        for k, b in self.nav_buttons.items():
            set_tone(b, "selected" if k == key else None)
            col = C["leaf"] if k == key else C["muted"]
            b.setIcon(qt_icon(dict((t[0], t[2]) for t in self.TABS)[k], col, 18))
        self.lbl_settings_title.setText(dict((t[0], t[1]) for t in self.TABS)[key])
        self.stack.setCurrentIndex(1)
        self.disarm_reboot()

        if key == "wifi":
            self.refresh_wifi(rescan=not self.wifi_networks)
        elif key == "device":
            self.refresh_device()
        self.update_telemetry()

    # Crops ------------------------------------------------------------------
    def build_tab_crops(self, page):
        grid = QGridLayout(page)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        self.crop_buttons = {}
        for i, (key, preset) in enumerate(CROP_PRESETS.items()):
            b = QPushButton()
            b.setFocusPolicy(Qt.NoFocus)
            b.setFixedHeight(58)
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

    # Cutoffs ----------------------------------------------------------------
    def build_tab_cutoffs(self, page):
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        self.step_dry = Stepper("power", "Pump starts below", C["sun"],
                                lambda d: self.adjust_cutoff("dry", d), 5, "{:.0f} %")
        self.step_stop = Stepper("drop", "Pump stops at", C["water"],
                                 lambda d: self.adjust_cutoff("stop", d), 5, "{:.0f} %")
        self.step_dry.setFixedHeight(66)
        self.step_stop.setFixedHeight(66)
        box.addWidget(self.step_dry)
        box.addWidget(self.step_stop)
        bar_card = card()
        bc = QVBoxLayout(bar_card)
        bc.setContentsMargins(8, 8, 8, 6)
        bc.setSpacing(2)
        bc.addWidget(caps("Watering band"))
        self.range_bar = RangeBar()
        bc.addWidget(self.range_bar)
        box.addWidget(bar_card)
        box.addStretch()

    def adjust_cutoff(self, which, delta):
        if which == "dry":
            hardware.adjust_dry_cutoff(delta)
        else:
            hardware.adjust_stop_cutoff(delta)
        self.update_telemetry()

    # Tank -------------------------------------------------------------------
    def build_tab_tank(self, page):
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)

        live = card()
        lrow = QHBoxLayout(live)
        lrow.setContentsMargins(10, 6, 10, 6)
        lrow.setSpacing(8)
        lrow.addWidget(icon_label("tank", C["tank"], 24))
        self.lbl_tank_level = label("--", 20, C["text"], bold=True)
        lrow.addWidget(self.lbl_tank_level)
        lrow.addStretch()
        self.lbl_tank_dist = label("", 12, C["muted"], align=Qt.AlignRight | Qt.AlignVCenter)
        lrow.addWidget(self.lbl_tank_dist)
        live.setFixedHeight(50)
        box.addWidget(live)

        self.step_tank_height = Stepper("tank", "Tank height", C["tank"],
                                        lambda dlt: self.adjust_tank("height", dlt), 5, "{:.0f} cm")
        self.step_tank_gap = Stepper("drop", "Gap when full", C["water"],
                                     lambda dlt: self.adjust_tank("gap", dlt), 1, "{:.0f} cm")
        for st in (self.step_tank_height, self.step_tank_gap):
            st.setFixedHeight(58)
            box.addWidget(st)

        marks = QHBoxLayout()
        marks.setSpacing(6)
        self.btn_mark_empty = button("Empty now", icon="minus", icon_color=C["muted"], icon_size=18, h=40)
        self.btn_mark_full = button("Full now", icon="check", icon_color=C["leaf"], icon_size=18, h=40)
        self.btn_mark_empty.setFont(px_font(13, True))
        self.btn_mark_full.setFont(px_font(13, True))
        self.btn_mark_empty.clicked.connect(lambda: self.mark_tank("empty"))
        self.btn_mark_full.clicked.connect(lambda: self.mark_tank("full"))
        marks.addWidget(self.btn_mark_empty)
        marks.addWidget(self.btn_mark_full)
        box.addLayout(marks)
        self.lbl_tank_hint = label("Height: sensor to floor. Gap: sensor to water when full.", 11, C["muted"])
        box.addWidget(self.lbl_tank_hint)
        box.addStretch()

    def adjust_tank(self, which, delta):
        if which == "height":
            hardware.set_tank_calibration(empty_cm=hardware.tank_empty_cm + delta)
        else:
            hardware.set_tank_calibration(full_cm=hardware.tank_full_cm + delta)
        self.update_telemetry()

    def mark_tank(self, which):
        if hardware.mark_tank(which) is None:
            self.lbl_tank_hint.setText("No sensor reading — check the ultrasonic wiring.")
            self.lbl_tank_hint.setStyleSheet(f"color: {C['alert']};")
        else:
            self.lbl_tank_hint.setText(f"Saved current distance as {'empty' if which == 'empty' else 'full'}.")
            self.lbl_tank_hint.setStyleSheet(f"color: {C['leaf']};")
        self.update_telemetry()

    # Simulator --------------------------------------------------------------
    def build_tab_sim(self, page):
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        self.btn_sim = button("Simulator OFF", icon="sliders", h=44)
        self.btn_sim.clicked.connect(self.toggle_sim)
        box.addWidget(self.btn_sim)
        box.addWidget(label("Fake values for testing. The pump follows soil.", 11, C["muted"]))
        self.step_sim_t = Stepper("thermo", "Temperature", C["sun"], lambda d: self.step_sim("temp", d), 1, "{:.0f} °C")
        self.step_sim_h = Stepper("drop", "Humidity", C["water"], lambda d: self.step_sim("hum", d), 5, "{:.0f} %")
        self.step_sim_s = Stepper("sprout", "Soil moisture", C["leaf"], lambda d: self.step_sim("soil", d), 5, "{:.0f} %")
        for s in (self.step_sim_t, self.step_sim_h, self.step_sim_s):
            s.setFixedHeight(56)
            box.addWidget(s)
        box.addStretch()

    def toggle_sim(self):
        hardware.toggle_simulator_mode()
        self.update_telemetry()

    def step_sim(self, kind, delta):
        if kind == "temp":
            hardware.set_simulated_sensors(temp=max(0, min(50, hardware.sim_temp + delta)))
        elif kind == "hum":
            hardware.set_simulated_sensors(humidity=max(0, min(100, hardware.sim_humidity + delta)))
        else:
            hardware.set_simulated_sensors(soil_moisture=max(0, min(100, hardware.sim_soil_moisture + delta)))
        self.update_telemetry()

    # Wi-Fi ------------------------------------------------------------------
    def build_tab_wifi(self, page):
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(6)
        self.lbl_wifi = label("Wi-Fi", 13, C["leaf"], bold=True)
        top.addWidget(self.lbl_wifi, stretch=1)
        btn_scan = button(icon="refresh", w=48, h=38)
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
        self.btn_wifi_prev = button(icon="back", w=56, h=36)
        self.btn_wifi_next = button(icon="next", w=56, h=36)
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
        if curr["connected"]:
            self.lbl_wifi.setText(f"{curr['ssid']}  ·  {curr['signal']}%")
            self.lbl_wifi.setStyleSheet(f"color: {C['leaf']};")
        else:
            self.lbl_wifi.setText("Not connected")
            self.lbl_wifi.setStyleSheet(f"color: {C['alert']};")
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
                ic.setPixmap(qt_pixmap("wifi", strength, 20))
                name.setText(net["ssid"][:22])
                name.setStyleSheet(f"color: {C['leaf'] if net['active'] else C['text']};")
                secured = net.get("security", "") not in ("", "--")
                if secured:
                    lock.setPixmap(qt_pixmap("lock", C["muted"], 16))
                else:
                    lock.clear()
                sig.setText(f"{net['signal']}%")
                set_tone(b, "selected" if net["active"] else None)
                b.setEnabled(True)
                b.show()
            else:
                b.hide()
        if not self.wifi_networks:
            self.lbl_wifi_page.setText("No networks found")
        else:
            self.lbl_wifi_page.setText(f"{self.wifi_page + 1} / {pages}")
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
        self.lbl_wifi.setStyleSheet(f"color: {C['sun']};")
        QApplication.processEvents()
        res = wifi_manager.connect_wifi(ssid, password)
        if not res["success"]:
            self.lbl_wifi.setText(f"Failed: {res['message'][:28]}")
            self.lbl_wifi.setStyleSheet(f"color: {C['alert']};")
            return
        self.refresh_wifi(rescan=True)

    # Device -----------------------------------------------------------------
    def build_tab_device(self, page):
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        info = card()
        grid = QGridLayout(info)
        grid.setContentsMargins(10, 8, 10, 8)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(5)
        self.device_values = {}
        rows = [
            ("ip_address", "wifi", "Address"),
            ("cpu_temp", "thermo", "CPU temp"),
            ("ram_usage", "chip", "Memory"),
            ("disk_usage", "disk", "Storage"),
            ("uptime", "clock", "Uptime"),
            ("arduino_mega", "plug", "Arduino"),
        ]
        for r, (key, icon, title) in enumerate(rows):
            grid.addWidget(icon_label(icon, C["muted"], 18), r, 0)
            grid.addWidget(label(title, 12, C["muted"]), r, 1)
            v = label("…", 12, C["text"], bold=True)
            grid.addWidget(v, r, 2)
            self.device_values[key] = v
        grid.setColumnStretch(2, 1)
        box.addWidget(info)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        btn_restart = button("Restart app", icon="refresh", h=44)
        btn_restart.clicked.connect(lambda: run_privileged(["systemctl", "restart", "iot-dashboard.service"]))
        self.btn_reboot = button("Reboot Pi", icon="power", icon_color=C["alert"], tone="danger", h=44)
        self.btn_reboot.clicked.connect(self.on_reboot)
        actions.addWidget(btn_restart)
        actions.addWidget(self.btn_reboot)
        box.addLayout(actions)
        box.addStretch()

    def refresh_device(self):
        diag = hardware.get_system_diagnostics()
        diag["arduino_mega"] = "Connected" if hardware.is_hardware_online else "Not connected"
        diag["ram_usage"] = diag["ram_usage"].split(" (")[0]
        diag["disk_usage"] = diag["disk_usage"].split(" (")[0]
        for key, lbl in self.device_values.items():
            lbl.setText(str(diag.get(key, "N/A")))

    def on_reboot(self):
        # Two taps needed: first arms, second reboots
        if not self.reboot_armed:
            self.reboot_armed = True
            self.btn_reboot.setText("Tap to confirm")
            self.btn_reboot.setIcon(qt_icon("power", C["bg"], 22))
            set_tone(self.btn_reboot, "danger-armed")
            QTimer.singleShot(4000, self.disarm_reboot)
            return
        self.btn_reboot.setText("Rebooting…")
        run_privileged(["reboot"])

    def disarm_reboot(self):
        if getattr(self, "reboot_armed", False):
            self.reboot_armed = False
            self.btn_reboot.setText("Reboot Pi")
            self.btn_reboot.setIcon(qt_icon("power", C["alert"], 22))
            set_tone(self.btn_reboot, "danger")

    # Wiring info ------------------------------------------------------------
    def build_tab_info(self, page):
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        pins = card()
        grid = QGridLayout(pins)
        grid.setContentsMargins(10, 6, 10, 6)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(1)
        rows = [
            ("sprout", C["leaf"], "Soil moisture", "A0"),
            ("rain", C["water"], "Rain sensor", "A1"),
            ("sun", C["light"], "Light (LDR)", "A2"),
            ("tank", C["tank"], "Ultrasonic TRIG", "D9"),
            ("tank", C["tank"], "Ultrasonic ECHO", "D10"),
            ("thermo", C["sun"], "DHT11 / DHT22", "D2"),
            ("power", C["alert"], "Pump relay (active LOW)", "D8"),
            ("chip", C["muted"], "Status LED", "D13"),
        ]
        for r, (icon, col, name, pin) in enumerate(rows):
            grid.addWidget(icon_label(icon, col, 18), r, 0)
            grid.addWidget(label(name, 12, C["text"]), r, 1)
            grid.addWidget(label(pin, 13, C["leaf"], bold=True, align=Qt.AlignRight | Qt.AlignVCenter), r, 2)
        grid.setColumnStretch(1, 1)
        box.addWidget(pins)
        note = label("Mega ↔ Pi over USB (/dev/ttyACM0, 115200). Relay COM → pump supply +, "
                     "NO → pump +. Join pump supply GND to Mega GND.", 11, C["muted"])
        note.setWordWrap(True)
        box.addWidget(note)
        box.addStretch()

    # ---------------------------------------------------------------- actions
    def on_pump(self):
        hardware.toggle_pump()
        self.update_telemetry()

    def set_mode(self, mode):
        if hardware.pump_mode != mode:
            hardware.toggle_mode()
        self.update_telemetry()

    # ------------------------------------------------------------- telemetry
    def update_telemetry(self):
        d = hardware.get_telemetry()
        sim, online = d["simulator_mode"], d["hardware_connected"]
        live = sim or online

        self.lbl_clock.setText(d["timestamp"][:5])
        if sim:
            status, col, bg = "SIMULATOR", C["sun"], "#3a2c12"
        elif online:
            status, col, bg = "ONLINE", C["leaf"], C["leaf_bg"]
        else:
            status, col, bg = "OFFLINE", C["alert"], C["alert_bg"]
        pill = f"color: {col}; background: {bg}; border-radius: 12px; padding: 4px 10px;"
        for lbl in (self.lbl_status, self.lbl_settings_status):
            lbl.setText(f"● {status}")
            lbl.setStyleSheet(pill)

        # Soil gauge
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
        crop_name = "Custom" if d["selected_crop"] == "custom" else d["crop_name"].split(" / ")[0]
        self.btn_crop.setText(f"{crop_name}  ·  {dry:.0f}–{stop:.0f}%")
        self.btn_crop.setIcon(qt_icon("sprout", CROP_COLORS.get(d["selected_crop"], C["muted"]), 16))

        # Tiles
        no_sensor = "No sensor" if online and not sim else "Offline"
        t = d["temperature_c"]
        if t is not None:
            self.tile_temp.set(f"{t:.1f}", "°C", f"{d['temperature_f']:.0f} °F")
        else:
            self.tile_temp.set("--", sub=no_sensor, sub_color=C["alert"] if online else C["dim"])
        h = d["humidity"]
        if h is not None:
            self.tile_hum.set(f"{h:.0f}", "%", "Air humidity")
        else:
            self.tile_hum.set("--", sub=no_sensor, sub_color=C["alert"] if online else C["dim"])

        off_sub = "Live only" if sim else "Offline"
        wl, wcm = d.get("water_level"), d.get("water_cm")
        if wl is not None:
            low = wl < 20
            self.tile_tank.set(f"{wl}", "%", "Refill tank" if low else f"{wcm:.0f} cm to water",
                               sub_color=C["alert"] if low else None)
        elif online and not sim:
            self.tile_tank.set("--", sub="No echo", sub_color=C["alert"])
        else:
            self.tile_tank.set("--", sub=off_sub, sub_color=C["dim"])

        # Tank settings page
        self.step_tank_height.set_value(d["tank_empty_cm"])
        self.step_tank_gap.set_value(d["tank_full_cm"])
        if wl is not None:
            self.lbl_tank_level.setText(f"{wl} % full")
            self.lbl_tank_dist.setText(f"{wcm:.0f} cm to water")
        else:
            self.lbl_tank_level.setText("--")
            self.lbl_tank_dist.setText("No sensor reading" if online and not sim else "Offline")
        rain, light = d.get("rain"), d.get("light")
        if rain is not None:
            raining = bool(rain)
            self.tile_weather.set("Rain" if raining else "Dry", "", f"Light {light}%",
                                  icon="rain" if raining else "sun",
                                  icon_color=C["water"] if raining else C["light"])
        else:
            self.tile_weather.set("--", sub=off_sub, sub_color=C["dim"], icon="sun", icon_color=C["light"])

        # Pump + mode
        if d["pump_on"]:
            self.btn_pump.setText("PUMP ON")
            self.btn_pump.setIcon(qt_icon("power", C["bg"], 24))
            set_tone(self.btn_pump, "primary")
        else:
            self.btn_pump.setText("PUMP OFF")
            self.btn_pump.setIcon(qt_icon("power", C["muted"], 24))
            set_tone(self.btn_pump, None)
        auto = d["pump_mode"] == "AUTO"
        set_tone(self.btn_auto, "selected" if auto else None)
        set_tone(self.btn_manual, None if auto else "selected")
        self.btn_auto.setIcon(qt_icon("auto", C["leaf"] if auto else C["muted"], 22))
        self.btn_manual.setIcon(qt_icon("hand", C["muted"] if auto else C["leaf"], 22))

        # Settings pages that mirror live state
        for key, b in self.crop_buttons.items():
            set_tone(b, "selected" if key == d["selected_crop"] else None)
        self.step_dry.set_value(dry)
        self.step_stop.set_value(stop)
        self.range_bar.set_state(dry, stop, soil)

        self.btn_sim.setText("Simulator ON" if sim else "Simulator OFF")
        self.btn_sim.setIcon(qt_icon("sliders", C["bg"] if sim else C["muted"], 22))
        set_tone(self.btn_sim, "primary" if sim else None)
        self.step_sim_t.set_value(d["sim_temp"])
        self.step_sim_h.set_value(d["sim_humidity"])
        self.step_sim_s.set_value(d["sim_soil_moisture"])


def main():
    fullscreen = "--fullscreen" in sys.argv
    app = QApplication(sys.argv)
    app.setFont(px_font(13))
    app.setStyleSheet(THEME)
    IoTTouchDashboard(fullscreen=fullscreen)
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
