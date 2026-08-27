# BinSight Hardware Budget and Local Sourcing

Checked: 27 August 2026

This is the working purchase baseline for the competition prototype. Prices and stock can change, so save the checkout pages and receipts when ordering.

## Budget basis

- Competition ceiling: USD150.
- The 27 August 2026 opening USD/MYR quote was RM4.0235 per USD, making the working ceiling **RM603.53**. Use RM580 as the internal purchasing limit so exchange movement does not create a late overrun.
- Count the existing Teensy 4.1 at its full local replacement value of **RM159.00**. Do not remove it from the competition total because it is already owned.
- Show the existing laptop separately as borrowed/existing equipment at RM0 cash cost. It is the prototype server, dashboard, route engine and initial classifier host.

Exchange reference: [Bernama, 27 August 2026](https://www.bernama.com/en/market/news.php?id=2599450). Competition requirement: `Degree level question paper-SEAR 1.pdf`, lines 137-140 of extracted text.

## Agreed prototype topology

```text
Three general-waste model bins
  -> three fill channels
  -> one Teensy 4.1 running scheduled sensing and health tasks
  -> one ESP32-C3 UART/Wi-Fi communications module
  -> laptop ingestion, prediction and route optimisation

One recycling-return model station
  -> ESP32-S3 camera board
  -> image capture and Wi-Fi upload
  -> laptop classification until the uploaded model is profiled
  -> accept/reject indication and servo feedback
```

One Teensy may control the three 1:20 general-waste bins because the brief requires three instrumented bins, not three separate controllers. Firmware must still produce a distinct `bin_id`, calibration and health state for each channel. The current hardware PR represents one bin per firmware instance, so three-bin multiplexing is future implementation work and must be tested before demonstration.

The recycling model has not been supplied yet. The ESP32-S3 purchase therefore provides camera capture, buffering and wireless delivery, but it is **not evidence that the final model runs on the board**. Keep the team-trained classifier on the laptop first. After the model is uploaded, measure its input size, operations, memory and latency before considering a quantised on-device classifier. Do not describe a YOLO model as running on the ESP32-S3 without a measured build.

## Recommended local bill of materials

| Item | Seller and live listing | Qty | Unit (RM) | Line total (RM) | Reason |
| --- | --- | ---: | ---: | ---: | --- |
| Teensy 4.1 | [Cytron](https://my.cytron.io/p-teensy-4p1-controller-board) | 1 | 159.00 | 159.00 | General-waste sensing and task scheduling; counted even though owned |
| 1x40 male header | [Cytron](https://my.cytron.io/p-straight-pin-header-male-1x40-ways) | 2 | 0.65 | 1.30 | Teensy and loose-header board assembly |
| USB Micro-B data cable | [Cytron Teensy accessory](https://my.cytron.io/p-teensy-4p1-controller-board) | 1 | 4.00 | 4.00 | Teensy programming |
| SR04P 3V-5.5V ultrasonic sensor | [Cytron](https://my.cytron.io/c-sensor/p-3v-5.5v-ultrasonic-ranging-module) | 3 | 4.90 | 14.70 | One fill channel per general-waste bin; no 5V echo divider required |
| 1 kg load cell with HX711 | [Cytron](https://my.cytron.io/ampp-1kg-load-cell-with-hx711-amplifier) | 3 | 14.90 | 44.70 | Retains the proposal's weight-monitoring claim; remove only if the proposal is revised |
| SG90 180-degree servo | [Cytron](https://my.cytron.io/p-sg90-micro-servo) | 1 | 6.50 | 6.50 | Recycling accept/reject chute feedback |
| 830-hole breadboard | [Cytron](https://my.cytron.io/ampp-breadboard-16.5x5.5cm-830-holes) | 1 | 3.90 | 3.90 | Low-voltage prototype distribution and testing |
| 40-way 20 cm jumper set | [Cytron](https://my.cytron.io/c-jumper-wire/p-40-way-20cm-dupont-jumper-wire) | 2 | 2.50 | 5.00 | Select one male-male and one male-female set |
| ESP32-C3 Super Mini | [MakerHub](https://makerhub.my/shop/microcontroller/esp32-super-mini-ultra-small-size-esp32-c3-risc-v-low-power-consumption/) | 1 | 17.95 | 17.95 | UART/Wi-Fi bridge for the Teensy; use acknowledgements and retry buffering |
| ESP32-S3 WROOM CAM with OV5640 | [MakerHub](https://makerhub.my/shop/devkit/esp32-s3-wroom-cam-development-board-ov5640-camera-module-wifi-bluetooth-dual-usb-c-iot-ai/) | 1 | 56.95 | 56.95 | Recycling camera, PSRAM, Wi-Fi and direct USB programming |
| 5V 3A DC adapter | [MakerHub](https://makerhub.my/shop/electrical/power-supply-adapter-dc-universal-ac-to-dc-converter-psu-5v2a-5v3a-9v2a-12v2a/) | 1 | 12.95 | 12.95 | Select the 5V3A variant; keeps exposed prototype voltage below 12V DC |
| 5.5x2.1 mm female connector | [MakerHub](https://makerhub.my/shop/electrical/5-5x2-1mm-dc-power-male-connector-plug-jack-adapter-for-arduino-diy-electronics-projects/) | 1 | 1.20 | 1.20 | Select the female variant for the 5V distribution input |
| USB-A to USB-C data cable, 0.5 m | [MakerHub S3 setup listing](https://makerhub.my/ms/panduan/esp32-s3-cam-stream-video-pertama/) | 1 | 4.90 | 4.90 | Programs the C3 and S3 sequentially |
| 5 mm status LEDs | [MakerHub shop](https://makerhub.my/shop/) | 9 | 0.10 | 0.90 | Three visible states for each general-waste bin |
| 400-piece resistor pack | [MakerHub](https://makerhub.my/shop/electrical/400-pcs-1-4w-resistor-pack-resistor-kit-20-common-value-with-20-each/) | 1 | 7.95 | 7.95 | LED current limiting and spare prototype values |
| Momentary test/control button | [MakerHub shop](https://makerhub.my/shop/) | 1 | 4.90 | 4.90 | Demonstration and calibration input |
| **Electronics subtotal** |  |  |  | **346.80** |  |
| Selangor delivery reserve | Cytron plus MakerHub | 1 | 15.00 | 15.00 | Cytron is free above RM9.90 in Peninsular Malaysia; reserve is for MakerHub checkout |
| Recycled-board enclosure and fixings reserve | Local/reused materials | 1 | 40.00 | 40.00 | Record receipts or document reused material provenance |
| Ten-percent contingency |  |  |  | 40.18 | Applied after delivery and fabrication reserves |
| **Planned competition total** |  |  |  | **441.98** | Includes the owned Teensy |

**Headroom against RM603.53: RM161.55.** If the Teensy is the only listed part already owned, the present cash-to-buy figure is RM282.98, while the competition total remains RM441.98.

## Delivery plan for Selangor

1. **Cytron basket: RM239.10.** Cytron states free Peninsular Malaysia shipping for orders above RM9.90 and an estimated two to three working days to major West Malaysian cities: [delivery policy](https://my.cytron.io/delivery-information).
2. **MakerHub basket: RM107.70.** The selected boards and parts are listed as ready stock in Sungai Besi, Kuala Lumpur, with dispatch within 24 hours and self-pickup or same-day Klang Valley delivery available. Use ordinary courier or pickup; only use same-day delivery if its checkout price stays within the RM15 reserve.
3. The exact MakerHub charge cannot be verified without the final Selangor postcode and checkout session. If it exceeds RM15, use pickup or move compatible accessories to the free-shipping Cytron basket before paying.

## Purchase gates

- Buy only **one** ESP32-C3 for the three-bin Teensy controller unless the physical layout later makes one shared UART/Wi-Fi bridge impractical.
- Buy only **one** ESP32-S3 camera board for the required recycling-return station. Each additional recycling camera station adds at least RM56.95 before enclosure and power distribution.
- Revise any final proposal sentence that says each normal bin has its own Teensy. The budgeted prototype has one Teensy servicing three independently identified scaled bins.
- Confirm the ESP32-S3 camera example works and can upload a labelled still image before integrating the unseen classifier.
- Load-test the 5V rail during Wi-Fi transmission and servo movement. The 5V3A label is a supply rating, not proof that the assembled prototype is stable or below the competition's 10W continuous target.
- Keep receipts, checkout screenshots, reused-material declarations and the final measured-power record with the submission evidence.

## Rejected budget variants

- **Three Teensy boards:** adding two more Teensy 4.1 boards raises the plan to RM759.98 before adding separate Wi-Fi modules, already RM156.45 over the converted ceiling.
- **ESP-01 as the normal-bin Wi-Fi module:** Cytron lists it at RM6.30, but the listing says it lacks SSL support and needs a separate 3.3V regulator capable of current spikes. The RM11.65 saving is not worth weakening authenticated delivery or power reliability.
- **Classic ESP32-CAM:** a local OV2640 option is cheaper, but the ESP32-S3 board provides direct USB, more memory and a cleaner path for profiling a future compact model. The classifier still remains on the laptop until measurements justify otherwise.
