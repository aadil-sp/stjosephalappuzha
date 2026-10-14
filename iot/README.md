# IoT Project

A modular Internet of Things (IoT) monitoring and telemetry platform.

## Target Hardware: Raspberry Pi 4

- **Hostname**: `school.local`
- **IP Address**: `10.180.5.188`
- **User**: `school`
- **Password**: `123456` *(Passwordless SSH key already configured from this Mac)*
- **Model**: Raspberry Pi 4 Model B (Rev 1.2, 2GB RAM)
- **OS**: Debian GNU/Linux 1:6.18 (aarch64 64-bit) with Python 3.13.5
- **Project Directory on Pi**: `~/stjoseph_iot/`

---

## Connecting via SSH

You have multiple easy ways to connect:

1. **One-Click Finder Launcher**: Double-click [**`SSH_To_Pi.command`**](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/SSH_To_Pi.command) or [**`iot/ssh_pi.command`**](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/iot/ssh_pi.command).
2. **Terminal Command**:
   ```bash
   ssh school@school.local
   ```
   *(No password required – public key authenticated)*

---

## Syncing Code to the Pi

To push changes from your Mac to the Pi:

```bash
cd /Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/iot
./sync_to_pi.sh
```

---

---

## Interactive Device & Blynk Dashboard Features

The dashboard runs full-screen on the 3.5" (480x320) LCD touchscreen (`/dev/fb1`) and over HTTP at `http://10.180.5.188:8000`:

1. **Blynk-Style UI**:
   - Real-time gauge tiles for Temperature, Humidity, and Soil Moisture.
   - Active Crop Badge (e.g. `🍅 Tomato (35%-65%)`).
   - Compact **Motor Relay Toggle Button** positioned in the bottom-right corner.
   - Status indicators and live clock.

2. **Crop Selection & Profiles (`🌾 Crops`)**:
   - `🍅 Tomato / Vegetables` (35% - 65% moisture)
   - `🌾 Paddy / Rice` (50% - 85% moisture)
   - `🌶️ Chilli / Pepper` (25% - 55% moisture)
   - `🥔 Potato / Tubers` (30% - 60% moisture)
   - `🌽 Corn / Maize` (30% - 65% moisture)
   - `🌵 Cactus / Arid` (15% - 35% moisture)
   - `⚙️ Custom Profile` (user-defined cutoffs)

3. **Cutoff Adjuster (`💧 Cutoffs`)**:
   - Fine-tune low cutoff (motor start) and high cutoff (motor stop) in 5% increments.
   - Automatically saved to `config/irrigation_settings.json`.

4. **Wi-Fi Manager & On-Screen Keyboard (`📶 Wi-Fi`)**:
   - Real-time network scanning via `nmcli`.
   - Virtual on-screen touch keyboard (QWERTY + 123/Symbols + Shift + Backspace) for entering Wi-Fi passwords directly on the 3.5" LCD touchscreen without external peripherals.

5. **Device Setup & Diagnostics (`⚙️ Device`)**:
   - Real-time CPU Temperature, RAM usage, Storage, and Uptime.
   - One-touch **Restart GUI** and **Reboot Pi** buttons.

---

## Directory Structure

- [`firmware/`](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/iot/firmware): Embedded C/C++ or MicroPython code for microcontrollers (ESP32, ESP8266, Arduino) and Pi GPIO.
- [`sensors/`](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/iot/sensors): Drivers, calibration algorithms, and standalone sensor test routines.
- [`backend/`](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/iot/backend): API services, database storage (InfluxDB/SQLite/PostgreSQL), and MQTT/HTTP brokers.
- [`dashboard/`](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/iot/dashboard): User interface and live data analytics frontend.
- [`config/`](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/iot/config): Pin mappings, network settings, and `.env` templates.
- [`docs/`](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/iot/docs): Wiring diagrams, hardware component datasheets, and architectural designs.


