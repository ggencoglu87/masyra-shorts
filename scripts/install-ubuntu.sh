#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/masyra-shorts"
WEB_DIR="/var/www/masyra-labs"
SERVICE_USER="${SERVICE_USER:-www-data}"

echo "Installing Masyra Labs Shorts automation on Ubuntu"
echo "App dir: ${APP_DIR}"
echo "Landing page dir: ${WEB_DIR}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script with sudo:"
  echo "sudo bash scripts/install-ubuntu.sh"
  exit 1
fi

apt-get update
apt-get install -y python3 python3-venv python3-pip ffmpeg nginx apache2-utils certbot python3-certbot-nginx rsync curl

mkdir -p "${APP_DIR}" "${WEB_DIR}"

SOURCE_DIR="$(pwd)"
if [[ "$(realpath "${SOURCE_DIR}")" != "$(realpath "${APP_DIR}")" ]]; then
  rsync -a \
    --exclude ".git" \
    --exclude ".venv" \
    --exclude "__pycache__" \
    --exclude "outputs" \
    ./ "${APP_DIR}/"
fi

if [[ -f "${APP_DIR}/public/index.html" ]]; then
  rsync -a "${APP_DIR}/public/" "${WEB_DIR}/"
fi

cd "${APP_DIR}"
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .

bash "${APP_DIR}/scripts/install-piper-ubuntu.sh"

mkdir -p "${APP_DIR}/outputs"
if [[ ! -f "${APP_DIR}/.env" ]]; then
  cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
  echo "Created ${APP_DIR}/.env. Edit API keys before live runs."
fi

chmod +x "${APP_DIR}/scripts/install-ubuntu.sh" "${APP_DIR}/scripts/install-piper-ubuntu.sh" "${APP_DIR}/scripts/daily-run.sh" "${APP_DIR}/scripts/start-dashboard.sh"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}" "${WEB_DIR}"

echo
echo "Install complete."
echo "Next steps:"
echo "1. Edit ${APP_DIR}/.env"
echo "2. Copy deploy/systemd/masyra-shorts-dashboard.service to /etc/systemd/system/"
echo "3. Copy deploy/nginx/*.conf examples into /etc/nginx/sites-available/ after review"
echo "4. Protect app.masyralabs.com with basic auth before enabling the dashboard proxy"
