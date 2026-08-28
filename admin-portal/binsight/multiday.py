from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd
from ortools.sat.python import cp_model

from .config import Config
from .fleet import trip_limit_for_stream


@dataclass(frozen=True)
class MultiDayAssignment:
    bin_index: int
    bin_id: str
    site_id: str
    waste_stream: str
    destination_id: str
    service_day: int
    deadline_day: int
    projected_fill_pct: float
    projected_load_kg: float
    reason: str


@dataclass(frozen=True)
class MultiDayPlan:
    horizon_days: int
    status: str
    assignments: tuple[MultiDayAssignment, ...]
    trips_by_day_and_stream: dict[str, int]
    unscheduled_required_bin_indices: tuple[int, ...]
    objective_m_equivalent: float

    @property
    def day_zero_bin_indices(self) -> tuple[int, ...]:
        return tuple(
            assignment.bin_index
            for assignment in self.assignments
            if assignment.service_day == 0
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "horizon_days": self.horizon_days,
            "status": self.status,
            "assignments": [asdict(item) for item in self.assignments],
            "trips_by_day_and_stream": dict(self.trips_by_day_and_stream),
            "unscheduled_required_bin_indices": list(
                self.unscheduled_required_bin_indices
            ),
            "objective_m_equivalent": self.objective_m_equivalent,
        }


def optimize_multiday_pickups(
    snapshot: pd.DataFrame,
    bins: pd.DataFrame,
    config: Config,
    destination_matrices: dict[str, tuple[np.ndarray, np.ndarray]],
) -> MultiDayPlan:
    """Create a bounded rolling assignment for pickups due in the next 2–7 days.

    The optimizer assigns each forecast-due bin no later than its conservative
    overflow day. It minimizes fleet trips, distinct site visits and premature
    low-fill service. Exact route order remains the same-day routing solver's job.
    """
    if snapshot["bin_id"].astype(str).tolist() != bins["bin_id"].astype(str).tolist():
        raise ValueError("Snapshot and district bin order must match")
    horizon = config.operations.multi_day_planning_horizon_days
    expected_shape = (len(bins) + 1, len(bins) + 1)
    for destination_id, matrices in destination_matrices.items():
        if matrices[0].shape != expected_shape or matrices[1].shape != expected_shape:
            raise ValueError(f"Invalid multiday matrix for {destination_id}")

    fill = pd.to_numeric(snapshot["fill_pct"], errors="coerce").to_numpy(float)
    weight = pd.to_numeric(snapshot["weight_kg"], errors="coerce").to_numpy(float)
    tto = pd.to_numeric(
        snapshot["time_to_overflow_hours"], errors="coerce"
    ).to_numpy(float)
    confidence = snapshot["confidence_flag"].astype(bool).to_numpy()
    risk = snapshot["risk_level"].astype(str).to_numpy()
    capacities = bins["capacity_kg"].to_numpy(float)
    capacity_litres = bins.get(
        "capacity_litres",
        pd.Series(config.waste.bin_capacity_litres, index=bins.index),
    ).to_numpy(float)
    streams = bins["waste_stream"].astype(str).tolist()
    destinations = bins["destination_id"].astype(str).tolist()

    candidates: list[int] = []
    deadline_day: dict[int, int] = {}
    required: set[int] = set()
    projected_fill: dict[tuple[int, int], float] = {}
    projected_mass: dict[tuple[int, int], int] = {}
    projected_volume_l: dict[tuple[int, int], int] = {}
    for index in range(len(bins)):
        if not confidence[index] or not np.isfinite(fill[index]):
            continue
        due_within_horizon = np.isfinite(tto[index]) and tto[index] <= horizon * 24
        emergency = risk[index] == "critical" or fill[index] >= 100.0
        economically_relevant = (
            fill[index] >= config.operations.smart_optional_min_central_fill_pct
        )
        if not (due_within_horizon or emergency or economically_relevant):
            continue
        candidates.append(index)
        if emergency:
            deadline = 0
            required.add(index)
        elif due_within_horizon:
            deadline = max(0, min(horizon - 1, math.ceil(tto[index] / 24.0) - 1))
            required.add(index)
        else:
            deadline = horizon - 1
        deadline_day[index] = deadline
        base_weight = (
            float(weight[index])
            if np.isfinite(weight[index])
            else capacities[index] * max(0.0, fill[index]) / 100.0
        )
        hourly_fill_growth = (
            max(0.0, 100.0 - fill[index]) / tto[index]
            if np.isfinite(tto[index]) and tto[index] > 0
            else 0.0
        )
        for day in range(horizon):
            service_fill = min(100.0, max(0.0, fill[index] + hourly_fill_growth * day * 24))
            service_mass = min(
                capacities[index],
                max(base_weight, capacities[index] * service_fill / 100.0),
            )
            service_volume = (
                service_fill
                / 100.0
                * capacity_litres[index]
                / config.operations.truck_compaction_ratio
            )
            projected_fill[index, day] = service_fill
            projected_mass[index, day] = max(0, int(math.ceil(service_mass)))
            projected_volume_l[index, day] = max(0, int(math.ceil(service_volume)))

    if not candidates:
        return MultiDayPlan(horizon, "NO_CANDIDATE", (), {}, (), 0.0)

    model = cp_model.CpModel()
    assignment = {
        (index, day): model.new_bool_var(f"assign_{index}_{day}")
        for index in candidates
        for day in range(horizon)
        if day <= deadline_day[index]
    }
    streams_in_scope = sorted({streams[index] for index in candidates})
    trips = {}
    for stream in streams_in_scope:
        limit = trip_limit_for_stream(stream, config.operations)
        for day in range(horizon):
            trips[stream, day] = model.new_int_var(0, limit, f"trips_{stream}_{day}")
            members = [
                assignment[index, day]
                for index in candidates
                if streams[index] == stream and (index, day) in assignment
            ]
            if not members:
                model.add(trips[stream, day] == 0)
                continue
            mass = sum(
                projected_mass[index, day] * assignment[index, day]
                for index in candidates
                if streams[index] == stream and (index, day) in assignment
            )
            volume = sum(
                projected_volume_l[index, day] * assignment[index, day]
                for index in candidates
                if streams[index] == stream and (index, day) in assignment
            )
            model.add(
                mass
                <= trips[stream, day]
                * int(math.floor(config.operations.truck_capacity_kg))
            )
            model.add(
                volume
                <= trips[stream, day]
                * int(math.floor(config.operations.truck_body_volume_m3 * 1000))
            )
            for member in members:
                model.add(member <= trips[stream, day])

    for index in candidates:
        choices = [
            assignment[index, day]
            for day in range(horizon)
            if (index, day) in assignment
        ]
        if index in required:
            model.add(sum(choices) == 1)
        else:
            model.add(sum(choices) <= 1)

    site_days = {}
    for site_id in sorted(bins.iloc[candidates]["site_id"].astype(str).unique()):
        for day in range(horizon):
            members = [
                assignment[index, day]
                for index in candidates
                if str(bins.iloc[index]["site_id"]) == site_id
                and (index, day) in assignment
            ]
            if not members:
                continue
            site_days[site_id, day] = model.new_bool_var(f"site_{site_id}_{day}")
            for member in members:
                model.add(member <= site_days[site_id, day])
            model.add(site_days[site_id, day] <= sum(members))

    objective_terms = []
    for (stream, day), variable in trips.items():
        objective_terms.append(
            int(config.operations.route_fixed_cost_m_equivalent) * variable
        )
    for (site_id, day), variable in site_days.items():
        indices = [
            index
            for index in candidates
            if str(bins.iloc[index]["site_id"]) == site_id
        ]
        representative = indices[0]
        destination = destinations[representative]
        matrix = destination_matrices.get(destination)
        if matrix is None:
            raise ValueError(f"No multiday road matrix for {destination}")
        round_trip = int(
            matrix[0][0, representative + 1]
            + matrix[0][representative + 1, 0]
        )
        objective_terms.append(round_trip * variable)
    for (index, day), variable in assignment.items():
        early_days = max(0, deadline_day[index] - day)
        low_fill_gap = max(
            0.0,
            config.operations.wasted_pickup_threshold_pct
            - projected_fill[index, day],
        )
        objective_terms.append(
            int(round(early_days * 500 + low_fill_gap * config.operations.low_fill_cost_m_per_pct))
            * variable
        )
    model.minimize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = min(
        2.0, config.operations.route_solver_milliseconds / 1000.0
    )
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    status = solver.solve(model)
    if status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
        return MultiDayPlan(
            horizon,
            solver.status_name(status),
            (),
            {},
            tuple(sorted(required)),
            0.0,
        )

    assignments = []
    scheduled_required: set[int] = set()
    for (index, day), variable in assignment.items():
        if not solver.boolean_value(variable):
            continue
        if index in required:
            scheduled_required.add(index)
        assignments.append(
            MultiDayAssignment(
                bin_index=index,
                bin_id=str(bins.iloc[index]["bin_id"]),
                site_id=str(bins.iloc[index]["site_id"]),
                waste_stream=streams[index],
                destination_id=destinations[index],
                service_day=day,
                deadline_day=deadline_day[index],
                projected_fill_pct=round(projected_fill[index, day], 3),
                projected_load_kg=float(projected_mass[index, day]),
                reason=(
                    "forecast deadline"
                    if index in required
                    else "economical consolidation"
                ),
            )
        )
    assignments.sort(key=lambda item: (item.service_day, item.waste_stream, item.bin_id))
    trip_counts = {
        f"day_{day}:{stream}": solver.value(variable)
        for (stream, day), variable in sorted(trips.items())
        if solver.value(variable) > 0
    }
    return MultiDayPlan(
        horizon,
        solver.status_name(status),
        tuple(assignments),
        trip_counts,
        tuple(sorted(required - scheduled_required)),
        float(solver.objective_value),
    )
