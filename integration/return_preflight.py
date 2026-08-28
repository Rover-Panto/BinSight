"""Run an isolated real-HTTP return cycle, optionally using PR3's serializer."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import secrets
import socket
import sqlite3
import sys
import tempfile
import threading
import time

import httpx
import uvicorn

from server.api import create_app
from server.settings import Settings


def vision_serializer(root):
    if root is None:
        return lambda packet: json.dumps(packet)
    path = root.resolve() / "recycling_vision/relay.py"
    spec = importlib.util.spec_from_file_location("preflight_pr3_relay", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return lambda packet: module.InferenceMetadata(**packet).to_json()


def run(vision_root=None):
    serialize = vision_serializer(vision_root)
    with tempfile.TemporaryDirectory(prefix="binsight-http-preflight-") as directory:
        settings = Settings(Path(directory) / "returns.sqlite3", {"fictional-citizen": secrets.token_urlsafe(32)}, secrets.token_urlsafe(32))
        with closing(socket.socket()) as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
            server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="error", access_log=False))
            thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]})
            thread.start()
            try:
                deadline = time.monotonic() + 10
                while not server.started:
                    if not thread.is_alive() or time.monotonic() > deadline:
                        raise RuntimeError("Temporary return server failed to start")
                    time.sleep(.02)
                with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5, trust_env=False) as client:
                    user = {"Authorization": "Bearer " + settings.citizen_tokens["fictional-citizen"]}
                    device = {"Authorization": "Bearer " + settings.device_token, "Content-Type": "application/json"}

                    def post(path, payload, headers=user):
                        response = client.post(path, json=payload, headers=headers)
                        response.raise_for_status()
                        return response.json()

                    station_url = "/api/v1/recycling/stations/RRS-001"
                    post(station_url + "/ready", {
                        "request_id": "ready-first", "device_id": settings.device_id,
                        "boot_id": "preflight-boot", "empty": True, "is_simulation": True,
                    }, device)
                    session = post("/api/v1/return-sessions", {"request_id": "session-once", "station_id": "RRS-001"})["session_id"]
                    session_url = "/api/v1/return-sessions/" + session
                    inspection = post(session_url + "/inspections", {"request_id": "item-one"})["inspection_id"]
                    packet = {}
                    for sequence in range(1, 4):
                        packet = {
                            "schema_version": 1, "event_id": f"preflight-{sequence}",
                            "station_id": "RRS-001", "device_id": settings.device_id,
                            "boot_id": "preflight-boot", "sequence": sequence,
                            "session_id": session, "inspection_id": inspection,
                            "observed_at": datetime.now(timezone.utc).isoformat(),
                            "source": "grove-vision-ai-v2", "model_version": "preflight-not-trained",
                            "material": "metal", "confidence": .7, "object_count": 1,
                            "inference_ms": 84, "is_simulation": True,
                        }
                        response = client.post("/api/v1/recycling/inferences", content=serialize(packet), headers=device)
                        response.raise_for_status()
                    if response.json()["decision"]["outcome"] != "accepted":
                        raise AssertionError("Three matching samples were not accepted")
                    replay = client.post("/api/v1/recycling/inferences", content=serialize(packet), headers=device)
                    replay.raise_for_status()
                    if not replay.json()["duplicate"]:
                        raise AssertionError("Lost-acknowledgement retry was not deduplicated")
                    post(station_url + "/ready", {
                        "request_id": "ready-second", "device_id": settings.device_id,
                        "boot_id": "preflight-boot", "after_inspection_id": inspection,
                        "empty": True, "is_simulation": True,
                    }, device)
                    second = post(session_url + "/inspections", {"request_id": "item-two"})["inspection_id"]
                    rejected = dict(packet, inspection_id=second, event_id="preflight-4", sequence=4,
                                    material="paper", observed_at=datetime.now(timezone.utc).isoformat())
                    response = client.post("/api/v1/recycling/inferences", content=serialize(rejected), headers=device)
                    response.raise_for_status()
                    if response.json()["decision"]["reason"] != "unsupported_material":
                        raise AssertionError("Paper was not rejected")
                    finished = post(session_url + "/finish", {"request_id": "finish-once"})
                    if finished["credit_cents"] != 20 or finished["status"] != "finished":
                        raise AssertionError("Incorrect session total or completion state")
                    with closing(sqlite3.connect(settings.database)) as db:
                        credit_rows = db.execute("SELECT COUNT(*) FROM credits").fetchone()[0]
                        event_rows = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
                    if (credit_rows, event_rows) != (1, 4):
                        raise AssertionError("Unexpected durable event or credit count")
                    return {
                        "transport": "real loopback HTTP", "mode": "simulation",
                        "serializer": "PR3 InferenceMetadata" if vision_root else "JSON fixture",
                        "accepted": 1, "rejected": 1, "credit_cents": 20,
                        "stored_events": event_rows, "credit_rows": credit_rows,
                        "duplicate_retry": "deduplicated",
                        "hardware_tested": False, "citizen_browser_tested": False,
                    }
            finally:
                server.should_exit = True
                thread.join(timeout=10)
                if thread.is_alive():
                    raise RuntimeError("Temporary return server did not stop")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vision-root", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.vision_root), indent=2))


if __name__ == "__main__":
    main()
