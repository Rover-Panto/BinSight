"""Train YOLO on an already annotated recycling dataset."""

from __future__ import annotations

import argparse
from pathlib import Path

from ultralytics import YOLO


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a five-class recycling YOLO model.")
    parser.add_argument("--data", default="recycling_data.yaml", help="Dataset YAML file.")
    parser.add_argument(
        "--model",
        default="weights/yolo11n.pt",
        help="Base YOLO weights path (default: weights/yolo11n.pt).",
    )
    parser.add_argument("--epochs", type=int, default=160, help="Training epochs (default: 160).")
    parser.add_argument("--imgsz", type=int, default=416, help="Image size (default: 416).")
    parser.add_argument("--batch", type=int, default=20, help="Batch size; -1 auto-selects it.")
    parser.add_argument("--device", default='0', help="GPU ID, 'cpu', or omit for automatic selection.")
    parser.add_argument("--project", default="runs/recycling", help="Folder for training results.")
    parser.add_argument("--name", default="yolo11n_recycling", help="Name for this training run.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_file = Path(args.data)
    if not data_file.is_file():
        raise FileNotFoundError(f"Dataset YAML not found: {data_file.resolve()}")

    model_path = Path(args.model)
    # Keep the first pretrained-weight download inside this writable project folder.
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model = YOLO(str(model_path))  # Downloads pretrained weights on the first run.
    model.train(
        data=str(data_file),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        project=args.project,
        name=args.name,
        pretrained=True,
        plots=True,
    )


if __name__ == "__main__":
    main()
