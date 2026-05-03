#!/usr/bin/env python3
"""
Send decorative animations to the LED display on a schedule.

Available types: fireworks, rainbow, dvd

Usage:
    python3 feeds/animations.py                    # random animation every 30 min
    python3 feeds/animations.py --interval 15      # every 15 min
    python3 feeds/animations.py --type fireworks   # always fireworks
    python3 feeds/animations.py --once             # send one and exit
"""

import time
import json
import random
import argparse
import urllib.request

BOARD_URL = "http://matrixportal.local:8080/add"

ANIMATION_TYPES = ["fireworks", "rainbow", "dvd", "dvd_text", "matrix",
                   "plasma", "fire", "life", "cube"]


def send_animation(anim_type=None, duration=10):
    if anim_type is None:
        anim_type = random.choice(ANIMATION_TYPES)
    payload = {
        "category":  "animation",
        "type":      anim_type,
        "duration":  duration,
        "ttl_minutes": 1,
        "max_plays": 1,
    }
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        BOARD_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def main():
    parser = argparse.ArgumentParser(description="Send animations to LED display")
    parser.add_argument("--interval", type=float, default=30,
                        help="Minutes between animations (default: 30)")
    parser.add_argument("--type", choices=ANIMATION_TYPES, default=None,
                        help="Animation type (default: random)")
    parser.add_argument("--duration", type=float, default=10,
                        help="Seconds each animation runs (default: 10)")
    parser.add_argument("--once", action="store_true",
                        help="Send one animation and exit")
    args = parser.parse_args()

    if not args.once:
        print(f"Sending animations every {args.interval} min to {BOARD_URL}")

    while True:
        try:
            chosen = args.type or random.choice(ANIMATION_TYPES)
            result = send_animation(chosen, args.duration)
            print(f"Sent {chosen} ({args.duration}s): {result}")
        except Exception as e:
            print(f"Error: {e}")

        if args.once:
            break
        time.sleep(args.interval * 60)


if __name__ == "__main__":
    main()
