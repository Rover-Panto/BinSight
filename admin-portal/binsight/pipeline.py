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
    route_coordinates,
)
from .simulation import PolicyResult, run_policy


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
    save_district(bins, root / "artifacts" / "district_bins.csv")
    np.save(root / "artifacts" / "road_distance_matrix_m.npy", matrix)
    return config, service_network, depot, bins, matrix


def run_experiment(
    project_dir: str | Path,
    refresh_graph: bool = False,
    replications: int | None = None,
) -> dict:
    root = Path(project_dir).resolve()
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    config, service_network, depot, bins, matrix = prepare_project(root, refresh_graph)
    replication_count = replications or config.operations.replications
    if replication_count < 2 or replication_count > 200:
        raise ValueError("replications must be between 2 and 200")

    forecaster, training_data = train_forecaster(
        bins, config, seed=config.operations.base_seed + 90_000
    )
    joblib.dump(forecaster, artifacts / "fill_forecaster.joblib")
    training_data.to_csv(artifacts / "synthetic_forecast_training_data.csv", index=False)
    (artifacts / "forecast_evaluation.json").write_text(
        json.dumps(forecaster.evaluation, indent=2), encoding="utf-8"
    )

    results: list[PolicyResult] = []
    representative: dict[str, list[dict]] = {}
    seed_manifest = []
    horizon_hours = config.operations.horizon_days * 24
    for replication in range(replication_count):
        # This final seed block is intentionally disjoint from both the original
        # study and the safety/fuel tuning trials used during model development.
        arrival_seed = config.operations.base_seed + 910_000 + replication * 101
        sensor_seed = config.operations.base_seed + 920_000 + replication * 103
        arrivals = generate_hourly_waste(
            bins, config, seed=arrival_seed, horizon_hours=horizon_hours
        )
        fixed = run_policy(
            "fixed",
            replication,
            bins,
            config,
            matrix,
            arrivals,
            sensor_seed,
            forecaster=None,
        )
        smart = run_policy(
            "smart",
            replication,
            bins,
            config,
            matrix,
            arrivals,
            sensor_seed,
            forecaster=forecaster,
        )
        results.extend([fixed, smart])
        if replication == 0:
            representative = {"fixed": fixed.route_events, "smart": smart.route_events}
        seed_manifest.append(
            {
                "replication": replication,
                "arrival_seed": arrival_seed,
                "sensor_seed": sensor_seed,
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
        service_network, depot, bins, representative, artifacts, root / "data"
    )
    provenance = build_provenance(config, replication_count)
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


def build_provenance(config: Config, replications: int) -> dict:
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
        "study_type": "terminating 30-day stochastic simulation",
        "comparison": "paired common-random-number fixed vs smart policies",
        "replications": replications,
        "base_seed": config.operations.base_seed,
        "time_unit": "hour",
        "horizon_hours": config.operations.horizon_days * 24,
        "warm_up": "none; initial empty-bin condition is part of the estimand",
        "inference_scope": "Monte Carlo uncertainty under configured assumptions, not real-world causality",
        "road_backend": "OSRM table/route services over OpenStreetMap data",
        "packages": packages,
    }
