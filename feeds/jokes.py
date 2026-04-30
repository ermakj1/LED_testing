#!/usr/bin/env python3
"""
Fetch a random joke and send to LED display.

Two-part jokes (setup + punchline) are sent as two sequential messages
so the setup scrolls first, then the punchline follows.

Uses JokeAPI (free, no API key).

Usage:
    python3 feeds/jokes.py                 # one joke every 30 min
    python3 feeds/jokes.py --interval 60   # every hour
    python3 feeds/jokes.py --once          # send one joke and exit
"""

import time
import json
import argparse
import urllib.request

BOARD_URL = "http://matrixportal.local:8080/add"

def fetch_joke():
    url = "https://v2.jokeapi.dev/joke/Any?safe-mode&blacklistFlags=nsfw,religious,political,racist,sexist"
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read())

def post_joke(setup=None, delivery=None, text=None, ttl_minutes=10):
    payload = {"category": "joke", "ttl_minutes": ttl_minutes}
    if text:
        payload["text"] = text
    if setup:
        payload["setup"] = setup
    if delivery:
        payload["delivery"] = delivery
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        BOARD_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())

def main():
    parser = argparse.ArgumentParser(description="Send jokes to LED display")
    parser.add_argument("--interval", type=float, default=30, help="Minutes between jokes (default: 30)")
    parser.add_argument("--once", action="store_true", help="Send one joke and exit")
    args = parser.parse_args()

    if not args.once:
        print(f"Sending jokes every {args.interval} min to {BOARD_URL}")

    while True:
        try:
            joke = fetch_joke()
            if joke["type"] == "twopart":
                post_joke(setup=joke["setup"], delivery=joke["delivery"], ttl_minutes=10)
                print(f"Joke: {joke['setup']} / {joke['delivery']}")
            else:
                post_joke(text=joke["joke"], ttl_minutes=10)
                print(f"Joke: {joke['joke']}")
        except Exception as e:
            print(f"Error: {e}")

        if args.once:
            break
        time.sleep(args.interval * 60)

if __name__ == "__main__":
    main()
