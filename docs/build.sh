#!/usr/bin/env zsh
# Rebuild the meteoearth manual: refresh figures (Selenium) + data table, then
# compile the PDF. The local server must be running (./start) for figure capture.
set -e
cd "$(dirname "$0")/.."

PY=venv/bin/python

if [[ "$1" != "--no-figures" ]]; then
  echo "[build] capturing figures via Selenium..."
  "$PY" docs/capture_figures.py
fi

echo "[build] generating data-sources table..."
"$PY" docs/gen_data_sources.py

echo "[build] running pdflatex (x2)..."
cd docs
pdflatex -interaction=nonstopmode -halt-on-error manual.tex >/dev/null
pdflatex -interaction=nonstopmode -halt-on-error manual.tex >/dev/null

echo "[build] done -> docs/manual.pdf"
