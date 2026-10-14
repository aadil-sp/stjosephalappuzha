# Smart Animal Deterrence System

An intelligent animal detection and deterrent system to protect agricultural fields and premises from wildlife intrusion (wild boars, elephants, monkeys, stray cattle).

## Directory Structure

- [`detection/`](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/animal-deterrence/detection): Computer vision models (OpenCV / YOLO / TensorFlow Lite) and sensor-based detection scripts (PIR, microwave radar, seismic).
- [`firmware/`](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/animal-deterrence/firmware): Microcontroller/Raspberry Pi embedded logic that coordinates sensors and triggers.
- [`deterrents/`](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/animal-deterrence/deterrents): Drivers and control routines for deterrent hardware (frequency-sweeping ultrasonic emitters, high-intensity strobe lights, siren relays, water sprayers).
- [`alerts/`](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/animal-deterrence/alerts): Real-time notification services via GSM (SMS/calls), Telegram bots, or push alerts to farmers/authorities.
- [`config/`](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/animal-deterrence/config): Hardware pin maps, sensitivity thresholds, operating schedules, and credentials.
- [`docs/`](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/animal-deterrence/docs): Circuit diagrams, power budget/solar calculations, field test observations, and component lists.

## Running the Detection Screen

Launch the real-time YOLO & OpenCV detection screen:

```bash
# From the animal-deterrence directory:
python3 main.py

# Or specify webcam index, video file, or test image:
python3 main.py --source 0
python3 main.py --source path/to/video.mp4
python3 main.py --source path/to/test_image.jpg

# Optional performance flags:
python3 main.py --conf 0.4 --device cpu
```

### Interactive Screen Controls

When the detection window is open:
- **`Q` or `ESC`**: Exit the application.
- **`A`**: Toggle between **All Objects** and **Animals Only** detection mode.
- **`S`**: Save an instant screenshot snapshot to [`alerts/snapshots/`](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/animal-deterrence/alerts/snapshots).
- **`D`**: Manually toggle the deterrent test mode on/off.

---

## Workflow

1. **Detect**: Sensor or camera captures real-time frames processed by YOLOv8.
2. **Classify & Highlight**:
   - Animals (dogs, cows, elephants, horses, birds, cats, etc.) trigger a prominent **Red/Orange alert box** with corner markers and activation of simulated deterrents (ultrasonic sound, strobe light).
   - Any other objects (people, vehicles, chairs, backpacks, etc.) are detected with **Cyan/Blue bounding boxes** with confidence percentages.
3. **Deterrent Trigger**: When wildlife is detected, the HUD status turns into an **Alert Banner** and auto-saves an intrusion snapshot.
4. **Alert Log**: Timestamped detection events are appended to [`alerts/detections.log`](file:///Users/aadilsp/Desktop/Antigravity/stjosephalappuzha/animal-deterrence/alerts/detections.log).

