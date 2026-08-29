# YOLO recycling detector

This contribution adds a webcam-based YOLO object detector and a training entry point for BinSight's recycling workflow.

## Scope

The model has five output classes:

| ID | Class | Meaning |
| --- | --- | --- |
| 0 | `plastic` | Plastic containers and objects |
| 1 | `metal` | Metal containers and objects |
| 2 | `glass` | Glass containers and objects |
| 3 | `paper` | Paper and cardboard (always rejected by the return policy) |
| 4 | `other` | Relevant trash that is not one of the four material labels |

Only `plastic`, `metal`, and `glass` are eligible for a return. The class map does not prove beverage-container eligibility; that requires separate dataset evidence.

The repository contains code and the dataset configuration only. Trained weights and image datasets should remain outside Git because they are large generated artifacts.

## Training

Install the pinned Python dependencies from `recycling_vision/requirements.txt`, then run from the repository root:

```powershell
python recycling_vision/train.py --data recycling_vision/recycling_data.yaml --epochs 160 --device 0
```

`--device 0` selects the first CUDA GPU. Use `--device cpu` when CUDA is unavailable. The default output is `runs/recycling/yolo11n_recycling/weights/best.pt`.

The dataset must use YOLO detection labels (`class_id x_center y_center width height`, all coordinates normalised to 0–1) and match the class order in `recycling_data.yaml`. Put the dataset under `dataset/images/{train,val,test}` and `dataset/labels/{train,val,test}`, or update the YAML path.

## Webcam inference

```powershell
python recycling_vision/webcam.py --model runs/recycling/yolo11n_recycling/weights/best.pt --camera 0
```

Press `Q` or `Esc` while the window is focused to stop. `--camera` selects a webcam index; this supports a laptop camera now and a Groove AI 2 camera later if it is exposed as a normal camera device.

## OTHER and confidence policy

The development webcam overlay is a debugging aid only. Predictions for `plastic`, `metal`, or `glass` below `--other-threshold` (70% by default) are displayed as `OTHER`; paper and other are rejected by the server policy. Its `--required-consecutive 3` option gives a visible local `CONFIRMING 1/3` to `ACCEPTED` cue and re-arms only after no item is detected. Final station acceptance must still be computed by the main server after its stability gate.

This threshold is a routing policy, not a calibrated probability. It should be evaluated on held-out images and adjusted for the cost of incorrectly sorting an item. An object that YOLO does not detect at all cannot be relabelled after inference, so the training set should include representative `other` examples such as organic waste, textiles, electronics, and contaminated or mixed items.

## Verification

Before opening a PR, verify the command-line interfaces without starting a long training run:

```powershell
python recycling_vision/train.py --help
python recycling_vision/webcam.py --help
```

For a real test, use a small epoch count and confirm that `best.pt` is created, then run webcam inference against that weight file.

## Hardware and deployment note

The committed `recycling_vision/artifacts/yolo11n_recycling-8_best.pt` file is trained for the laptop Python/OpenCV prototype only. It is **not for Grove Vision AI V2** and must not be flashed to the camera module. Grove Vision AI V2 deployment requires a separately produced, fully integer quantized Vela artifact (`*_int8_vela.tflite`) with its checksum and class order recorded. The export artifact is generated output and is ignored by Git until the team approves a licensed release artifact.

The reproducible export sequence is:

```powershell
python -m ultralytics export model=runs/recycling/yolo11n_recycling/weights/best.pt format=tflite int8=True data=recycling_vision/recycling_data.yaml
vela --accelerator ethos-u --optimise Performance runs/recycling/yolo11n_recycling/weights/best_saved_model/yolo11n_recycling_full_integer_quant.tflite
Get-FileHash runs/recycling/yolo11n_recycling/weights/best_saved_model/*int8_vela.tflite -Algorithm SHA256
```

The exact Vela output filename depends on the Ultralytics export version. Record the final filename, SHA-256, export versions, and class map in the evaluation record. Do not describe a model as Grove-compatible until this artifact has been flashed and exercised on the target module.

## ESP32-C3 relay contract

`recycling_vision/relay.py` defines the image-free metadata payload for the dedicated recycling relay. It contains the schema version, event/session identifiers, station/device/boot identity, sequence, material, confidence, object count, timing, model version, and simulation flag. It contains no JPEG, base64 image, video, webcam URL, or stream field. The server—not the relay—owns confidence/stability, idempotency, session binding, and the accepted/rejected decision.

The physical target is one shared ESP32-C3. PR2 owns the common gateway, Teensy UART/fill queue and Wi-Fi services; PR3 supplies the Grove SSCMA I2C recognition module, recognition queue and station-feedback hooks. Recognition and fill use separate queues and sequence spaces. The relay transport (SSCMA I2C pins, firmware and library versions) must be recorded with physical deployment evidence before this PR is hardware-complete.

## Evidence required before merge

Record the trained model provenance, dataset licence, class order, held-out per-class precision/recall, confusion matrix, confidence threshold, failure examples, Vela export command, artifact checksum, and physical Grove/ESP32-C3 test results. This repository intentionally does not claim those results without a completed run.
