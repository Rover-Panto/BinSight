# BinSight — Computer Setup & Circuit Wiring Guide (Windows)

This guide has two parts: getting all the software running on your Windows
laptop, and wiring the physical prototype. Do Part A first so you can flash
and test the firmware as soon as the circuit is wired in Part B.

You'll run **4 things at once** by the end: the cloud backend, the
dashboard, the serial bridge script, and the Teensy itself. Four separate
terminal windows, each left running, is the easiest way to manage that.

---

## Part A — Computer Setup

### A.1 Install Python

1. Download Python 3.11+ from https://www.python.org/downloads/windows/
2. Run the installer. **Check "Add python.exe to PATH"** on the first screen — easy to miss, and everything below depends on it.
3. Verify in PowerShell (Start menu → type `PowerShell` → Enter):
   ```powershell
   python --version
   ```
   Should print `Python 3.11.x` or newer.

### A.2 Install the Arduino IDE + Teensyduino

1. Download and install the **Arduino IDE** (2.x) from https://www.arduino.cc/en/software
2. Download and run **Teensyduino** from https://www.pjrc.com/teensy/teensyduino.html — this is PJRC's add-on that teaches the Arduino IDE how to program the Teensy 4.1. Point it at your Arduino IDE install when it asks.
3. Open the Arduino IDE, go to **Tools → Board**, and confirm a "Teensy" submenu now exists.

### A.3 Get the BinSight files onto your computer

1. Unzip the `BinSight_package.zip` you were sent somewhere easy to find, e.g. `C:\BinSight\`.
2. You should see four folders: `firmware`, `cloud_backend`, `dashboard`, `tools`, plus this guide and the `README.md`.

### A.4 Install the Arduino libraries

In the Arduino IDE: **Sketch → Include Library → Manage Libraries**, then search for and install each of these:

| Search term | Install |
|---|---|
| `Bounce2` | Bounce2 by Thomas O Fredericks |
| `ArduinoJson` | ArduinoJson by Benoit Blanchon (v6 or v7) |
| `Time` | Time by Michael Margolis / PaulStoffregen |

One library likely **won't** show up in the Library Manager — the FreeRTOS port for Teensy 4.x:

1. Go to https://github.com/tsandmann/freertos-teensy, click **Code → Download ZIP**.
2. In the Arduino IDE: **Sketch → Include Library → Add .ZIP Library...**, select the downloaded zip.
3. Restart the Arduino IDE.

### A.5 Set up the cloud backend

Open a PowerShell window:

```powershell
cd C:\BinSight\cloud_backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
notepad .env
```

In Notepad, set `BINSIGHT_API_KEY` to something you make up (e.g.
`binsight-demo-key-2026`) — you'll reuse this exact value in `tools\.env`
in step A.7. Leave `BINSIGHT_REQUIRE_HMAC=false`. Save and close.

> If PowerShell blocks the activation script with a "running scripts is
> disabled" error, run this once (as your normal user, not admin):
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then retry.

Start the backend (keep this PowerShell window open — this is terminal #1):

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Verify: open http://localhost:8000/docs in a browser. You should see the
interactive API docs. Try the `/health` endpoint — it should return
`{"status": "ok"}`.

### A.6 Set up the dashboard

Open a **second** PowerShell window (terminal #2):

```powershell
cd C:\BinSight\dashboard
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run streamlit_app.py
```

A browser tab should open at http://localhost:8501. It'll say "No
telemetry received yet" — that's expected until the firmware is sending
data. Leave this running.

### A.7 Set up the serial bridge

Open a **third** PowerShell window (terminal #3):

```powershell
cd C:\BinSight\tools
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
notepad .env
```

Set `BINSIGHT_API_KEY` to the **exact same value** you put in
`cloud_backend\.env`. Leave `SERIAL_PORT` for now — you'll fill it in once
the Teensy is plugged in (next section tells you how to find it). Save and
close, but don't run the script yet.

---

## Part B — Circuit Prototype Wiring

### B.1 Parts list

From your kit: Teensy 4.1, 2x HC-SR04 ultrasonic sensors, 3x push buttons,
breadboard, jumper wires (mostly male-male).

**You'll also need 4 resistors that aren't in the original kit list** — see
the safety note below for why. Any of these combinations work (±10% is
fine): **2x 1kΩ + 2x 2kΩ**, or **2x 1kΩ + 2x 1.8kΩ**. These are extremely
common values in any basic resistor kit or electronics starter pack.

> **⚠️ Why the resistors are required — read this before wiring anything.**
> The HC-SR04 ultrasonic sensor's ECHO pin outputs a **5V** signal. The
> Teensy 4.1's GPIO pins are **3.3V only and NOT 5V-tolerant** (unlike some
> older Arduino boards) — feeding 5V directly into a Teensy pin can
> permanently damage it. Each ECHO line needs a simple two-resistor
> voltage divider to step 5V down to a safe ~3.3V before it reaches the
> Teensy. The TRIG pins are fine to drive directly from the Teensy at
> 3.3V — HC-SR04 modules reliably read that as a logic HIGH.

### B.2 Pin map (already set in `firmware/BinSight_Teensy41/config.h`)

| Signal | Teensy 4.1 pin |
|---|---|
| Ultrasonic #1 TRIG | 2 |
| Ultrasonic #1 ECHO (via divider) | 3 |
| Ultrasonic #2 TRIG | 4 |
| Ultrasonic #2 ECHO (via divider) | 5 |
| Button 1 — Heavy/Wet | 6 |
| Button 2 — Dry/Recyclable | 7 |
| Button 3 — Calibrate/Reset (long-press) | 8 |
| Status LED | 13 (Teensy's built-in LED — no wiring needed) |
| 5V supply for sensors | VIN |
| Ground | GND |

### B.3 Voltage divider (build this twice, one per ultrasonic sensor)

```
   ECHO ──┬── R1 (1kΩ) ──┬── Teensy pin (3 or 5)
  (5V)    │              │
          │            R2 (2kΩ)
          │              │
          └──────────────┴── GND
```

In words: the ECHO pin connects to one end of a 1kΩ resistor. The other
end of that 1kΩ resistor is the "tap point" — it connects both to a 2kΩ
resistor going to GND, *and* to the Teensy's input pin (3 for sensor 1, 5
for sensor 2). This divides the 5V ECHO signal down to about 3.33V, safely
within the Teensy's input range.

### B.4 Step-by-step wiring

Unplug the Teensy from USB before wiring anything.

1. **Seat the Teensy 4.1** across the center gap of the breadboard, pins straddling the gap so each pin's row is separately accessible.
2. **Ground rail:** jumper wire from a Teensy GND pin to the breadboard's blue (−) rail.
3. **5V rail:** jumper wire from the Teensy's VIN pin to the breadboard's red (+) rail. (VIN outputs ~5V here because the Teensy will be powered over USB — that's exactly what you want for the sensors.)
4. **Ultrasonic sensor #1:**
   - VCC → red (+) rail
   - GND → blue (−) rail
   - TRIG → Teensy pin 2 (direct wire)
   - ECHO → build the divider from B.3, with the Teensy-pin end going to **pin 3**
5. **Ultrasonic sensor #2:** repeat step 4, but TRIG → **pin 4**, divider output → **pin 5**.
6. **Buttons** (all 3 wired the same way — internal pull-ups are enabled in firmware, so no extra resistor is needed per button):
   - Button 1: one leg → pin 6, opposite leg → blue (−) rail
   - Button 2: one leg → pin 7, opposite leg → blue (−) rail
   - Button 3: one leg → pin 8, opposite leg → blue (−) rail
7. **Double-check before powering on:**
   - No wire connects the red (5V) rail directly to any Teensy signal pin (2–8) — only to VCC pins on the sensors and through the resistor dividers.
   - Both ECHO lines go through their divider, not straight to the Teensy.
   - Everything shares one common ground (blue rail ↔ Teensy GND).

### B.5 Flash the firmware

1. Plug the Teensy into your computer via USB — this powers the board (and, through VIN, the sensors).
2. In the Arduino IDE, open `C:\BinSight\firmware\BinSight_Teensy41\BinSight_Teensy41.ino`. The other `.h`/`.cpp` files will appear as tabs automatically.
3. **Tools → Board → Teensyduino → Teensy 4.1**
4. **Tools → USB Type → Serial**
5. **Tools → Port** → select the port the Teensy appeared on (it'll be labeled "Teensy").
6. Click **Upload** (the → arrow icon). The Teensy Loader will open automatically and program the board — you may need to briefly press the Teensy's physical button if it's a first-time flash.
7. Open **Tools → Serial Monitor**, set the baud rate to **115200**.

### B.6 Bring-up checklist

With the Serial Monitor open, you should see:

```
=== BinSight Teensy 4.1 — booting ===
Firmware version: 1.0.0
Bin ID: bin_01
Initializing serial-bridge transport...
Serial-bridge transport ready — run tools/serial_bridge.py on the host.
Starting scheduler — control now passes to RTOS tasks.
[Task1] US1=45.2cm US2=44.8cm fill=48.4% density=1.20 conf=1 hint=0
[Task1] US1=45.1cm US2=44.9cm fill=48.6% density=1.20 conf=1 hint=0
...
```

Work through this checklist:

- **Wave your hand in front of sensor 1** — `fill=` should rise as your hand gets closer, fall as it moves away.
- **Cover/block sensor 2 only** — `conf=` should drop to `0` (the two sensors now disagree). Uncover it and confirm `conf=1` returns.
- **Press Button 1 (Heavy/Wet)** — `hint=` should change to `1`, and `density=` should jump toward ~3.0, holding for about 8 seconds before decaying back.
- **Press Button 2 (Dry/Recyclable)** — `hint=` should change to `2`, `density=` should drop toward ~0.6.
- **Hold Button 3 for 2+ seconds** — you should see a one-time `[Task1] Calibration requested` message.
- **Status LED (pin 13, built into the board)** should be solid on whenever `conf=1`, and turn off when `conf=0`.

Once wiring checks out, close the Serial Monitor (the serial port can only be held open by one program at a time) and move to Part C.

> To quiet the per-sample debug prints later (e.g. for the actual
> competition run), set `DEBUG_SERIAL_PRINTS` to `0` in `config.h` and
> re-upload — the `BINSIGHT:` telemetry frames the bridge script needs
> keep flowing either way.

---

## Part C — Run the Full Pipeline

By now terminals #1 (backend) and #2 (dashboard) should already be running
from Part A. Add two more steps:

1. **Find the Teensy's COM port** (terminal #3, from A.7):
   ```powershell
   cd C:\BinSight\tools
   .venv\Scripts\Activate.ps1
   python serial_bridge.py --list-ports
   ```
   Note the `COMx` entry that mentions "Teensy" or "USB Serial."

2. **Edit `tools\.env`** and set `SERIAL_PORT=COM<x>` to that value.

3. **Start the bridge** (still terminal #3):
   ```powershell
   python serial_bridge.py
   ```
   You should see `[teensy]` boot messages followed by `[frame] {...}` lines and `-> stored bin=bin_01 fill=...` acknowledgments.

4. **Check the dashboard** (already open at http://localhost:8501) — it should now show `bin_01` with a live fill % metric, an overflow-risk badge, and the fill/density charts updating on each refresh.

If a step doesn't work, the fix is almost always in this order: is the
backend terminal (#1) still running and showing no errors → is the bridge
script (#3) connected to the right COM port → is the Teensy's Serial
Monitor closed (it can't be open in two places at once) → does
`BINSIGHT_API_KEY` match exactly between `cloud_backend\.env` and
`tools\.env`.

---

## Part D — [Added 2026-08-28] Optional ESP32 Wi-Fi Gateway

This is an **additional** path, not a replacement for Part C — the laptop
bridge (`serial_bridge.py`) keeps working exactly as before whether or not
you wire up an ESP32. Add this once Parts A–C are working, so you have a
known-good baseline to fall back to if something in this section doesn't
behave.

**What this gets you:** the Teensy forwards each reading to a second,
independent board (an ESP32) over a direct wire, and that board pushes it
to the cloud backend over Wi-Fi — no laptop/USB tether required for that
path. See `firmware/BinSight_ESP32_Gateway/BinSight_ESP32_Gateway.ino` for
the full design notes.

### D.1 Parts needed

- 1x ESP32 dev board (e.g. ESP32-WROOM-32 dev kit)
- Its own USB cable, separate from the Teensy's
- 3 jumper wires (TX, RX, GND) — **no resistors needed here**: unlike the
  HC-SR04 sensors' 5V ECHO signal, the ESP32's GPIO pins are 3.3V logic,
  same as the Teensy's, so they connect directly.

### D.2 Wiring

| Signal | Teensy 4.1 pin | ESP32 pin |
|---|---|---|
| Teensy TX3 → ESP32 RX | 14 | GPIO16 |
| Teensy RX3 ← ESP32 TX | 15 | GPIO17 |
| Ground | any GND | any GND |

> **⚠️ Power the ESP32 from its own USB cable, not from the Teensy.**
> Wi-Fi transmission draws current spikes up to ~500mA — trying to power
> the ESP32 off the Teensy's 3.3V pin can brown out the Teensy itself.
> Plug the ESP32 into its own USB port (on the same computer, a USB hub,
> or any 5V USB power adapter) — just make sure its ground is still tied
> to the Teensy's ground per the table above, or the UART link won't work
> reliably.

These pins are separate from everything wired in Part B (pins 2–8, 13) —
you don't need to touch or re-check the existing sensor/button wiring.

### D.3 Software setup

1. In the Arduino IDE: **Tools → Board → Boards Manager**, search `esp32`,
   install **esp32 by Espressif Systems** (if not already installed).
2. Open `firmware/BinSight_ESP32_Gateway/BinSight_ESP32_Gateway.ino`.
3. In that same folder, copy `esp_config.example.h` to `esp_config.h` and
   fill in:
   - `WIFI_SSID` / `WIFI_PASSWORD` — your Wi-Fi network.
   - `BINSIGHT_API_KEY` — the **exact same value** already in
     `cloud_backend\.env` and `tools\.env`.
   - `CLOUD_BACKEND_URL` — your laptop's LAN IP (find it with `ipconfig`,
     look for "IPv4 Address" under your Wi-Fi adapter), e.g.
     `http://192.168.1.50:8000`. **This can't be `localhost`** — that
     would mean the ESP32 itself, not your laptop.
4. **Tools → Board** → select your ESP32 board (e.g. "ESP32 Dev Module").
5. **Tools → Port** → select the ESP32's port (it'll be a different COM
   port than the Teensy's).
6. Click **Upload**.
7. Open **Tools → Serial Monitor** for the ESP32 (115200 baud) — you
   should see it connect to Wi-Fi and print its IP address.
8. Re-flash the Teensy sketch too (it now includes `esp_link.h`) if you
   haven't already picked up the latest firmware changes.

### D.4 Bring-up checklist

With both boards powered and the cloud backend (terminal #1) still
running:

- The Teensy's Serial Monitor should print `ESP32 gateway link ready`
  during boot.
- The ESP32's Serial Monitor should print `Wi-Fi connected, IP: ...`,
  then start showing lines like `[gateway] flushed ...` (if it had
  anything queued) — a steady stream with no `could not reach backend`
  messages means it's working.
- The dashboard should keep updating even if you **stop**
  `serial_bridge.py` (terminal #3) — that confirms the ESP32 path is
  independently getting data to the backend, not just riding along with
  the laptop bridge.
- If the ESP32 keeps printing `[gateway] could not reach backend`, double
  check `CLOUD_BACKEND_URL` is your laptop's actual LAN IP (not
  `localhost`) and that both devices are on the same Wi-Fi network —
  guest Wi-Fi networks often block device-to-device traffic, which would
  show up exactly as this symptom.
