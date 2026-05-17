#!/bin/bash
# Pull latest code and rebuild the Director container.
# Run this on the Pi after changes are pushed from the Mac.

cd "$(dirname "$0")/.."
# Rebuild and restart the director; bring up homeassistant if not already running.
git pull \
  && docker compose build director \
  && docker compose up -d --no-build homeassistant \
  && docker compose up -d director
