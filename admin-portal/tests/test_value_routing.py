import numpy as np

from binsight.routing import solve_value_routes


def _matrices(count):
    size = count + 1
    distance = np.full((size, size), 100, dtype=int)
    duration = np.full((size, size), 60.0)
    np.fill_diagonal(distance, 0)
    np.fill_diagonal(duration, 0)
    return distance, duration


def _solve(candidates, mandatory, benefits, volumes=None, fixed=1000):
    count = len(benefits)
    distance, duration = _matrices(count)
    return solve_value_routes(
        candidates,
        mandatory,
        np.full(count, 50.0),
        np.asarray(volumes if volumes is not None else [0.1] * count),
        distance,
        duration,
        np.asarray(benefits, dtype=float),
        100.0,
        1.0,
        1,
        60.0,
        3600.0,
        fixed,
        0.0,
        0.0,
        np.zeros(count),
        100,
    )


def test_optional_trip_is_deferred_when_avoided_loss_does_not_cover_dispatch():
    plan = _solve([0], [], [100.0])
    assert plan.routes == []
    assert plan.dropped_bin_indices == [0]
    assert plan.dispatch_reason in {"wait_has_lower_expected_cost", "no_positive_value_route"}


def test_emergency_stop_remains_mandatory_even_with_negative_trip_value():
    plan = _solve([0], [0], [0.0])
    assert plan.routes
    assert plan.served_bin_indices == [0]
    assert plan.dispatch_reason == "emergency_service_constraint"


def test_compacted_volume_constraint_prevents_an_overfilled_trip():
    plan = _solve([0, 1], [], [10_000.0, 10_000.0], volumes=[0.6, 0.6], fixed=100)
    assert len(plan.served_bin_indices) == 1
    assert len(plan.dropped_bin_indices) == 1
    assert plan.route_volumes_m3[0] <= 1.0


def test_one_truck_orders_equal_deadlines_so_both_arrivals_are_on_time():
    distance = np.array(
        [[0, 100, 100], [100, 0, 100], [100, 100, 0]], dtype=int
    )
    duration = distance.astype(float)
    plan = solve_value_routes(
        [0, 1],
        [0, 1],
        np.array([50.0, 50.0]),
        np.array([0.1, 0.1]),
        distance,
        duration,
        np.array([1000.0, 1000.0]),
        100.0,
        1.0,
        1,
        60.0,
        3600.0,
        0,
        0.0,
        0.0,
        np.zeros(2),
        100,
        arrival_deadline_s_by_bin=np.array([300.0, 300.0]),
    )

    assert len(plan.routes) == 1
    assert set(plan.served_bin_indices) == {0, 1}
    for arrivals in plan.route_arrival_times_s:
        assert all(arrival <= 300.0 for arrival in arrivals.values())


def test_impossible_deadlines_dispatch_feasible_route_as_soon_as_possible():
    distance, duration = _matrices(2)
    plan = solve_value_routes(
        [0, 1],
        [0, 1],
        np.array([50.0, 50.0]),
        np.array([0.1, 0.1]),
        distance,
        duration,
        np.array([1000.0, 1000.0]),
        100.0,
        1.0,
        1,
        60.0,
        3600.0,
        0,
        0.0,
        0.0,
        np.zeros(2),
        100,
        arrival_deadline_s_by_bin=np.array([30.0, 30.0]),
    )

    assert plan.routes
    assert set(plan.served_bin_indices) == {0, 1}
    assert "deadline_relaxed" in plan.solver_method
    assert plan.dispatch_reason == "deadline_infeasible_serve_asap"
