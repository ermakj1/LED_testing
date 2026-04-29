#!/usr/bin/env python3
"""
Send a message to the MatrixPortal display.

Usage:
    python3 send_message.py news     "Big headline here"
    python3 send_message.py weather  rain 72
    python3 send_message.py stock    AAPL 2.3
    python3 send_message.py calendar "2pm" "Dentist"
    python3 send_message.py text     "anything at all"

Optional last argument: ttl_minutes (default 60)
    python3 send_message.py stock AAPL -1.5 30
"""

import sys
import json
import urllib.request

BOARD_URL = "http://matrixportal.local/add"

def post(payload, ttl_minutes=60):
    payload["ttl_minutes"] = ttl_minutes
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        BOARD_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        print(json.loads(resp.read()))

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    category = args[0].lower()

    if category == "news":
        # news <text> [ttl]
        post({"category": "news", "text": args[1]},
             ttl_minutes=float(args[2]) if len(args) > 2 else 60)

    elif category == "weather":
        # weather <condition> <high> <low> <precip%> [ttl]
        post({"category": "weather", "condition": args[1],
              "high": float(args[2]), "low": float(args[3]), "precip": float(args[4])},
             ttl_minutes=float(args[5]) if len(args) > 5 else 120)

    elif category == "stock":
        # stock <symbol> <change%> [ttl]
        post({"category": "stock", "symbol": args[1], "change": float(args[2])},
             ttl_minutes=float(args[3]) if len(args) > 3 else 30)

    elif category == "calendar":
        # calendar <time> <text> [ttl]
        post({"category": "calendar", "time": args[1], "text": args[2]},
             ttl_minutes=float(args[3]) if len(args) > 3 else 120)

    else:
        # text <text> [ttl]  (generic fallback)
        text = args[1] if len(args) > 1 else category
        post({"category": "", "text": text},
             ttl_minutes=float(args[2]) if len(args) > 2 else 60)
