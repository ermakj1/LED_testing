#!/usr/bin/env bash
# Installs the LED feeds watchdog as a systemd service.
# Run once on WSL2 or a Raspberry Pi — same script, both platforms.
#
# Usage:
#   chmod +x install-service.sh
#   ./install-service.sh

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_USER="$(whoami)"
SERVICE_NAME="led-feeds"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "Installing ${SERVICE_NAME} service"
echo "  Repo: ${REPO_DIR}"
echo "  User: ${RUN_USER}"

# Write the service file with repo path and current user substituted in
sed -e "s|REPO_PATH|${REPO_DIR}|g" \
    -e "s|RUN_USER|${RUN_USER}|g" \
    "${REPO_DIR}/led-feeds.service" \
    | sudo tee "${SERVICE_FILE}" > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"

echo ""
echo "Done. Useful commands:"
echo "  sudo systemctl status ${SERVICE_NAME}     # check status"
echo "  sudo journalctl -fu ${SERVICE_NAME}       # live logs"
echo "  sudo systemctl stop ${SERVICE_NAME}       # stop"
echo "  sudo systemctl restart ${SERVICE_NAME}    # restart"
