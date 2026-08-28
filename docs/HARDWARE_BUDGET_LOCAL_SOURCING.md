# BinSight Hardware Budget and Local Sourcing

Prices checked: 27 August 2026. Quantities revised: 28 August 2026.

This is the working purchase baseline for the competition prototype. Prices and stock can change, so save the checkout pages and receipts when ordering.

**Architecture rule:** The USD150 demonstrator has three physical bins: one general-waste and two recycling bins. One Teensy measures all three fill levels. One shared ESP32-C3 carries both Teensy fill telemetry and Grove recognition metadata, with separate queues and server contracts. See [SHARED_ESP32_GATEWAY.md](SHARED_ESP32_GATEWAY.md). This revision changes quantities, not the dated supplier quotes.

## Budget basis

- Competition ceiling: USD150.
- The 27 August 2026 opening USD/MYR quote was RM4.0235 per USD, making the working ceiling **RM603.53**. Use RM580 as the internal purchasing limit so exchange movement does not create a late overrun.
- Count the existing Teensy 4.1 at its full local replacement value of **RM159.00**. Do not remove it from the competition total because it is already owned.
- Show the existing laptop separately as borrowed/existing equipment at RM0 cash cost. It is the prototype server, dashboard and route engine; the selected Grove V2 performs recycling inference locally.

Exchange reference: [Bernama, 27 August 2026](https://www.bernama.com/en/market/news.php?id=2599450). Competition requirement: `Degree level question paper-SEAR 1.pdf`, lines 137-140 of extracted text.

## Agreed prototype topology

```text
One general-waste model bin + two recycling model bins
  -> three independent fill channels
  -> one Teensy 4.1 running scheduled sensing and health tasks
  -> shared ESP32-C3 UART input and fill queue
  -> laptop ingestion, prediction and route optimisation

Shared recycling-return demonstration path
  -> OV5647 CSI camera
  -> Grove Vision AI V2 image processing and local classification
  -> same ESP32-C3, using I2C input and a recognition queue
  -> main server decision -> accept/reject indication and servo feedback
```

One Teensy may control the three 1:20 bins because the brief requires three instrumented bins, not three separate controllers. Firmware must still produce a distinct `bin_id`, `bin_type`, calibration and health state for each channel. The current hardware PR represents one bin per firmware instance, so three-channel multiplexing is implementation work and must be tested before demonstration.

The Grove V2 owns recycling image preprocessing and model inference. The single C3 is the Wi-Fi gateway for all three Teensy fill channels and the compact Grove class/confidence results. It controls return-station feedback only after a matching server decision. The recycling model has not yet been supplied, so selection of Grove V2 does not prove model compatibility or accuracy. The model must pass the deployment gates below before the hardware path is called complete.

The budget includes one shared Grove/camera return point for the two recycling-bin demonstrators. If each recycling bin needs its own simultaneous insertion point, a second Grove/camera and its gateway connectivity require a new budget check. Do not present the one-module demonstrator as two independently operating vision stations.

## Recommended local bill of materials

| Item | Seller and live listing | Qty | Unit (RM) | Line total (RM) | Reason |
| --- | --- | ---: | ---: | ---: | --- |
| Teensy 4.1 | [Cytron](https://my.cytron.io/p-teensy-4p1-controller-board) | 1 | 159.00 | 159.00 | General-waste sensing and task scheduling; counted even though owned |
| 1x40 male header | [Cytron](https://my.cytron.io/p-straight-pin-header-male-1x40-ways) | 2 | 0.65 | 1.30 | Teensy and loose-header board assembly |
| USB Micro-B data cable | [Cytron Teensy accessory](https://my.cytron.io/p-teensy-4p1-controller-board) | 1 | 4.00 | 4.00 | Teensy programming |
| SR04P 3V-5.5V ultrasonic sensor | [Cytron](https://my.cytron.io/c-sensor/p-3v-5.5v-ultrasonic-ranging-module) | 3 | 4.90 | 14.70 | One independent fill channel for each physical bin; no 5V echo divider required |
| 1 kg load cell with HX711 | [Cytron](https://my.cytron.io/ampp-1kg-load-cell-with-hx711-amplifier) | 3 | 14.90 | 44.70 | Retains the demonstrator's weight-monitoring scope; remove only if that scope is revised |
| SG90 180-degree servo | [Cytron](https://my.cytron.io/p-sg90-micro-servo) | 1 | 6.50 | 6.50 | Recycling accept/reject chute feedback |
| 830-hole breadboard | [Cytron](https://my.cytron.io/ampp-breadboard-16.5x5.5cm-830-holes) | 1 | 3.90 | 3.90 | Low-voltage prototype distribution and testing |
| 40-way 20 cm jumper set | [Cytron](https://my.cytron.io/c-jumper-wire/p-40-way-20cm-dupont-jumper-wire) | 2 | 2.50 | 5.00 | Select one male-male and one male-female set |
| ESP32-C3 Super Mini | [MakerHub](https://makerhub.my/shop/microcontroller/esp32-super-mini-ultra-small-size-esp32-c3-risc-v-low-power-consumption/) | 1 | 17.95 | 17.95 | Shared Teensy UART/Grove I2C gateway, Wi-Fi and station feedback; no model inference |
| Grove AI Vision Module V2 | [Cytron](https://my.cytron.io/p-grove-ai-vision-module-v2) | 1 | 95.00 | 95.00 | Recycling image processing and local classifier inference |
| OV5647 5MP CSI camera | [Cytron](https://my.cytron.io/p-5mp-camera-board-for-raspberry-pi) | 1 | 29.00 | 29.00 | Image input for the Grove V2; close-focus suitability remains a purchase gate |
| Grove-to-female cable | [Cytron](https://my.cytron.io/p-grove-4-pin-buckled-to-female-cable) | 1 | 1.50 | 1.50 | Grove inference-result connection to the recycling C3 |
| 5V 3A DC adapter | [MakerHub](https://makerhub.my/shop/electrical/power-supply-adapter-dc-universal-ac-to-dc-converter-psu-5v2a-5v3a-9v2a-12v2a/) | 1 | 12.95 | 12.95 | Select the 5V3A variant; keeps exposed prototype voltage below 12V DC |
| 5.5x2.1 mm female connector | [MakerHub](https://makerhub.my/shop/electrical/5-5x2-1mm-dc-power-male-connector-plug-jack-adapter-for-arduino-diy-electronics-projects/) | 1 | 1.20 | 1.20 | Select the female variant for the 5V distribution input |
| USB-A to USB-C data cable, 0.5 m | [MakerHub](https://makerhub.my/shop/) | 1 | 4.90 | 4.90 | Programs the shared C3 and Grove V2 sequentially |
| 5 mm status LEDs | [MakerHub shop](https://makerhub.my/shop/) | 9 | 0.10 | 0.90 | Three visible fill/health states for each of the three bins |
| 400-piece resistor pack | [MakerHub](https://makerhub.my/shop/electrical/400-pcs-1-4w-resistor-pack-resistor-kit-20-common-value-with-20-each/) | 1 | 7.95 | 7.95 | LED current limiting and spare prototype values |
| Momentary test/control button | [MakerHub shop](https://makerhub.my/shop/) | 1 | 4.90 | 4.90 | Demonstration and calibration input |
| **Electronics subtotal** |  |  |  | **415.35** |  |
| Selangor delivery reserve | Cytron plus MakerHub | 1 | 15.00 | 15.00 | Cytron is free above RM9.90 in Peninsular Malaysia; reserve is for MakerHub checkout |
| Recycled-board enclosure and fixings reserve | Local/reused materials | 1 | 40.00 | 40.00 | Record receipts or document reused material provenance |
| Ten-percent contingency |  |  |  | 47.04 | Applied after delivery and fabrication reserves |
| **Planned competition total** |  |  |  | **517.39** | Includes the owned Teensy |

**Headroom against RM603.53: RM86.14.** The plan remains RM62.61 below the internal RM580 purchasing limit. If the Teensy is the only listed part already owned, the cash-to-buy estimate is RM358.39, while the competition total remains RM517.39. Sharing the C3 removes RM17.95 in electronics and RM19.74 from the total including contingency.

## Delivery plan for Selangor

1. **Cytron basket: RM364.60.** Cytron states free Peninsular Malaysia shipping for orders above RM9.90 and an estimated two to three working days to major West Malaysian cities: [delivery policy](https://my.cytron.io/delivery-information).
2. **MakerHub basket: RM50.75.** At the price check, the selected board and parts were listed as ready stock in Sungai Besi, Kuala Lumpur, with dispatch within 24 hours and self-pickup or same-day Klang Valley delivery available. Use ordinary courier or pickup; only use same-day delivery if its checkout price stays within the RM15 reserve.
3. The exact MakerHub charge cannot be verified without the final Selangor postcode and checkout session. If it exceeds RM15, use pickup or move compatible accessories to the free-shipping Cytron basket before paying.

## Selected recycling stack: Grove Vision AI Module V2

The Grove Vision AI Module V2 replaces the ESP32-S3 camera board for the recycling-return station. It performs local inference but needs a separate CSI camera and a Wi-Fi-capable host to send results to the BinSight server. The architecture is selected; model conversion, measured accuracy and close-range optical testing remain release gates before the path may be described as working.

| Replacement component | Local listing | Qty | Line total (RM) | Status at check |
| --- | --- | ---: | ---: | --- |
| Grove AI Vision Module V2 | [Cytron](https://my.cytron.io/p-grove-ai-vision-module-v2) | 1 | 95.00 | RM95; two units shown available |
| OV5647 5MP CSI camera | [Cytron](https://my.cytron.io/p-5mp-camera-board-for-raspberry-pi) | 1 | 29.00 | RM29; local stock shown |
| Grove-to-female cable | [Cytron](https://my.cytron.io/p-grove-4-pin-buckled-to-female-cable) | 1 | 1.50 | RM1.50; local stock shown |
| **Incremental Grove recycling-stack subtotal** |  |  | **125.50** | Module, camera and cable; shared C3 counted once in the main bill |

These lines are included in the selected bill of materials above. The planned competition total is **RM517.39**, leaving **RM86.14** below the RM603.53 converted ceiling and **RM62.61** below the internal RM580 purchasing limit.

### Connectivity

```text
OV5647 CSI camera
  -> Grove Vision AI V2: image processing and local classification
  -> I2C at address 0x62, subject to selected firmware verification
  -> shared ESP32-C3: recognition queue, server Wi-Fi and servo command
  -> authenticated main-owned recycling endpoint
```

The Grove module has USB-C, I2C, UART, SPI and CSI, but no built-in Wi-Fi radio. Grove runs the model. The shared C3 receives its compact class/confidence/timing outputs over I2C while receiving Teensy fill frames over hardware UART. Teensy remains the fill-sensor controller. Do not deploy or duplicate the recycling classifier on the C3.

Seeed's documented network configuration adds a XIAO ESP32-C3; the budget substitutes the locally stocked ESP32-C3 Super Mini and requires its wiring and SSCMA protocol compatibility to be tested. The official SSCMA documentation lists ESP32-C3 support over I2C and hardware UART. Select I2C for Grove metadata and reserve hardware UART for Teensy. The citizen path sends no image data.

Power the vision module from the verified 5V rail and use 3.3V signalling with the C3 and a common ground. Do not power the camera module or Wi-Fi radio from a microcontroller's 3.3V pin. Drive the SG90 signal from the C3 while powering the servo from the shared 5V rail. Measure the assembled system during inference, Wi-Fi transmission and servo movement; the module's published power figure does not prove that the complete prototype remains below 10W continuous.

### Model and optical gates

- Do not purchase this replacement solely because a model is labelled YOLO. The uploaded model must be exported and tested as fully integer `int8_vela.tflite` for the Grove V2. Seeed recommends square inputs and no more than 240x240; its worked deployment uses 192x192.
- Re-evaluate class accuracy, rejection thresholds, latency and confusion after integer quantisation. A successful model upload is not an acceptance test.
- The listed OV5647 camera is specified for focus from approximately one metre to infinity, while a return chute is likely much closer. Test cans and bottles at the actual mounting distance before accepting this camera. Use a verified close-focus or adjustable-focus OV5647 alternative if labels and container features are blurred.
- Keep the Grove result, C3 transport result and server storage acknowledgement as separate states. A local classification does not prove that the return was logged or paid.
- If the model cannot be converted, uses unsupported operators or loses unacceptable accuracy, retain the ESP32-S3 capture path with laptop inference rather than weakening the classifier claim.

## Purchase gates

- Buy only **one** Teensy and **one shared ESP32-C3** for the USD150 demonstrator. Do not count a second C3 for recognition.
- Build one gateway firmware target containing independent fill and recognition modules. Test simultaneous UART, I2C, Wi-Fi and servo operation; a shared power failure or C3 reset interrupts both streams.
- Do not buy an ESP32-S3 camera in addition to the selected Grove stack. Retain that architecture only as a documented fallback if the Grove model gates fail.
- Keep submission wording aligned with the budgeted demonstrator: one Teensy services one general-waste and two recycling bins as independently identified channels.
- Confirm the Grove V2 model conversion, close-range image and result relay before describing the recycling classifier as implemented.
- Load-test the 5V rail during Wi-Fi transmission and servo movement. The 5V3A label is a supply rating, not proof that the assembled prototype is stable or below the competition's 10W continuous target.
- Keep receipts, checkout screenshots, reused-material declarations and the final measured-power record with the submission evidence.

## Rejected budget variants

- **Three Teensy boards:** two unnecessary extra Teensy 4.1 boards add RM318.00 in parts before contingency. The one-controller demonstrator is the budgeted design.
- **ESP-01 as the normal-bin Wi-Fi module:** Cytron lists it at RM6.30, but the listing says it lacks SSL support and needs a separate 3.3V regulator capable of current spikes. The RM11.65 saving is not worth weakening authenticated delivery or power reliability.
- **ESP32-S3 camera plus laptop inference:** cheaper and easier to integrate, but it does not meet the selected goal of local recycling inference. Retain it only as a fallback if the model cannot be converted for Grove V2 or loses unacceptable accuracy after quantisation.
