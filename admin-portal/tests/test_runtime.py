from pathlib import Path

from binsight.runtime import collect_runtime_health, create_state_backup


ROOT = Path(__file__).resolve().parents[1]


def test_local_runtime_health_is_ready_for_four_bin_demo():
    result = collect_runtime_health(ROOT)
    assert result["status"] == "READY"
    assert all(item["ok"] for item in result["checks"])
    assert {item["name"] for item in result["checks"]} == {
        "configuration",
        "district",
        "road_matrices",
        "road_network",
        "planning_store",
        "local_storage",
    }


def test_state_backup_has_manifest_and_consistent_database(tmp_path):
    destination = create_state_backup(ROOT, tmp_path / "operator-backup")
    assert (destination / "backup_manifest.json").exists()
    assert (destination / "routing_plans.sqlite3").exists()
