# St. Joseph's Alappuzha - Projects Workspace

This workspace contains two distinct projects:

1. [**IoT System (`iot/`)**](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/iot/README.md) - Internet of Things monitoring, sensor data acquisition, cloud/local backend, and live dashboard.
2. [**Animal Deterrence System (`animal-deterrence/`)**](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/animal-deterrence/README.md) - Smart wildlife/intrusion detection, automated deterrent triggers (ultrasonic/strobe/siren), and real-time alert notifications.

---

## Quick Launch Shortcuts

- [**`Open_Web_Dashboard.command`**](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/Open_Web_Dashboard.command): Opens the live IoT Smart Agriculture Dashboard in your browser (`http://10.180.5.188:8000`).
- [**`Start_Animal_Detector.command`**](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/Start_Animal_Detector.command): Launches the interactive camera selector and YOLO detection screen.
- [**`SSH_To_Pi.command`**](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/SSH_To_Pi.command): One-click instant SSH shell into your Raspberry Pi 4 (`school@school.local`).



## Directory Overview

```text
stjosephalappuzha/
├── iot/
│   ├── firmware/     # Microcontroller code (ESP32 / Arduino / Raspberry Pi Pico)
│   ├── sensors/      # Sensor drivers, calibration, and test scripts
│   ├── backend/      # Server, APIs, data logging, MQTT brokers
│   ├── dashboard/    # Web / mobile visualization dashboard
│   ├── config/       # Environment configs & hardware pin definitions
│   └── docs/         # Circuit schematics, wiring guides, design notes
│
└── animal-deterrence/
    ├── detection/    # Computer vision / PIR / motion detection pipelines
    ├── firmware/     # Edge device & microcontroller control firmware
    ├── deterrents/   # Repeller control (ultrasonic, strobe, audio alarms)
    ├── alerts/       # Notification dispatchers (GSM / SMS / Telegram / Email)
    ├── config/       # Threshold configs and device mappings
    └── docs/         # Project documentation, field test records, schematics
```
