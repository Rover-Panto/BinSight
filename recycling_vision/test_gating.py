import unittest

from recycling_vision.gating import ConsecutiveDetectionGate


class ConsecutiveDetectionGateTests(unittest.TestCase):
    def test_three_matching_detections_emit_one_acceptance(self):
        gate = ConsecutiveDetectionGate(3)
        self.assertEqual(gate.observe("plastic").status, "confirming")
        self.assertEqual(gate.observe("plastic").consecutive, 2)
        accepted = gate.observe("plastic")
        self.assertTrue(accepted.emitted_acceptance)
        self.assertEqual(gate.observe("plastic").emitted_acceptance, False)

    def test_label_change_resets_confirmation(self):
        gate = ConsecutiveDetectionGate(3)
        gate.observe("plastic")
        changed = gate.observe("metal")
        self.assertEqual(changed.consecutive, 1)
        self.assertEqual(changed.label, "metal")

    def test_no_detection_rearms_after_acceptance(self):
        gate = ConsecutiveDetectionGate(1)
        self.assertTrue(gate.observe("glass").emitted_acceptance)
        self.assertEqual(gate.observe(None).status, "idle")
        self.assertTrue(gate.observe("glass").emitted_acceptance)

    def test_ineligible_material_is_rejected(self):
        self.assertEqual(ConsecutiveDetectionGate().observe("paper").status, "rejected")


if __name__ == "__main__":
    unittest.main()
