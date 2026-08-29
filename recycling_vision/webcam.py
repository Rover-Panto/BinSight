"""Run a five-class recycling YOLO model on a webcam.

Expected model classes: plastic, metal, glass, paper, other.
Press Q or Esc while the video window is selected to exit.
"""

from __future__ import annotations

import argparse

import cv2
from ultralytics import YOLO

try:
    from recycling_vision.gating import ACCEPTED_CLASSES, ConsecutiveDetectionGate, GateResult
except ModuleNotFoundError:  # Supports `python recycling_vision/webcam.py` from the repository root.
    from gating import ACCEPTED_CLASSES, ConsecutiveDetectionGate, GateResult


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run recycling detection on a webcam.")
    parser.add_argument("--model", default="runs/recycling/yolo11n_recycling/weights/best.pt", help="Path to trained best.pt weights.")
    parser.add_argument("--camera", type=int, default=0, help="Webcam index (default: 0).")
    parser.add_argument(
        "--detection-confidence",
        type=float,
        default=0.20,
        help="Lowest detection score to draw (default: 0.20).",
    )
    parser.add_argument(
        "--required-consecutive",
        type=int,
        default=3,
        help="Matching eligible detections required for the local acceptance cue (default: 3).",
    )
    parser.add_argument(
        "--other-threshold",
        type=float,
        default=0.70,
        help=(
            "Scores below this for plastic, metal, or glass are shown as OTHER "
            "(default: 0.70)."
        ),
    )
    return parser.parse_args()


def label_for_detection(class_name: str, confidence: float, other_threshold: float) -> str:
    """Apply the project's confidence-based fallback to the OTHER category."""
    if class_name.lower() in ACCEPTED_CLASSES and confidence < other_threshold:
        return "other"
    return class_name.lower()


def draw_detection(frame, box, label: str, confidence: float) -> None:
    x1, y1, x2, y2 = (int(value) for value in box.xyxy[0].tolist())
    color = (0, 200, 0) if label != "other" else (0, 165, 255)  # green / orange (BGR)
    text = f"{label.upper()} {confidence:.0%}"
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    cv2.putText(frame, text, (x1, max(y1 - 8, 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)


def draw_gate_status(frame, result: GateResult, required_consecutive: int) -> None:
    if result.status == "accepted":
        text, color = f"ACCEPTED: {result.label.upper()}", (0, 200, 0)
    elif result.status == "confirming":
        text, color = f"CONFIRMING {result.label.upper()} {result.consecutive}/{required_consecutive}", (0, 255, 255)
    elif result.status == "rejected":
        text, color = f"REJECTED: {result.label.upper()}", (0, 165, 255)
    else:
        text, color = "WAITING FOR ONE ITEM", (220, 220, 220)
    cv2.putText(frame, text, (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2)


def main() -> None:
    args = parse_args()
    if not 0 <= args.detection_confidence <= args.other_threshold <= 1:
        raise ValueError("Require 0 <= --detection-confidence <= --other-threshold <= 1.")
    gate = ConsecutiveDetectionGate(args.required_consecutive)

    model = YOLO(args.model)
    camera = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
    if not camera.isOpened():
        raise RuntimeError(f"Could not open camera {args.camera}; try --camera 1.")

    print("Recycling detection started. Press Q or Esc to quit.")
    try:
        while True:
            ok, frame = camera.read()
            if not ok:
                break

            result = model(frame, conf=args.detection_confidence, verbose=False)[0]
            labels: list[str] = []
            for box in result.boxes:
                class_id = int(box.cls[0])
                confidence = float(box.conf[0])
                class_name = result.names[class_id]
                label = label_for_detection(class_name, confidence, args.other_threshold)
                labels.append(label)
                draw_detection(frame, box, label, confidence)

            observed_label = labels[0] if len(labels) == 1 and labels[0] in ACCEPTED_CLASSES else None
            draw_gate_status(frame, gate.observe(observed_label), args.required_consecutive)

            cv2.imshow("YOLO Recycling Detection", frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break
    finally:
        camera.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
