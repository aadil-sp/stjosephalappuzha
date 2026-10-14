"""
Animal Deterrence System - Object & Wildlife Detector
Utilizes YOLOv8 (Ultralytics) and OpenCV for real-time object detection
with specialized wildlife detection and deterrent activation logic.
"""

import time
import cv2
import numpy as np
import torch
from pathlib import Path
from typing import List, Dict, Any, Tuple


class AnimalDeterrenceDetector:
    # Standard COCO classes categorized as animals / wildlife
    ANIMAL_CLASSES = {
        'bird', 'cat', 'dog', 'horse', 'sheep',
        'cow', 'elephant', 'bear', 'zebra', 'giraffe'
    }

    # Color palette (BGR format for OpenCV)
    COLOR_ANIMAL = (0, 69, 255)       # High-visibility Red-Orange
    COLOR_OBJECT = (255, 200, 0)      # Cyan / Neon Blue
    COLOR_HUD_BG = (20, 20, 20)       # Dark charcoal
    COLOR_ALERT_BG = (0, 0, 180)      # Alert Red
    COLOR_SECURE_BG = (34, 139, 34)   # Forest Green
    COLOR_TEXT = (255, 255, 255)      # White

    def __init__(
        self,
        model_name: str = "yolov8n.pt",
        confidence_threshold: float = 0.35,
        device: str = "auto"
    ):
        """
        Initialize the detector with YOLO model and inference settings.
        """
        self.conf_threshold = confidence_threshold

        # Device selection: Apple Silicon MPS -> CUDA -> CPU
        if device == "auto":
            if torch.backends.mps.is_available():
                self.device = "mps"
            elif torch.cuda.is_available():
                self.device = "cuda"
            else:
                self.device = "cpu"
        else:
            self.device = device

        print(f"[Detector] Loading YOLO model: {model_name} on device: {self.device.upper()}...")
        from ultralytics import YOLO
        self.model = YOLO(model_name)
        print(f"[Detector] Model loaded successfully. Classes supported: {len(self.model.names)}")

        # Performance monitoring
        self.prev_time = time.time()
        self.fps = 0.0

        # State tracking
        self.animal_detected = False
        self.deterrent_active = False
        self.last_detection_time = 0.0
        self.deterrent_cooldown_duration = 4.0  # seconds deterrent remains active after detection

    def detect(self, frame: np.ndarray, filter_animals_only: bool = False) -> List[Dict[str, Any]]:
        """
        Runs YOLO inference on the input frame and returns parsed detection dictionaries.
        """
        results = self.model.predict(
            source=frame,
            conf=self.conf_threshold,
            device=self.device,
            verbose=False
        )

        detections = []
        animal_count = 0

        for r in results:
            boxes = r.boxes
            if boxes is None:
                continue

            for box in boxes:
                cls_id = int(box.cls[0].item())
                cls_name = self.model.names[cls_id]
                conf = float(box.conf[0].item())
                xyxy = box.xyxy[0].cpu().numpy().astype(int)

                is_animal = cls_name.lower() in self.ANIMAL_CLASSES
                if is_animal:
                    animal_count += 1

                if filter_animals_only and not is_animal:
                    continue

                detections.append({
                    "box": xyxy,  # [x1, y1, x2, y2]
                    "class_name": cls_name,
                    "confidence": conf,
                    "is_animal": is_animal
                })

        # Update deterrent state
        now = time.time()
        if animal_count > 0:
            self.animal_detected = True
            self.deterrent_active = True
            self.last_detection_time = now
        else:
            self.animal_detected = False
            # Keep deterrent active for cooldown period
            self.deterrent_active = (now - self.last_detection_time) < self.deterrent_cooldown_duration

        return detections

    def draw_hud_and_boxes(
        self,
        frame: np.ndarray,
        detections: List[Dict[str, Any]],
        filter_animals_only: bool = False,
        manual_deterrent_test: bool = False,
        source_label: str = ""
    ) -> np.ndarray:
        """
        Renders bounding boxes, labels, and real-time heads-up display on the frame.
        """
        annotated = frame.copy()
        h, w = annotated.shape[:2]

        # Calculate FPS
        curr_time = time.time()
        time_diff = curr_time - self.prev_time
        if time_diff > 0:
            self.fps = (self.fps * 0.9) + (1.0 / time_diff * 0.1)
        self.prev_time = curr_time

        # Count objects
        animal_count = sum(1 for d in detections if d["is_animal"])
        other_count = len(detections) - animal_count

        # 1. Draw Bounding Boxes with styling
        for det in detections:
            x1, y1, x2, y2 = det["box"]
            cls_name = det["class_name"]
            conf = det["confidence"]
            is_animal = det["is_animal"]

            # Choose color scheme
            if is_animal:
                box_color = self.COLOR_ANIMAL
                label_text = f"ANIMAL: {cls_name.upper()} {conf:.0%}"
                border_thick = 3
            else:
                box_color = self.COLOR_OBJECT
                label_text = f"{cls_name} {conf:.0%}"
                border_thick = 2

            # Rectangle around object
            cv2.rectangle(annotated, (x1, y1), (x2, y2), box_color, border_thick)

            # High-tech corner accents for animals
            if is_animal:
                corner_len = min(20, (x2 - x1) // 4, (y2 - y1) // 4)
                accent_color = (0, 255, 255)  # Bright yellow accents
                # Top-left
                cv2.line(annotated, (x1, y1), (x1 + corner_len, y1), accent_color, 4)
                cv2.line(annotated, (x1, y1), (x1, y1 + corner_len), accent_color, 4)
                # Top-right
                cv2.line(annotated, (x2, y1), (x2 - corner_len, y1), accent_color, 4)
                cv2.line(annotated, (x2, y1), (x2, y1 + corner_len), accent_color, 4)
                # Bottom-left
                cv2.line(annotated, (x1, y2), (x1 + corner_len, y2), accent_color, 4)
                cv2.line(annotated, (x1, y2), (x1, y2 - corner_len), accent_color, 4)
                # Bottom-right
                cv2.line(annotated, (x2, y2), (x2 - corner_len, y2), accent_color, 4)
                cv2.line(annotated, (x2, y2), (x2, y2 - corner_len), accent_color, 4)

            # Label badge
            (tw, th), baseline = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
            badge_y1 = max(0, y1 - th - 10)
            badge_y2 = y1
            cv2.rectangle(annotated, (x1, badge_y1), (x1 + tw + 10, badge_y2), box_color, -1)
            cv2.putText(
                annotated,
                label_text,
                (x1 + 5, badge_y2 - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 0, 0) if not is_animal else (255, 255, 255),
                1,
                cv2.LINE_AA
            )

        # 2. Top Header HUD Bar
        header_height = 45
        overlay = annotated.copy()
        cv2.rectangle(overlay, (0, 0), (w, header_height), self.COLOR_HUD_BG, -1)
        cv2.addWeighted(overlay, 0.75, annotated, 0.25, 0, annotated)

        # Title
        cv2.putText(
            annotated,
            "SMART ANIMAL DETERRENCE | OBJECT DETECTION",
            (14, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
            cv2.LINE_AA
        )

        # System Metrics (FPS & Device & Camera)
        cam_info = f" | {source_label}" if source_label else ""
        metrics_text = f"FPS: {self.fps:.1f}{cam_info} | {self.device.upper()} | Objs: {len(detections)}"
        (mw, _), _ = cv2.getTextSize(metrics_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.putText(
            annotated,
            metrics_text,
            (w - mw - 14, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 220, 255),
            1,
            cv2.LINE_AA
        )

        # 3. Status Alert Banner (Just below header)
        is_deterrent_active = self.deterrent_active or manual_deterrent_test
        status_bar_h = 32
        status_overlay = annotated.copy()

        if is_deterrent_active:
            # Flashing or prominent red/orange alert
            banner_color = self.COLOR_ALERT_BG
            status_text = "WARNING: ANIMAL DETECTED - DETERRENT TRIGGERED [ULTRASONIC & STROBE ON]"
            if manual_deterrent_test:
                status_text += " (MANUAL TEST MODE)"
            text_color = (255, 255, 255)
        else:
            banner_color = self.COLOR_SECURE_BG
            status_text = "ZONE STATUS: MONITORING ACTIVE - NO INTRUSION"
            text_color = (220, 255, 220)

        cv2.rectangle(status_overlay, (0, header_height), (w, header_height + status_bar_h), banner_color, -1)
        cv2.addWeighted(status_overlay, 0.85, annotated, 0.15, 0, annotated)

        cv2.putText(
            annotated,
            status_text,
            (15, header_height + 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            text_color,
            2 if is_deterrent_active else 1,
            cv2.LINE_AA
        )

        # 4. Bottom Controls / Navigation Bar
        footer_height = 30
        footer_overlay = annotated.copy()
        cv2.rectangle(footer_overlay, (0, h - footer_height), (w, h), (15, 15, 15), -1)
        cv2.addWeighted(footer_overlay, 0.8, annotated, 0.2, 0, annotated)

        mode_str = "ANIMALS ONLY" if filter_animals_only else "ALL OBJECTS"
        footer_text = f"[Q] Quit | [C] Switch Cam | [0-3] Cam # | [A] Filter: {mode_str} | [S] Snap | [D] Test"
        cv2.putText(
            annotated,
            footer_text,
            (15, h - 9),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (180, 180, 180),
            1,
            cv2.LINE_AA
        )

        return annotated
