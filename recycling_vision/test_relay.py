import unittest

from recycling_vision.relay import InferenceMetadata


def sample(material: str = "plastic") -> InferenceMetadata:
    return InferenceMetadata(1, "event-1", "RRS-001", "relay-1", "boot-1", 42,
                             "session-1", "inspection-1", "2026-08-27T09:30:12.345Z",
                             "grove-vision-ai-v2", "recycling-yolo-1.0.0", material, 0.93, 1, 84, True)


class RelayContractTests(unittest.TestCase):
    def test_round_trip(self):
        self.assertEqual(InferenceMetadata.from_json(sample().to_json()), sample())

    def test_paper_is_a_valid_model_output_for_server_rejection(self):
        self.assertEqual(sample("paper").material, "paper")

    def test_unknown_material_fails_closed(self):
        with self.assertRaises(ValueError):
            sample("ceramic")


if __name__ == "__main__":
    unittest.main()
