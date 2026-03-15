#!/usr/bin/env bash
set -euo pipefail

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to run the smoke test." >&2
  exit 1
fi

python3 scripts/check_env.py
python3 -m compileall src
python3 -m pytest -q
python3 -m niche_scout.cli expand "realtor template" "therapy notes"
python3 -m niche_scout.cli score tests/fixtures/sample_scan.json
python3 -m niche_scout.cli import metrics tests/fixtures/erank_sample.csv
python3 -m niche_scout.cli enrich data/processed/latest.json --metrics tests/fixtures/erank_sample.csv
python3 -m niche_scout.cli compare data/processed/latest.json data/processed/latest.json
