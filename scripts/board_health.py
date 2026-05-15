#!/usr/bin/env python3
"""
Board health watchdog — runs every 5 minutes via cron.

Checks board responsiveness and crash state, attempts soft recovery,
and notifies via Home Assistant when things go wrong.

Cron setup (runs as user jeff on the Pi):
    */5 * * * * /usr/bin/python3 /home/jeff/source/github.com/ermakj1/FeedMe/scripts/board_health.py >> /home/jeff/board_health.log 2>&1

Config (add to feeds/config.json):
    "health": {
        "ha_base_url":   "http://192.168.86.25:8123",   # HA local URL
        "ha_token":      "YOUR_LONG_LIVED_TOKEN",
        "ha_notify":     "notify.mobile_app_your_phone", # HA notify service
        "outlet_entity": ""                               # e.g. switch.led_panel  (leave blank until set up)
    }
"""

import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

CONFIG_PATH  = Path(__file__).parent.parent / "feeds" / "config.json"
STATE_PATH   = Path(__file__).parent / ".board_health_state.json"
BOARD_URL    = "http://192.168.86.178:8080"
TIMEOUT      = 6   # seconds per HTTP request
MAX_FAILURES = 2   # consecutive unreachable checks before acting


def log(msg):
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {msg}", flush=True)


def load_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def load_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {"consecutive_failures": 0, "last_crash_line": "", "reload_sent_at": 0}


def save_state(state):
    try:
        with open(STATE_PATH, "w") as f:
            json.dump(state, f)
    except Exception as e:
        log(f"Warning: could not save state: {e}")


# ── Board HTTP helpers ────────────────────────────────────────────────────────

def fetch_log(board_url):
    """Fetch /log from the board. Returns plain text or None on failure."""
    import re
    try:
        req = urllib.request.Request(board_url + "/log")
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            html = r.read().decode()
        m = re.search(r"<pre>(.*?)</pre>", html, re.DOTALL)
        return m.group(1).strip() if m else html
    except Exception:
        return None


def board_reload(board_url):
    """Send a soft reload (supervisor.reload()) to the board."""
    try:
        req = urllib.request.Request(
            board_url + "/reload", data=b"",
            headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Home Assistant helpers ────────────────────────────────────────────────────

def ha_notify(cfg, title, message):
    """Send a push notification via HA notify service."""
    ha_url   = cfg.get("ha_base_url", "").rstrip("/")
    token    = cfg.get("ha_token", "")
    service  = cfg.get("ha_notify", "")
    if not (ha_url and token and service):
        log("  (HA notify not configured — skipping notification)")
        return False
    # service is like "notify.mobile_app_jeff_iphone"
    # → endpoint is /api/services/notify/mobile_app_jeff_iphone
    endpoint = "/api/services/" + service.replace(".", "/", 1)
    payload  = json.dumps({"title": title, "message": message}).encode()
    try:
        req = urllib.request.Request(
            ha_url + endpoint, data=payload,
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            log(f"  HA notify sent ({r.status}): {title}")
            return True
    except Exception as e:
        log(f"  HA notify failed: {e}")
        return False


def ha_outlet_cycle(cfg, off_secs=10):
    """Turn the smart outlet off then back on. No-op if entity not configured."""
    ha_url  = cfg.get("ha_base_url", "").rstrip("/")
    token   = cfg.get("ha_token", "")
    entity  = cfg.get("outlet_entity", "").strip()
    if not entity:
        log("  (outlet_entity not configured — skipping power cycle)")
        return False

    def call(service, entity_id):
        payload = json.dumps({"entity_id": entity_id}).encode()
        req = urllib.request.Request(
            f"{ha_url}/api/services/switch/{service}", data=payload,
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status

    try:
        log(f"  Power cycling outlet {entity}...")
        call("turn_off", entity)
        time.sleep(off_secs)
        call("turn_on", entity)
        log("  Outlet back on.")
        return True
    except Exception as e:
        log(f"  Outlet cycle failed: {e}")
        return False


# ── Main health check ─────────────────────────────────────────────────────────

def run():
    cfg   = load_config().get("health", {})
    state = load_state()
    board_url = load_config().get("board_url", BOARD_URL).rstrip("/add").rstrip("/")

    log(f"Checking board at {board_url}")

    board_log = fetch_log(board_url)

    # ── Board unreachable ──────────────────────────────────────────────────────
    if board_log is None:
        state["consecutive_failures"] += 1
        n = state["consecutive_failures"]
        log(f"Board unreachable (failure #{n})")

        if n >= MAX_FAILURES:
            now = time.time()
            # Avoid spamming: only act once per 15 minutes
            if now - state.get("reload_sent_at", 0) > 900:
                log("  Attempting soft reload via /reload...")
                result = board_reload(board_url)
                log(f"  Reload result: {result}")
                state["reload_sent_at"] = now

                ha_notify(cfg, "🔴 LED Panel Offline",
                          f"Board unreachable for {n} checks. Soft reload attempted.")

                # If outlet is configured, power cycle after reload fails
                if not result.get("ok"):
                    time.sleep(8)
                    still_down = fetch_log(board_url) is None
                    if still_down:
                        log("  Reload didn't help — power cycling outlet...")
                        ha_outlet_cycle(cfg)
                        ha_notify(cfg, "⚡ LED Panel Power Cycled",
                                  "Board was unresponsive. Outlet power-cycled.")

        save_state(state)
        return

    # ── Board is up ────────────────────────────────────────────────────────────
    state["consecutive_failures"] = 0
    log("Board reachable.")

    # Check for new crash breadcrumb in this boot's log
    crash_line = ""
    for line in board_log.splitlines():
        if "Hard crash detected" in line:
            crash_line = line.strip()

    if crash_line and crash_line != state.get("last_crash_line", ""):
        # New crash since last check
        state["last_crash_line"] = crash_line
        log(f"  New crash detected: {crash_line}")
        ha_notify(cfg, "⚠️ LED Panel Crashed & Recovered",
                  f"{crash_line}\nBoard restarted automatically.")
    elif not crash_line:
        state["last_crash_line"] = ""  # clear after clean boot

    # Check if board looks recently active (optional deep check)
    lines = board_log.splitlines()
    if lines:
        last_line = lines[-1]
        log(f"  Last log: {last_line}")

    save_state(state)
    log("Done.")


if __name__ == "__main__":
    run()
