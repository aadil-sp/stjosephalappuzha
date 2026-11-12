# IoT Project

A modular Internet of Things (IoT) monitoring and telemetry platform.

## Target Hardware: Raspberry Pi 4

- **Hostname**: `school.local`
- **IP Address**: `10.139.93.188` (DHCP; check the Device app if it changes)
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

The touchscreen (480x320 LCD on `/dev/fb1`, `dashboard_app.py`) works like a small tablet: a status bar (time, page title, link status), the page, and a bottom bar with **Back**, **Home** and **Apps**. The same features are in the browser at `http://<pi-ip>:8000` (`dashboard/index.html`). Both use one dark theme and the shared icon set in `icons.py`.

**Home** is the farm dashboard: Alappuzha weather, the soil moisture gauge, field sensors (temperature, humidity, rain, light), today's advice, the **rain tank** level and switches for **pump 1** (water) and **pump 2** (fertilizer). **Apps** opens the app drawer:

1. **Today**: daily advice from today's Alappuzha forecast and the selected crop: how much water the crop needs (or *No watering today* when rain covers it) and whether to give fertilizer (due, not due yet, or *Postpone* when heavy rain would wash it off), with a button to run pump 2 for today's amount. See [Daily advice](#daily-advice).
2. **Farm AI**: Google Gemini suggestions. **Brief**: today's plan from the weekday, forecast, sensors and crop (for example *Rainy till Thu: water less*), with actions, reminders and warnings; refreshed every 3 hours. **Crop**: a profile for any crop (moisture cutoffs, Kc, feeding interval, season, pests) that you can apply as the Custom crop. **Settings**: checks your cutoffs, tank alert, feed size and crop stage and lets you apply each suggestion. **Ask**: preset or typed questions. See [Farm AI](#farm-ai).
3. **Water** (pump 1): AUTO / MANUAL and the start / stop soil moisture cutoffs. In AUTO the Arduino switches pump 1 by itself, so watering keeps working if the Pi is down.
4. **Fertilizer** (pump 2): manual. **On / Off**, or run for 30 s / 1 / 2 / 5 min. Every run stops by itself (auto-off limit in Settings).
5. **Rain tank**: level and litres from the ultrasonic sensor, alert level, height, gap when full, surface area, **Empty now / Full now**. See [Arduino Mega Wiring](docs/ARDUINO_MEGA_WIRING.md#3-rain-tank-ultrasonic-sensor).
6. **Weather**: Alappuzha now, the next hours and 5 days (Open-Meteo, refreshed every 15 min, cached for offline use).
7. **Crops**: Tomato, Paddy, Chilli, Potato, Corn, Cactus, Onion or Custom; sets the moisture cutoffs. See the [**Crop Care Guide**](docs/CROP_CARE_GUIDE.md).
8. **Simulator**: fake temperature, humidity, soil moisture and rain tank level.
9. **Wi-Fi**: scan, paged network list, on-screen keyboard for passwords.
10. **Settings**: crop stage, field area, fertilizer per feed, pump 1 and pump 2 flow (L/min), pump 2 auto-off.
11. **Device**: IP address, web address, CPU temperature, memory, storage, uptime, Arduino link, **Restart app**, **Reboot Pi** (tap twice).
12. **Wiring**: Arduino Mega pin map.

**Rain tank full:** when the level reaches the alert level (default 90 %), the touchscreen shows a *Rain tank is full* popup on every page, the status bar shows **TANK FULL**, and the web page shows a red banner. Open the outlet, release the water, then tap **Released · Reset**. *Later* hides the popup for 30 minutes. After a reset the alert only comes back once the level has dropped 10 % below the alert level and filled up again.

### Farm AI
Farm AI uses the Google Gemini API (`farm_ai.py`, plain HTTPS, no extra packages).

1. Create a key at [Google AI Studio](https://aistudio.google.com/apikey) (**Get API key**).
2. Open the web dashboard (`http://<pi-ip>:8000`), **Device** tab, paste it under **Gemini API key**, **Save key**. It is written to `config/.env` on the Pi as `GEMINI_API_KEY=...` (git-ignored, never sent back to the browser). You can also add that line to `config/.env` by hand and restart the app.
3. Optional: `GEMINI_MODEL=...` in `config/.env` picks a model (default `gemini-2.5-flash`; if that model is gone, the newest Flash model is used).

Farm AI sends Gemini the date, forecast, sensor readings, crop, settings and today's rule-based advice, and asks for JSON answers. It never switches a pump: settings only change when someone taps **Apply**, and they go through the same range checks as the manual controls. Answers are cached in `config/ai_cache.json`, so the last brief still shows without internet. Check AI advice on chemicals and doses with the [Crop Care Guide](docs/CROP_CARE_GUIDE.md) or the local Krishi Bhavan before using it.

### Daily advice
- **Water:** crop water use = ET0 (from the forecast) × Kc for the crop and stage (FAO-56, see the [Crop Care Guide](docs/CROP_CARE_GUIDE.md#2-working-out-how-much-water-to-give)), minus the useful part of today's forecast rain. Litres = mm × field area ÷ 0.9; minutes = litres ÷ pump 1 flow. In AUTO the soil sensor still decides when pump 1 runs; the figure shows how much the crop should get.
- **Fertilizer:** liquid feed every 7 days (tomato, chilli), 10 days (onion, potato, corn, custom), 14 days (paddy) or 30 days (cactus). A pump 2 run of 20 s or more counts as that day's feed. It is postponed when 10 mm or more of rain is forecast (or a likely 5 mm or more), and the next dry day is suggested.
- These are rules of thumb. Set the crop stage, field area and pump flows in **Settings** so the numbers fit your farm.

The resistive touch driver only reports taps, so the touchscreen UI avoids sliders and scrolling: every control is a button, a +/- stepper or a number pad.

---

## Android App (control from anywhere)

`android/` holds a native Android app with the same controls (APK in `android/release/`).
To use it away from the farm, give the Pi an internet address once with
`bash setup_remote_access.sh <ngrok-authtoken> <static-domain>`. Requests from the
internet must carry the app access key, shown on the touchscreen under **Device → App key**;
devices on the local network need no key. See [android/README.md](android/README.md).

---

## Directory Structure

- [`firmware/`](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/iot/firmware): Embedded C/C++ or MicroPython code for microcontrollers (ESP32, ESP8266, Arduino) and Pi GPIO.
- [`sensors/`](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/iot/sensors): Drivers, calibration algorithms, and standalone sensor test routines.
- [`backend/`](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/iot/backend): API services, database storage (InfluxDB/SQLite/PostgreSQL), and MQTT/HTTP brokers.
- [`dashboard/`](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/iot/dashboard): User interface and live data analytics frontend.
- [`config/`](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/iot/config): Pin mappings, network settings, and `.env` templates.
- [`docs/`](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/iot/docs): Wiring diagrams, hardware component datasheets, and architectural designs.


