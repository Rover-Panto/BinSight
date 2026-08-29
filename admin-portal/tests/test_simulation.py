import numpy as np
from pathlib import Path

from binsight.config import load_config
from binsight.simulation import (
    _greedy_proxy_distance_m,
    _incremental_proxy_distance_m,
    _risk_levels,
    _time_to_overflow_hours,
)
from binsight.routing import select_capacity_feasible


ROOT = Path(__file__).resolve().parents[1]


def test_route_proxy_is_deterministic_and_capacity_aware():
    matrix = np.array(
        [
            [0, 100, 200, 300],
            [100, 0, 100, 200],
            [200, 100, 0, 100],
            [300, 200, 100, 0],
        ],
        dtype=float,
    )
    demands = np.array([60.0, 60.0, 20.0])
    first = _greedy_proxy_distance_m([0, 1, 2], demands, matrix, 100.0, 3)
    second = _greedy_proxy_distance_m([0, 1, 2], demands, matrix, 100.0, 3)
    assert first == second
    assert first == 1000.0
    assert _greedy_proxy_distance_m([0, 1, 2], demands, matrix, 100.0, 1) == float("inf")


def test_time_to_overflow_uses_conservative_growth_rate():
    result = _time_to_overflow_hours(
        np.array([50.0, 100.0, 80.0]),
        np.array([25.0, 0.0, 0.0]),
        50.0,
    )
    assert result[0] == 100.0
    assert result[1] == 0.0
    assert np.isinf(result[2])


def test_risk_levels_prioritize_emergency_deadlines_and_fill():
    config = load_config(ROOT / "config.json")
    result = _risk_levels(
        np.array(
            [
                config.operations.smart_emergency_current_trigger_pct,
                70.0,
                60.0,
                40.0,
            ]
        ),
        np.array([100.0, 40.0, 60.0, 100.0]),
        config,
    )
    assert result.tolist() == ["critical", "high", "medium", "low"]


def test_colocated_optional_bin_adds_no_proxy_road_distance():
    matrix = np.array(
        [
            [0, 100, 100],
            [100, 0, 0],
            [100, 0, 0],
        ],
        dtype=float,
    )
    proposal, added = _incremental_proxy_distance_m(
        [0],
        1,
        np.array([40.0, 30.0]),
        matrix,
        100.0,
        1,
    )
    assert proposal == 200.0
    assert added == 0.0


def test_capacity_selection_checks_trip_partition_not_only_total_mass():
    selected, unserved = select_capacity_feasible(
        [0, 1, 2],
        np.array([6.0, 6.0, 6.0]),
        truck_capacity_kg=10.0,
        max_trips=2,
    )
    assert selected == [0, 1]
    assert unserved == [2]
