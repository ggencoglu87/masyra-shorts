#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/masyra-shorts}"
MODEL_DIR="${PIPER_MODEL_DIR:-${APP_DIR}/models/piper}"
VOICE_BASE_URL="${PIPER_VOICE_BASE_URL:-https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium}"
MODEL_NAME="${PIPER_MODEL_NAME:-en_US-lessac-medium}"

echo "Installing Piper TTS offline fallback"

if [[ ! -d "${APP_DIR}/.venv" ]]; then
  echo "Python virtualenv not found at ${APP_DIR}/.venv"
  echo "Run scripts/install-ubuntu.sh first, or set APP_DIR to the project directory."
  exit 1
fi

mkdir -p "${MODEL_DIR}"

. "${APP_DIR}/.venv/bin/activate"
python -m pip install --upgrade piper-tts

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required to download Piper voices."
  echo "Install it with: sudo apt-get install -y curl"
  exit 1
fi

MODEL_PATH="${MODEL_DIR}/${MODEL_NAME}.onnx"
CONFIG_PATH="${MODEL_DIR}/${MODEL_NAME}.onnx.json"

if [[ ! -f "${MODEL_PATH}" ]]; then
  curl -L "${VOICE_BASE_URL}/${MODEL_NAME}.onnx" -o "${MODEL_PATH}"
fi

if [[ ! -f "${CONFIG_PATH}" ]]; then
  curl -L "${VOICE_BASE_URL}/${MODEL_NAME}.onnx.json" -o "${CONFIG_PATH}"
fi

ENV_PATH="${APP_DIR}/.env"
if [[ -f "${ENV_PATH}" ]]; then
  if ! grep -q '^PIPER_BIN=' "${ENV_PATH}"; then
    echo "PIPER_BIN=${APP_DIR}/.venv/bin/piper" >> "${ENV_PATH}"
  fi
  if ! grep -q '^PIPER_MODEL_PATH=' "${ENV_PATH}"; then
    echo "PIPER_MODEL_PATH=${MODEL_PATH}" >> "${ENV_PATH}"
  fi
fi

cat <<EOF
Piper install complete.

Add or confirm these values in ${APP_DIR}/.env:

TTS_PROVIDER=piper
PIPER_BIN=${APP_DIR}/.venv/bin/piper
PIPER_MODEL_PATH=${MODEL_PATH}
EOF
