#!/bin/bash
# Pull latest code and rebuild the Director container.
# Run this on the Pi after changes are pushed from the Mac.

cd "$(dirname "$0")/.."
git pull && docker compose down && docker rm -f director 2>/dev/null; docker compose up -d --build director
