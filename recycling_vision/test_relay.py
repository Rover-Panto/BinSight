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

    def test_boolean_numeric_fields_are_rejected(self):
        with self.assertRaises(ValueError):
            InferenceMetadata(**{**sample().__dict__, "sequence": True})
        with self.assertRaises(ValueError):
            InferenceMetadata(**{**sample().__dict__, "object_count": 1.0})

    def test_identifiers_and_timestamp_are_strict(self):
        with self.assertRaises(ValueError):
            InferenceMetadata(**{**sample().__dict__, "station_id": " "})
        with self.assertRaises(ValueError):
            InferenceMetadata(**{**sample().__dict__, "observed_at": "2026-08-27T09:30:12"})

    def test_simulation_flag_must_be_boolean(self):
        with self.assertRaises(ValueError):
            InferenceMetadata(**{**sample().__dict__, "is_simulation": "true"})


if __name__ == "__main__":
    unittest.main()
