#!/usr/bin/env bash
# One scheduled scan on macOS / Linux. Register with:
#   crontab -e
#   30 7 * * 1-6 /full/path/to/triangle_convergence/scripts/run_daily.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -x ".venv/bin/python" ]; then
  echo "[ERROR] .venv not found; run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

mkdir -p logs
exec .venv/bin/python -m channel_monitor daily --config "${1:-monitor.config.json}" >> logs/daily.out.log 2>&1
