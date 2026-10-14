# 🔌 Arduino Mega 2560 Smart Farm Hardware & Wiring Specification

This document provides the complete hardware wiring diagram, pin connections, electrical ratings, and flashing instructions for the **Arduino Mega 2560** microcontroller in the **St. Joseph Alappuzha Smart Agriculture & Deterrence System**.

---

## 1. Pin Connection Matrix

| Component | Arduino Mega Pin | Signal Type | Component Voltage | Wiring Details |
| :--- | :--- | :--- | :--- | :--- |
| **🌱 Soil Moisture Sensor** | **`A0`** | Analog Input (0 - 5V) | `5V` | VCC ➔ `5V`<br>GND ➔ `GND`<br>AOUT ➔ `A0` |
| **🌧️ Rain Drop Sensor** | **`A1`** | Analog Input (0 - 5V) | `5V` | VCC ➔ `5V`<br>GND ➔ `GND`<br>AOUT ➔ `A1` (Wet < 600) |
| **☀️ LDR Light Sensor** | **`A2`** | Analog Input (0 - 5V) | `5V` | VCC ➔ `5V`<br>GND ➔ `GND`<br>AOUT ➔ `A2` (0 - 100%) |
| **💧 Water Level Sensor** | **`A3`** | Analog Input (0 - 5V) | `5V` | VCC ➔ `5V`<br>GND ➔ `GND`<br>Signal ➔ `A3` (Tank depth) |
| **🌡️ DHT11 / DHT22 Sensor** | **`Pin 2`** | Digital (1-Wire Bidirectional) | `5V` / `3.3V` | VCC ➔ `5V`<br>GND ➔ `GND`<br>DATA ➔ `Pin 2` |
| **⚡ Water Pump Relay Module**| **`Pin 8`** | Digital Output (Active LOW) | `5V` | VCC ➔ `5V`<br>GND ➔ `GND`<br>IN1 ➔ `Pin 8` |
| **🔊 Deterrence Buzzer** | **`Pin 9`** | Digital Output / PWM | `5V` | Positive (+) ➔ `Pin 9`<br>Negative (-) ➔ `GND` |
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

## 3. Arduino ➔ Raspberry Pi Serial Communication Protocol

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
- `BUZZ:ON` / `BUZZ:OFF` — Triggers animal deterrence acoustic alarm.

---

## 4. How to Flash / Upload Firmware

### Option A: Direct from Raspberry Pi (Automated)
```bash
~/.local/bin/arduino-cli compile --fqbn arduino:avr:mega ~/stjoseph_iot/firmware/arduino_mega_farm
~/.local/bin/arduino-cli upload -p /dev/ttyACM0 --fqbn arduino:avr:mega ~/stjoseph_iot/firmware/arduino_mega_farm
```

### Option B: Via Arduino IDE (Windows / Mac)
1. Open the [**`arduino_mega_farm.ino`**](file:///c:/Users/hp/OneDrive/Desktop/smart_farm/stjosephalappuzha/iot/firmware/arduino_mega_farm/arduino_mega_farm.ino) file in Arduino IDE.
2. Select **Tools ➔ Board ➔ Arduino AVR Boards ➔ Arduino Mega or Mega 2560**.
3. Select **Tools ➔ Port** (Select your Arduino USB Port).
4. Click **Upload** (Ctrl+U / Cmd+U).
