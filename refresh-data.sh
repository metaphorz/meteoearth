#!/usr/bin/env zsh
# Pull the latest GFS cycle and regenerate the data files the frontend reads.
# Run this any time you want fresher data (NOAA publishes every 6 hours).
set -e
cd "$(dirname "$0")"

if [[ ! -d venv ]]; then
  echo "venv/ not found — create it first:"
  echo "  python3 -m venv venv && venv/bin/pip install -r pipeline/requirements.txt"
  exit 1
fi

echo "[refresh] fetching latest GFS cycle..."
venv/bin/python pipeline/fetch_gfs.py

echo "[refresh] encoding wind PNG + metadata..."
venv/bin/python pipeline/encode.py

echo "[refresh] done."
echo ""
echo "Outputs:"
ls -lh data/*.png data/*.json
