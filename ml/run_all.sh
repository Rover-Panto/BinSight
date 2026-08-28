#!/usr/bin/env bash
# Runs the full BinSight ML pipeline end to end: simulate -> features -> label -> train -> serve smoke test -> tests.
# Usage: ./run_all.sh   (from the repo root)
set -e

cd "$(dirname "$0")"

echo "== 1/6 Installing dependencies =="
pip install -r requirements.txt --break-system-packages -q || pip install -r requirements.txt -q

echo "== 2/6 Simulating synthetic sensor data =="
python3 src/simulate.py

echo "== 3/6 Building features =="
python3 src/features.py

echo "== 4/6 Building labels =="
python3 src/label.py

echo "== 5/6 Training models =="
python3 src/train.py

echo "== 6/6 Serving smoke test =="
python3 src/serve.py

echo "== Running sanity tests =="
python3 tests/test_pipeline.py

echo ""
echo "Done. Model artifacts are in models/, data in data/."
