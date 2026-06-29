#!/usr/bin/env zsh
# Pull the latest cycle for each global model and regenerate the data the
# frontend reads. Pass source ids to limit (default: all).
#   ./refresh-data.sh             # gfs + ecmwf + gem
#   ./refresh-data.sh gfs         # just GFS (fast)
set -e
cd "$(dirname "$0")"

if [[ ! -d venv ]]; then
  echo "venv/ not found — create it first:"
  echo "  python3 -m venv venv && venv/bin/pip install -r pipeline/requirements.txt"
  exit 1
fi

echo "[refresh] building model data (${@:-all sources})..."
venv/bin/python pipeline/build.py "$@"

echo "[refresh] done."
echo ""
echo "Outputs:"
du -sh data/*/ 2>/dev/null
ls -1 data/index.json
