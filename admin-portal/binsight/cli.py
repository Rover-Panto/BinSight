from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import prepare_project, run_experiment


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="BinSight Focus C OSM routing simulation")
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare", help="Download/cache OSM and build district")
    prepare.add_argument("--refresh-map", action="store_true")
    run = subparsers.add_parser("run", help="Run paired 30-day experiment")
    run.add_argument("--refresh-map", action="store_true")
    run.add_argument("--replications", type=int, default=None)
    args = parser.parse_args()
    if args.command == "prepare":
        config, service_network, _, bins, _ = prepare_project(project_root(), args.refresh_map)
        print(
            f"Prepared {config.pilot.label}: {service_network.service_count} OSM-routed "
            f"service points, {len(bins)} bins."
        )
        return
    result = run_experiment(project_root(), args.refresh_map, args.replications)
    print(f"Completed. Results: {result['artifacts_dir']}")
    print(result["effects"][["metric", "beneficial_change_pct_vs_fixed"]].to_string(index=False))


if __name__ == "__main__":
    main()
