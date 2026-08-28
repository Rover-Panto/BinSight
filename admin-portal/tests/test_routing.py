import numpy as np

from binsight.routing import (
    _fallback_routes,
    improve_route_order,
    route_distance_m,
    select_capacity_feasible,
    solve_routes,
)


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


def test_preselection_uses_same_upward_rounding_as_solver():
    demands = np.array([50.01, 49.01])
    selected, rejected = select_capacity_feasible([0, 1], demands, 100.0, 1)

    assert selected == [0]
    assert rejected == [1]


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


def test_bounded_two_opt_only_accepts_a_shorter_order_with_same_stops():
    coordinates = np.array(
        [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 2.0]]
    )
    matrix = np.rint(
        np.linalg.norm(coordinates[:, None, :] - coordinates[None, :, :], axis=2)
        * 1000
    ).astype(int)
    crossing = [-1, 0, 2, 1, 3, -1]

    improved = improve_route_order(crossing, matrix)

    assert improved[0] == improved[-1] == -1
    assert sorted(improved[1:-1]) == sorted(crossing[1:-1])
    assert route_distance_m(improved, matrix) < route_distance_m(crossing, matrix)

    protected = improve_route_order(
        crossing,
        matrix,
        protected_bin_indices=set(crossing[1:-1]),
        full_duration_matrix_s=matrix.astype(float),
    )

    def arrivals(route):
        elapsed = 0.0
        result = {}
        for origin, destination in zip(route[:-1], route[1:]):
            origin_location = 0 if origin == -1 else origin + 1
            destination_location = 0 if destination == -1 else destination + 1
            elapsed += float(
                matrix[origin_location, destination_location]
            )
            if destination != -1:
                result[destination] = elapsed
        return result

    original_arrivals = arrivals(crossing)
    protected_arrivals = arrivals(protected)
    assert all(
        protected_arrivals[index] <= original_arrivals[index]
        for index in crossing[1:-1]
    )
