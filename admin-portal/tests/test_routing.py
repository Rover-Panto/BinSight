import numpy as np

from binsight.routing import _fallback_routes, solve_routes


def test_capacity_routes_start_and_end_at_depot():
    matrix = np.array(
        [
            [0, 100, 200, 300],
            [100, 0, 100, 200],
            [200, 100, 0, 100],
            [300, 200, 100, 0],
        ],
        dtype=np.int64,
    )
    demands = np.array([60.0, 60.0, 20.0])
    plan = solve_routes([0, 1, 2], demands, matrix, 100.0, 3, 150)
    assert sorted(plan.served_bin_indices) == [0, 1, 2]
    assert all(route[0] == -1 and route[-1] == -1 for route in plan.routes)
    assert plan.distance_m > 0


def test_empty_selection_has_no_route():
    plan = solve_routes([], np.zeros(2), np.zeros((3, 3), dtype=int), 100.0, 1, 150)
    assert plan.routes == []
    assert plan.distance_m == 0


def test_deterministic_fallback_respects_capacity_and_serves_every_bin():
    matrix = np.array(
        [
            [0, 100, 200, 300],
            [100, 0, 100, 200],
            [200, 100, 0, 100],
            [300, 200, 100, 0],
        ],
        dtype=np.int64,
    )
    demands = np.array([60.0, 60.0, 20.0])
    plan = _fallback_routes([0, 1, 2], demands, matrix, 100.0, 2)
    assert plan.solver_method == "deterministic_fallback"
    assert sorted(plan.served_bin_indices) == [0, 1, 2]
    for route in plan.routes:
        load = sum(demands[index] for index in route if index != -1)
        assert load <= 100.0
