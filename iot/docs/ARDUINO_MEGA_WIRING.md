# 🔌 Arduino Mega 2560 Smart Farm Hardware & Wiring Specification

This document provides the complete hardware wiring diagram, pin connections, electrical ratings, and flashing instructions for the **Arduino Mega 2560** microcontroller in the **St. Joseph Alappuzha Smart Agriculture (IoT irrigation) system**.

---

## 1. Pin Connection Matrix

| Component | Arduino Mega Pin | Signal Type | Component Voltage | Wiring Details |
| :--- | :--- | :--- | :--- | :--- |
| **🌱 Soil Moisture Sensor** | **`A0`** | Analog Input (0 - 5V) | `5V` | VCC ➔ `5V`<br>GND ➔ `GND`<br>AOUT ➔ `A0` |
| **🌧️ Rain Drop Sensor** | **`A1`** | Analog Input (0 - 5V) | `5V` | VCC ➔ `5V`<br>GND ➔ `GND`<br>AOUT ➔ `A1` (Wet < 600) |
| **☀️ LDR Light Sensor** | **`A2`** | Analog Input (0 - 5V) | `5V` | VCC ➔ `5V`<br>GND ➔ `GND`<br>AOUT ➔ `A2` (0 - 100%) |
| **💧 Ultrasonic Tank Sensor** (HC-SR04 / JSN-SR04T) | **`Pin 9`** TRIG<br>**`Pin 10`** ECHO | Digital Out / Digital In | `5V` | VCC ➔ `5V`<br>GND ➔ `GND`<br>TRIG ➔ `Pin 9`<br>ECHO ➔ `Pin 10` |
| **🌡️ DHT11 / DHT22 Sensor** | **`Pin 2`** | Digital (1-Wire Bidirectional) | `5V` / `3.3V` | VCC ➔ `5V`<br>GND ➔ `GND`<br>DATA ➔ `Pin 2` |
| **⚡ Water Pump Relay Module**| **`Pin 8`** | Digital Output (Active LOW) | `5V` | VCC ➔ `5V`<br>GND ➔ `GND`<br>IN1 ➔ `Pin 8` |
| **💡 Status LED** | **`Pin 13`** | Digital Output | Built-in | Blinks on pump activity & serial telemetry |
| **🖥️ Raspberry Pi 4 Link** | **USB Cable** | Bidirectional UART Serial | `5V` USB | Connects to Pi USB 3.0/2.0 port (`/dev/ttyACM0` @ 115200 baud) |

---

## 2. Water Pump Relay Wiring Diagram

> [!WARNING]
> **Relay Isolation Warning:**
> Never power a 12V or high-current submersible water pump directly from the Arduino Mega 5V pin! Use an external power adapter with a common ground.

```
       +------------------------------------+
       |   External 12V DC Power Supply     |
       |  (+) 12V                  (-) GND  |
       +-----+------------------------+-----+
             |                        |
             |                        +----------+
             v                                   |
      +--------------+                           |
      | Relay Module |                           |
      |              |                           |
      |   [ COM ] <---+                          |
      |              |                           |
      |   [ NO  ] ----+                          |
      +--------------+ |                         |
                       v                         v
               +---------------+         +---------------+
               |  (+) Water    |         |  (-) Water    |
               |  Pump Input   |         |  Pump Ground  |
               +---------------+         +---------------+
```

### Common Ground
Connect the **(-) GND** of the external 12V pump power supply to the **GND** pin of the Arduino Mega so that signal levels remain referenced properly.

---

## 3. Ultrasonic Water Tank Sensor

The tank level is measured with an ultrasonic distance sensor mounted at the **top of the tank, pointing straight down** at the water. The Mega pings 5 times every 0.5 s, takes the median distance, and converts it to a fill percentage:

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
| **Tank height** | Distance from the sensor face to the tank floor (= reading when empty) | `100 cm` | Touchscreen **Settings ➔ Tank** (±5 cm), web **Tank** tab, or tap **Empty now** with the tank empty |
| **Gap when full** | Distance from the sensor face to the water when the tank is full | `10 cm` | Same places (±1 cm), or tap **Full now** with the tank full |

Both values are stored in `config/irrigation_settings.json` (`tank_empty_cm`, `tank_full_cm`) and pushed to the Mega with `TANK:<height>:<gap>` whenever the Pi connects, the Mega reboots, or a value changes.

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
  "mode": "AUTO",
  "dry_cutoff": 35.0,
  "stop_cutoff": 65.0
}
```

### Commands Received (Raspberry Pi ➔ Arduino)
- `PUMP:ON` — Manually turns on the water pump relay.
- `PUMP:OFF` — Manually turns off the water pump relay.
- `MODE:AUTO` — Switches Arduino to automatic soil-threshold irrigation mode.
- `MODE:MANUAL` — Stops automatic triggering and waits for manual commands.
- `CUTOFF:<dry>:<stop>` — Updates low and target moisture percentages (e.g., `CUTOFF:30:60`).
- `TANK:<height_cm>:<gap_cm>` — Sets the ultrasonic tank calibration (e.g., `TANK:120:20`).

`temp`, `humidity`, `water_level` and `water_cm` are sent as `null` when the sensor is not responding.

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
