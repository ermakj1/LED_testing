#!/usr/bin/env python3
"""
Jeopardy feed — sends real Jeopardy clues to the LED display.

Questions come from the jwolle1 dataset on GitHub (530k clues, seasons 1-41).
On first run it downloads the TSV and builds a local sample cache (~5000 clues).
Subsequent runs pick from the cache instantly.

Config in feeds/config.json under "jeopardy":
  {
    "enabled": true,
    "interval_minutes": 30,
    "count": 3,
    "min_value": 200,
    "max_value": 1000,
    "ttl_minutes": 35
  }

Usage:
    python3 feeds/jeopardy.py         # run on schedule
    python3 feeds/jeopardy.py --once  # send once and exit
    python3 feeds/jeopardy.py --once --refresh  # force rebuild cache
"""

import sys
import time
import json
import csv
import io
import random
import argparse
import traceback
import urllib.request
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).parent))
from util import single_instance, is_network_error

def log(msg):
    print(f"{datetime.now().strftime('%H:%M:%S')}  {msg}", flush=True)

CONFIG_PATH  = Path(__file__).parent / "config.json"
CACHE_PATH   = Path(__file__).parent / ".jeopardy_cache.json"
DATASET_URL  = (
    "https://raw.githubusercontent.com/jwolle1/jeopardy_clue_dataset"
    "/main/combined_season1-41.tsv"
)
CACHE_SIZE   = 5000   # questions kept in local cache
MIN_CLUE_LEN = 15     # skip very short/empty clues
MAX_CLUE_LEN = 200    # skip clues too long to be useful


def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}

def get_board_url():
    return load_config().get("board_url", "http://matrixportal.local:8080") + "/add"

def get_interval():
    return load_config().get("jeopardy", {}).get("interval_minutes", 30)

def get_count():
    return load_config().get("jeopardy", {}).get("count", 3)

def get_min_value():
    return load_config().get("jeopardy", {}).get("min_value", 200)

def get_max_value():
    return load_config().get("jeopardy", {}).get("max_value", 1000)

def get_ttl():
    return load_config().get("jeopardy", {}).get("ttl_minutes", 35)

def is_enabled():
    return load_config().get("jeopardy", {}).get("enabled", True)


# ── Cache management ──────────────────────────────────────────────────────────

def _clue_ok(row, min_val, max_val):
    """Return True if this TSV row is a usable clue."""
    try:
        val = int(row.get("clue_value", 0) or 0)
    except (ValueError, TypeError):
        return False
    if val < min_val or val > max_val:
        return False
    clue   = (row.get("answer") or "").strip()    # "answer" column = clue text
    answer = (row.get("question") or "").strip()  # "question" column = response
    if len(clue) < MIN_CLUE_LEN or len(clue) > MAX_CLUE_LEN:
        return False
    if not answer or len(answer) > 60:
        return False
    # Skip clues with HTML or backslashes (formatting artifacts)
    if "<" in clue or "\\" in clue or "(" in answer:
        return False
    return True


def build_cache(min_val=200, max_val=1000):
    """Download the full TSV dataset, sample CACHE_SIZE usable clues, save JSON."""
    log(f"Downloading Jeopardy dataset from GitHub (~60 MB, one-time)...")
    req = urllib.request.Request(DATASET_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    log(f"Download complete ({len(raw) // 1024 // 1024} MB). Filtering clues...")

    reader   = csv.DictReader(io.StringIO(raw), delimiter="\t")
    eligible = [row for row in reader if _clue_ok(row, min_val, max_val)]
    log(f"Found {len(eligible)} eligible clues. Sampling {CACHE_SIZE}...")

    sample = random.sample(eligible, min(CACHE_SIZE, len(eligible)))
    cache  = [
        {
            "clue":     row["answer"].strip(),
            "answer":   row["question"].strip(),
            "category": row["category"].strip().upper(),
            "value":    int(row["clue_value"] or 0),
        }
        for row in sample
    ]
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f)
    log(f"Cache built: {len(cache)} clues saved to {CACHE_PATH.name}")
    return cache


def load_cache():
    """Load cached clues from disk, or return None if missing/corrupt."""
    if not CACHE_PATH.exists():
        return None
    try:
        with open(CACHE_PATH) as f:
            data = json.load(f)
        if isinstance(data, list) and len(data) > 0:
            return data
    except Exception:
        pass
    return None


def get_clues(count, force_refresh=False):
    """Return `count` random clues, building/refreshing cache as needed."""
    cache = None if force_refresh else load_cache()
    if cache is None:
        cache = build_cache(get_min_value(), get_max_value())
    return random.sample(cache, min(count, len(cache)))


# ── Board posting ─────────────────────────────────────────────────────────────

def post_clue(board_url, clue, answer, category, value, ttl_minutes):
    payload = {
        "category":          "jeopardy",
        "clue":              clue,
        "answer":            answer,
        "jeopardy_category": category,
        "value":             value,
        "ttl_minutes":       ttl_minutes,
    }
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        board_url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def send_clues(force_refresh=False):
    board_url = get_board_url()
    count     = get_count()
    ttl       = get_ttl()

    clues = get_clues(count, force_refresh=force_refresh)
    for q in clues:
        try:
            result = post_clue(
                board_url, q["clue"], q["answer"],
                q["category"], q["value"], ttl,
            )
            log(f"Jeopardy [{q['category']} ${q['value']}]: {q['clue'][:40]}... → {result}")
        except Exception as e:
            friendly = is_network_error(e)
            if friendly:
                log(f"Error: {friendly}")
            else:
                log(f"Error posting clue: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    single_instance("jeopardy")
    parser = argparse.ArgumentParser(description="Send Jeopardy clues to LED display")
    parser.add_argument("--interval", type=float, default=None)
    parser.add_argument("--once",    action="store_true")
    parser.add_argument("--refresh", action="store_true", help="Force rebuild clue cache")
    args = parser.parse_args()

    while True:
        interval = args.interval or get_interval()
        if is_enabled():
            try:
                send_clues(force_refresh=args.refresh)
                args.refresh = False  # only force on first loop
            except Exception as e:
                friendly = is_network_error(e)
                if friendly:
                    log(f"Error: {friendly}")
                else:
                    log(f"Error: {e}")
                    log(traceback.format_exc().strip())
        else:
            log("Jeopardy disabled — sleeping")

        if args.once:
            break
        time.sleep(interval * 60)


if __name__ == "__main__":
    main()
