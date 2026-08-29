import numpy as np
import pandas as pd

from binsight.config import load_config
from binsight.district import BinSpec, generate_hourly_waste


ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]


def _bins():
    return [
        BinSpec("BIN-01", 1, 3.06, 101.57, 250, 10, 540.0, "mixed/commercial"),
        BinSpec("BIN-02", 2, 3.07, 101.58, 250, 10, 540.0, "mixed/commercial"),
    ]


def test_arrivals_are_seeded_nonnegative_and_policy_independent(tmp_path):
    source = ROOT / "config.json"
    config = load_config(source)
    first = generate_hourly_waste(_bins(), config, seed=123, horizon_hours=72)
    second = generate_hourly_waste(_bins(), config, seed=123, horizon_hours=72)
    different = generate_hourly_waste(_bins(), config, seed=124, horizon_hours=72)
    assert first.shape == (72, 2)
    assert np.all(first >= 0)
    np.testing.assert_allclose(first, second)
    assert not np.allclose(first, different)


def test_every_service_site_has_general_plastic_metal_and_glass_bins():
    bins = pd.read_csv(ROOT / "artifacts" / "district_bins.csv")
    expected_materials = {
        "mixed_general_waste",
        "plastic_cups",
        "metal_cans",
        "glass_bottles",
    }
    expected_capacities = {
        "mixed_general_waste": 540.0,
        "plastic_cups": 112.5,
        "metal_cans": 315.0,
        "glass_bottles": 1125.0,
    }
    for _, site in bins.groupby("site_id"):
        assert len(site) == 4
        assert set(site["material_type"]) == expected_materials
        assert (site["waste_stream"] == "dry_recycling").sum() == 3
        assert (site["destination_id"] == "recycling_facility").sum() == 3
        for row in site.itertuples():
            assert row.capacity_kg == expected_capacities[row.material_type]
