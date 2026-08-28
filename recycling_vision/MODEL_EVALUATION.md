# Recycling model evaluation record

This record must be completed from a held-out test set before the model is used for station acceptance. Do not replace the placeholders with estimates.

- Candidate laptop-training artifact: `artifacts/yolo11n_recycling-8_best.pt`
- Candidate SHA-256: `6A3B1863CCC9663253D2614CE353626F21C9A95D0C3C6003B3CEE83B0FC4232F`
- Training run: `yolo11n_recycling-8`, 160 epochs, 416px, batch 20, device `0`; trained 17 August 2026
- Validation summary at epoch 160: precision 0.90755, recall 0.87728, mAP50 0.92160, mAP50-95 0.70211
- Dataset name/licence: **TODO — record source and licence**
- Dataset split and image count: **TODO**
- Training commit and Ultralytics version: **TODO**
- Class order: `plastic`, `metal`, `glass`, `paper`, `other`
- Image size / epochs / device: **TODO**
- Acceptance threshold: **TODO — choose from held-out results; policy default is 0.70**
- Per-class precision and recall: **TODO**
- Confusion matrix: **TODO**
- Failure examples under hopper lighting: **TODO**
- Export command and tool versions: **TODO**
- Grove artifact filename and SHA-256: **TODO**
- Grove Vision AI V2 test firmware/library and SSCMA transport/pins: **TODO**

The laptop webcam overlay is not evidence of Grove deployment or container eligibility. The main server remains the source of the final accepted/rejected decision.

This `.pt` file is supplied for reproducibility of the laptop prototype only. It is not an approved deployment model: it has no completed dataset licence/provenance record, per-class held-out evaluation, or Grove Vision AI V2 `*_int8_vela.tflite` export/flash evidence.
