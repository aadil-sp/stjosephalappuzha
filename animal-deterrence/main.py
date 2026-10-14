#!/usr/bin/env python3
"""
Main entry point for Animal Deterrence & Object Detection System.
Captures video from camera/file, runs YOLO inference, renders detection screen,
and triggers deterrent logic for animals while detecting all objects.
Supports live camera switching (press 'c' or '0'-'3') and camera discovery.
"""

import os
import sys
import argparse
import time
from datetime import datetime
from pathlib import Path
import cv2
import numpy as np

# Add project root to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from detection.detector import AnimalDeterrenceDetector


def find_connected_cameras(max_to_check: int = 5) -> list:
    """
    Probes system for available video capture devices.
    Returns list of dicts: [{"index": 0, "width": 1280, "height": 720}, ...]
    """
    detected = []
    print("[Video] Scanning for connected camera devices...")
    for idx in range(max_to_check):
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                detected.append({"index": idx, "width": w, "height": h})
            cap.release()
    return detected


def parse_args():
    parser = argparse.ArgumentParser(
        description="Smart Animal Deterrence - YOLO & OpenCV Real-time Object Detection"
    )
    parser.add_argument(
        "--source",
        type=str,
        default="0",
        help="Video source: camera index ('0', '1', '2'...) or path to video/image file (default: 0)"
    )
    parser.add_argument(
        "--list-cameras",
        action="store_true",
        help="Probe and list all connected cameras and exit"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=str(SCRIPT_DIR / "yolov8n.pt"),
        help="Path or name of YOLO model (default: yolov8n.pt in project folder)"
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.35,
        help="Detection confidence threshold between 0.0 and 1.0 (default: 0.35)"
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        choices=["auto", "mps", "cuda", "cpu"],
        help="Inference device: 'auto' (Apple Silicon MPS if available), 'mps', 'cuda', 'cpu'"
    )
    parser.add_argument(
        "--animals-only",
        action="store_true",
        help="If set, only displays bounding boxes for animals. Default detects ANY object."
    )
    parser.add_argument(
        "--save-alerts",
        action="store_true",
        default=True,
        help="Automatically save snapshot photos when animals are detected (default: True)"
    )
    parser.add_argument(
        "--width",
        type=int,
        default=1280,
        help="Requested capture width (default: 1280)"
    )
    parser.add_argument(
        "--height",
        type=int,
        default=720,
        help="Requested capture height (default: 720)"
    )
    return parser.parse_args()


def open_camera_by_index(cam_idx: int, req_w: int, req_h: int):
    """
    Attempts to open a specific camera index.
    """
    print(f"[Video] Initializing Camera #{cam_idx}...")
    cap = cv2.VideoCapture(cam_idx)
    if cap.isOpened():
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, req_w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, req_h)
        act_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        act_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"[Video] Camera #{cam_idx} active ({act_w}x{act_h})")
        return cap, f"Cam #{cam_idx} ({act_w}x{act_h})"
    return None, ""


def create_synthetic_frame(tick: int) -> np.ndarray:
    """
    Creates a simulated live camera feed with moving demo subjects
    in case no physical camera is connected.
    """
    frame = np.full((720, 1280, 3), (35, 45, 35), dtype=np.uint8)  # Grass background

    # Ground line & sky
    cv2.rectangle(frame, (0, 0), (1280, 260), (95, 75, 45), -1)  # Dusk sky
    cv2.line(frame, (0, 260), (1280, 260), (50, 150, 50), 3)

    # Fence line
    for x in range(0, 1280, 80):
        cv2.line(frame, (x, 220), (x, 400), (40, 80, 120), 4)
    cv2.line(frame, (0, 270), (1280, 270), (40, 80, 120), 3)
    cv2.line(frame, (0, 350), (1280, 350), (40, 80, 120), 3)

    # Animated simulated subject moving across screen
    x_pos = int((tick * 6) % 1100) + 90
    y_pos = 380

    # Draw simulated animal silhouette
    cv2.ellipse(frame, (x_pos, y_pos), (70, 45), 0, 0, 360, (60, 90, 130), -1)
    cv2.circle(frame, (x_pos + 60, y_pos - 25), 30, (60, 90, 130), -1)
    # Ears
    cv2.polygon = np.array([
        [x_pos + 50, y_pos - 50],
        [x_pos + 65, y_pos - 75],
        [x_pos + 80, y_pos - 45]
    ], np.int32)
    cv2.fillPoly(frame, [cv2.polygon], (60, 90, 130))
    # Legs
    cv2.rectangle(frame, (x_pos - 45, y_pos + 30), (x_pos - 30, y_pos + 110), (50, 75, 110), -1)
    cv2.rectangle(frame, (x_pos + 30, y_pos + 30), (x_pos + 45, y_pos + 110), (50, 75, 110), -1)

    cv2.putText(
        frame,
        "SIMULATION MODE - NO CAMERA DETECTED",
        (400, 310),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 255),
        2
    )
    return frame


def log_detection(alert_log_path: Path, animal_names: list):
    """
    Appends an alert log entry with timestamp.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] ALERT: Animal Detected: {', '.join(animal_names)} | Deterrent Triggered\n"
    alert_log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(alert_log_path, "a") as f:
        f.write(log_line)


def main():
    args = parse_args()

    # Discover cameras
    connected_cams = find_connected_cameras(max_to_check=5)
    print(f"[Video] Found {len(connected_cams)} active camera(s):")
    for cam in connected_cams:
        print(f"  -> Camera #{cam['index']}: {cam['width']}x{cam['height']}")

    if args.list_cameras:
        print("[System] Camera discovery complete.")
        return

    # Paths setup
    snapshots_dir = SCRIPT_DIR / "alerts" / "snapshots"
    alerts_log_file = SCRIPT_DIR / "alerts" / "detections.log"
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    print("\n==================================================================")
    print("        SMART ANIMAL DETERRENCE & OBJECT DETECTION SYSTEM         ")
    print("==================================================================")
    print(f" Initial Source: {args.source}")
    print(f" Model:          {args.model}")
    print(f" Confidence:     {args.conf}")
    print(f" Device:         {args.device}")
    print(f" Save Alerts:    {args.save_alerts}")
    print("==================================================================")

    # Initialize YOLO detector
    detector = AnimalDeterrenceDetector(
        model_name=args.model,
        confidence_threshold=args.conf,
        device=args.device
    )

    # Initialize video capture source
    cap = None
    is_static_image = False
    synthetic_mode = False
    source_label = ""
    current_cam_idx = 0
    available_indices = [c["index"] for c in connected_cams]

    if args.source.isdigit():
        current_cam_idx = int(args.source)
        cap, source_label = open_camera_by_index(current_cam_idx, args.width, args.height)
        if cap is None:
            # Fallback to first available camera if any
            if connected_cams:
                current_cam_idx = connected_cams[0]["index"]
                cap, source_label = open_camera_by_index(current_cam_idx, args.width, args.height)
            else:
                print("[Notice] No physical camera could be opened.")
                synthetic_mode = True
                source_label = "Simulation Mode"
    else:
        source_path = Path(args.source)
        if not source_path.exists():
            print(f"[Error] Source file not found: {source_path}")
            sys.exit(1)
        if source_path.suffix.lower() in [".jpg", ".jpeg", ".png", ".bmp", ".webp"]:
            is_static_image = True
            cap = str(source_path)
            source_label = f"Image: {source_path.name}"
        else:
            cap = cv2.VideoCapture(str(source_path))
            source_label = f"Video: {source_path.name}"

    window_name = "Smart Animal Deterrence - Real-Time YOLO & OpenCV"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 1280, 720)

    filter_animals = args.animals_only
    manual_test_mode = False
    last_auto_snapshot_time = 0.0
    tick = 0

    print("\n[Interactive Controls]")
    print("  [Q] or [ESC] : Exit Application")
    print("  [C]          : Cycle to Next Connected Camera")
    print("  [0] - [3]    : Directly Select Camera #0, #1, #2, or #3")
    print("  [A]          : Toggle All Objects vs Animals Only")
    print("  [S]          : Save Manual Screenshot")
    print("  [D]          : Toggle Deterrent Test Mode\n")

    try:
        while True:
            if is_static_image:
                frame = cv2.imread(cap)
                if frame is None:
                    print("[Error] Failed to read image file.")
                    break
            elif synthetic_mode:
                tick += 1
                frame = create_synthetic_frame(tick)
                time.sleep(0.03)
            else:
                ret, frame = cap.read()
                if not ret:
                    if not args.source.isdigit():
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ret, frame = cap.read()
                    if not ret:
                        print("[Video] Frame read failed or stream ended.")
                        break

            # Run YOLO detection
            detections = detector.detect(frame, filter_animals_only=filter_animals)

            # Auto-save snapshot on animal detection
            now = time.time()
            detected_animals = [d["class_name"] for d in detections if d["is_animal"]]
            if detected_animals and args.save_alerts and (now - last_auto_snapshot_time > 5.0):
                last_auto_snapshot_time = now
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                snap_filename = f"animal_alert_{stamp}_{detected_animals[0]}.jpg"
                snap_path = snapshots_dir / snap_filename
                cv2.imwrite(str(snap_path), frame)
                log_detection(alerts_log_file, detected_animals)
                print(f"[Alert] Animal Detected ({', '.join(detected_animals)}). Snapshot saved: {snap_path.name}")

            # Draw HUD, Bounding Boxes, and Alerts
            display_frame = detector.draw_hud_and_boxes(
                frame=frame,
                detections=detections,
                filter_animals_only=filter_animals,
                manual_deterrent_test=manual_test_mode,
                source_label=source_label
            )

            # Show on screen
            cv2.imshow(window_name, display_frame)

            # Handle user keys
            key = cv2.waitKey(1 if not is_static_image else 0) & 0xFF

            if key == ord('q') or key == 27:  # 'q' or ESC
                print("[System] Exiting detection display.")
                break

            elif key == ord('c') and not is_static_image and not synthetic_mode and available_indices:
                # Cycle to next camera
                curr_pos = available_indices.index(current_cam_idx) if current_cam_idx in available_indices else 0
                next_idx = available_indices[(curr_pos + 1) % len(available_indices)]
                print(f"[Switch] Switching from Camera #{current_cam_idx} -> Camera #{next_idx}...")
                cap.release()
                new_cap, new_label = open_camera_by_index(next_idx, args.width, args.height)
                if new_cap is not None:
                    cap = new_cap
                    current_cam_idx = next_idx
                    source_label = new_label
                else:
                    # Reopen previous camera
                    cap, source_label = open_camera_by_index(current_cam_idx, args.width, args.height)

            elif key in [ord('0'), ord('1'), ord('2'), ord('3')] and not is_static_image and not synthetic_mode:
                target_idx = key - ord('0')
                if target_idx != current_cam_idx:
                    print(f"[Switch] Switching directly to Camera #{target_idx}...")
                    cap.release()
                    new_cap, new_label = open_camera_by_index(target_idx, args.width, args.height)
                    if new_cap is not None:
                        cap = new_cap
                        current_cam_idx = target_idx
                        source_label = new_label
                    else:
                        print(f"[Warning] Failed to open Camera #{target_idx}. Restoring Camera #{current_cam_idx}...")
                        cap, source_label = open_camera_by_index(current_cam_idx, args.width, args.height)

            elif key == ord('a'):
                filter_animals = not filter_animals
                mode_label = "ANIMALS ONLY" if filter_animals else "ALL OBJECTS"
                print(f"[System] Detection filter toggled -> {mode_label}")

            elif key == ord('d'):
                manual_test_mode = not manual_test_mode
                status = "ACTIVATED" if manual_test_mode else "DEACTIVATED"
                print(f"[Deterrent] Manual test mode: {status}")

            elif key == ord('s'):
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                snap_filename = f"manual_snapshot_{stamp}.jpg"
                snap_path = snapshots_dir / snap_filename
                cv2.imwrite(str(snap_path), display_frame)
                print(f"[Snapshot] Screen saved to: {snap_path}")

    except KeyboardInterrupt:
        print("\n[System] Interrupted by user.")
    finally:
        if cap is not None and not is_static_image and not synthetic_mode:
            cap.release()
        cv2.destroyAllWindows()
        print("[System] Resources released cleanly.")


if __name__ == "__main__":
    main()
