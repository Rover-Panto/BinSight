import numpy as np

from binsight.config import load_config
from binsight.district import BinSpec, generate_hourly_waste


def _bins():
    return [
        BinSpec("BIN-01", 1, 3.06, 101.57, 250, 10, 540.0, "mixed/commercial"),
        BinSpec("BIN-02", 2, 3.07, 101.58, 250, 10, 540.0, "mixed/commercial"),
    ]


def test_arrivals_are_seeded_nonnegative_and_policy_independent(tmp_path):
    source = __import__("pathlib").Path(__file__).resolve().parents[1] / "config.json"
    config = load_config(source)
    first = generate_hourly_waste(_bins(), config, seed=123, horizon_hours=72)
    second = generate_hourly_waste(_bins(), config, seed=123, horizon_hours=72)
    different = generate_hourly_waste(_bins(), config, seed=124, horizon_hours=72)
    assert first.shape == (72, 2)
    assert np.all(first >= 0)
    np.testing.assert_allclose(first, second)
    assert not np.allclose(first, different)
