#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/masyra-shorts}"

cd "${APP_DIR}"

if [[ -f "${APP_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "${APP_DIR}/.env"
  set +a
fi

exec "${APP_DIR}/.venv/bin/python" -m shorts_automation.cli daily-run --render --tts-provider "${TTS_PROVIDER:-elevenlabs}"
