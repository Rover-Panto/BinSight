# Three-bin ESP32 wiring reference

This is a low-voltage prototype reference, not a civil/structural installation drawing.

## Chosen competition-prototype parts

- 1 x ESP32 DevKit V1.
- 3 x JSN-SR04T waterproof ultrasonic modules (HC-SR04 is acceptable for an indoor tabletop demo).
- 3 x FSR 402 analogue force/pressure pads, each used in a 10 kOhm voltage divider under a small bin platform.
- 1 x Raspberry Pi 4 or 5 with Raspberry Pi OS, Mosquitto MQTT broker, and the BinSight gateway.
- Regulated 5 V / 2 A supply, common ground, breadboard/terminal blocks, and three ECHO voltage dividers or level shifters.

The FSR pads are only for the scaled competition prototype. A full-size underground installation needs manufacturer-approved industrial load cells or hydraulic pressure transducers rated for the complete container and structure.

| Bin | Ultrasonic TRIG | Ultrasonic ECHO | Pressure analogue |
|---|---:|---:|---:|
| 1 | GPIO16 | GPIO17 | GPIO32 |
| 2 | GPIO18 | GPIO19 | GPIO33 |
| 3 | GPIO25 | GPIO26 | GPIO34 |

- GPIO34 is input-only, which is suitable for the third analogue channel.
- A 5 V ultrasonic ECHO output must pass through a correctly sized divider or level shifter before reaching the ESP32.
- Pressure/force signal conditioning must output 0–3.3 V and share a defined ground reference.
- Use fused power, waterproof connectors, surge/ESD protection, strain relief, and an IP-rated ventilated enclosure.
- Keep ultrasonic cabling away from switching power and crane/vehicle wiring.
- Install each ultrasonic sensor above the waste surface with a clear cone and no chute obstruction.
- Do not place an ESP32, ordinary sensor, or unapproved battery in a potentially hazardous gas zone without an appropriate safety assessment.
