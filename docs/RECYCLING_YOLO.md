# YOLO recycling detector

This contribution adds a webcam-based YOLO object detector and a training entry point for BinSight's recycling workflow.

## Scope

The model has five classes:

| ID | Class | Meaning |
| --- | --- | --- |
| 0 | `plastic` | Plastic containers and objects |
| 1 | `metal` | Metal containers and objects |
| 2 | `glass` | Glass containers and objects |
| 3 | `paper` | Paper and cardboard |
| 4 | `other` | Relevant trash that is not one of the four recyclable materials |

The repository contains code and the dataset configuration only. Trained weights and image datasets should remain outside Git because they are large generated artifacts.

## Training

Install the Python dependencies from `requirements.txt`, then run from the directory containing the scripts:

```powershell
python train_recycling.py --data recycling_data.yaml --epochs 160 --device 0
```

`--device 0` selects the first CUDA GPU. Use `--device cpu` when CUDA is unavailable. The default output is `runs/recycling/yolo11n_recycling/weights/best.pt`.

The dataset must use YOLO detection labels (`class_id x_center y_center width height`, all coordinates normalised to 0–1) and match the class order in `recycling_data.yaml`. Put the dataset under `dataset/images/{train,val,test}` and `dataset/labels/{train,val,test}`, or update the YAML path.

## Webcam inference

```powershell
python webcam_recycling.py --model runs/recycling/yolo11n_recycling/weights/best.pt --camera 0
```

Press `Q` or `Esc` while the window is focused to stop. `--camera` selects a webcam index; this supports a laptop camera now and a Groove AI 2 camera later if it is exposed as a normal camera device.

## OTHER and confidence policy

The detector draws predictions at or above `--detection-confidence` (20% by default). Predictions for `plastic`, `metal`, `glass`, or `paper` below `--other-threshold` (70% by default) are displayed as `OTHER`. A direct `other` prediction is always displayed as `OTHER`.

This threshold is a routing policy, not a calibrated probability. It should be evaluated on held-out images and adjusted for the cost of incorrectly sorting an item. An object that YOLO does not detect at all cannot be relabelled after inference, so the training set should include representative `other` examples such as organic waste, textiles, electronics, and contaminated or mixed items.

## Verification

Before opening a PR, verify the command-line interfaces without starting a long training run:

```powershell
python train_recycling.py --help
python webcam_recycling.py --help
```

For a real test, use a small epoch count and confirm that `best.pt` is created, then run webcam inference against that weight file.

## Hardware and deployment note

The current implementation uses Ultralytics YOLO through Python and OpenCV. It is intentionally camera-backend agnostic: any device that appears as a DirectShow/OpenCV camera index can be selected with `--camera`. Moving inference to the Groove AI 2 requires confirming its supported runtime and camera interface; that hardware integration is separate from this laptop prototype.

