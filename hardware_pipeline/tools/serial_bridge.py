"""
BinSight Serial Bridge
=====================================================================
Bridges the Teensy 4.1's USB-serial telemetry stream to the FastAPI
cloud backend over HTTP. This exists because the prototype has no
Ethernet/WiFi hardware (Teensy 4.1, 2x ultrasonic, 3x buttons only) —
Task 3 on the MCU writes each packaged reading as a framed line over
USB serial, and this script reads it, parses the JSON, and POSTs it to
the backend with the API key attached.

Run:
    pip install -r requirements.txt
    python serial_bridge.py --list-ports        # find your Teensy's COM port
    python serial_bridge.py --port COM5          # start bridging

Or configure via a .env file (copy tools/.env.example -> tools/.env)
and just run `python serial_bridge.py`.
"""
import argparse
import json
import os
import sys
import time

import requests
import serial
import serial.tools.list_ports
from dotenv import load_dotenv

FRAME_PREFIX = "BINSIGHT:"  # must match network.cpp's FRAME_PREFIX exactly

load_dotenv()


def list_ports():
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("No serial ports found.")
        return
    print("Available serial ports:")
    for p in ports:
        print(f"  {p.device}  —  {p.description}")


def post_reading(api_base: str, api_key: str, payload: dict, timeout: float = 5.0) -> None:
    resp = requests.post(
        f"{api_base}/api/v1/telemetry",
        json=payload,
        headers={"X-API-Key": api_key},
        timeout=timeout,
    )
    if resp.status_code >= 400:
        print(f"  -> REJECTED ({resp.status_code}): {resp.text}")
    else:
        body = resp.json()
        print(f"  -> {body.get('status', 'ok')}  bin={payload.get('bin_id')} "
              f"fill={payload.get('fill_pct')}%")


def bridge_loop(port: str, baud: int, api_base: str, api_key: str) -> None:
    print(f"Opening {port} @ {baud} baud...")
    while True:
        try:
            with serial.Serial(port, baud, timeout=1) as ser:
                print(f"Connected to {port}. Waiting for BINSIGHT: frames from the Teensy...")
                while True:
                    line = ser.readline().decode("utf-8", errors="replace").strip()
                    if not line:
                        continue

                    if not line.startswith(FRAME_PREFIX):
                        # Firmware debug/boot output (e.g. "[Task1] ..." or
                        # "=== BinSight Teensy 4.1 — booting ===") — just echo it.
                        print(f"[teensy] {line}")
                        continue

                    raw_json = line[len(FRAME_PREFIX):]
                    try:
                        payload = json.loads(raw_json)
                    except json.JSONDecodeError as e:
                        print(f"  !! could not parse frame as JSON: {e} -- {raw_json!r}")
                        continue

                    print(f"[frame] {raw_json}")
                    try:
                        post_reading(api_base, api_key, payload)
                    except requests.exceptions.RequestException as e:
                        print(f"  !! could not reach cloud backend at {api_base}: {e}")

        except serial.SerialException as e:
            print(f"Serial error ({e}) — retrying in 3s. Is the Teensy plugged in / port correct?")
            time.sleep(3)
        except KeyboardInterrupt:
            print("\nStopping bridge.")
            sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="BinSight Teensy <-> Cloud serial bridge")
    parser.add_argument("--list-ports", action="store_true", help="List available serial ports and exit")
    parser.add_argument("--port", default=os.getenv("SERIAL_PORT"), help="Serial port, e.g. COM5")
    parser.add_argument("--baud", type=int, default=int(os.getenv("BAUD_RATE", "115200")))
    parser.add_argument("--api-base", default=os.getenv("API_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--api-key", default=os.getenv("BINSIGHT_API_KEY"))
    args = parser.parse_args()

    if args.list_ports:
        list_ports()
        return

    if not args.port:
        print("No serial port specified. Run with --list-ports to find it, "
              "then pass --port COM5 (or set SERIAL_PORT in tools/.env).")
        sys.exit(1)

    if not args.api_key:
        print("No API key specified. Pass --api-key or set BINSIGHT_API_KEY in tools/.env "
              "(must match BINSIGHT_API_KEY in cloud_backend/.env).")
        sys.exit(1)

    bridge_loop(args.port, args.baud, args.api_base, args.api_key)


if __name__ == "__main__":
    main()
