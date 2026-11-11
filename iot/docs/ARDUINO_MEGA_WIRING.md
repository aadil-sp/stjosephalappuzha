# 🔌 Arduino Mega 2560 Smart Farm Hardware & Wiring Specification

This document provides the complete hardware wiring diagram, pin connections, electrical ratings, and flashing instructions for the **Arduino Mega 2560** microcontroller in the **St. Joseph Alappuzha Smart Agriculture (IoT irrigation) system**.

---

## 1. Pin Connection Matrix

| Component | Arduino Mega Pin | Signal Type | Component Voltage | Wiring Details |
| :--- | :--- | :--- | :--- | :--- |
| **🌱 Soil Moisture Sensor** | **`A0`** | Analog Input (0 - 5V) | `5V` | VCC ➔ `5V`<br>GND ➔ `GND`<br>AOUT ➔ `A0` |
| **🌧️ Rain Drop Sensor** | **`A1`** | Analog Input (0 - 5V) | `5V` | VCC ➔ `5V`<br>GND ➔ `GND`<br>AOUT ➔ `A1` (Wet < 600) |
| **☀️ LDR Light Sensor** | **`A2`** | Analog Input (0 - 5V) | `5V` | VCC ➔ `5V`<br>GND ➔ `GND`<br>AOUT ➔ `A2` (0 - 100%) |
| **🌧️ Rain Tank Ultrasonic** (HC-SR04 / JSN-SR04T) | **`Pin 9`** TRIG<br>**`Pin 10`** ECHO | Digital Out / Digital In | `5V` | VCC ➔ `5V`<br>GND ➔ `GND`<br>TRIG ➔ `Pin 9`<br>ECHO ➔ `Pin 10` |
| **🌡️ DHT11 / DHT22 Sensor** | **`Pin 2`** | Digital (1-Wire Bidirectional) | `5V` / `3.3V` | VCC ➔ `5V`<br>GND ➔ `GND`<br>DATA ➔ `Pin 2` |
| **⚡ Pump 1 (water), motor driver A** (L298N) | **`Pin 5`** IN1<br>**`Pin 7`** IN2 | Digital Out | Pump supply | IN1 ➔ `Pin 5`<br>IN2 ➔ `Pin 7`<br>OUT1 / OUT2 ➔ pump 1<br>ENA jumper on |
| **⚡ Pump 2 (fertilizer), motor driver B** | **`Pin 6`** IN3<br>**`Pin 8`** IN4 | Digital Out | Pump supply | IN3 ➔ `Pin 6`<br>IN4 ➔ `Pin 8`<br>OUT3 / OUT4 ➔ pump 2<br>ENB jumper on. Manual only |
| **💡 Status LED** | **`Pin 13`** | Digital Output | Built-in | Blinks on pump activity & serial telemetry |
| **🖥️ Raspberry Pi 4 Link** | **USB Cable** | Bidirectional UART Serial | `5V` USB | Connects to Pi USB 3.0/2.0 port (`/dev/ttyACM0` @ 115200 baud) |

---

## 2. Pump Motor Driver Wiring

> [!WARNING]
> Never power a pump from the Arduino Mega's 5V pin. Use an external supply for the motor driver and join its GND to the Mega GND.

```
  External 12V supply (+) ──► driver 12V / VS          driver GND ◄── supply (−) ──► Mega GND
                                                     
   Mega D5 ──► IN1   ┐ motor A ──► OUT1 / OUT2 ──► Pump 1 (water)        ENA jumper ON
   Mega D7 ──► IN2   ┘
   Mega D6 ──► IN3   ┐ motor B ──► OUT3 / OUT4 ──► Pump 2 (fertilizer)   ENB jumper ON
   Mega D8 ──► IN4   ┘
```

Both inputs of each motor are driven by the Mega, so none is left floating:

| Pump state | IN1 / IN3 | IN2 / IN4 |
| :--- | :--- | :--- |
| OFF | LOW | LOW |
| ON (forward) | HIGH | LOW |
| ON (reversed) | LOW | HIGH |

A DC pump that spins backwards still runs but pumps weakly. Reverse it in the touchscreen **Wiring** app or the web **Wiring** tab (no rewiring). The direction is stored in the Mega's EEPROM.

---

## 3. Rain Tank Ultrasonic Sensor

The rainwater tank's level is measured with an ultrasonic distance sensor mounted at the **top of the tank, pointing straight down** at the water. The Mega reads it once a second (5 pings, median). The distance becomes a fill percentage:

```
level % = (tank height − distance) / (tank height − gap when full) × 100

        ┌──[ sensor ]──┐  ◄── top of tank
        │      ↓       │      ↕ gap when full (≥ sensor blind zone)
        │~~~~~~~~~~~~~~│  ◄── water when FULL  (100 %)
        │              │
        │   distance   │  ◄── measured each ping
        │      ↓       │
        │~~~~~~~~~~~~~~│  ◄── current water surface
        │              │
        └──────────────┘  ◄── tank floor = tank height (0 %)
```

| Setting | Meaning | Default | Where to change |
| :--- | :--- | :--- | :--- |
| **Tank height** | Distance from the sensor face to the tank floor (= reading when empty) | `100 cm` | Touchscreen **Rain tank** app (±5 cm), web **Tank** tab, or tap **Empty now** with the tank empty |
| **Gap when full** | Distance from the sensor face to the water when the tank is full | `10 cm` | Same places (±1 cm), or tap **Full now** with the tank full |

| **Surface area** | Area of the water surface in cm² (length × width, or 0.785 × diameter² for a round tank). Shows the level in litres: 1 cm over 1000 cm² = 1 L | `10000 cm²` | Touchscreen **Rain tank** app, web **Tank** tab |
| **Alert level** | Level at which the *Rain tank is full* alert appears | `90 %` | Touchscreen **Rain tank** app (±5 %), web **Tank** tab |

They are stored in `config/irrigation_settings.json` (`tank_*`) and pushed to the Mega with `TANK:<height>:<gap>` whenever the Pi connects, the Mega reboots, or a value changes.

### Full-tank alert
The Pi raises the alert when the level reaches the alert level. It stays on (also after a restart) until someone releases the water and taps **Released · Reset** on the touchscreen or the web page. It can only fire again once the level has dropped 10 % below the alert level.

### Pump 2 (fertilizer) safety
Pump 2 is manual. Every run is sent as `FERT:ON:<seconds>`, so the Mega switches it off by itself when the time is up, even if the Pi crashes. The longest run is **Settings ➔ Pump 2 auto-off** (default 5 min).

### Sensor choice & mounting
- **HC-SR04**: cheap, 2–400 cm, but **not waterproof** — keep it dry and above splash level. Fine for a covered tank.
- **JSN-SR04T / AJ-SR04M**: waterproof probe, recommended for outdoor tanks. Its **blind zone is ~20–25 cm**, so set *Gap when full* to at least that (mount the probe higher above the overflow if needed).
- Mount the sensor centred, away from the inlet pipe and the tank walls (≥ 10 cm), so the sound cone only sees the water surface.
- Use shielded or twisted wire for runs longer than ~2 m; keep the ECHO wire away from the pump power cable.
- If the reading shows **"No echo"**, check VCC/GND, swap TRIG/ECHO if reversed, and make sure the sensor is not closer to the water than its blind zone.

---

## 4. Arduino ➔ Raspberry Pi Serial Communication Protocol

The Arduino Mega and Raspberry Pi 4 communicate over USB Serial at **115200 baud** (`/dev/ttyACM0`).

### Telemetry Broadcast (Arduino ➔ Raspberry Pi every 1 sec)
```json
{
  "temp": 28.4,
  "humidity": 64.0,
  "soil": 42.0,
  "rain": 0,
  "light": 72,
  "water_level": 85,
  "water_cm": 23.5,
  "pump": 0,
  "fert_pump": 0,
  "mode": "AUTO",
  "dry_cutoff": 35.0,
  "stop_cutoff": 65.0
}
```

### Commands Received (Raspberry Pi ➔ Arduino)
- `PUMP:ON` — Turns pump 1 (water) on.
- `PUMP:ON:<seconds>` — Water pump on, switching itself off after that many seconds.
- `FERT:ON:<seconds>` — Fertilizer pump on for at most that many seconds (`FERT:ON` alone = 300 s, max 3600 s).
- `FERT:OFF` — Fertilizer pump off.
- `PUMP:OFF` — Turns pump 1 off.
- `MODE:AUTO` — Switches Arduino to automatic soil-threshold irrigation mode.
- `MODE:MANUAL` — Stops automatic triggering and waits for manual commands.
- `CUTOFF:<dry>:<stop>` — Updates low and target moisture percentages (e.g., `CUTOFF:30:60`).
- `TANK:<height_cm>:<gap_cm>` — Sets the rain tank calibration (e.g., `TANK:120:20`).
- `DIR:PUMP:FWD|REV`, `DIR:FERT:FWD|REV` — Pump 1 / pump 2 motor direction (saved in EEPROM).

`temp`, `humidity`, `water_level` and `water_cm` are sent as `null` when the sensor is not responding. `water_*` is the rain tank.

---

## 5. How to Flash / Upload Firmware

### Option A: Build on a laptop, flash from the Raspberry Pi
The Pi has `avrdude` but not the Arduino toolchain, so build the `.hex` elsewhere and copy it over:
```bash
arduino-cli compile --fqbn arduino:avr:mega iot/firmware/arduino_mega_farm --output-dir build
scp build/arduino_mega_farm.ino.hex school@<pi-ip>:/tmp/arduino_mega_farm.hex
ssh school@<pi-ip> 'sudo systemctl stop iot-dashboard && \
  avrdude -p atmega2560 -c wiring -P /dev/ttyACM0 -b 115200 -D -U flash:w:/tmp/arduino_mega_farm.hex:i && \
  sudo systemctl start iot-dashboard'
```
The dashboard service must be stopped while flashing because it holds `/dev/ttyACM0`.

### Option B: Via Arduino IDE (Windows / Mac)
1. Open `iot/firmware/arduino_mega_farm/arduino_mega_farm.ino` in Arduino IDE.
2. Select **Tools ➔ Board ➔ Arduino AVR Boards ➔ Arduino Mega or Mega 2560**.
3. Select **Tools ➔ Port** (Select your Arduino USB Port).
4. Click **Upload** (Ctrl+U / Cmd+U).
