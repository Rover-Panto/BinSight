from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .analysis import save_analysis
from .config import Config, load_config
from .district import BinSpec, build_district, generate_hourly_waste, load_site_plan, save_district
from .forecast import train_forecaster
from .network import (
    ServiceNetwork,
    download_or_load_service_network,
    expand_bin_distance_matrix,
    expand_bin_duration_matrix,
    route_coordinates,
)
from .simulation import PolicyResult, SimulationScenario, run_policy


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
    save_district(bins, root / "artifacts" / "district_bins.csv")
    np.save(root / "artifacts" / "road_distance_matrix_m.npy", matrix)
    np.save(root / "artifacts" / "road_duration_matrix_s.npy", duration_matrix)
    return config, service_network, depot, bins, matrix, duration_matrix


def experiment_scenarios(config: Config) -> tuple[SimulationScenario, ...]:
    """Return the declared base and stress conditions for paired evaluation."""
    return (
        SimulationScenario(name="base"),
        SimulationScenario(
            name="high_demand",
            demand_multiplier=config.stress.high_demand_multiplier,
        ),
        SimulationScenario(
            name="traffic",
            traffic_multiplier=config.stress.traffic_multiplier,
        ),
        SimulationScenario(
            name="sensor_failure",
            sensor_missing_probability=config.stress.sensor_failure_probability,
            sensor_outlier_probability=config.stress.sensor_outlier_probability,
        ),
        SimulationScenario(
            name="truck_capacity",
            truck_capacity_multiplier=config.stress.truck_capacity_multiplier,
        ),
    )


def run_experiment(
    project_dir: str | Path,
    refresh_graph: bool = False,
    replications: int | None = None,
    scenario_names: tuple[str, ...] | None = None,
) -> dict:
    root = Path(project_dir).resolve()
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    config, service_network, depot, bins, matrix, duration_matrix = prepare_project(
        root, refresh_graph
    )
    replication_count = (
        config.operations.replications if replications is None else int(replications)
    )
    if replication_count < 2 or replication_count > 200:
        raise ValueError("replications must be between 2 and 200")
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
    training_data.to_csv(artifacts / "synthetic_forecast_training_data.csv", index=False)
    (artifacts / "forecast_evaluation.json").write_text(
        json.dumps(forecaster.evaluation, indent=2), encoding="utf-8"
    )

    results: list[PolicyResult] = []
    representative: dict[str, dict[str, list[dict]]] = {}
    seed_manifest = []
    horizon_hours = config.operations.horizon_days * 24
    for replication in range(replication_count):
        # This final seed block is intentionally disjoint from the original study,
        # the startup-artifact audit, and the dispatch-gap/optional-stop tuning trials.
        arrival_seed = config.operations.base_seed + 1_310_000 + replication * 101
        sensor_seed = config.operations.base_seed + 1_320_000 + replication * 103
        base_arrivals = generate_hourly_waste(
            bins, config, seed=arrival_seed, horizon_hours=horizon_hours
        )
        for scenario in scenarios:
            arrivals = base_arrivals * scenario.demand_multiplier
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
            )
            results.extend([fixed, smart])
            if replication == 0:
                representative[scenario.name] = {
                    "fixed": fixed.route_events,
                    "smart": smart.route_events,
                }
            seed_manifest.append(
                {
                    "scenario": scenario.name,
                    "replication": replication,
                    "arrival_seed": arrival_seed,
                    "sensor_seed": sensor_seed,
                    "demand_multiplier": scenario.demand_multiplier,
                    "traffic_multiplier": scenario.traffic_multiplier,
                    "sensor_missing_probability": scenario.sensor_missing_probability,
                    "sensor_outlier_probability": scenario.sensor_outlier_probability,
                    "truck_capacity_multiplier": scenario.truck_capacity_multiplier,
                    "policies_share_arrivals_and_sensor_noise": True,
                }
            )

    metrics = pd.DataFrame([result.metrics for result in results])
    summary, effects = save_analysis(metrics, artifacts, config.operations.base_seed + 30_000)
    (artifacts / "representative_route_events.json").write_text(
        json.dumps(representative, indent=2), encoding="utf-8"
    )
    (artifacts / "seed_manifest.json").write_text(
        json.dumps(seed_manifest, indent=2), encoding="utf-8"
    )
    write_representative_route_geojson(
        service_network,
        depot,
        bins,
        representative.get("base", next(iter(representative.values()))),
        artifacts,
        root / "data",
    )
    provenance = build_provenance(config, replication_count, scenarios)
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
        for trip_index, route in enumerate(event["route_bin_indices"], start=1):
            service_indices = [
                depot if index == -1 else bins[index].service_index for index in route
            ]
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
    return {
        "study_type": "terminating 30-day stochastic simulation with base and stress scenarios",
        "comparison": "paired common-random-number fixed vs smart policies",
        "paired_replications_per_scenario": replications,
        "scenario_count": len(scenarios),
        "total_policy_runs": replications * len(scenarios) * 2,
        "scenarios": [item.__dict__ for item in scenarios],
        "base_seed": config.operations.base_seed,
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
