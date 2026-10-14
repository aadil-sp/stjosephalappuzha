"""
FastAPI Blynk-Inspired Telemetry Web Server & Interactive Control Hub
Provides REST API, live telemetry, crop profiles, Wi-Fi management,
device diagnostics, cutoff adjustments, and corner motor control.
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from hardware_manager import hardware, CROP_PRESETS
import wifi_manager
import os

web_app = FastAPI(title="Blynk IoT Agriculture Interactive Hub")


class CutoffSettings(BaseModel):
    dry_cutoff: float
    stop_cutoff: float


class CropSelection(BaseModel):
    crop_key: str


class WifiConnectionRequest(BaseModel):
    ssid: str
    password: str = ""


HTML_BLYNK_DASHBOARD = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🌿 Blynk IoT Agri-Hub</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: #0b1120;
            color: #f8fafc;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            padding: 16px;
        }
        .container {
            width: 100%;
            max-width: 680px;
            background: #131d31;
            border: 1px solid #1e293b;
            border-radius: 16px;
            padding: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.6);
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid #1e293b;
            padding-bottom: 12px;
            margin-bottom: 14px;
        }
        .logo-group {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .title {
            font-size: 18px;
            font-weight: 800;
            color: #38bdf8;
        }
        .badge-crop {
            background: rgba(16, 185, 129, 0.2);
            color: #10b981;
            border: 1px solid #10b981;
            padding: 4px 10px;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 700;
        }
        .btn-settings {
            background: #1e293b;
            color: #38bdf8;
            border: 1px solid #0284c7;
            padding: 6px 12px;
            border-radius: 8px;
            font-size: 12px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.2s;
        }
        .btn-settings:hover {
            background: #0284c7;
            color: #ffffff;
        }
        /* Grid of 3 Telemetry Cards */
        .grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
            margin-bottom: 14px;
        }
        .blynk-card {
            background: #0b1120;
            border: 1.5px solid #1e293b;
            border-radius: 12px;
            padding: 14px;
            text-align: center;
        }
        .card-tag {
            font-size: 10px;
            font-weight: 800;
            letter-spacing: 0.5px;
            margin-bottom: 6px;
        }
        .card-val {
            font-size: 30px;
            font-weight: 900;
            margin-bottom: 2px;
        }
        .card-sub {
            font-size: 11px;
            color: #94a3b8;
        }
        .meter {
            height: 6px;
            background: #1e293b;
            border-radius: 3px;
            margin-top: 8px;
            overflow: hidden;
        }
        .meter-fill {
            height: 100%;
            transition: width 0.3s;
        }
        /* Bottom Row */
        .bottom-row {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 12px;
            margin-bottom: 12px;
        }
        .info-card {
            background: #0b1120;
            border: 1.5px solid #1e293b;
            border-radius: 12px;
            padding: 14px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        .info-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 6px;
        }
        .btn-mode {
            background: #1e293b;
            color: #38bdf8;
            border: 1px solid #0284c7;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: bold;
            cursor: pointer;
        }
        .corner-motor-card {
            background: #0b1120;
            border: 1.5px solid #1e293b;
            border-radius: 12px;
            padding: 12px;
            text-align: center;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        .btn-motor {
            width: 100%;
            height: 48px;
            border-radius: 8px;
            font-size: 12px;
            font-weight: 800;
            cursor: pointer;
            transition: all 0.2s;
            border: 2px solid transparent;
        }
        .btn-motor.off {
            background: #1e293b;
            color: #94a3b8;
            border-color: #475569;
        }
        .btn-motor.on {
            background: #059669;
            color: #ffffff;
            border-color: #34d399;
            box-shadow: 0 0 15px rgba(16, 185, 129, 0.4);
        }
        /* Crop Strip */
        .crops-strip {
            display: flex;
            gap: 6px;
            overflow-x: auto;
            padding-bottom: 4px;
            margin-bottom: 14px;
        }
        .crop-btn {
            background: #0b1120;
            color: #cbd5e1;
            border: 1px solid #1e293b;
            padding: 6px 12px;
            border-radius: 8px;
            font-size: 11px;
            font-weight: bold;
            white-space: nowrap;
            cursor: pointer;
        }
        .crop-btn.active {
            background: #0284c7;
            color: #ffffff;
            border-color: #38bdf8;
        }
        /* Modal Tabs */
        .modal {
            display: none;
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.75);
            justify-content: center;
            align-items: center;
            z-index: 100;
        }
        .modal-box {
            background: #131d31;
            border: 1.5px solid #0284c7;
            border-radius: 16px;
            width: 92%;
            max-width: 480px;
            max-height: 85vh;
            overflow-y: auto;
            padding: 20px;
        }
        .modal-tabs {
            display: flex;
            gap: 6px;
            margin-bottom: 14px;
        }
        .modal-tab-btn {
            flex: 1;
            padding: 8px;
            background: #0b1120;
            color: #94a3b8;
            border: 1px solid #1e293b;
            border-radius: 8px;
            font-size: 11px;
            font-weight: bold;
            cursor: pointer;
        }
        .modal-tab-btn.active {
            background: #0284c7;
            color: #ffffff;
            border-color: #38bdf8;
        }
        .ctrl-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-top: 8px;
        }
        .btn-adj {
            background: #1e293b;
            color: #38bdf8;
            border: 1px solid #0284c7;
            border-radius: 8px;
            padding: 8px 16px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
        }
        .setting-card {
            background: #0b1120;
            border: 1px solid #1e293b;
            border-radius: 10px;
            padding: 12px;
            margin-bottom: 10px;
        }
        .footer {
            margin-top: 10px;
            text-align: center;
            font-size: 11px;
            color: #475569;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo-group">
                <div class="title">🌿 BLYNK AGRI IOT</div>
                <div class="badge-crop" id="badge_crop">🍅 Tomato</div>
            </div>
            <div style="display: flex; gap: 8px; align-items: center;">
                <span id="clock" style="font-size: 12px; color: #94a3b8;">--:--:--</span>
                <button class="btn-settings" onclick="openSettings()">⚙️ Settings</button>
            </div>
        </div>

        <!-- Quick Crop Selector Strip -->
        <div class="crops-strip" id="crops_strip">
            <!-- Dynamically populated -->
        </div>

        <!-- 3 Blynk Telemetry Cards -->
        <div class="grid">
            <div class="blynk-card" style="border-color: #f97316;">
                <div class="card-tag" style="color: #f97316;">🌡️ TEMPERATURE</div>
                <div class="card-val" id="temp_c" style="color: #f97316;">--.-</div>
                <div class="card-sub" id="temp_sub">°C | --.- °F</div>
                <div class="meter"><div class="meter-fill" id="temp_bar" style="background: #f97316; width: 50%;"></div></div>
            </div>
            <div class="blynk-card" style="border-color: #38bdf8;">
                <div class="card-tag" style="color: #38bdf8;">💧 HUMIDITY</div>
                <div class="card-val" id="hum" style="color: #38bdf8;">--.-</div>
                <div class="card-sub">% RH (Normal)</div>
                <div class="meter"><div class="meter-fill" id="hum_bar" style="background: #38bdf8; width: 60%;"></div></div>
            </div>
            <div class="blynk-card" id="soil_card" style="border-color: #10b981;">
                <div class="card-tag" style="color: #10b981;">🌱 SOIL MOISTURE</div>
                <div class="card-val" id="soil" style="color: #10b981;">--.-</div>
                <div class="card-sub" id="soil_badge" style="color: #10b981; font-weight: bold;">OPTIMAL</div>
                <div class="meter"><div class="meter-fill" id="soil_bar" style="background: #10b981; width: 40%;"></div></div>
            </div>
        </div>

        <!-- Bottom Row: Automation Status & Corner Motor Button -->
        <div class="bottom-row">
            <div class="info-card">
                <div class="info-top">
                    <span style="font-size: 11px; font-weight: bold; color: #38bdf8;">⚡ IRRIGATION AUTOMATION</span>
                    <button class="btn-mode" id="btn_mode" onclick="toggleMode()">MODE: AUTO</button>
                </div>
                <div id="cutoff_display" style="font-size: 12px; color: #cbd5e1; margin-bottom: 6px;">
                    Cutoff: Start < 35% | Stop >= 65%
                </div>
                <div style="display: flex; gap: 6px;">
                    <button class="btn-settings" style="font-size: 11px; padding: 4px 8px;" onclick="openSettingsTab('crops')">🌾 Crops</button>
                    <button class="btn-settings" style="font-size: 11px; padding: 4px 8px;" onclick="openSettingsTab('cutoffs')">💧 Cutoffs</button>
                    <button class="btn-settings" style="font-size: 11px; padding: 4px 8px;" onclick="openSettingsTab('wifi')">📶 Wi-Fi</button>
                </div>
            </div>

            <!-- Compact Corner Motor Button -->
            <div class="corner-motor-card">
                <span style="font-size: 10px; font-weight: bold; color: #94a3b8;">MOTOR (GPIO 17)</span>
                <button class="btn-motor off" id="btn_motor" onclick="toggleMotor()">💧 MOTOR: OFF</button>
            </div>
        </div>

        <div class="footer">
            Raspberry Pi 4 | 3.5" Touchscreen (/dev/fb1) | ADS7846 SPI Active
        </div>
    </div>

    <!-- Interactive Settings Modal with Tabs -->
    <div class="modal" id="settings_modal">
        <div class="modal-box">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <h3 style="color: #38bdf8;">⚙️ Device Settings & Setup</h3>
                <span style="cursor: pointer; font-size: 24px;" onclick="closeSettings()">&times;</span>
            </div>

            <!-- Tab Headers -->
            <div class="modal-tabs">
                <button class="modal-tab-btn active" id="tab_btn_crops" onclick="switchModalTab('crops')">🌾 Crops</button>
                <button class="modal-tab-btn" id="tab_btn_cutoffs" onclick="switchModalTab('cutoffs')">💧 Cutoffs</button>
                <button class="modal-tab-btn" id="tab_btn_wifi" onclick="switchModalTab('wifi')">📶 Wi-Fi</button>
                <button class="modal-tab-btn" id="tab_btn_device" onclick="switchModalTab('device')">⚙️ Device</button>
                <button class="modal-tab-btn" id="tab_btn_info" onclick="switchModalTab('info')">ℹ️ Info</button>
            </div>

            <!-- Tab Content: Crops -->
            <div id="tab_crops">
                <div id="modal_crops_list" style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;"></div>
            </div>

            <!-- Tab Content: Cutoffs -->
            <div id="tab_cutoffs" style="display: none;">
                <div class="setting-card">
                    <div style="font-size: 11px; font-weight: bold; color: #f97316;">1. Low Moisture Cutoff (Starts Motor)</div>
                    <div class="ctrl-row">
                        <button class="btn-adj" onclick="changeCutoff('dry', -5)">- 5%</button>
                        <span id="modal_dry_val" style="font-size: 22px; font-weight: bold;">35 %</span>
                        <button class="btn-adj" onclick="changeCutoff('dry', 5)">+ 5%</button>
                    </div>
                </div>
                <div class="setting-card">
                    <div style="font-size: 11px; font-weight: bold; color: #10b981;">2. Target Moisture Cutoff (Stops Motor)</div>
                    <div class="ctrl-row">
                        <button class="btn-adj" onclick="changeCutoff('stop', -5)">- 5%</button>
                        <span id="modal_stop_val" style="font-size: 22px; font-weight: bold;">65 %</span>
                        <button class="btn-adj" onclick="changeCutoff('stop', 5)">+ 5%</button>
                    </div>
                </div>
            </div>

            <!-- Tab Content: Wi-Fi -->
            <div id="tab_wifi" style="display: none;">
                <div class="setting-card">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span id="wifi_curr_label" style="font-size: 12px; color: #38bdf8; font-weight: bold;">Wi-Fi: Scanning...</span>
                        <button class="btn-settings" style="font-size: 10px; padding: 4px 8px;" onclick="scanWifi()">🔄 Rescan</button>
                    </div>
                    <div id="wifi_list" style="max-height: 140px; overflow-y: auto; display: flex; flex-direction: column; gap: 4px;"></div>
                </div>
                <div class="setting-card" id="wifi_connect_box" style="display: none;">
                    <div id="wifi_target_ssid" style="font-weight: bold; color: #38bdf8; margin-bottom: 6px;"></div>
                    <input type="password" id="wifi_password" placeholder="Enter Wi-Fi Password" style="width: 100%; padding: 8px; border-radius: 6px; background: #131d31; border: 1px solid #334155; color: #fff; margin-bottom: 8px;">
                    <button class="btn-settings" style="width: 100%; background: #059669; color: #fff;" onclick="submitWifiConnect()">Connect Network</button>
                </div>
            </div>

            <!-- Tab Content: Device Diagnostics -->
            <div id="tab_device" style="display: none;">
                <div class="setting-card" id="device_diag_box">
                    <div style="font-size: 12px; margin-bottom: 4px;" id="diag_cpu">CPU Temp: Loading...</div>
                    <div style="font-size: 12px; margin-bottom: 4px;" id="diag_ram">Memory: Loading...</div>
                    <div style="font-size: 12px; margin-bottom: 4px;" id="diag_disk">Storage: Loading...</div>
                    <div style="font-size: 12px; margin-bottom: 4px;" id="diag_uptime">Uptime: Loading...</div>
                </div>
                <div style="display: flex; gap: 8px; margin-top: 10px;">
                    <button class="btn-settings" style="flex: 1;" onclick="restartGui()">🔄 Restart GUI</button>
                    <button class="btn-settings" style="flex: 1; background: #7f1d1d; border-color: #ef4444; color: #fff;" onclick="rebootPi()">⚠️ Reboot Pi</button>
                </div>
            </div>

            <!-- Tab Content: Hardware & Connections Info -->
            <div id="tab_info" style="display: none;">
                <div class="setting-card">
                    <div style="font-size: 12px; font-weight: bold; color: #38bdf8; margin-bottom: 6px;">🔌 Arduino Mega 2560 Pinout & Wiring</div>
                    <div style="font-size: 11px; color: #94a3b8; margin-bottom: 10px;">USB Serial to Raspberry Pi: <code>/dev/ttyACM0 @ 115200 baud</code></div>
                    <table style="width: 100%; font-size: 11px; border-collapse: collapse; text-align: left;">
                        <tr style="border-bottom: 1px solid #334155; color: #38bdf8;">
                            <th style="padding: 4px;">Component</th>
                            <th style="padding: 4px;">Arduino Mega Pin</th>
                            <th style="padding: 4px;">Power & Wiring</th>
                        </tr>
                        <tr style="border-bottom: 1px solid #1e293b;">
                            <td style="padding: 5px;">🌱 Soil Moisture</td>
                            <td style="padding: 5px; color: #10b981; font-weight: bold;">Pin A0 (Analog)</td>
                            <td style="padding: 5px; color: #94a3b8;">VCC: 5V | GND: GND</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #1e293b;">
                            <td style="padding: 5px;">🌧️ Rain Sensor</td>
                            <td style="padding: 5px; color: #10b981; font-weight: bold;">Pin A1 (Analog)</td>
                            <td style="padding: 5px; color: #94a3b8;">VCC: 5V | GND: GND</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #1e293b;">
                            <td style="padding: 5px;">☀️ LDR Light</td>
                            <td style="padding: 5px; color: #10b981; font-weight: bold;">Pin A2 (Analog)</td>
                            <td style="padding: 5px; color: #94a3b8;">VCC: 5V | GND: GND</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #1e293b;">
                            <td style="padding: 5px;">💧 Water Level</td>
                            <td style="padding: 5px; color: #10b981; font-weight: bold;">Pin A3 (Analog)</td>
                            <td style="padding: 5px; color: #94a3b8;">VCC: 5V | GND: GND</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #1e293b;">
                            <td style="padding: 5px;">🌡️ DHT11 / DHT22</td>
                            <td style="padding: 5px; color: #38bdf8; font-weight: bold;">Pin 2 (Digital)</td>
                            <td style="padding: 5px; color: #94a3b8;">VCC: 5V | GND: GND</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #1e293b;">
                            <td style="padding: 5px;">⚡ Water Pump Relay</td>
                            <td style="padding: 5px; color: #f97316; font-weight: bold;">Pin 8 (Digital)</td>
                            <td style="padding: 5px; color: #94a3b8;">Signal IN (Active LOW)</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #1e293b;">
                            <td style="padding: 5px;">🔊 Deterrence Buzzer</td>
                            <td style="padding: 5px; color: #ec4899; font-weight: bold;">Pin 9 (PWM)</td>
                            <td style="padding: 5px; color: #94a3b8;">Pos (+) to Pin 9, Neg to GND</td>
                        </tr>
                        <tr>
                            <td style="padding: 5px;">💡 Status LED</td>
                            <td style="padding: 5px; color: #eab308; font-weight: bold;">Pin 13 (Built-in)</td>
                            <td style="padding: 5px; color: #94a3b8;">Heartbeat indicator</td>
                        </tr>
                    </table>
                </div>
                <div class="setting-card" style="border-left: 3px solid #f59e0b; font-size: 11px;">
                    <b style="color: #f59e0b;">⚠️ Water Pump Relay Wiring:</b><br>
                    • <b>COM</b>: External 12V/5V Power Supply (+)<br>
                    • <b>NO</b>: Water Pump (+)<br>
                    • Water Pump (-) connects directly to External Power Supply (-)<br>
                    • Connect External Power GND to Arduino GND (Common Ground).
                </div>
            </div>

            <button class="btn-settings" style="width: 100%; background: #059669; color: #fff; padding: 10px; margin-top: 12px;" onclick="closeSettings()">✓ Done</button>
        </div>
    </div>

    <script>
        let currentDry = 35;
        let currentStop = 65;
        let selectedCropKey = 'tomato';
        let targetSsid = '';

        async function fetchTelemetry() {
            try {
                const res = await fetch('/api/telemetry');
                const data = await res.json();
                document.getElementById('clock').innerText = data.timestamp;
                document.getElementById('badge_crop').innerText = `${data.crop_icon} ${data.crop_name}`;
                document.getElementById('temp_c').innerText = data.temperature_c;
                document.getElementById('temp_sub').innerText = '°C  |  ' + data.temperature_f + ' °F';
                document.getElementById('temp_bar').style.width = Math.min(100, data.temperature_c * 2) + '%';

                document.getElementById('hum').innerText = data.humidity;
                document.getElementById('hum_bar').style.width = data.humidity + '%';

                document.getElementById('soil').innerText = data.soil_moisture;
                document.getElementById('soil_bar').style.width = data.soil_moisture + '%';
                document.getElementById('soil_badge').innerText = data.soil_condition;
                document.getElementById('soil_badge').style.color = data.soil_color;

                currentDry = data.dry_cutoff;
                currentStop = data.stop_cutoff;
                selectedCropKey = data.selected_crop;

                document.getElementById('cutoff_display').innerText = `Cutoff: Start < ${currentDry}% | Stop >= ${currentStop}%`;
                document.getElementById('modal_dry_val').innerText = currentDry + ' %';
                document.getElementById('modal_stop_val').innerText = currentStop + ' %';

                const motorBtn = document.getElementById('btn_motor');
                if (data.pump_on) {
                    motorBtn.className = 'btn-motor on';
                    motorBtn.innerText = '⚡ MOTOR: ON';
                } else {
                    motorBtn.className = 'btn-motor off';
                    motorBtn.innerText = '💧 MOTOR: OFF';
                }

                document.getElementById('btn_mode').innerText = 'MODE: ' + data.pump_mode;
                updateCropsUI();
            } catch (e) {
                console.error("Telemetry error:", e);
            }
        }

        async function toggleMotor() {
            await fetch('/api/pump/toggle', { method: 'POST' });
            fetchTelemetry();
        }

        async function toggleMode() {
            await fetch('/api/pump/mode', { method: 'POST' });
            fetchTelemetry();
        }

        async function changeCutoff(type, delta) {
            if (type === 'dry') {
                currentDry = Math.max(10, Math.min(currentStop - 5, currentDry + delta));
            } else {
                currentStop = Math.max(currentDry + 5, Math.min(95, currentStop + delta));
            }
            await fetch('/api/settings/cutoffs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ dry_cutoff: currentDry, stop_cutoff: currentStop })
            });
            fetchTelemetry();
        }

        async function selectCrop(key) {
            await fetch('/api/crops/select', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ crop_key: key })
            });
            fetchTelemetry();
        }

        async function updateCropsUI() {
            const cropsRes = await fetch('/api/crops');
            const crops = await cropsRes.json();
            const strip = document.getElementById('crops_strip');
            const modalList = document.getElementById('modal_crops_list');

            strip.innerHTML = '';
            modalList.innerHTML = '';

            for (const [key, c] of Object.entries(crops)) {
                const isActive = (key === selectedCropKey);
                // Strip button
                const btn = document.createElement('button');
                btn.className = `crop-btn ${isActive ? 'active' : ''}`;
                btn.innerText = `${c.icon} ${c.name}`;
                btn.onclick = () => selectCrop(key);
                strip.appendChild(btn);

                // Modal card
                const mBtn = document.createElement('button');
                mBtn.className = `crop-btn ${isActive ? 'active' : ''}`;
                mBtn.style.padding = '10px';
                mBtn.style.textAlign = 'left';
                mBtn.innerHTML = `<div>${c.icon} <b>${c.name}</b></div><div style="font-size: 10px; color: #94a3b8;">${c.dry_cutoff}% - ${c.stop_cutoff}%</div>`;
                mBtn.onclick = () => selectCrop(key);
                modalList.appendChild(mBtn);
            }
        }

        async function scanWifi() {
            const res = await fetch('/api/wifi/scan');
            const data = await res.json();
            const list = document.getElementById('wifi_list');
            list.innerHTML = '';

            document.getElementById('wifi_curr_label').innerText = `Active: ${data.current.ssid} (${data.current.signal}%)`;

            data.networks.forEach(n => {
                const item = document.createElement('div');
                item.style.padding = '6px';
                item.style.background = '#131d31';
                item.style.borderRadius = '6px';
                item.style.cursor = 'pointer';
                item.style.display = 'flex';
                item.style.justifyContent = 'space-between';
                item.innerHTML = `<span>${n.active ? '● ' : ''}${n.ssid}</span><span style="color: #38bdf8;">${n.signal}%</span>`;
                item.onclick = () => {
                    targetSsid = n.ssid;
                    document.getElementById('wifi_target_ssid').innerText = `Connect to: ${n.ssid}`;
                    document.getElementById('wifi_connect_box').style.display = 'block';
                };
                list.appendChild(item);
            });
        }

        async function submitWifiConnect() {
            const pass = document.getElementById('wifi_password').value;
            const res = await fetch('/api/wifi/connect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ssid: targetSsid, password: pass })
            });
            const out = await res.json();
            alert(out.message);
            scanWifi();
        }

        async function loadDiagnostics() {
            const res = await fetch('/api/system/diagnostics');
            const d = await res.json();
            document.getElementById('diag_cpu').innerText = `🌡️ CPU Temp: ${d.cpu_temp}`;
            document.getElementById('diag_ram').innerText = `🧠 Memory: ${d.ram_usage}`;
            document.getElementById('diag_disk').innerText = `💾 Storage: ${d.disk_usage}`;
            document.getElementById('diag_uptime').innerText = `⏱️ Uptime: ${d.uptime}`;
        }

        async function restartGui() {
            if (confirm("Restart dashboard service on Raspberry Pi?")) {
                await fetch('/api/system/restart-gui', { method: 'POST' });
            }
        }

        async function rebootPi() {
            if (confirm("Reboot the entire Raspberry Pi system?")) {
                await fetch('/api/system/reboot', { method: 'POST' });
            }
        }

        function switchModalTab(tab) {
            ['crops', 'cutoffs', 'wifi', 'device', 'info'].forEach(t => {
                document.getElementById(`tab_${t}`).style.display = (t === tab ? 'block' : 'none');
                document.getElementById(`tab_btn_${t}`).className = `modal-tab-btn ${t === tab ? 'active' : ''}`;
            });
            if (tab === 'wifi') scanWifi();
            if (tab === 'device') loadDiagnostics();
        }

        function openSettingsTab(tab) {
            openSettings();
            switchModalTab(tab);
        }

        function openSettings() {
            document.getElementById('settings_modal').style.display = 'flex';
            switchModalTab('crops');
        }

        function closeSettings() {
            document.getElementById('settings_modal').style.display = 'none';
        }

        setInterval(fetchTelemetry, 1000);
        fetchTelemetry();
    </script>
</body>
</html>
"""


@web_app.get("/", response_class=HTMLResponse)
def index():
    return HTML_BLYNK_DASHBOARD


@web_app.get("/api/telemetry")
def get_telemetry():
    return JSONResponse(hardware.get_telemetry())


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
    os.system("echo 123456 | sudo -S systemctl restart iot-dashboard.service &")
    return JSONResponse({"status": "restarting"})


@web_app.post("/api/system/reboot")
def api_reboot_pi():
    os.system("echo 123456 | sudo -S reboot &")
    return JSONResponse({"status": "rebooting"})
