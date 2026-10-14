#!/usr/bin/env python3
"""
Blynk-Inspired 3.5" (480x320) TFT Touchscreen IoT Interactive Device & Dashboard
Engineered specifically for ADS7846 SPI Resistive Touch on Raspberry Pi 4.
Features:
- Main Blynk-style dashboard with active crop badge & small corner motor button
- Multi-Tab Settings Hub:
  * 🌾 Crop Profiles (Tomato, Paddy, Chilli, Potato, Corn, Cactus, Custom)
  * 💧 Cutoff Adjuster (5% increment/decrement touch buttons)
  * 📶 Wi-Fi Controls (Network scanner + On-Screen Touch Keyboard for passwords)
  * ⚙️ Device Diagnostics (CPU Temp, RAM, Disk, Uptime, Reboot)
- Full virtual on-screen QWERTY touch keyboard
"""

import sys
import os
import time
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QProgressBar, QFrame, QGridLayout,
    QScrollArea, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QColor

from hardware_manager import hardware, CROP_PRESETS
from touch_driver import HardwareTouchInjector, inject_qt_click
from keyboard_dialog import get_text_input
import wifi_manager

BLYNK_THEME = """
QMainWindow, QWidget#MainRoot {
    background-color: #0b1120;
    color: #f8fafc;
    font-family: "DejaVu Sans", "Noto Sans", -apple-system, sans-serif;
}

QFrame {
    border: none;
    background: transparent;
}

/* Header Bars */
QFrame#HeaderBar {
    background-color: #131d31;
    border-bottom: 2px solid #1e293b;
    border-radius: 6px;
}

/* Blynk-style Tile Cards */
QFrame#BlynkCard {
    background-color: #131d31;
    border: 1.5px solid #1e293b;
    border-radius: 10px;
}

QFrame#BlynkCardHighlight {
    background-color: #131d31;
    border: 1.5px solid #334155;
    border-radius: 10px;
}

/* Base Tactile Buttons */
QPushButton {
    background-color: #1e293b;
    color: #f8fafc;
    border: 1.5px solid #334155;
    border-radius: 8px;
    font-weight: bold;
    font-size: 11px;
    padding: 3px 6px;
}

QPushButton:pressed {
    background-color: #334155;
    border-color: #0284c7;
}

/* Navigation / Settings Header Button */
QPushButton#BtnSettings {
    background-color: #1e293b;
    color: #38bdf8;
    border: 1.5px solid #0284c7;
    border-radius: 6px;
    font-size: 10px;
    font-weight: bold;
    padding: 3px 8px;
}

QPushButton#BtnBack {
    background-color: #0284c7;
    color: #ffffff;
    border: 1.5px solid #38bdf8;
    border-radius: 6px;
    font-size: 11px;
    font-weight: bold;
    padding: 4px 10px;
}

/* Tab Selector Buttons */
QPushButton#BtnTabActive {
    background-color: #0284c7;
    color: #ffffff;
    border: 1.5px solid #38bdf8;
    border-radius: 6px;
    font-size: 10px;
    font-weight: bold;
}

QPushButton#BtnTabInactive {
    background-color: #0f172a;
    color: #94a3b8;
    border: 1px solid #1e293b;
    border-radius: 6px;
    font-size: 10px;
}

/* Small Corner Pump Widget Buttons */
QPushButton#BtnCornerPumpOff {
    background-color: #1e293b;
    color: #94a3b8;
    border: 2px solid #475569;
    border-radius: 8px;
    font-size: 11px;
    font-weight: bold;
}

QPushButton#BtnCornerPumpOn {
    background-color: #059669;
    color: #ffffff;
    border: 2px solid #34d399;
    border-radius: 8px;
    font-size: 11px;
    font-weight: bold;
}

/* Adjustment Buttons in Settings */
QPushButton#BtnAdjust {
    background-color: #1e293b;
    color: #38bdf8;
    border: 1.5px solid #0284c7;
    border-radius: 8px;
    font-size: 14px;
    font-weight: bold;
}

QPushButton#BtnPreset {
    background-color: #0f172a;
    color: #94a3b8;
    border: 1px solid #334155;
    border-radius: 6px;
    font-size: 9px;
    padding: 2px 4px;
}

/* Crop Selection Cards */
QPushButton#BtnCropActive {
    background-color: #0c2340;
    color: #38bdf8;
    border: 2px solid #0284c7;
    border-radius: 8px;
    font-weight: bold;
    font-size: 10px;
}

QPushButton#BtnCropInactive {
    background-color: #131d31;
    color: #cbd5e1;
    border: 1.5px solid #1e293b;
    border-radius: 8px;
    font-size: 10px;
}

/* Progress Bars */
QProgressBar {
    background-color: #0b1120;
    border: 1px solid #1e293b;
    border-radius: 4px;
    text-align: center;
    color: #ffffff;
    font-size: 9px;
    font-weight: bold;
}

QProgressBar::chunk {
    background-color: #10b981;
    border-radius: 3px;
}
"""


class IoTTouchDashboard(QMainWindow):
    hardware_touch_signal = pyqtSignal(int, int)

    def __init__(self, fullscreen: bool = False):
        super().__init__()
        self.setWindowTitle("Smart IoT Agriculture Dashboard")
        self.setObjectName("MainRoot")
        self.setFixedSize(480, 320)

        # Multi-page stack (0: Dashboard, 1: Settings Hub)
        self.stack = QStackedWidget(self)
        self.setCentralWidget(self.stack)

        self.page_dashboard = QWidget()
        self.page_settings = QWidget()

        self.init_dashboard_ui()
        self.init_settings_ui()

        self.stack.addWidget(self.page_dashboard)
        self.stack.addWidget(self.page_settings)

        # Hardware touch listener
        self.hardware_touch_signal.connect(self.handle_hardware_touch)
        self.touch_injector = HardwareTouchInjector(self.hardware_touch_signal.emit)
        self.touch_injector.start()

        # Telemetry refresh timer (5 Hz)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.update_telemetry)
        self.refresh_timer.start(200)

        # Wi-Fi cached scan
        self.scanned_networks = []

        if fullscreen:
            self.showFullScreen()
        else:
            self.show()

    def handle_hardware_touch(self, x: int, y: int):
        inject_qt_click(self, x, y)

    # =========================================================================
    # PAGE 0: BLYNK-INSPIRED MAIN DASHBOARD
    # =========================================================================
    def init_dashboard_ui(self):
        dash_layout = QVBoxLayout(self.page_dashboard)
        dash_layout.setContentsMargins(6, 4, 6, 4)
        dash_layout.setSpacing(4)

        # 1. Header Strip (28px)
        header = QFrame()
        header.setObjectName("HeaderBar")
        header.setFixedHeight(28)
        h_box = QHBoxLayout(header)
        h_box.setContentsMargins(6, 2, 6, 2)

        lbl_logo = QLabel("🌿 BLYNK IOT")
        lbl_logo.setFont(QFont("DejaVu Sans", 9, QFont.Bold))
        lbl_logo.setStyleSheet("color: #38bdf8;")

        self.lbl_crop_badge = QLabel("🍅 Tomato (35%-65%)")
        self.lbl_crop_badge.setFont(QFont("DejaVu Sans", 8, QFont.Bold))
        self.lbl_crop_badge.setStyleSheet("color: #34d399; background: #064e3b; border-radius: 4px; padding: 2px 6px;")

        self.lbl_clock = QLabel("--:--:--")
        self.lbl_clock.setFont(QFont("DejaVu Sans", 8))
        self.lbl_clock.setStyleSheet("color: #94a3b8;")

        btn_settings = QPushButton("⚙️ SETTINGS")
        btn_settings.setObjectName("BtnSettings")
        btn_settings.clicked.connect(lambda: self.open_settings(0))

        h_box.addWidget(lbl_logo)
        h_box.addSpacing(6)
        h_box.addWidget(self.lbl_crop_badge)
        h_box.addStretch()
        h_box.addWidget(self.lbl_clock)
        h_box.addSpacing(6)
        h_box.addWidget(btn_settings)
        dash_layout.addWidget(header)

        # 2. Main Blynk Metric Cards (Height ~155px)
        cards_row = QHBoxLayout()
        cards_row.setSpacing(6)

        # Card 1: Temperature
        self.card_temp = QFrame()
        self.card_temp.setObjectName("BlynkCard")
        t_box = QVBoxLayout(self.card_temp)
        t_box.setContentsMargins(6, 6, 6, 6)
        t_box.setSpacing(1)

        t_title = QLabel("🌡️ TEMPERATURE")
        t_title.setFont(QFont("DejaVu Sans", 8, QFont.Bold))
        t_title.setStyleSheet("color: #f97316;")
        t_title.setAlignment(Qt.AlignCenter)

        self.lbl_temp_val = QLabel("28.4")
        self.lbl_temp_val.setFont(QFont("DejaVu Sans", 22, QFont.Bold))
        self.lbl_temp_val.setStyleSheet("color: #ffffff;")
        self.lbl_temp_val.setAlignment(Qt.AlignCenter)

        self.lbl_temp_sub = QLabel("°C  |  83.1 °F")
        self.lbl_temp_sub.setFont(QFont("DejaVu Sans", 8))
        self.lbl_temp_sub.setStyleSheet("color: #94a3b8;")
        self.lbl_temp_sub.setAlignment(Qt.AlignCenter)

        self.bar_temp = QProgressBar()
        self.bar_temp.setFixedHeight(5)
        self.bar_temp.setRange(0, 50)
        self.bar_temp.setValue(28)
        self.bar_temp.setTextVisible(False)
        self.bar_temp.setStyleSheet("QProgressBar::chunk { background-color: #f97316; }")

        t_box.addWidget(t_title)
        t_box.addWidget(self.lbl_temp_val)
        t_box.addWidget(self.lbl_temp_sub)
        t_box.addSpacing(2)
        t_box.addWidget(self.bar_temp)
        cards_row.addWidget(self.card_temp)

        # Card 2: Humidity
        self.card_hum = QFrame()
        self.card_hum.setObjectName("BlynkCard")
        h_card_box = QVBoxLayout(self.card_hum)
        h_card_box.setContentsMargins(6, 6, 6, 6)
        h_card_box.setSpacing(1)

        h_title = QLabel("💧 HUMIDITY")
        h_title.setFont(QFont("DejaVu Sans", 8, QFont.Bold))
        h_title.setStyleSheet("color: #38bdf8;")
        h_title.setAlignment(Qt.AlignCenter)

        self.lbl_hum_val = QLabel("64.0")
        self.lbl_hum_val.setFont(QFont("DejaVu Sans", 22, QFont.Bold))
        self.lbl_hum_val.setStyleSheet("color: #ffffff;")
        self.lbl_hum_val.setAlignment(Qt.AlignCenter)

        self.lbl_hum_sub = QLabel("% RH (Normal)")
        self.lbl_hum_sub.setFont(QFont("DejaVu Sans", 8))
        self.lbl_hum_sub.setStyleSheet("color: #38bdf8;")
        self.lbl_hum_sub.setAlignment(Qt.AlignCenter)

        self.bar_hum = QProgressBar()
        self.bar_hum.setFixedHeight(5)
        self.bar_hum.setRange(0, 100)
        self.bar_hum.setValue(64)
        self.bar_hum.setTextVisible(False)
        self.bar_hum.setStyleSheet("QProgressBar::chunk { background-color: #38bdf8; }")

        h_card_box.addWidget(h_title)
        h_card_box.addWidget(self.lbl_hum_val)
        h_card_box.addWidget(self.lbl_hum_sub)
        h_card_box.addSpacing(2)
        h_card_box.addWidget(self.bar_hum)
        cards_row.addWidget(self.card_hum)

        # Card 3: Soil Moisture
        self.card_soil = QFrame()
        self.card_soil.setObjectName("BlynkCard")
        s_box = QVBoxLayout(self.card_soil)
        s_box.setContentsMargins(6, 6, 6, 6)
        s_box.setSpacing(1)

        s_title = QLabel("🌱 SOIL MOISTURE")
        s_title.setFont(QFont("DejaVu Sans", 8, QFont.Bold))
        s_title.setStyleSheet("color: #10b981;")
        s_title.setAlignment(Qt.AlignCenter)

        self.lbl_soil_val = QLabel("42.0")
        self.lbl_soil_val.setFont(QFont("DejaVu Sans", 22, QFont.Bold))
        self.lbl_soil_val.setStyleSheet("color: #ffffff;")
        self.lbl_soil_val.setAlignment(Qt.AlignCenter)

        self.lbl_soil_badge = QLabel("OPTIMAL")
        self.lbl_soil_badge.setFont(QFont("DejaVu Sans", 8, QFont.Bold))
        self.lbl_soil_badge.setStyleSheet("color: #10b981;")
        self.lbl_soil_badge.setAlignment(Qt.AlignCenter)

        self.bar_soil = QProgressBar()
        self.bar_soil.setFixedHeight(5)
        self.bar_soil.setRange(0, 100)
        self.bar_soil.setValue(42)
        self.bar_soil.setTextVisible(False)
        self.bar_soil.setStyleSheet("QProgressBar::chunk { background-color: #10b981; }")

        s_box.addWidget(s_title)
        s_box.addWidget(self.lbl_soil_val)
        s_box.addWidget(self.lbl_soil_badge)
        s_box.addSpacing(2)
        s_box.addWidget(self.bar_soil)
        cards_row.addWidget(self.card_soil)

        dash_layout.addLayout(cards_row)

        # 3. Bottom Row: Left Auto Status + Right Corner Small Motor Button
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(6)

        # Left Panel (Width: ~300px)
        info_panel = QFrame()
        info_panel.setObjectName("BlynkCardHighlight")
        info_box = QVBoxLayout(info_panel)
        info_box.setContentsMargins(8, 5, 8, 5)
        info_box.setSpacing(2)

        info_header = QHBoxLayout()
        lbl_info_title = QLabel("⚡ IRRIGATION AUTOMATION")
        lbl_info_title.setFont(QFont("DejaVu Sans", 8, QFont.Bold))
        lbl_info_title.setStyleSheet("color: #38bdf8;")

        self.btn_mode_toggle = QPushButton("MODE: AUTO")
        self.btn_mode_toggle.setFixedHeight(22)
        self.btn_mode_toggle.setStyleSheet("font-size: 10px; color: #38bdf8; border-color: #0284c7;")
        self.btn_mode_toggle.clicked.connect(self.on_mode_toggle)

        info_header.addWidget(lbl_info_title)
        info_header.addStretch()
        info_header.addWidget(self.btn_mode_toggle)
        info_box.addLayout(info_header)

        self.lbl_cutoff_summary = QLabel("Cutoff: Start < 35% | Stop >= 65%")
        self.lbl_cutoff_summary.setFont(QFont("DejaVu Sans", 8))
        self.lbl_cutoff_summary.setStyleSheet("color: #cbd5e1;")

        quick_links = QHBoxLayout()
        quick_links.setSpacing(4)
        btn_quick_crops = QPushButton("🌾 Set Crop")
        btn_quick_crops.setFixedHeight(20)
        btn_quick_crops.setStyleSheet("background: #0f172a; border: 1px solid #334155; font-size: 9px; color: #38bdf8;")
        btn_quick_crops.clicked.connect(lambda: self.open_settings(0))

        btn_quick_cutoffs = QPushButton("💧 Cutoff %")
        btn_quick_cutoffs.setFixedHeight(20)
        btn_quick_cutoffs.setStyleSheet("background: #0f172a; border: 1px solid #334155; font-size: 9px; color: #10b981;")
        btn_quick_cutoffs.clicked.connect(lambda: self.open_settings(1))

        btn_quick_wifi = QPushButton("📶 Wi-Fi")
        btn_quick_wifi.setFixedHeight(20)
        btn_quick_wifi.setStyleSheet("background: #0f172a; border: 1px solid #334155; font-size: 9px; color: #fbbf24;")
        btn_quick_wifi.clicked.connect(lambda: self.open_settings(2))

        quick_links.addWidget(btn_quick_crops)
        quick_links.addWidget(btn_quick_cutoffs)
        quick_links.addWidget(btn_quick_wifi)
        info_box.addWidget(self.lbl_cutoff_summary)
        info_box.addLayout(quick_links)
        bottom_row.addWidget(info_panel, stretch=2)

        # Right Corner Small Motor Widget (Width: ~160px)
        motor_corner = QFrame()
        motor_corner.setObjectName("BlynkCardHighlight")
        motor_box = QVBoxLayout(motor_corner)
        motor_box.setContentsMargins(6, 4, 6, 4)
        motor_box.setSpacing(2)

        lbl_m_title = QLabel("MOTOR (GPIO 17)")
        lbl_m_title.setFont(QFont("DejaVu Sans", 7, QFont.Bold))
        lbl_m_title.setStyleSheet("color: #94a3b8;")
        lbl_m_title.setAlignment(Qt.AlignCenter)

        self.btn_motor = QPushButton("💧 MOTOR: OFF")
        self.btn_motor.setObjectName("BtnCornerPumpOff")
        self.btn_motor.setFixedHeight(44)
        self.btn_motor.clicked.connect(self.on_motor_click)

        motor_box.addWidget(lbl_m_title)
        motor_box.addWidget(self.btn_motor)
        bottom_row.addWidget(motor_corner, stretch=1)

        dash_layout.addLayout(bottom_row)

        # 4. Footer Strip (16px)
        footer = QHBoxLayout()
        footer.setContentsMargins(4, 0, 4, 0)
        self.lbl_footer = QLabel("● Touch: ADS7846 Active | IP: 10.180.5.188:8000 | Wi-Fi: Active")
        self.lbl_footer.setFont(QFont("DejaVu Sans", 7))
        self.lbl_footer.setStyleSheet("color: #475569;")
        footer.addWidget(self.lbl_footer)
        dash_layout.addLayout(footer)

    # =========================================================================
    # PAGE 1: INTERACTIVE SETTINGS HUB (CROPS, CUTOFFS, WIFI, DEVICE)
    # =========================================================================
    def init_settings_ui(self):
        sett_layout = QVBoxLayout(self.page_settings)
        sett_layout.setContentsMargins(6, 4, 6, 4)
        sett_layout.setSpacing(4)

        # Header: Back Button and Title
        header = QFrame()
        header.setObjectName("HeaderBar")
        header.setFixedHeight(28)
        h_box = QHBoxLayout(header)
        h_box.setContentsMargins(6, 2, 6, 2)

        lbl_title = QLabel("⚙️ SYSTEM SETTINGS")
        lbl_title.setFont(QFont("DejaVu Sans", 9, QFont.Bold))
        lbl_title.setStyleSheet("color: #38bdf8;")

        btn_back = QPushButton("← DASHBOARD")
        btn_back.setObjectName("BtnBack")
        btn_back.clicked.connect(lambda: self.stack.setCurrentIndex(0))

        h_box.addWidget(lbl_title)
        h_box.addStretch()
        h_box.addWidget(btn_back)
        sett_layout.addWidget(header)

        # Tab Navigation Strip (5 Tabs: Crops, Cutoffs, Wi-Fi, Device, Info)
        tabs_box = QHBoxLayout()
        tabs_box.setSpacing(4)
        self.tab_buttons = []

        tab_names = ["🌾 Crops", "💧 Cutoffs", "📶 Wi-Fi", "⚙️ Device", "ℹ️ Info"]
        for idx, name in enumerate(tab_names):
            btn = QPushButton(name)
            btn.setFixedHeight(24)
            btn.setObjectName("BtnTabActive" if idx == 0 else "BtnTabInactive")
            btn.clicked.connect(lambda _, i=idx: self.switch_settings_tab(i))
            self.tab_buttons.append(btn)
            tabs_box.addWidget(btn)
        sett_layout.addLayout(tabs_box)

        # Settings Content Stack (StackedWidget for the 5 tabs)
        self.settings_content_stack = QStackedWidget()
        sett_layout.addWidget(self.settings_content_stack, stretch=1)

        # Tab 0: Crop Selection
        self.tab_crops = QWidget()
        self.init_tab_crops()
        self.settings_content_stack.addWidget(self.tab_crops)

        # Tab 1: Cutoff Percentages
        self.tab_cutoffs = QWidget()
        self.init_tab_cutoffs()
        self.settings_content_stack.addWidget(self.tab_cutoffs)

        # Tab 2: Wi-Fi Controls
        self.tab_wifi = QWidget()
        self.init_tab_wifi()
        self.settings_content_stack.addWidget(self.tab_wifi)

        # Tab 3: Device Diagnostics & Setup
        self.tab_device = QWidget()
        self.init_tab_device()
        self.settings_content_stack.addWidget(self.tab_device)

        # Tab 4: Hardware & Pinout Connections Info
        self.tab_info = QWidget()
        self.init_tab_info()
        self.settings_content_stack.addWidget(self.tab_info)

    def switch_settings_tab(self, tab_idx: int):
        self.settings_content_stack.setCurrentIndex(tab_idx)
        for i, btn in enumerate(self.tab_buttons):
            btn.setObjectName("BtnTabActive" if i == tab_idx else "BtnTabInactive")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        if tab_idx == 2:  # Wi-Fi Tab
            self.refresh_wifi_ui()
        elif tab_idx == 3:  # Device Tab
            self.refresh_device_ui()

    def open_settings(self, tab_idx: int = 0):
        self.switch_settings_tab(tab_idx)
        self.stack.setCurrentIndex(1)

    # --- TAB 0: CROPS ---
    def init_tab_crops(self):
        layout = QVBoxLayout(self.tab_crops)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        lbl = QLabel("Select Crop Profile (Auto-sets moisture cutoffs):")
        lbl.setFont(QFont("DejaVu Sans", 8, QFont.Bold))
        lbl.setStyleSheet("color: #38bdf8;")
        layout.addWidget(lbl)

        grid = QGridLayout()
        grid.setSpacing(5)

        self.crop_buttons = {}
        crops_list = list(CROP_PRESETS.items())

        for idx, (key, info) in enumerate(crops_list):
            row = idx // 2
            col = idx % 2
            text = f"{info['icon']} {info['name']}\nCutoffs: {int(info['dry_cutoff'])}% - {int(info['stop_cutoff'])}%"
            btn = QPushButton(text)
            btn.setFixedHeight(44)
            btn.setObjectName("BtnCropActive" if key == hardware.selected_crop else "BtnCropInactive")
            btn.clicked.connect(lambda _, k=key: self.select_crop(k))
            self.crop_buttons[key] = btn
            grid.addWidget(btn, row, col)

        layout.addLayout(grid)
        layout.addStretch()

    def select_crop(self, crop_key: str):
        hardware.set_crop(crop_key)
        for k, btn in self.crop_buttons.items():
            btn.setObjectName("BtnCropActive" if k == crop_key else "BtnCropInactive")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self.update_telemetry()

    # --- TAB 1: CUTOFFS ---
    def init_tab_cutoffs(self):
        layout = QVBoxLayout(self.tab_cutoffs)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 1. Low Moisture Cutoff
        card1 = QFrame()
        card1.setObjectName("BlynkCard")
        c1_box = QVBoxLayout(card1)
        c1_box.setContentsMargins(6, 4, 6, 4)
        c1_box.setSpacing(2)

        lbl1 = QLabel("1. LOW MOISTURE CUTOFF (Starts Motor)")
        lbl1.setFont(QFont("DejaVu Sans", 8, QFont.Bold))
        lbl1.setStyleSheet("color: #f97316;")

        row1 = QHBoxLayout()
        btn_m1 = QPushButton("  - 5%  ")
        btn_m1.setObjectName("BtnAdjust")
        btn_m1.setFixedHeight(30)
        btn_m1.clicked.connect(lambda: self.adjust_dry(-5))

        self.lbl_dry_cutoff_val = QLabel("35 %")
        self.lbl_dry_cutoff_val.setFont(QFont("DejaVu Sans", 16, QFont.Bold))
        self.lbl_dry_cutoff_val.setAlignment(Qt.AlignCenter)
        self.lbl_dry_cutoff_val.setStyleSheet("color: #ffffff; background: #0b1120; border-radius: 6px;")

        btn_p1 = QPushButton("  + 5%  ")
        btn_p1.setObjectName("BtnAdjust")
        btn_p1.setFixedHeight(30)
        btn_p1.clicked.connect(lambda: self.adjust_dry(+5))

        row1.addWidget(btn_m1)
        row1.addWidget(self.lbl_dry_cutoff_val, stretch=2)
        row1.addWidget(btn_p1)
        c1_box.addWidget(lbl1)
        c1_box.addLayout(row1)
        layout.addWidget(card1)

        # 2. Target Moisture Cutoff
        card2 = QFrame()
        card2.setObjectName("BlynkCard")
        c2_box = QVBoxLayout(card2)
        c2_box.setContentsMargins(6, 4, 6, 4)
        c2_box.setSpacing(2)

        lbl2 = QLabel("2. TARGET MOISTURE CUTOFF (Stops Motor)")
        lbl2.setFont(QFont("DejaVu Sans", 8, QFont.Bold))
        lbl2.setStyleSheet("color: #10b981;")

        row2 = QHBoxLayout()
        btn_m2 = QPushButton("  - 5%  ")
        btn_m2.setObjectName("BtnAdjust")
        btn_m2.setFixedHeight(30)
        btn_m2.clicked.connect(lambda: self.adjust_stop(-5))

        self.lbl_stop_cutoff_val = QLabel("65 %")
        self.lbl_stop_cutoff_val.setFont(QFont("DejaVu Sans", 16, QFont.Bold))
        self.lbl_stop_cutoff_val.setAlignment(Qt.AlignCenter)
        self.lbl_stop_cutoff_val.setStyleSheet("color: #ffffff; background: #0b1120; border-radius: 6px;")

        btn_p2 = QPushButton("  + 5%  ")
        btn_p2.setObjectName("BtnAdjust")
        btn_p2.setFixedHeight(30)
        btn_p2.clicked.connect(lambda: self.adjust_stop(+5))

        row2.addWidget(btn_m2)
        row2.addWidget(self.lbl_stop_cutoff_val, stretch=2)
        row2.addWidget(btn_p2)
        c2_box.addWidget(lbl2)
        c2_box.addLayout(row2)
        layout.addWidget(card2)

        layout.addStretch()

    # --- TAB 2: WI-FI CONTROLS ---
    def init_tab_wifi(self):
        layout = QVBoxLayout(self.tab_wifi)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Current Connection Banner
        cur_card = QFrame()
        cur_card.setObjectName("BlynkCard")
        c_layout = QHBoxLayout(cur_card)
        c_layout.setContentsMargins(8, 4, 8, 4)

        self.lbl_wifi_status = QLabel("Wi-Fi: Scanning...")
        self.lbl_wifi_status.setFont(QFont("DejaVu Sans", 8, QFont.Bold))
        self.lbl_wifi_status.setStyleSheet("color: #38bdf8;")

        btn_rescan = QPushButton("🔄 Rescan")
        btn_rescan.setFixedHeight(24)
        btn_rescan.setStyleSheet("font-size: 9px; padding: 2px 6px;")
        btn_rescan.clicked.connect(self.scan_and_populate_wifi)

        c_layout.addWidget(self.lbl_wifi_status)
        c_layout.addStretch()
        c_layout.addWidget(btn_rescan)
        layout.addWidget(cur_card)

        # Scanned Networks List (Scrollable)
        lbl_list = QLabel("Available Networks (Tap to connect):")
        lbl_list.setFont(QFont("DejaVu Sans", 7, QFont.Bold))
        lbl_list.setStyleSheet("color: #94a3b8;")
        layout.addWidget(lbl_list)

        self.scroll_wifi = QScrollArea()
        self.scroll_wifi.setWidgetResizable(True)
        self.scroll_wifi.setStyleSheet("QScrollArea { border: 1px solid #1e293b; background: #0b1120; border-radius: 6px; }")

        self.wifi_list_container = QWidget()
        self.wifi_list_layout = QVBoxLayout(self.wifi_list_container)
        self.wifi_list_layout.setContentsMargins(4, 4, 4, 4)
        self.wifi_list_layout.setSpacing(3)
        self.scroll_wifi.setWidget(self.wifi_list_container)

        layout.addWidget(self.scroll_wifi, stretch=1)

    def refresh_wifi_ui(self):
        curr = wifi_manager.get_current_wifi()
        if curr["connected"]:
            self.lbl_wifi_status.setText(f"Connected: {curr['ssid']} ({curr['signal']}%)")
        else:
            self.lbl_wifi_status.setText("Wi-Fi: Disconnected")
        self.scan_and_populate_wifi()

    def scan_and_populate_wifi(self):
        # Clear list
        while self.wifi_list_layout.count():
            item = self.wifi_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        networks = wifi_manager.scan_wifi_networks()
        for net in networks[:8]:  # Show top 8
            ssid = net["ssid"]
            sig = net["signal"]
            active = net["active"]

            btn = QPushButton(f"{'● ' if active else ''}{ssid}  ({sig}%)")
            btn.setFixedHeight(28)
            btn.setStyleSheet(f"text-align: left; padding-left: 8px; font-size: 10px; {'color: #10b981; border-color: #10b981;' if active else ''}")
            btn.clicked.connect(lambda _, s=ssid: self.prompt_wifi_connect(s))
            self.wifi_list_layout.addWidget(btn)

        self.wifi_list_layout.addStretch()

    def prompt_wifi_connect(self, ssid: str):
        """Opens On-Screen Keyboard to enter Wi-Fi password."""
        password = get_text_input(
            parent=self,
            prompt=f"Enter Wi-Fi Password for '{ssid}':",
            default="",
            is_password=True
        )
        if password is not None:
            # User clicked Done on keyboard
            self.lbl_wifi_status.setText(f"Connecting to {ssid}...")
            res = wifi_manager.connect_wifi(ssid, password)
            if res["success"]:
                self.lbl_wifi_status.setText(f"Connected to {ssid}!")
            else:
                self.lbl_wifi_status.setText(f"Connect failed: {res['message'][:24]}")
            self.refresh_wifi_ui()

    # --- TAB 3: DEVICE & SETUP ---
    def init_tab_device(self):
        layout = QVBoxLayout(self.tab_device)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        diag_card = QFrame()
        diag_card.setObjectName("BlynkCard")
        d_box = QVBoxLayout(diag_card)
        d_box.setContentsMargins(8, 6, 8, 6)
        d_box.setSpacing(3)

        lbl_header = QLabel("DEVICE DIAGNOSTICS & SYSTEM SETUP")
        lbl_header.setFont(QFont("DejaVu Sans", 8, QFont.Bold))
        lbl_header.setStyleSheet("color: #38bdf8;")
        d_box.addWidget(lbl_header)

        self.lbl_diag_temp = QLabel("CPU Temp: Loading...")
        self.lbl_diag_ram = QLabel("RAM: Loading...")
        self.lbl_diag_disk = QLabel("Storage: Loading...")
        self.lbl_diag_uptime = QLabel("Uptime: Loading...")

        for lbl in [self.lbl_diag_temp, self.lbl_diag_ram, self.lbl_diag_disk, self.lbl_diag_uptime]:
            lbl.setFont(QFont("DejaVu Sans", 8))
            lbl.setStyleSheet("color: #cbd5e1;")
            d_box.addWidget(lbl)

        layout.addWidget(diag_card)

        # System Actions
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        btn_restart_gui = QPushButton("🔄 Restart GUI")
        btn_restart_gui.setFixedHeight(30)
        btn_restart_gui.clicked.connect(self.action_restart_gui)

        btn_reboot_pi = QPushButton("⚠️ Reboot Pi")
        btn_reboot_pi.setFixedHeight(30)
        btn_reboot_pi.setStyleSheet("background: #7f1d1d; border-color: #ef4444; color: #ffffff;")
        btn_reboot_pi.clicked.connect(self.action_reboot_pi)

        btn_row.addWidget(btn_restart_gui)
        btn_row.addWidget(btn_reboot_pi)
        layout.addLayout(btn_row)
        layout.addStretch()

    def refresh_device_ui(self):
        diag = hardware.get_system_diagnostics()
        self.lbl_diag_temp.setText(f"🌡️ CPU Temp: {diag['cpu_temp']}")
        self.lbl_diag_ram.setText(f"🧠 Memory: {diag['ram_usage']}")
        self.lbl_diag_disk.setText(f"💾 Storage: {diag['disk_usage']}")
        self.lbl_diag_uptime.setText(f"⏱️ Uptime: {diag['uptime']}")

    def action_restart_gui(self):
        print("[System] Restarting dashboard application...")
        os.system("echo 123456 | sudo -S systemctl restart iot-dashboard.service &")

    def action_reboot_pi(self):
        print("[System] Rebooting Raspberry Pi...")
        os.system("echo 123456 | sudo -S reboot &")

    # --- TAB 4: HARDWARE & ARDUINO MEGA CONNECTIONS INFO ---
    def init_tab_info(self):
        layout = QVBoxLayout(self.tab_info)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #1e293b; background: #0b1120; border-radius: 6px; }")

        container = QWidget()
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(6, 6, 6, 6)
        c_layout.setSpacing(4)

        # Header card
        lbl_head = QLabel("🔌 ARDUINO MEGA 2560 WIRING & PINOUT")
        lbl_head.setFont(QFont("DejaVu Sans", 8, QFont.Bold))
        lbl_head.setStyleSheet("color: #38bdf8; padding: 2px 0px;")
        c_layout.addWidget(lbl_head)

        lbl_sub = QLabel("Serial Link: Raspberry Pi 4 USB (/dev/ttyACM0 @ 115200 baud)")
        lbl_sub.setFont(QFont("DejaVu Sans", 7))
        lbl_sub.setStyleSheet("color: #94a3b8;")
        c_layout.addWidget(lbl_sub)

        # Pinout items
        pinout_data = [
            ("🌱 Soil Moisture", "Pin A0 (Analog)", "VCC: 5V | GND: GND | Output: 0-100%"),
            ("🌧️ Rain Drop Sensor", "Pin A1 (Analog)", "VCC: 5V | GND: GND | Wet < 600"),
            ("☀️ LDR Light Sensor", "Pin A2 (Analog)", "VCC: 5V | GND: GND | Sunlight lvl"),
            ("💧 Water Tank Level", "Pin A3 (Analog)", "VCC: 5V | GND: GND | Depth/Float"),
            ("🌡️ DHT11 / DHT22", "Pin 2 (Digital)", "VCC: 5V | GND: GND | 1-Wire Data"),
            ("⚡ Water Pump Relay", "Pin 8 (Digital)", "Signal IN (Active LOW) to Relay"),
            ("💡 Heartbeat LED", "Pin 13 (Builtin)", "Blinks on pump & serial activity")
        ]

        for comp, pin, desc in pinout_data:
            card = QFrame()
            card.setObjectName("BlynkCard")
            card.setStyleSheet("background-color: #131d31; border: 1px solid #1e293b; border-radius: 6px; padding: 3px;")
            box = QHBoxLayout(card)
            box.setContentsMargins(6, 3, 6, 3)

            lbl_comp = QLabel(comp)
            lbl_comp.setFont(QFont("DejaVu Sans", 8, QFont.Bold))
            lbl_comp.setStyleSheet("color: #f8fafc;")

            lbl_pin = QLabel(pin)
            lbl_pin.setFont(QFont("DejaVu Sans", 8, QFont.Bold))
            lbl_pin.setStyleSheet("color: #10b981;")

            lbl_desc = QLabel(desc)
            lbl_desc.setFont(QFont("DejaVu Sans", 7))
            lbl_desc.setStyleSheet("color: #94a3b8;")

            box.addWidget(lbl_comp, stretch=2)
            box.addWidget(lbl_pin, stretch=2)
            box.addWidget(lbl_desc, stretch=3)
            c_layout.addWidget(card)

        # Relay Wiring Note Card
        note_card = QFrame()
        note_card.setStyleSheet("background-color: #1a1625; border: 1px solid #7c3aed; border-radius: 6px; padding: 4px;")
        n_box = QVBoxLayout(note_card)
        n_box.setContentsMargins(6, 4, 6, 4)
        n_box.setSpacing(2)

        lbl_note_t = QLabel("⚠️ WATER PUMP RELAY SAFETY WIRING")
        lbl_note_t.setFont(QFont("DejaVu Sans", 8, QFont.Bold))
        lbl_note_t.setStyleSheet("color: #c084fc;")

        lbl_note_b = QLabel(
            "• COM: Connect to External 12V / 5V Pump Power (+)\n"
            "• NO (Normally Open): Connect to Pump Positive (+)\n"
            "• Pump Negative (-): Directly to External Power (-)\n"
            "• Connect External Power GND to Arduino Mega GND for common ground."
        )
        lbl_note_b.setFont(QFont("DejaVu Sans", 7))
        lbl_note_b.setStyleSheet("color: #e2e8f0;")

        n_box.addWidget(lbl_note_t)
        n_box.addWidget(lbl_note_b)
        c_layout.addWidget(note_card)

        scroll.setWidget(container)
        layout.addWidget(scroll)

    # =========================================================================
    # USER ACTIONS
    # =========================================================================
    def on_motor_click(self):
        hardware.toggle_pump()
        self.update_telemetry()

    def on_mode_toggle(self):
        new_mode = hardware.toggle_mode()
        self.btn_mode_toggle.setText(f"MODE: {new_mode}")
        self.update_telemetry()

    def adjust_dry(self, delta: float):
        val = hardware.adjust_dry_cutoff(delta)
        self.lbl_dry_cutoff_val.setText(f"{int(val)} %")
        self.update_telemetry()

    def adjust_stop(self, delta: float):
        val = hardware.adjust_stop_cutoff(delta)
        self.lbl_stop_cutoff_val.setText(f"{int(val)} %")
        self.update_telemetry()

    # =========================================================================
    # TELEMETRY REFRESH
    # =========================================================================
    def update_telemetry(self):
        data = hardware.get_telemetry()

        # Update Clock
        self.lbl_clock.setText(data["timestamp"])

        # Update Crop Badge
        dry_cut = int(data["dry_cutoff"])
        stop_cut = int(data["stop_cutoff"])
        self.lbl_crop_badge.setText(f"{data['crop_icon']} {data['crop_name']} ({dry_cut}%-{stop_cut}%)")

        # Update Temperature
        self.lbl_temp_val.setText(f"{data['temperature_c']}")
        self.lbl_temp_sub.setText(f"°C  |  {data['temperature_f']} °F")
        self.bar_temp.setValue(min(50, max(0, int(data['temperature_c']))))

        # Update Humidity
        self.lbl_hum_val.setText(f"{data['humidity']}")
        self.bar_hum.setValue(min(100, max(0, int(data['humidity']))))

        # Update Soil Moisture
        self.lbl_soil_val.setText(f"{data['soil_moisture']}")
        self.bar_soil.setValue(int(data["soil_moisture"]))
        self.lbl_soil_badge.setText(data["soil_condition"])
        self.lbl_soil_badge.setStyleSheet(f"color: {data['soil_color']}; font-weight: bold;")

        # Cutoffs info in Main View
        self.lbl_cutoff_summary.setText(f"Cutoff: Start < {dry_cut}% | Stop >= {stop_cut}%")
        self.lbl_dry_cutoff_val.setText(f"{dry_cut} %")
        self.lbl_stop_cutoff_val.setText(f"{stop_cut} %")

        # Small Corner Motor Button
        if data["pump_on"]:
            self.btn_motor.setObjectName("BtnCornerPumpOn")
            self.btn_motor.setText("⚡ MOTOR: ON")
            self.card_soil.setStyleSheet("QFrame#BlynkCard { border: 1.5px solid #10b981; }")
        else:
            self.btn_motor.setObjectName("BtnCornerPumpOff")
            self.btn_motor.setText("💧 MOTOR: OFF")
            self.card_soil.setStyleSheet("QFrame#BlynkCard { border: 1.5px solid #1e293b; }")

        self.btn_motor.style().unpolish(self.btn_motor)
        self.btn_motor.style().polish(self.btn_motor)

        # Mode button
        self.btn_mode_toggle.setText(f"MODE: {data['pump_mode']}")


def main():
    fullscreen = "--fullscreen" in sys.argv
    app = QApplication(sys.argv)
    app.setStyleSheet(BLYNK_THEME)
    window = IoTTouchDashboard(fullscreen=fullscreen)
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
