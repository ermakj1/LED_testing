#!/bin/bash
# Deploy to the board.
# - If CIRCUITPY is mounted (USB): copies files directly.
# - Otherwise: uploads over WiFi using CircuitPython Web Workflow API.
#
# For WiFi deploy, set CIRCUITPY_WEB_API_PASSWORD in your environment
# or create a .env file with: export CIRCUITPY_WEB_API_PASSWORD=yourpassword

CIRCUITPY="/Volumes/CIRCUITPY"
BOARD_HOST="${BOARD_HOST:-matrixportal.local}"
FILES="code.py renderers.py ui.html"

# Load .env if present
if [ -f .env ]; then
    source .env
fi

deploy_usb() {
    for f in $FILES; do
        cp "$f" "$CIRCUITPY/$f" && echo "  $f"
    done
    if [ -d "lib" ] && [ "$(ls -A lib)" ]; then
        cp -r lib/. "$CIRCUITPY/lib/"
        echo "  lib/"
    fi
}

deploy_wifi() {
    if [ -z "$CIRCUITPY_WEB_API_PASSWORD" ]; then
        echo "ERROR: CIRCUITPY_WEB_API_PASSWORD not set."
        echo "Add it to .env or run: export CIRCUITPY_WEB_API_PASSWORD=yourpassword"
        exit 1
    fi
    AUTH=$(echo -n ":$CIRCUITPY_WEB_API_PASSWORD" | base64)
    for f in $FILES; do
        HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
            -X PUT "http://$BOARD_HOST/cp/files/$f" \
            -H "Authorization: Basic $AUTH" \
            -H "Content-Type: application/octet-stream" \
            --data-binary "@$f")
        if [ "$HTTP" = "201" ] || [ "$HTTP" = "204" ]; then
            echo "  $f"
        else
            echo "  $f  (HTTP $HTTP - failed)"
        fi
    done
    if [ -d "lib" ] && [ "$(ls -A lib)" ]; then
        find lib -type f | while read lf; do
            remote="$lf"
            HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
                -X PUT "http://$BOARD_HOST/cp/files/$remote" \
                -H "Authorization: Basic $AUTH" \
                -H "Content-Type: application/octet-stream" \
                --data-binary "@$lf")
            echo "  $lf  (HTTP $HTTP)"
        done
    fi
}

if [ -d "$CIRCUITPY" ]; then
    echo "USB detected — deploying to $CIRCUITPY"
    deploy_usb
else
    echo "No USB mount — deploying over WiFi to $BOARD_HOST"
    deploy_wifi
fi

echo "Done"
