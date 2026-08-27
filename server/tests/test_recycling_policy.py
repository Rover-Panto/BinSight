import unittest

from server.recycling_policy import InferenceSample, PolicyConfig, RecyclingInspection


class RecyclingPolicyTests(unittest.TestCase):
    def test_each_allowed_material_accepts_after_three_high_confidence_results(self):
        for material in ("plastic", "metal", "glass"):
            with self.subTest(material=material):
                inspection = RecyclingInspection()
                self.assertEqual(inspection.observe(InferenceSample(1, material, 0.95), 100).outcome, "waiting")
                self.assertEqual(inspection.observe(InferenceSample(2, material, 0.90), 200).outcome, "waiting")
                result = inspection.observe(InferenceSample(3, material, 0.70), 300)
                self.assertEqual(result.outcome, "accepted")
                self.assertEqual(result.value_cents, 20)
                self.assertEqual(result.confidence, 0.70)

    def test_every_other_material_rejects(self):
        for material in ("paper", "other", "unknown", "can", "plastic_bottle", "", "wood"):
            with self.subTest(material=material):
                result = RecyclingInspection().observe(InferenceSample(1, material, 0.99), 100)
                self.assertEqual(result.outcome, "rejected")
                self.assertEqual(result.reason, "unsupported_material")
                self.assertEqual(result.value_cents, 0)

    def test_normalizes_material_case_and_whitespace(self):
        inspection = RecyclingInspection(PolicyConfig(required_consecutive_results=1))
        self.assertEqual(inspection.observe(InferenceSample(1, " GLASS ", 0.99), 0).material, "glass")

    def test_low_confidence_waits_and_then_times_out(self):
        inspection = RecyclingInspection()
        result = inspection.observe(InferenceSample(1, "plastic", 0.69), 100)
        self.assertEqual(result.outcome, "waiting")
        self.assertEqual(result.value_cents, 0)
        self.assertEqual(inspection.poll(5000).outcome, "rejected")

    def test_low_confidence_resets_the_stable_run(self):
        inspection = RecyclingInspection()
        for sequence, confidence in ((1, 0.9), (2, 0.9), (3, 0.4), (4, 0.9), (5, 0.9)):
            result = inspection.observe(InferenceSample(sequence, "metal", confidence), sequence * 100)
        self.assertEqual(result.outcome, "waiting")
        self.assertEqual(result.stable_results, 2)

    def test_class_change_resets_the_stable_run(self):
        inspection = RecyclingInspection()
        for sequence, material in ((1, "plastic"), (2, "plastic"), (3, "glass")):
            result = inspection.observe(InferenceSample(sequence, material, 0.99), sequence * 100)
        self.assertEqual(result.outcome, "waiting")
        self.assertEqual(result.stable_results, 1)

    def test_duplicate_and_out_of_order_results_do_not_count(self):
        inspection = RecyclingInspection()
        inspection.observe(InferenceSample(2, "metal", 0.99), 100)
        inspection.observe(InferenceSample(2, "metal", 0.99), 200)
        result = inspection.observe(InferenceSample(1, "metal", 0.99), 300)
        self.assertEqual(result.stable_results, 1)
        self.assertEqual(result.outcome, "waiting")

    def test_sequence_gap_resets_the_stable_run(self):
        inspection = RecyclingInspection()
        inspection.observe(InferenceSample(1, "metal", 0.99), 100)
        inspection.observe(InferenceSample(2, "metal", 0.99), 200)
        result = inspection.observe(InferenceSample(4, "metal", 0.99), 300)
        self.assertEqual(result.stable_results, 1)

    def test_multiple_items_reject(self):
        result = RecyclingInspection().observe(InferenceSample(1, "glass", 0.99, 2), 100)
        self.assertEqual(result.reason, "multiple_items")
        self.assertEqual(result.value_cents, 0)

    def test_no_detection_waits_and_times_out(self):
        inspection = RecyclingInspection()
        self.assertEqual(inspection.observe(InferenceSample(1, None, None, 0), 100).outcome, "waiting")
        self.assertEqual(inspection.poll(5000).reason, "inspection_timeout")

    def test_invalid_confidence_rejects(self):
        for confidence in (None, float("nan"), float("inf"), -0.1, 1.1, True):
            with self.subTest(confidence=confidence):
                result = RecyclingInspection().observe(InferenceSample(1, "plastic", confidence), 100)
                self.assertEqual(result.reason, "invalid_inference")

    def test_terminal_decision_cannot_be_changed_or_repeated_as_a_new_decision(self):
        inspection = RecyclingInspection(PolicyConfig(required_consecutive_results=1))
        accepted = inspection.observe(InferenceSample(1, "plastic", 0.99), 100)
        self.assertIs(inspection.observe(InferenceSample(2, "paper", 0.99), 200), accepted)
        self.assertIs(inspection.poll(6000), accepted)

    def test_timeout_prevents_late_acceptance(self):
        inspection = RecyclingInspection(PolicyConfig(required_consecutive_results=1))
        self.assertEqual(inspection.observe(InferenceSample(1, "plastic", 0.99), 5000).outcome, "rejected")

    def test_invalid_sequence_and_object_count_reject(self):
        for sample in (InferenceSample(-1, "plastic", 0.99), InferenceSample(True, "plastic", 0.99), InferenceSample(1, "plastic", 0.99, -1)):
            with self.subTest(sample=sample):
                self.assertEqual(RecyclingInspection().observe(sample, 100).reason, "invalid_inference")

    def test_server_time_cannot_go_backwards(self):
        inspection = RecyclingInspection()
        inspection.poll(100)
        self.assertEqual(inspection.poll(99).reason, "invalid_server_time")

    def test_invalid_configuration_raises(self):
        for kwargs in ({"min_confidence": float("nan")}, {"min_confidence": 1.1}, {"required_consecutive_results": 0}, {"timeout_ms": 0}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    PolicyConfig(**kwargs)


if __name__ == "__main__":
    unittest.main()
