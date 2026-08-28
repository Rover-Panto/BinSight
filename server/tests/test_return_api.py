from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from server.api import create_app
from server.backup import backup_database
from server.settings import Settings


class TestClock:
    def __init__(self):
        self.wall = datetime(2026, 8, 28, 9, tzinfo=timezone.utc).timestamp()
        self.tick = 1000.0

    def utc(self):
        return self.wall

    def monotonic(self):
        return self.tick

    def advance(self, seconds):
        self.wall += seconds
        self.tick += seconds


class ReturnApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="binsight-return-test-")
        self.addCleanup(self.temp.cleanup)
        self.clock = TestClock()
        self.settings = Settings(
            Path(self.temp.name) / "returns.sqlite3",
            {"citizen-a": "a" * 40, "citizen-b": "b" * 40},
            "d" * 40,
        )
        self.user = {"Authorization": "Bearer " + "a" * 40}
        self.other = {"Authorization": "Bearer " + "b" * 40}
        self.device = {"Authorization": "Bearer " + "d" * 40}
        self.counter = 0
        self.boot = "boot-1"
        self.client = self.open_client()
        self.addCleanup(lambda: self.client.__exit__(None, None, None))

    def open_client(self):
        client = TestClient(create_app(self.settings, clock=self.clock))
        client.__enter__()
        return client

    def request_id(self):
        self.counter += 1
        return f"request-{self.counter}"

    def ready(self, after=None, **overrides):
        payload = {
            "request_id": self.request_id(), "device_id": self.settings.device_id,
            "boot_id": self.boot, "after_inspection_id": after,
            "empty": True, "is_simulation": True, **overrides,
        }
        return self.client.post("/api/v1/recycling/stations/RRS-001/ready", headers=self.device, json=payload)

    def start(self, headers=None, **overrides):
        return self.client.post("/api/v1/return-sessions", headers=headers or self.user,
                                json={"request_id": self.request_id(), "station_id": "RRS-001", **overrides})

    def inspect(self, session, **overrides):
        return self.client.post(f"/api/v1/return-sessions/{session}/inspections", headers=self.user,
                                json={"request_id": self.request_id(), **overrides})

    def setup_inspection(self):
        self.assertEqual(self.ready().status_code, 200)
        session = self.start().json()["session_id"]
        response = self.inspect(session)
        self.assertEqual(response.status_code, 200, response.text)
        return session, response.json()["inspection_id"]

    def packet(self, session, inspection, sample_sequence, **overrides):
        return {
            "schema_version": 1, "event_id": f"event-{self.boot}-{sample_sequence}",
            "station_id": "RRS-001", "device_id": self.settings.device_id,
            "boot_id": self.boot, "sequence": sample_sequence, "session_id": session,
            "inspection_id": inspection,
            "observed_at": datetime.fromtimestamp(self.clock.utc(), timezone.utc).isoformat(),
            "source": "grove-vision-ai-v2", "model_version": "test-only-not-trained",
            "material": "plastic", "confidence": 0.7, "object_count": 1,
            "inference_ms": 84, "is_simulation": True, **overrides,
        }

    def send(self, packet):
        return self.client.post("/api/v1/recycling/inferences", headers=self.device, json=packet)

    def view(self, session, headers=None):
        return self.client.get(f"/api/v1/return-sessions/{session}", headers=headers or self.user)

    def complete_item(self, session, inspection, start=1, material="plastic"):
        for sequence in range(start, start + 3):
            self.clock.advance(0.1)
            packet = self.packet(session, inspection, sequence, material=material)
            response = self.send(packet)
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["decision"]["outcome"], "accepted")
        return packet

    def test_exact_threshold_persists_one_credit_and_idempotent_replays(self):
        session, inspection = self.setup_inspection()
        packet = self.complete_item(session, inspection)
        for _ in range(3):
            replay = self.send(packet)
            self.assertTrue(replay.json()["duplicate"])
        view = self.view(session).json()
        self.assertEqual(view["credit_cents"], 20)
        self.assertEqual(view["currency"], "MYR")
        self.assertEqual(len(view["inspections"]), 1)
        with closing(sqlite3.connect(self.settings.database)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM credits").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 3)

    def test_authentication_roles_and_citizen_ownership(self):
        self.assertEqual(self.client.post("/api/v1/return-sessions", json={"request_id": "x", "station_id": "RRS-001"}).status_code, 401)
        session, inspection = self.setup_inspection()
        self.assertEqual(self.view(session, self.other).status_code, 404)
        self.assertEqual(self.start(headers=self.device).status_code, 401)
        self.assertEqual(self.client.post("/api/v1/recycling/inferences", headers=self.user, json=self.packet(session, inspection, 1)).status_code, 401)
        self.assertEqual(self.client.get("/api/v1/recycling/stations/RRS-001", headers=self.user).status_code, 401)

    def test_station_exclusivity_and_start_retry(self):
        response = self.start(request_id="create-once")
        again = self.start(request_id="create-once")
        self.assertEqual(response.json()["session_id"], again.json()["session_id"])
        self.assertEqual(self.start(headers=self.other).status_code, 409)
        self.assertEqual(self.start(request_id="create-once", station_id="RRS-002").status_code, 409)

    def test_one_inspection_and_idempotent_start(self):
        self.ready()
        session = self.start().json()["session_id"]
        first = self.inspect(session, request_id="inspect-once")
        again = self.inspect(session, request_id="inspect-once")
        self.assertEqual(first.json()["inspection_id"], again.json()["inspection_id"])
        self.assertEqual(self.inspect(session).status_code, 409)

    def test_rejection_requires_device_removal_before_another_item(self):
        session, inspection = self.setup_inspection()
        result = self.send(self.packet(session, inspection, 1, material="paper"))
        self.assertEqual(result.json()["decision"]["reason"], "unsupported_material")
        self.assertEqual(self.view(session).json()["credit_cents"], 0)
        self.assertEqual(self.inspect(session).status_code, 409)
        self.assertEqual(self.ready(after=inspection, empty=False).status_code, 409)
        self.assertEqual(self.ready(after=inspection).status_code, 200)
        second = self.inspect(session).json()["inspection_id"]
        self.complete_item(session, second, start=2, material="metal")
        self.assertEqual(self.view(session).json()["credit_cents"], 20)

    def test_glass_accepted_and_held_item_cannot_start_next_inspection(self):
        session, inspection = self.setup_inspection()
        self.complete_item(session, inspection, material="glass")
        self.assertEqual(self.inspect(session).status_code, 409)
        self.assertEqual(self.ready(after=None).status_code, 409)
        self.assertEqual(self.send(self.packet(session, inspection, 4)).status_code, 409)

    def test_ready_retry_does_not_rearm_a_new_inspection(self):
        self.ready(request_id="ready-once")
        session = self.start().json()["session_id"]
        inspection = self.inspect(session).json()["inspection_id"]
        self.complete_item(session, inspection)
        self.assertTrue(self.ready(request_id="ready-once").json()["duplicate"])
        self.assertEqual(self.inspect(session).status_code, 409)

    def test_conflicting_event_id_and_sequence_do_not_increase_stability(self):
        session, inspection = self.setup_inspection()
        first = self.packet(session, inspection, 1)
        self.send(first)
        self.assertEqual(self.send({**first, "material": "metal"}).status_code, 409)
        self.assertEqual(self.send({**first, "event_id": "other-event"}).status_code, 409)
        self.assertEqual(self.send(first).json()["decision"]["stable_results"], 1)
        self.assertEqual(self.view(session).json()["credit_cents"], 0)

    def test_sequence_gap_resets_confirmation(self):
        session, inspection = self.setup_inspection()
        for seq in (1, 3, 4):
            result = self.send(self.packet(session, inspection, seq))
        self.assertEqual(result.json()["decision"]["outcome"], "waiting")
        self.assertEqual(self.send(self.packet(session, inspection, 5)).json()["decision"]["outcome"], "accepted")

    def test_low_confidence_and_class_change_reset_confirmation(self):
        session, inspection = self.setup_inspection()
        samples = [("plastic", .7), ("metal", .7), ("metal", .69), ("metal", .7), ("metal", .7)]
        for seq, (material, confidence) in enumerate(samples):
            result = self.send(self.packet(session, inspection, seq, material=material, confidence=confidence))
        self.assertEqual(result.json()["decision"]["outcome"], "waiting")
        self.assertEqual(self.view(session).json()["credit_cents"], 0)

    def test_no_object_and_multiple_objects_never_credit(self):
        session, inspection = self.setup_inspection()
        no_item = self.send(self.packet(session, inspection, 1, object_count=0, confidence=None))
        self.assertEqual(no_item.json()["decision"]["reason"], "no_detection")
        multiple = self.send(self.packet(session, inspection, 2, object_count=2))
        self.assertEqual(multiple.json()["decision"]["reason"], "multiple_items")
        self.assertEqual(self.view(session).json()["credit_cents"], 0)

    def test_timeout_uses_server_monotonic_time(self):
        session, inspection = self.setup_inspection()
        self.send(self.packet(session, inspection, 1))
        self.clock.advance(5)
        result = self.view(session).json()
        self.assertEqual(result["inspections"][0]["decision"]["reason"], "inspection_timeout")
        self.assertEqual(result["credit_cents"], 0)

    def test_device_timestamp_cannot_extend_window(self):
        session, inspection = self.setup_inspection()
        self.clock.tick += 5
        response = self.send(self.packet(session, inspection, 1))
        self.assertEqual(response.json()["decision"]["outcome"], "rejected")
        self.assertEqual(self.view(session).json()["credit_cents"], 0)

    def test_stale_future_and_wrong_binding_rejected(self):
        session, inspection = self.setup_inspection()
        for override, status in (
            ({"observed_at": "2026-08-28T08:59:00Z"}, 409),
            ({"observed_at": "2026-08-28T09:01:00Z"}, 409),
            ({"session_id": "wrong-session"}, 404),
            ({"station_id": "RRS-002"}, 404),
            ({"device_id": "unknown-device"}, 404),
            ({"boot_id": "unknown-boot"}, 409),
            ({"is_simulation": False}, 409),
        ):
            with self.subTest(override=override):
                self.assertEqual(self.send(self.packet(session, inspection, 1, **override)).status_code, status)
        self.assertEqual(self.view(session).json()["credit_cents"], 0)

    def test_strict_metadata_and_no_image_fields(self):
        session, inspection = self.setup_inspection()
        for override in (
            {"schema_version": True}, {"sequence": True}, {"confidence": True},
            {"confidence": "0.9"}, {"object_count": 1.5}, {"material": "unknown"},
            {"event_id": ""}, {"observed_at": "2026-08-28T09:00:00"},
            {"is_simulation": "true"}, {"image": "not-permitted"}, {"stable_results": 3},
        ):
            with self.subTest(override=override):
                self.assertEqual(self.send(self.packet(session, inspection, 1, **override)).status_code, 422)
        self.assertEqual(self.view(session).json()["credit_cents"], 0)

    def test_request_size_and_content_type_limits(self):
        self.assertEqual(self.client.post("/api/v1/recycling/inferences", headers=self.device, json={"image": "x" * 20000}).status_code, 413)
        self.assertEqual(self.client.post("/api/v1/recycling/inferences", headers=self.device, content="text").status_code, 415)

    def test_finish_cancels_pending_but_preserves_credits(self):
        session, inspection = self.setup_inspection()
        self.complete_item(session, inspection)
        self.ready(after=inspection)
        self.inspect(session)
        url = f"/api/v1/return-sessions/{session}/finish"
        result = self.client.post(url, headers=self.user, json={"request_id": "finish-once"}).json()
        self.assertEqual(result["status"], "finished")
        self.assertEqual(result["credit_cents"], 20)
        self.assertEqual(result["inspections"][-1]["decision"]["reason"], "session_finished")
        self.assertEqual(self.client.post(url, headers=self.user, json={"request_id": "finish-once"}).json(), result)
        self.assertEqual(self.inspect(session).status_code, 409)

    def test_expired_session_frees_station_without_losing_history(self):
        session, inspection = self.setup_inspection()
        self.clock.advance(self.settings.session_seconds + 1)
        old = self.view(session).json()
        self.assertEqual(old["status"], "expired")
        self.assertEqual(old["inspections"][0]["decision"]["reason"], "session_expired")
        self.assertEqual(self.start(headers=self.other).status_code, 200)
        self.assertEqual(self.view(session).json()["status"], "expired")

    def test_restart_keeps_credit_and_aborts_pending_inspection(self):
        session, inspection = self.setup_inspection()
        packet = self.complete_item(session, inspection)
        self.ready(after=inspection)
        self.inspect(session)
        self.client.__exit__(None, None, None)
        self.client = self.open_client()
        view = self.view(session).json()
        self.assertEqual(view["credit_cents"], 20)
        self.assertEqual(view["inspections"][-1]["decision"]["reason"], "server_restarted")
        self.assertTrue(self.send(packet).json()["duplicate"])
        self.assertEqual(self.inspect(session).status_code, 409)

    def test_device_restart_interrupts_pending_and_rejects_retired_boot(self):
        session, inspection = self.setup_inspection()
        self.send(self.packet(session, inspection, 1))
        self.boot = "boot-2"
        self.assertEqual(self.ready(after=inspection).status_code, 200)
        self.assertEqual(self.view(session).json()["inspections"][0]["decision"]["reason"], "gateway_restarted")
        self.assertEqual(self.ready(after=inspection, boot_id="boot-1").status_code, 409)
        second = self.inspect(session).json()["inspection_id"]
        self.complete_item(session, second, start=0)
        self.assertEqual(self.view(session).json()["credit_cents"], 20)

    def test_concurrent_retry_commits_one_credit(self):
        session, inspection = self.setup_inspection()
        self.send(self.packet(session, inspection, 1))
        self.send(self.packet(session, inspection, 2))
        packet = self.packet(session, inspection, 3)
        with ThreadPoolExecutor(max_workers=6) as pool:
            responses = list(pool.map(lambda _: self.send(packet), range(12)))
        self.assertTrue(all(response.status_code == 200 for response in responses))
        self.assertEqual(self.view(session).json()["credit_cents"], 20)

    def test_failed_commit_does_not_leave_a_partial_credit_or_event(self):
        session, inspection = self.setup_inspection()
        self.send(self.packet(session, inspection, 1))
        self.send(self.packet(session, inspection, 2))
        packet = self.packet(session, inspection, 3)
        store = self.client.app.state.store
        finish = store._finish

        def fail_after_writes(*args):
            finish(*args)
            raise RuntimeError("injected failure before commit")

        with patch.object(store, "_finish", side_effect=fail_after_writes):
            with self.assertRaisesRegex(RuntimeError, "injected failure"):
                self.send(packet)
        self.assertEqual(self.view(session).json()["credit_cents"], 0)
        with closing(sqlite3.connect(self.settings.database)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 2)
        self.assertEqual(self.send(packet).json()["decision"]["outcome"], "accepted")
        self.assertEqual(self.view(session).json()["credit_cents"], 20)

    def test_second_server_cannot_interrupt_first(self):
        session, inspection = self.setup_inspection()
        with self.assertRaisesRegex(RuntimeError, "already has a running server"):
            with TestClient(create_app(self.settings, clock=self.clock)):
                pass
        self.complete_item(session, inspection)

    def test_unknown_schema_is_not_migrated(self):
        path = Path(self.temp.name) / "unrelated.sqlite3"
        with closing(sqlite3.connect(path)) as db:
            db.execute("CREATE TABLE preserved (value TEXT)")
            db.execute("INSERT INTO preserved VALUES ('keep-me')")
            db.execute("PRAGMA user_version=99")
            db.commit()
        settings = Settings(path, self.settings.citizen_tokens, self.settings.device_token)
        with self.assertRaisesRegex(RuntimeError, "Unknown return database schema"):
            with TestClient(create_app(settings)):
                pass
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute("SELECT value FROM preserved").fetchone()[0], "keep-me")
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 99)

    def test_live_backup_restores_credit_and_refuses_overwrite(self):
        session, inspection = self.setup_inspection()
        self.complete_item(session, inspection)
        destination = Path(self.temp.name) / "backups" / "copy.sqlite3"
        backup_database(self.settings.database, destination)
        with self.assertRaises(FileExistsError):
            backup_database(self.settings.database, destination)
        restored = Settings(destination, self.settings.citizen_tokens, self.settings.device_token)
        with TestClient(create_app(restored, clock=self.clock)) as client:
            view = client.get(f"/api/v1/return-sessions/{session}", headers=self.user).json()
            self.assertEqual(view["credit_cents"], 20)
            self.assertEqual(len(view["inspections"]), 1)
        self.assertEqual(self.view(session).json()["credit_cents"], 20)

    def test_health_is_explicitly_simulation_without_payments_or_actuation(self):
        response = self.client.get("/health")
        self.assertEqual(response.json()["mode"], "simulation")
        self.assertFalse(response.json()["payments_enabled"])
        self.assertFalse(response.json()["actuation_enabled"])
        self.assertEqual(response.headers["cache-control"], "no-store")
