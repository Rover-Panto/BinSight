"""Report recorded gates and staged revisions without changing Git or services."""

import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent.parent
SOFTWARE_GATES = {f"G{i:02}" for i in range(1, 14)}
HARDWARE_GATES = {"H01", "H02"}
SHA = re.compile(r"[0-9a-f]{40}")


def blockers(candidate, is_included, hardware=False):
    """Return outstanding requirements; malformed ledgers fail closed."""
    if not isinstance(candidate, dict) or type(candidate.get("schema_version")) is not int or candidate["schema_version"] != 1:
        raise ValueError("Unsupported candidate schema")
    components = candidate.get("components", [])
    if len(components) != 4 or {c["pr"] for c in components} != {1, 2, 3, 4}:
        raise ValueError("The candidate must track PR1, PR2, PR3 and PR4 once each")
    decisions = candidate.get("decisions", [])
    if len(decisions) != 3 or {d["id"] for d in decisions} != {"D1", "D2", "D3"}:
        raise ValueError("The candidate must record D1-D3")
    gates = candidate.get("gates", [])
    expected = SOFTWARE_GATES | HARDWARE_GATES
    if len(gates) != len(expected) or {g["id"] for g in gates} != expected:
        raise ValueError("The candidate must retain all G01-G13 and H01-H02 gates")

    result = []
    for component in components:
        sha = component.get("sha", "")
        if not SHA.fullmatch(sha):
            raise ValueError(f"Invalid commit for PR{component['pr']}")
        if component.get("review") != "accepted_for_testing":
            result.append(f"PR{component['pr']}: current candidate needs review")
        if not is_included(sha):
            result.append(f"PR{component['pr']}: {sha[:7]} is not staged on this branch")
    for decision in decisions:
        allowed = {"confirmed", "deferred"} if decision["id"] == "D2" else {"confirmed"}
        if decision.get("status") not in allowed or not decision.get("evidence"):
            result.append(f"{decision['id']}: owner decision/evidence pending")

    for gate in gates:
        gate_id = gate["id"]
        expected_level = "software" if gate_id in SOFTWARE_GATES else "hardware"
        if gate.get("level") != expected_level:
            raise ValueError(f"Wrong level for {gate_id}")
        if not hardware and gate_id in HARDWARE_GATES:
            continue
        passed = gate.get("status") == "passed"
        deferred = gate_id == "G13" and gate.get("status") == "owner_deferred" and any(
            d["id"] == "D2" and d.get("status") == "deferred" and d.get("evidence")
            for d in decisions
        )
        if not (passed or deferred) or not gate.get("evidence"):
            result.append(f"{gate_id}: {gate.get('status', 'not_run')} (evidence required)")
    return result


def is_staged(sha):
    check = subprocess.run(
        ["git", "merge-base", "--is-ancestor", sha, "HEAD"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    return check.returncode == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-ready", action="store_true", help="Exit 1 if requirements remain")
    parser.add_argument("--hardware", action="store_true", help="Include physical hardware gates")
    args = parser.parse_args()
    try:
        candidate = json.loads((ROOT / "integration/candidate.json").read_text(encoding="utf-8"))
        outstanding = blockers(candidate, is_staged, hardware=args.hardware)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"INVALID READINESS RECORD: {error}")
        return 2
    print("Recorded readiness only; this does not run integration tests or authorise a merge.")
    if outstanding:
        print("NOT READY")
        for item in outstanding:
            print(f"- {item}")
    else:
        print("Recorded gates satisfied. Verify evidence against current code and obtain owner approval.")
    return 1 if args.require_ready and outstanding else 0


if __name__ == "__main__":
    raise SystemExit(main())
