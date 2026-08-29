from binsight.config import load_config
from scripts.tune_distance_policy import (
    CANDIDATES,
    PHASE_SEEDS,
    ROOT,
    candidate_config,
)


def test_every_distance_tuning_candidate_is_a_valid_bounded_configuration():
    for candidate in CANDIDATES:
        config = candidate_config(candidate)
        assert config.operations.horizon_days == 30
        assert config.pilot.bin_count == 44
        assert config.waste.sensor_interval_hours in {2, 3, 6}


def test_tuning_seed_blocks_are_disjoint_and_current_candidate_is_unchanged():
    assert len(set(PHASE_SEEDS.values())) == len(PHASE_SEEDS)
    assert set(PHASE_SEEDS["screen"]).isdisjoint(PHASE_SEEDS["confirm"])
    assert candidate_config("current_90") == load_config(ROOT / "config.json")
