#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${1:-$HOME/demo0908/recruiter-agent}"

if [[ ! -f "$REPO_DIR/.env.cloudshell" ]]; then
  echo "[error] Missing $REPO_DIR/.env.cloudshell"
  echo "[hint] Run bootstrap from jd-agent repo first."
  exit 1
fi

cd "$REPO_DIR"
source .venv/bin/activate
set -a
source .env.cloudshell
set +a
python -m uvicorn src.main:app --host 0.0.0.0 --port 8090
