from contextlib import redirect_stdout
from io import StringIO
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
import unittest
from unittest.mock import patch

from integration.check_readiness import blockers, main
from server.recycling_policy import InferenceSample, RecyclingInspection

ROOT = Path(__file__).resolve().parents[2]


def fixture(name):
    return json.loads((ROOT / "integration/fixtures" / name).read_text(encoding="utf-8"))


class SharedFixtureTests(unittest.TestCase):
    def test_three_fill_channels_have_the_required_types(self):
        data = fixture("three_bins.json")
        self.assertIs(data["is_simulation"], True)
        self.assertEqual(len({b["bin_id"] for b in data["bins"]}), 3)
        self.assertEqual(Counter(b["bin_type"] for b in data["bins"]), {
            "general-waste": 1, "recycling-return": 2,
        })
        self.assertEqual(data["gateway_id"], "shared-gateway-01")

    def test_fill_example_preserves_unknowns_identity_and_cutoff(self):
        data = fixture("three_bins.json")
        cutoff = datetime.fromisoformat(data["decision_at"])
        ids = {b["bin_id"] for b in data["bins"]}
        self.assertEqual(len({r["event_id"] for r in data["observations"]}), len(data["observations"]))
        self.assertTrue(any(r["fill_pct"] is None for r in data["observations"]))
        for row in data["observations"]:
            self.assertIn(row["bin_id"], ids)
            self.assertIsNone(row["weight_kg"])
            self.assertLessEqual(datetime.fromisoformat(row["timestamp"]), datetime.fromisoformat(row["received_at"]))
            self.assertLessEqual(datetime.fromisoformat(row["received_at"]), cutoff)
            if row["fill_pct"] is None:
                self.assertEqual(row["confidence_flag"], 0)
            self.assertTrue({"material", "session_id", "confidence", "image"}.isdisjoint(row))

    def test_shared_recognition_cases_match_the_real_server_policy(self):
        data = fixture("recycling_cases.json")
        self.assertIs(data["is_simulation"], True)
        for case in data["cases"]:
            with self.subTest(case=case["id"]):
                inspection = RecyclingInspection()
                for sequence, material, confidence, object_count, elapsed in case["samples"]:
                    decision = inspection.observe(InferenceSample(sequence, material, confidence, object_count), elapsed)
                if "poll_at_ms" in case:
                    decision = inspection.poll(case["poll_at_ms"])
                self.assertEqual(decision.outcome, case["outcome"])
                self.assertEqual(decision.reason, case["reason"])
                self.assertEqual(decision.value_cents, case["value_cents"])

    def test_rejected_inspection_does_not_poison_a_separate_new_inspection(self):
        rejected = RecyclingInspection()
        rejected.observe(InferenceSample(1, "paper", 0.99), 100)
        another = RecyclingInspection()
        case = fixture("recycling_cases.json")["cases"][0]
        for sequence, material, confidence, count, elapsed in case["samples"]:
            decision = another.observe(InferenceSample(sequence, material, confidence, count), elapsed)
        self.assertEqual(decision.value_cents, 20)
        self.assertEqual(rejected.decision.outcome, "rejected")
        self.assertEqual(rejected.decision.value_cents, 0)


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.candidate = json.loads((ROOT / "integration/candidate.json").read_text(encoding="utf-8"))

    def ready_record(self):
        for c in self.candidate["components"]:
            c["review"] = "accepted_for_testing"
        for d in self.candidate["decisions"]:
            d.update(status="confirmed", evidence=["synthetic unit-test evidence"])
        for g in self.candidate["gates"]:
            g.update(status="passed", evidence=["synthetic unit-test evidence"])
        return self.candidate

    def test_unstaged_components_block_readiness(self):
        result = blockers(self.ready_record(), lambda sha: False)
        self.assertEqual(len(result), 4)
        self.assertTrue(all("not staged" in r for r in result))

    def test_review_and_owner_decisions_are_required(self):
        candidate = self.ready_record()
        candidate["components"][0]["review"] = "changes_required"
        candidate["decisions"][0]["status"] = "pending"
        self.assertEqual(len(blockers(candidate, lambda sha: True)), 2)

    def test_station_and_access_decisions_cannot_be_silently_deferred(self):
        candidate = self.ready_record()
        candidate["decisions"][0]["status"] = "deferred"
        candidate["decisions"][2]["status"] = "deferred"
        self.assertEqual(len(blockers(candidate, lambda sha: True)), 2)

    def test_physical_demo_requires_both_hardware_gates_by_default(self):
        candidate = self.ready_record()
        candidate["demo_mode"] = "physical"
        for gate in candidate["gates"][-2:]:
            gate["status"] = "not_run"
        result = blockers(candidate, lambda sha: True)
        self.assertEqual({r.split(":")[0] for r in result}, {"H01", "H02"})

    def test_software_only_preflight_must_be_explicit_for_physical_demo(self):
        candidate = self.ready_record()
        candidate["demo_mode"] = "physical"
        candidate["gates"][-1]["status"] = "not_run"
        self.assertEqual(blockers(candidate, lambda sha: True, hardware=False), [])
        self.assertEqual(len(blockers(candidate, lambda sha: True)), 1)

    def test_software_candidate_can_require_hardware_explicitly(self):
        candidate = self.ready_record()
        candidate["demo_mode"] = "software"
        candidate["gates"][-1]["status"] = "not_run"
        self.assertEqual(blockers(candidate, lambda sha: True), [])
        self.assertEqual(len(blockers(candidate, lambda sha: True, hardware=True)), 1)

    def test_missing_or_unknown_demo_mode_fails_closed(self):
        for mode in (None, "", "unknown", True):
            with self.subTest(mode=mode):
                candidate = self.ready_record()
                candidate["demo_mode"] = mode
                with self.assertRaises(ValueError):
                    blockers(candidate, lambda sha: True)
        del candidate["demo_mode"]
        with self.assertRaises(ValueError):
            blockers(candidate, lambda sha: True)

    def test_cli_default_cannot_skip_physical_gates(self):
        candidate = self.ready_record()
        candidate["demo_mode"] = "physical"
        candidate["gates"][-1]["status"] = "not_run"
        output = StringIO()
        with patch("sys.argv", ["check_readiness", "--require-ready"]), \
             patch("pathlib.Path.read_text", return_value=json.dumps(candidate)), \
             patch("integration.check_readiness.is_staged", return_value=True), \
             redirect_stdout(output):
            self.assertEqual(main(), 1)
        self.assertIn("software and physical hardware gates", output.getvalue())
        self.assertIn("H02: not_run", output.getvalue())

    def test_cli_software_only_labels_its_limited_scope(self):
        candidate = self.ready_record()
        candidate["demo_mode"] = "physical"
        candidate["gates"][-1]["status"] = "not_run"
        output = StringIO()
        with patch("sys.argv", ["check_readiness", "--require-ready", "--software-only"]), \
             patch("pathlib.Path.read_text", return_value=json.dumps(candidate)), \
             patch("integration.check_readiness.is_staged", return_value=True), \
             redirect_stdout(output):
            self.assertEqual(main(), 0)
        self.assertIn("does not establish physical demo readiness", output.getvalue())
        self.assertNotIn("H02: not_run", output.getvalue())

    def test_pass_without_evidence_is_not_ready(self):
        candidate = self.ready_record()
        candidate["gates"][0]["evidence"] = []
        self.assertEqual(len(blockers(candidate, lambda sha: True)), 1)

    def test_only_report_scope_can_be_deferred_with_owner_evidence(self):
        candidate = self.ready_record()
        candidate["gates"][12]["status"] = "owner_deferred"
        self.assertEqual(len(blockers(candidate, lambda sha: True)), 1)
        candidate["decisions"][1]["status"] = "deferred"
        self.assertEqual(blockers(candidate, lambda sha: True), [])
        candidate["gates"][1]["status"] = "owner_deferred"
        self.assertEqual(len(blockers(candidate, lambda sha: True)), 1)

    def test_cannot_drop_a_required_gate_or_component(self):
        self.candidate["gates"].pop()
        with self.assertRaises(ValueError):
            blockers(self.candidate, lambda sha: True)
        self.setUp()
        self.candidate["components"].pop()
        with self.assertRaises(ValueError):
            blockers(self.candidate, lambda sha: True)

    def test_invalid_revision_or_gate_level_fails_closed(self):
        self.candidate["components"][0]["sha"] = "not-a-commit"
        with self.assertRaises(ValueError):
            blockers(self.candidate, lambda sha: True)
        self.setUp()
        self.candidate["gates"][0]["level"] = "hardware"
        with self.assertRaises(ValueError):
            blockers(self.candidate, lambda sha: True)


if __name__ == "__main__":
    unittest.main()
