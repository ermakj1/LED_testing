#!/bin/bash
# Deploy code.py and lib/ to the CIRCUITPY drive.

CIRCUITPY="/Volumes/CIRCUITPY"

if [ ! -d "$CIRCUITPY" ]; then
    echo "ERROR: CIRCUITPY drive not found. Is the board plugged in?"
    exit 1
fi

cp code.py "$CIRCUITPY/code.py"
echo "Deployed code.py"

if [ -d "lib" ] && [ "$(ls -A lib)" ]; then
    cp -r lib/. "$CIRCUITPY/lib/"
    echo "Deployed lib/"
fi

echo "Done - board is restarting"
