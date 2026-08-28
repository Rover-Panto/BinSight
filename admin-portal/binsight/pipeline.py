from __future__ import annotations

import hashlib
import importlib.metadata
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .analysis import save_analysis
from .config import Config, load_config
from .demand import DemandScenario, generate_demand_realization
from .district import BinSpec, build_district, load_site_plan, save_district
from .dispatch import POLICY_VERSION
from .forecast import train_forecaster
from .network import (
    ServiceNetwork,
    download_or_load_service_network,
    expand_base_distance_matrix,
    expand_base_duration_matrix,
    expand_bin_distance_matrix,
    expand_bin_duration_matrix,
    route_coordinates,
)
from .simulation import SimulationScenario, run_policy


def prepare_project(project_dir: str | Path, refresh_graph: bool = False):
    root = Path(project_dir).resolve()
    config = load_config(root / "config.json")
    site_plan_path = root / config.pilot.site_plan_file
    sites = load_site_plan(site_plan_path, config)
    service_network = download_or_load_service_network(
        config,
        sites,
        root / "data" / "subang_jaya_osrm_network.json",
        refresh=refresh_graph,
    )
    depot, bins = build_district(config, service_network, site_plan_path)
    matrix = expand_bin_distance_matrix(
        service_network, [item.service_index for item in bins]
    )
    duration_matrix = expand_bin_duration_matrix(
        service_network, [item.service_index for item in bins]
    )
    recycling_matrix = expand_base_distance_matrix(
        service_network, [item.service_index for item in bins], 1
    )
    recycling_duration = expand_base_duration_matrix(
        service_network, [item.service_index for item in bins], 1
    )
    save_district(bins, root / "artifacts" / "district_bins.csv")
    np.save(root / "artifacts" / "road_distance_matrix_m.npy", matrix)
    np.save(root / "artifacts" / "road_duration_matrix_s.npy", duration_matrix)
    np.save(
        root / "artifacts" / "recycling_road_distance_matrix_m.npy",
        recycling_matrix,
    )
    np.save(
        root / "artifacts" / "recycling_road_duration_matrix_s.npy",
        recycling_duration,
    )
    return config, service_network, depot, bins, matrix, duration_matrix


def experiment_scenarios(config: Config) -> tuple[SimulationScenario, ...]:
    """Return the declared base and stress conditions for paired evaluation."""
    return (
        SimulationScenario(
            name="normal_patterned",
            demand=DemandScenario(name="normal_patterned"),
        ),
        SimulationScenario(
            name="high_demand_seasonal",
            demand=DemandScenario(
                name="high_demand_seasonal",
                calendar_start_day=334,
                demand_multiplier=config.stress.high_demand_multiplier,
            ),
        ),
        SimulationScenario(
            name="event_heavy",
            demand=DemandScenario(
                name="event_heavy",
                calendar_start_day=60,
                event_intensity_multiplier=1.5,
                event_frequency_multiplier=2,
                add_unannounced_event=True,
            ),
        ),
        SimulationScenario(
            name="persistent_multi_day_surge",
            demand=DemandScenario(
                name="persistent_multi_day_surge",
                shared_surge_windows=((7, 16, 1.55),),
            ),
        ),
        SimulationScenario(
            name="localized_surge",
            demand=DemandScenario(
                name="localized_surge",
                local_surge_windows=((9, 20, 1.80),),
                local_surge_bin_ids=tuple(f"UGB-{index:03d}" for index in range(1, 7)),
            ),
        ),
        SimulationScenario(
            name="gradual_upward_trend",
            demand=DemandScenario(
                name="gradual_upward_trend",
                trend_per_year=1.20,
            ),
        ),
        SimulationScenario(
            name="abrupt_behavior_change",
            demand=DemandScenario(
                name="abrupt_behavior_change",
                change_point_day=12,
                change_point_multiplier=1.45,
            ),
        ),
        SimulationScenario(
            name="traffic_disruption",
            demand=DemandScenario(name="traffic_disruption"),
            traffic_multiplier=config.stress.traffic_multiplier,
        ),
        SimulationScenario(
            name="sensor_failure",
            demand=DemandScenario(name="sensor_failure"),
            sensor_missing_probability=config.stress.sensor_failure_probability,
            sensor_outlier_probability=config.stress.sensor_outlier_probability,
        ),
        SimulationScenario(
            name="reduced_truck_capacity",
            demand=DemandScenario(name="reduced_truck_capacity"),
            truck_capacity_multiplier=config.stress.truck_capacity_multiplier,
        ),
        SimulationScenario(
            name="combined_demand_operational_stress",
            demand=DemandScenario(
                name="combined_demand_operational_stress",
                calendar_start_day=334,
                demand_multiplier=1.20,
                event_intensity_multiplier=1.40,
                event_frequency_multiplier=2,
                shared_surge_windows=((6, 17, 1.45),),
                local_surge_windows=((10, 23, 1.50),),
                local_surge_bin_ids=tuple(f"UGB-{index:03d}" for index in range(1, 7)),
                change_point_day=18,
                change_point_multiplier=1.25,
                add_unannounced_event=True,
            ),
            traffic_multiplier=config.stress.traffic_multiplier,
            sensor_missing_probability=config.stress.sensor_failure_probability,
            sensor_outlier_probability=config.stress.sensor_outlier_probability,
            truck_capacity_multiplier=config.stress.truck_capacity_multiplier,
        ),
    )


def run_experiment(
    project_dir: str | Path,
    refresh_graph: bool = False,
    replications: int | None = None,
    scenario_names: tuple[str, ...] | None = None,
    artifact_set: str | None = None,
    parallel_workers: int = 1,
) -> dict:
    root = Path(project_dir).resolve()
    if artifact_set is not None and (
        not artifact_set.replace("-", "").replace("_", "").isalnum()
        or "/" in artifact_set
        or "\\" in artifact_set
    ):
        raise ValueError("artifact_set must be a simple alphanumeric, dash or underscore name")
    artifacts = root / "artifacts" / artifact_set if artifact_set else root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    config, service_network, depot, bins, matrix, duration_matrix = prepare_project(
        root, refresh_graph
    )
    recycling_matrix = np.load(
        root / "artifacts" / "recycling_road_distance_matrix_m.npy"
    )
    recycling_duration_matrix = np.load(
        root / "artifacts" / "recycling_road_duration_matrix_s.npy"
    )
    destination_matrices = {
        "recycling_facility": (recycling_matrix, recycling_duration_matrix)
    }
    replication_count = (
        config.operations.replications if replications is None else int(replications)
    )
    if replication_count < 2 or replication_count > 200:
        raise ValueError("replications must be between 2 and 200")
    worker_count = int(parallel_workers)
    if worker_count < 1 or worker_count > 8:
        raise ValueError("parallel_workers must be between 1 and 8")
    declared_scenarios = experiment_scenarios(config)
    if scenario_names is None:
        scenarios = declared_scenarios
    else:
        wanted = set(scenario_names)
        scenarios = tuple(item for item in declared_scenarios if item.name in wanted)
        unknown = sorted(wanted - {item.name for item in declared_scenarios})
        if unknown:
            raise ValueError("Unknown experiment scenarios: " + ", ".join(unknown))
        if not scenarios:
            raise ValueError("At least one experiment scenario is required")

    forecaster, training_data = train_forecaster(
        bins, config, seed=config.operations.base_seed + 90_000
    )
    joblib.dump(forecaster, artifacts / "fill_forecaster.joblib")
    training_data.to_csv(
        artifacts / "synthetic_forecast_training_data.csv.gz",
        index=False,
        compression="gzip",
    )
    (artifacts / "forecast_evaluation.json").write_text(
        json.dumps(forecaster.evaluation, indent=2), encoding="utf-8"
    )

    results: list[dict] = []
    regime_results: list[dict] = []
    representative: dict[str, dict[str, list[dict]]] = {}
    seed_manifest = []
    horizon_hours = config.operations.horizon_days * 24
    tasks = [
        (replication, scenario)
        for replication in range(replication_count)
        for scenario in scenarios
    ]

    def execute_pair(task):
        replication, scenario = task
        # Locked v2 evaluation seeds are disjoint from the original study,
        # startup audit and all +1.31m/+1.32m demand/routing development screens.
        arrival_seed = config.operations.base_seed + 1_610_000 + replication * 101
        sensor_seed = config.operations.base_seed + 1_620_000 + replication * 103
        demand = generate_demand_realization(
            bins,
            config,
            seed=arrival_seed,
            horizon_hours=horizon_hours,
            scenario=scenario.demand,
        )
        arrivals = demand.arrivals_kg
        fixed = run_policy(
            "fixed",
            replication,
            bins,
            config,
            matrix,
            duration_matrix,
            arrivals,
            sensor_seed,
            forecaster=None,
            scenario=scenario,
            demand_context=demand.context,
            destination_matrices=destination_matrices,
        )
        smart = run_policy(
            "smart",
            replication,
            bins,
            config,
            matrix,
            duration_matrix,
            arrivals,
            sensor_seed,
            forecaster=forecaster,
            scenario=scenario,
            demand_context=demand.context,
            destination_matrices=destination_matrices,
        )
        manifest = {
            "scenario": scenario.name,
            "replication": replication,
            "arrival_seed": arrival_seed,
            "sensor_seed": sensor_seed,
            "demand_scenario": asdict(scenario.demand),
            "traffic_multiplier": scenario.traffic_multiplier,
            "sensor_missing_probability": scenario.sensor_missing_probability,
            "sensor_outlier_probability": scenario.sensor_outlier_probability,
            "truck_capacity_multiplier": scenario.truck_capacity_multiplier,
            "policies_share_arrivals_and_sensor_noise": True,
            "arrival_matrix_sha256": hashlib.sha256(
                np.ascontiguousarray(arrivals).tobytes()
            ).hexdigest(),
        }
        return replication, scenario.name, fixed, smart, manifest

    if worker_count == 1:
        pair_outputs = map(execute_pair, tasks)
    else:
        pair_outputs = joblib.Parallel(
            n_jobs=worker_count,
            prefer="processes",
            return_as="generator",
        )(
            joblib.delayed(execute_pair)(task) for task in tasks
        )
    for replication, scenario_name, fixed, smart, manifest in pair_outputs:
        results.extend([fixed.metrics, smart.metrics])
        regime_results.extend(fixed.regime_metrics)
        regime_results.extend(smart.regime_metrics)
        if replication == 0:
            representative[scenario_name] = {
                "fixed": fixed.route_events,
                "smart": smart.route_events,
            }
        seed_manifest.append(manifest)

    metrics = pd.DataFrame(results)
    summary, effects = save_analysis(metrics, artifacts, config.operations.base_seed + 30_000)
    driver_columns = [
        "forecast_driven_dispatches",
        "capacity_constrained_decisions",
        "dispatch_limit_blocks",
        "sensor_uncertainty_decisions",
    ]
    (
        metrics.groupby(["scenario", "policy"], as_index=False)[driver_columns]
        .mean()
        .to_csv(artifacts / "decision_driver_summary.csv", index=False)
    )
    regime_frame = pd.DataFrame(regime_results)
    regime_frame.to_csv(artifacts / "demand_regime_metrics.csv", index=False)
    regime_numeric = [
        column
        for column in regime_frame.columns
        if column not in {"scenario", "policy", "replication", "demand_regime"}
    ]
    regime_frame.groupby(
        ["scenario", "policy", "demand_regime"], as_index=False
    )[regime_numeric].mean().to_csv(
        artifacts / "demand_regime_summary.csv", index=False
    )
    (artifacts / "representative_route_events.json").write_text(
        json.dumps(representative, indent=2), encoding="utf-8"
    )
    write_dashboard_replays(representative, artifacts)
    write_monthly_fleet_events(representative, artifacts)
    (artifacts / "seed_manifest.json").write_text(
        json.dumps(seed_manifest, indent=2), encoding="utf-8"
    )
    (artifacts / "fixed_baseline_route_audit.json").write_text(
        json.dumps(
            build_fixed_baseline_route_audit(
                config, matrix, duration_matrix, representative
            ),
            indent=2,
        ),
        encoding="utf-8",
    )
    write_representative_route_geojson(
        service_network,
        depot,
        bins,
        representative.get("normal_patterned", next(iter(representative.values()))),
        artifacts,
        root / "data",
    )
    provenance = build_provenance(
        config,
        replication_count,
        scenarios,
        artifact_set=artifact_set,
        parallel_workers=worker_count,
        distance_matrix=matrix,
        duration_matrix=duration_matrix,
    )
    (artifacts / "run_provenance.json").write_text(
        json.dumps(provenance, indent=2), encoding="utf-8"
    )
    return {
        "config": config,
        "forecast_evaluation": forecaster.evaluation,
        "summary": summary,
        "effects": effects,
        "artifacts_dir": artifacts,
    }


def write_dashboard_replays(
    representative: dict[str, dict[str, list[dict]]],
    output_dir: Path,
) -> None:
    """Write a compact subset of the 30-day events for the local website.

    The full event artifact is retained for audit, but loading tens of
    megabytes of unrelated timelines on every Streamlit refresh is unnecessary.
    """
    scenario_name = (
        "normal_patterned"
        if "normal_patterned" in representative
        else next(iter(representative))
    )
    smart_events = representative[scenario_name].get("smart", [])
    completed = [event for event in smart_events if event.get("completed", False)]
    if not completed:
        raise ValueError("Dashboard replay export requires a completed smart route")
    representative_event = max(completed, key=lambda event: event["distance_km"])
    candidates_by_vehicle: dict[str, dict] = {}
    for event in completed:
        vehicle_ids = event.get("route_vehicle_ids", [])
        vehicle_types = event.get("route_vehicle_types", [])
        for route_position, vehicle_id in enumerate(vehicle_ids):
            trip_number = route_position + 1
            rows = [
                row
                for row in event.get("timeline", [])
                if int(row.get("trip_number", -1)) == trip_number
            ]
            if not any(row.get("status") == "TRIP_COMPLETE" for row in rows):
                continue
            distance_km = sum(float(row.get("distance_km", 0.0)) for row in rows)
            candidate = {
                "event": event,
                "trip_number": trip_number,
                "vehicle_id": str(vehicle_id),
                "vehicle_type": (
                    str(vehicle_types[route_position])
                    if route_position < len(vehicle_types)
                    else "general_waste"
                ),
                "distance_km": distance_km,
            }
            prior = candidates_by_vehicle.get(str(vehicle_id))
            if prior is None or distance_km > float(prior["distance_km"]):
                candidates_by_vehicle[str(vehicle_id)] = candidate
    if not candidates_by_vehicle:
        raise ValueError("Dashboard replay export found no completed vehicle trip")
    payload = {
        "schema_version": "1.0",
        "source": "representative replication from the paired 30-day simulation",
        "scenario": scenario_name,
        "representative_smart_event": representative_event,
        "tracking_candidates": list(candidates_by_vehicle.values()),
    }
    (output_dir / "dashboard_replays.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def write_monthly_fleet_events(
    representative: dict[str, dict[str, list[dict]]],
    output_dir: Path,
) -> None:
    """Write the completed smart dispatches needed for 30-day fleet playback."""
    scenario_name = (
        "normal_patterned"
        if "normal_patterned" in representative
        else next(iter(representative))
    )
    keys = (
        "hour",
        "dispatch_minute",
        "day",
        "policy",
        "scenario",
        "distance_km",
        "trip_count",
        "routes",
        "route_destinations",
        "route_vehicle_types",
        "route_vehicle_ids",
        "route_bin_indices",
        "served_bins",
        "timeline",
        "completed",
        "completed_minute",
    )
    days: dict[str, list[dict]] = {str(day): [] for day in range(1, 31)}
    for event in representative[scenario_name].get("smart", []):
        if not event.get("completed", False):
            continue
        day = int(event.get("day", 0))
        if not 1 <= day <= 30:
            continue
        days[str(day)].append({key: event[key] for key in keys if key in event})
    for events in days.values():
        events.sort(key=lambda event: float(event.get("dispatch_minute", 0.0)))
    payload = {
        "schema_version": "1.0",
        "source": "completed smart dispatches from the representative 30-day replication",
        "scenario": scenario_name,
        "day_count": 30,
        "vehicle_ids": ["GENERAL-01", "RECYCLING-01"],
        "active_days": [int(day) for day, events in days.items() if events],
        "days": days,
    }
    (output_dir / "monthly_fleet_events.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def build_fixed_baseline_route_audit(
    config: Config,
    distance_matrix: np.ndarray,
    duration_matrix: np.ndarray,
    representative: dict[str, dict[str, list[dict]]],
) -> dict:
    """Describe and structurally validate the fixed comparator's road plans.

    The benchmark fixes *when* and *what* to collect, but deliberately gives it
    a fresh capacitated shortest-distance route at every scheduled dispatch.
    That is a strong comparator, not a claim that one static path is globally
    optimal or robust to every possible future condition.
    """
    if distance_matrix.shape != duration_matrix.shape:
        raise ValueError("Fixed-baseline audit requires matching road matrices")
    if not np.all(np.isfinite(distance_matrix)) or np.any(distance_matrix < 0):
        raise ValueError("Fixed-baseline distance matrix must be finite and non-negative")
    if not np.all(np.isfinite(duration_matrix)) or np.any(duration_matrix < 0):
        raise ValueError("Fixed-baseline duration matrix must be finite and non-negative")
    if not np.allclose(np.diag(distance_matrix), 0.0):
        raise ValueError("Fixed-baseline distance matrix diagonal must be zero")
    if not np.allclose(np.diag(duration_matrix), 0.0):
        raise ValueError("Fixed-baseline duration matrix diagonal must be zero")

    scenarios: dict[str, dict] = {}
    for scenario_name, policies in representative.items():
        events = policies.get("fixed", [])
        routes = [route for event in events for route in event.get("route_bin_indices", [])]
        invalid_endpoints = sum(
            not route or route[0] != -1 or route[-1] != -1 for route in routes
        )
        duplicate_stops = sum(
            len([index for index in route if index != -1])
            != len(set(index for index in route if index != -1))
            for route in routes
        )
        off_schedule = [
            int(event["hour"])
            for event in events
            if not (
                int(event["hour"])
                >= config.operations.fixed_interval_days * 24
                + config.operations.decision_hour
                and (
                    int(event["hour"])
                    - config.operations.fixed_interval_days * 24
                    - config.operations.decision_hour
                )
                % (config.operations.fixed_interval_days * 24)
                == 0
            )
        ]
        blocked_capacity = sum(
            row.get("status") == "COLLECTION_BLOCKED_CAPACITY"
            for event in events
            for row in event.get("timeline", [])
        )
        scenarios[scenario_name] = {
            "dispatches": len(events),
            "trips": len(routes),
            "planned_stops": sum(len(event.get("served_bins", [])) for event in events),
            "unserved_required_stops": sum(
                len(event.get("unserved_required_bins", [])) for event in events
            ),
            "collection_blocked_capacity_events": blocked_capacity,
            "route_solver_methods": dict(
                sorted(Counter(event.get("route_solver_method", "unknown") for event in events).items())
            ),
            "all_dispatches_on_fixed_schedule": not off_schedule,
            "off_schedule_hours": off_schedule,
            "all_routes_start_and_end_at_depot": invalid_endpoints == 0,
            "routes_with_duplicate_stops": duplicate_stops,
        }

    return {
        "baseline_definition": (
            "Fixed three-day service timing and all-bin service intent; a fresh "
            "capacitated shortest-distance road route is solved for each dispatch."
        ),
        "fairness": {
            "same_osrm_distance_matrix_as_dynamic": True,
            "same_osrm_duration_matrix_as_dynamic": True,
            "same_vehicle_mass_and_trip_limits_as_dynamic": True,
            "same_arrivals_and_sensor_noise_within_each_pair": True,
            "fixed_has_reoptimized_path_each_dispatch": True,
        },
        "limitations": [
            "OR-Tools returns a feasible heuristic route; this is not an exact global-optimality certificate.",
            "The fixed comparator adapts route order and capacity assignment, but not collection timing or all-bin service intent.",
            "Declared stress scenarios are bounded tests, not proof against every possible disruption.",
            "The network matrix is a cached OSM/OSRM snapshot and does not prove live road availability.",
        ],
        "matrix": {
            "location_count_including_depot": int(distance_matrix.shape[0]),
            "finite_nonnegative": True,
            "zero_diagonal": True,
            "directed_distance_matrix": not np.allclose(distance_matrix, distance_matrix.T),
            "directed_duration_matrix": not np.allclose(duration_matrix, duration_matrix.T),
        },
        "representative_replication_checks": scenarios,
    }


def write_representative_route_geojson(
    service_network: ServiceNetwork,
    depot: int,
    bins: list[BinSpec],
    representative: dict[str, list[dict]],
    output_dir: Path,
    data_dir: Path,
) -> None:
    features = []
    for policy in ("fixed", "smart"):
        events = representative.get(policy, [])
        if not events:
            continue
        event = max(events, key=lambda item: item["distance_km"])
        destinations = event.get("route_destinations", [])
        for trip_index, route in enumerate(event["route_bin_indices"], start=1):
            service_indices = [
                depot if index == -1 else bins[index].service_index for index in route
            ]
            destination_id = (
                destinations[trip_index - 1]
                if trip_index - 1 < len(destinations)
                else "waste_depot"
            )
            if destination_id == "recycling_facility":
                service_indices[0] = 1
                service_indices[-1] = 1
            coordinates = route_coordinates(
                service_network,
                service_indices,
                data_dir / "osrm_route_geometry_cache.json",
            )
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "policy": policy,
                        "day": event["day"],
                        "trip": trip_index,
                        "distance_km_for_dispatch": event["distance_km"],
                        "unload_destination": destination_id,
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[lon, lat] for lat, lon in coordinates],
                    },
                }
            )
    payload = {
        "type": "FeatureCollection",
        "name": "BinSight representative OSM-road routes",
        "crs_note": "RFC 7946 WGS84 longitude/latitude",
        "attribution": "© OpenStreetMap contributors; ODbL",
        "features": features,
    }
    (output_dir / "representative_routes.geojson").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def build_provenance(
    config: Config,
    replications: int,
    scenarios: tuple[SimulationScenario, ...],
    *,
    artifact_set: str | None = None,
    parallel_workers: int = 1,
    distance_matrix: np.ndarray | None = None,
    duration_matrix: np.ndarray | None = None,
) -> dict:
    packages = {}
    for package in [
        "simpy",
        "scikit-learn",
        "scipy",
        "pandas",
        "numpy",
        "ortools",
        "requests",
        "folium",
        "streamlit",
    ]:
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = "not installed"
    config_json = json.dumps(config.to_dict(), sort_keys=True, separators=(",", ":"))
    return {
        "study_type": (
            "terminating 30-day stochastic simulation with patterned demand, "
            "persistent regimes and operational stress scenarios"
        ),
        "comparison": "paired common-random-number fixed vs smart policies",
        "paired_replications_per_scenario": replications,
        "scenario_count": len(scenarios),
        "total_policy_runs": replications * len(scenarios) * 2,
        "parallel_workers": int(parallel_workers),
        "scenarios": [asdict(item) for item in scenarios],
        "base_seed": config.operations.base_seed,
        "artifact_set": artifact_set or "historical-v1-root",
        "policy_version": POLICY_VERSION,
        "config_sha256": hashlib.sha256(config_json.encode("utf-8")).hexdigest(),
        "forecast_model_version": "hist-gradient-boosting-multihorizon-q90-overflow-v3",
        "telemetry_contract_version": "2.1",
        "registry_version": "pilot-registry-2026-08-28",
        "road_network_version": "subang-jaya-osrm-v1",
        "distance_matrix_sha256": (
            hashlib.sha256(np.ascontiguousarray(distance_matrix).tobytes()).hexdigest()
            if distance_matrix is not None
            else None
        ),
        "duration_matrix_sha256": (
            hashlib.sha256(np.ascontiguousarray(duration_matrix).tobytes()).hexdigest()
            if duration_matrix is not None
            else None
        ),
        "simulation_time_unit": "minute",
        "horizon_hours": config.operations.horizon_days * 24,
        "warm_up": (
            f"Raw metrics use all {config.operations.horizon_days} days; post-warm-up metrics "
            f"exclude the first {config.operations.analysis_warmup_days} days for both policies"
        ),
        "inference_scope": "Monte Carlo uncertainty under configured assumptions, not real-world causality",
        "road_backend": "OSRM table/route services over OpenStreetMap data",
        "packages": packages,
    }
