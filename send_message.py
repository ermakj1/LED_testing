#!/usr/bin/env python3
"""
Send a message to the MatrixPortal display.

Usage:
    python3 send_message.py "AAPL +2.3%" stock 30
    python3 send_message.py "Rain at 3pm" weather 120
    python3 send_message.py "Meeting at 2pm" calendar 60
    python3 send_message.py "Big news headline" news

Arguments:
    text          message to display
    category      news | weather | calendar | stock  (default: news)
    ttl_minutes   how long to keep showing it        (default: 60)
"""

import sys
import json
import urllib.request

BOARD_URL = "http://matrixportal.local/add"

def send(text, category="news", ttl_minutes=60):
    payload = json.dumps({
        "text": text,
        "category": category,
        "ttl_minutes": ttl_minutes,
    }).encode()
    req = urllib.request.Request(
        BOARD_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        print(json.loads(resp.read()))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    text = sys.argv[1]
    category = sys.argv[2] if len(sys.argv) > 2 else "news"
    ttl = float(sys.argv[3]) if len(sys.argv) > 3 else 60
    send(text, category, ttl)
