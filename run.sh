#!/usr/bin/env sh
# Lance IACity (Linux/macOS)
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
python -m pip install --quiet -r requirements.txt
exec python app.py
