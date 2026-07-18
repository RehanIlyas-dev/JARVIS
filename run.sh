#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
source "$VENV_DIR/bin/activate"
python -m jarvis.main "$@"
