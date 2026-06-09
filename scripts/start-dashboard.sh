#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/masyra-shorts}"
DASHBOARD_HOST="${DASHBOARD_HOST:-127.0.0.1}"
DASHBOARD_PORT="${DASHBOARD_PORT:-8765}"

cd "${APP_DIR}"

if [[ -f "${APP_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "${APP_DIR}/.env"
  set +a
fi

exec "${APP_DIR}/.venv/bin/python" -m shorts_automation.cli dashboard \
  --output-dir "${SHORTS_OUTPUT_DIR:-outputs}" \
  --host "${DASHBOARD_HOST}" \
  --port "${DASHBOARD_PORT}"
