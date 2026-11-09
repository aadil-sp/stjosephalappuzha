# IoT Project

A modular Internet of Things (IoT) monitoring and telemetry platform.

## Target Hardware: Raspberry Pi 4

- **Hostname**: `school.local`
- **IP Address**: `10.180.5.188`
- **User**: `school`
- **Password**: stored in `config/.env` as `PI_PASSWORD` (git-ignored; see `config/.env.example`). *Passwordless SSH key already configured from this Mac.*
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

## Touchscreen & Web Dashboard

The same dashboard runs full-screen on the 3.5" (480x320) LCD (`/dev/fb1`, `dashboard_app.py`) and in the browser at `http://<pi-ip>:8000` (`dashboard/index.html`). Both use one dark "field" theme and the shared vector icon set in `icons.py` (drawn with QPainter on the Pi, inline SVG in the browser).

1. **Home**: soil moisture gauge with the start (amber) and stop (blue) cutoff markers, tiles for temperature, humidity, water tank (ultrasonic) and weather (rain + light), a large **PUMP** button and an **AUTO / MANUAL** switch.
2. **Crops**: Tomato, Paddy, Chilli, Potato, Corn, Cactus, Onion or Custom. Picking a crop sets the cutoffs and sends them to the Arduino. How to grow, water, feed and protect each crop: [**Crop Care Guide**](docs/CROP_CARE_GUIDE.md).
3. **Cutoffs**: +/- 5% steppers for the start and stop moisture, plus a watering-band bar showing the current soil reading. Saved to `config/irrigation_settings.json`.
4. **Tank**: ultrasonic water level (HC-SR04 / JSN-SR04T on Mega D9/D10). Set the **tank height** (sensor to floor) and the **gap when full**, or tap **Empty now / Full now** to capture them from the sensor. See [Arduino Mega Wiring](docs/ARDUINO_MEGA_WIRING.md#3-ultrasonic-water-tank-sensor).
5. **Simulator**: fake temperature, humidity and soil values for testing; the pump follows the simulated soil value.
6. **Wi-Fi**: scan via `nmcli`, paged network list, on-screen keyboard for passwords.
7. **Device**: IP address, CPU temperature, memory, storage, uptime, Arduino link, **Restart app** and **Reboot Pi** (tap twice to confirm).
8. **Wiring**: Arduino Mega pin map.

The resistive touch driver only reports taps, so the touchscreen UI avoids sliders and scrolling: every control is a button of at least ~34px.

---

## Directory Structure

- [`firmware/`](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/iot/firmware): Embedded C/C++ or MicroPython code for microcontrollers (ESP32, ESP8266, Arduino) and Pi GPIO.
- [`sensors/`](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/iot/sensors): Drivers, calibration algorithms, and standalone sensor test routines.
- [`backend/`](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/iot/backend): API services, database storage (InfluxDB/SQLite/PostgreSQL), and MQTT/HTTP brokers.
- [`dashboard/`](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/iot/dashboard): User interface and live data analytics frontend.
- [`config/`](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/iot/config): Pin mappings, network settings, and `.env` templates.
- [`docs/`](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/iot/docs): Wiring diagrams, hardware component datasheets, and architectural designs.


