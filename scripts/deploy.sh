#!/bin/bash
# Deploy to the board.
# - If CIRCUITPY is mounted (USB): copies files directly.
# - Otherwise: uploads over WiFi via the board's /upload endpoint (port 8080).

CIRCUITPY="/Volumes/CIRCUITPY"
BOARD_HOST="${BOARD_HOST:-matrixportal.local}"
FILES="code.py renderers.py ui.html boot.py"
FORCE_WIFI=false
WITH_LIB=false

for arg in "$@"; do
    case "$arg" in
        --wifi) FORCE_WIFI=true ;;
        --with-lib) WITH_LIB=true ;;
    esac
done

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
    put_file() {
        local src="$1" dst="$2"
        HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
            -X POST "http://$BOARD_HOST:8080/upload" \
            -H "X-Path: $dst" \
            -H "Content-Type: application/octet-stream" \
            --data-binary "@$src")
        if [ "$HTTP" = "200" ]; then
            echo "  $dst"
        else
            echo "  $dst  (HTTP $HTTP - failed)"
        fi
    }

    for f in $FILES; do
        put_file "$f" "$f"
    done
    if [ "$WITH_LIB" = true ] && [ -d "lib" ] && [ "$(ls -A lib)" ]; then
        find lib -type f -not -name ".DS_Store" | while read lf; do
            put_file "$lf" "$lf"
        done
    fi

    echo "  [reloading board]"
    curl -s -X POST "http://$BOARD_HOST:8080/reload" > /dev/null
}

if [ -d "$CIRCUITPY" ] && [ "$FORCE_WIFI" = false ]; then
    echo "USB detected — deploying to $CIRCUITPY"
    deploy_usb
else
    if [ -d "$CIRCUITPY" ] && [ "$FORCE_WIFI" = true ]; then
        echo "Unmounting $CIRCUITPY before WiFi deploy..."
        diskutil unmount "$CIRCUITPY"
        sleep 1
    fi
    echo "Deploying over WiFi to $BOARD_HOST"
    deploy_wifi
fi

echo "Done"
