#!/usr/bin/env python3
"""
display_agent.py
Sends scheduled content to the LED matrix display.
Receives board events (person_detected, wifi_off) via HTTP callback.
Uses Claude API (optional) for AI-generated content.

Run:  python display_agent.py
See README.md for Windows Task Scheduler setup.
"""

import os
import sys
import json
import time
import queue
import random
import socket
import threading
import urllib.request
import urllib.error
from datetime import datetime

# ---------------------------------------------------------------------------
# Optional dependencies
# ---------------------------------------------------------------------------

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        sys.exit("Python 3.11+ required, or: pip install tomli")

try:
    import anthropic as _ant
    HAS_CLAUDE = True
except ImportError:
    HAS_CLAUDE = False

from http.server import HTTPServer, BaseHTTPRequestHandler

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))

def _load_config():
    path = os.path.join(_HERE, "config.toml")
    with open(path, "rb") as f:
        return tomllib.load(f)

_cfg = _load_config()

def _get(section, key, default=None):
    return _cfg.get(section, {}).get(key, default)

def _local_ip():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]

BOARD_URL        = _cfg["board"]["url"].rstrip("/")
CALLBACK_HOST    = _get("agent", "callback_host") or _local_ip()
CALLBACK_PORT    = int(_get("agent", "callback_port", 8090))
API_KEY          = _get("anthropic", "api_key", "")
CLAUDE_MODEL     = _get("anthropic", "model", "claude-haiku-4-5-20251001")

STOCK_SYMBOL     = _get("content", "stock_symbol",  "MSFT")
WEATHER_LAT      = float(_get("content", "weather_lat",  47.6815))
WEATHER_LON      = float(_get("content", "weather_lon", -122.2087))

ENABLE_STOCK     = bool(_get("content", "enable_stock",      True))
ENABLE_WEATHER   = bool(_get("content", "enable_weather",    True))
ENABLE_JOKES     = bool(_get("content", "enable_jokes",      True))
ENABLE_ANIMS     = bool(_get("content", "enable_animations", True))
ENABLE_ONTHISDAY = bool(_get("content", "enable_onthisday",  True))
ENABLE_CLAUDE    = bool(_get("content", "enable_claude",     True)) and HAS_CLAUDE and bool(API_KEY)

STOCK_INTERVAL   = int(_get("schedule", "stock_interval_minutes",   5))
WEATHER_INTERVAL = int(_get("schedule", "weather_interval_minutes", 30))
JOKE_INTERVAL    = int(_get("schedule", "joke_interval_minutes",    45))
ANIM_INTERVAL    = int(_get("schedule", "animation_interval_minutes", 20))
CLAUDE_INTERVAL  = int(_get("schedule", "claude_interval_minutes",  60))
ONTHISDAY_HOUR   = int(_get("schedule", "onthisday_hour", 8))  # send once at this hour

ANIM_TYPES = ["fireworks", "rainbow", "plasma", "fire", "matrix", "dvd_text", "life", "cube"]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log(msg):
    print(f"{datetime.now().strftime('%H:%M:%S')}  {msg}", flush=True)

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

_wifi_online    = True
_last_sent      = {}        # content_type → time.monotonic()
_onthisday_date = None      # date on which on-this-day was last sent
_retry_queue    = []
_retry_lock     = threading.Lock()
_event_queue    = queue.Queue()
_claude_client  = _ant.Anthropic(api_key=API_KEY) if ENABLE_CLAUDE else None

def _elapsed(key, minutes):
    return time.monotonic() - _last_sent.get(key, 0) >= minutes * 60

def _mark(key):
    _last_sent[key] = time.monotonic()

def _hour():
    return datetime.now().hour

# ---------------------------------------------------------------------------
# Board communication
# ---------------------------------------------------------------------------

def _http_get(url, timeout=8):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())

def _http_post(url, payload, timeout=5):
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def _summarize(p):
    cat = p.get("category", "")
    if cat == "stock":
        return f"{p.get('symbol','')} ${p.get('price','')} {p.get('change','')}%"
    if cat == "weather":
        return f"{p.get('condition','')} H:{p.get('high','')} L:{p.get('low','')}"
    if cat == "animation":
        return p.get("type", "")
    return str(p.get("text", p.get("setup", "")))[:60]

def board_queue_count():
    try:
        return _http_get(f"{BOARD_URL}/")["count"]
    except Exception:
        return -1

def board_add(payload):
    """Post a message to the board. Failed sends go to the retry queue."""
    try:
        _http_post(f"{BOARD_URL}/add", payload)
        log(f"→ [{payload.get('category','?')}] {_summarize(payload)}")
        return True
    except Exception as e:
        log(f"✗ send failed ({e}) — queued for retry")
        with _retry_lock:
            _retry_queue.append(payload)
        return False

def board_register():
    callback = f"http://{CALLBACK_HOST}:{CALLBACK_PORT}/"
    try:
        _http_post(f"{BOARD_URL}/register", {"url": callback})
        log(f"Registered callback: {callback}")
    except Exception as e:
        log(f"Registration failed (will retry on next wake): {e}")

def flush_retry():
    with _retry_lock:
        pending = list(_retry_queue)
        _retry_queue.clear()
    if not pending:
        return
    log(f"Flushing {len(pending)} queued message(s)")
    for payload in pending:
        try:
            _http_post(f"{BOARD_URL}/add", payload)
            log(f"  retried [{payload.get('category','?')}]")
        except Exception:
            with _retry_lock:
                _retry_queue.append(payload)

# ---------------------------------------------------------------------------
# Content fetchers
# ---------------------------------------------------------------------------

_WMO = {
    0: "clear",  1: "clear",  2: "partly cloudy",  3: "cloudy",
    45: "fog",  48: "fog",
    51: "drizzle", 53: "drizzle", 55: "drizzle",
    61: "rain",  63: "rain",  65: "rain",
    71: "snow",  73: "snow",  75: "snow",  77: "snow",
    80: "rain",  81: "rain",  82: "rain",
    85: "snow",  86: "snow",
    95: "storm", 96: "storm", 99: "storm",
}

def fetch_weather():
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={WEATHER_LAT}&longitude={WEATHER_LON}"
        f"&daily=temperature_2m_max,temperature_2m_min,"
        f"precipitation_probability_max,weathercode"
        f"&temperature_unit=fahrenheit&forecast_days=1&timezone=auto"
    )
    d = _http_get(url)["daily"]
    return {
        "category":    "weather",
        "condition":   _WMO.get(d["weathercode"][0], "cloudy"),
        "high":        round(d["temperature_2m_max"][0]),
        "low":         round(d["temperature_2m_min"][0]),
        "precip":      d["precipitation_probability_max"][0],
        "ttl_minutes": WEATHER_INTERVAL,
    }

def fetch_stock():
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{STOCK_SYMBOL}"
        f"?interval=1d&range=2d"
    )
    meta  = _http_get(url)["chart"]["result"][0]["meta"]
    state = meta.get("marketState", "CLOSED")
    if state == "CLOSED":
        return None
    price  = round(meta["regularMarketPrice"], 2)
    prev   = meta.get("chartPreviousClose", price)
    change = round((price - prev) / prev * 100, 2) if prev else 0
    return {
        "category":    "stock",
        "symbol":      STOCK_SYMBOL,
        "price":       price,
        "change":      change,
        "ttl_minutes": STOCK_INTERVAL,
    }

def fetch_joke():
    url = (
        "https://v2.jokeapi.dev/joke/Any?safe-mode"
        "&blacklistFlags=nsfw,religious,political,racist,sexist&maxLength=120"
    )
    j       = _http_get(url)
    payload = {"category": "joke", "ttl_minutes": 10, "max_plays": 1}
    if j["type"] == "twopart":
        payload["setup"]    = j["setup"]
        payload["delivery"] = j["delivery"]
    else:
        payload["text"] = j["joke"]
    return payload

def fetch_onthisday():
    today = datetime.now()
    url   = (
        f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/events"
        f"/{today.month}/{today.day}"
    )
    events = _http_get(url).get("events", [])
    if not events:
        return None
    event = random.choice(events[:10])
    text  = f"{event['year']}: {event['text']}"

    if ENABLE_CLAUDE and _claude_client:
        try:
            rsp = _claude_client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=80,
                system=(
                    "Summarize this historical event in under 70 characters "
                    "for an LED ticker display. Be concise. No quotes."
                ),
                messages=[{"role": "user", "content": text}],
            )
            text = rsp.content[0].text.strip().strip('"')
        except Exception as e:
            log(f"Claude error (on-this-day): {e}")
            text = text[:70]
    else:
        text = text[:70]

    return {"category": "news", "text": text, "ttl_minutes": 120}

# ---------------------------------------------------------------------------
# Claude content generation
# ---------------------------------------------------------------------------

def generate_claude_message(context):
    if not ENABLE_CLAUDE or not _claude_client:
        return None
    try:
        rsp = _claude_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=100,
            system=(
                "You write short messages for a 64×32 LED matrix display. "
                "Max 75 characters. Be interesting, varied, and occasionally witty. "
                "No hashtags. No quotes around the message. Plain text only."
            ),
            messages=[{"role": "user", "content": context}],
        )
        text = rsp.content[0].text.strip().strip('"')
        return {"category": "text", "text": text, "ttl_minutes": 30}
    except Exception as e:
        log(f"Claude error: {e}")
        return None

# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

def run_schedule():
    """Decide what to send based on time and elapsed intervals."""
    global _onthisday_date
    today = datetime.now().date()

    if ENABLE_WEATHER and _elapsed("weather", WEATHER_INTERVAL):
        try:
            if board_add(fetch_weather()):
                _mark("weather")
        except Exception as e:
            log(f"Weather error: {e}")

    if ENABLE_STOCK and 9 <= _hour() < 17 and _elapsed("stock", STOCK_INTERVAL):
        try:
            payload = fetch_stock()
            if payload and board_add(payload):
                _mark("stock")
        except Exception as e:
            log(f"Stock error: {e}")

    if ENABLE_JOKES and _elapsed("joke", JOKE_INTERVAL):
        try:
            if board_add(fetch_joke()):
                _mark("joke")
        except Exception as e:
            log(f"Joke error: {e}")

    if ENABLE_ANIMS and _elapsed("animation", ANIM_INTERVAL):
        payload = {
            "category": "animation",
            "type":     random.choice(ANIM_TYPES),
            "duration": 10,
            "ttl_minutes": 1,
            "max_plays": 1,
        }
        if board_add(payload):
            _mark("animation")

    if (ENABLE_ONTHISDAY
            and _onthisday_date != today
            and _hour() >= ONTHISDAY_HOUR):
        try:
            payload = fetch_onthisday()
            if payload and board_add(payload):
                _onthisday_date = today
        except Exception as e:
            log(f"On-this-day error: {e}")

    if ENABLE_CLAUDE and _elapsed("claude", CLAUDE_INTERVAL):
        h       = _hour()
        periods = {
            range(5,  12): f"It's morning ({h}am). Write something uplifting to start the day.",
            range(12, 17): f"It's afternoon ({h}pm). Write something interesting or useful.",
            range(17, 21): f"It's evening ({h}pm). Write something relaxing or fun.",
        }
        context = next(
            (v for r, v in periods.items() if h in r),
            "It's late. Write something brief and calm for a quiet room.",
        )
        payload = generate_claude_message(context)
        if payload and board_add(payload):
            _mark("claude")

# ---------------------------------------------------------------------------
# Event handling
# ---------------------------------------------------------------------------

def handle_event(event):
    global _wifi_online
    log(f"Board event: {event}")

    if event == "wifi_off":
        _wifi_online = False

    elif event == "person_detected":
        was_offline  = not _wifi_online
        _wifi_online = True

        if was_offline:
            log("WiFi back — flushing retry queue and re-registering")
            board_register()
            flush_retry()

        # If queue is empty, generate something to greet the arrival
        count = board_queue_count()
        if count == 0:
            h       = _hour()
            context = (
                f"Someone just walked into the room at "
                f"{'{}am'.format(h) if h < 12 else '{}pm'.format(h - 12 if h > 12 else h)}. "
                f"Write a short welcoming or interesting message."
            )
            payload = generate_claude_message(context)
            if payload:
                board_add(payload)

# ---------------------------------------------------------------------------
# HTTP callback server (runs in background thread)
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)
        try:
            data = json.loads(body)
            _event_queue.put(data.get("event", ""))
        except Exception:
            pass
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, *_):
        pass  # suppress default access log

def _start_callback_server():
    server = HTTPServer(("0.0.0.0", CALLBACK_PORT), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log(f"Callback server on port {CALLBACK_PORT} (reachable at {CALLBACK_HOST}:{CALLBACK_PORT})")

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    log("display_agent starting")
    if not HAS_CLAUDE:
        log("anthropic package not found — Claude features disabled")
    if ENABLE_CLAUDE:
        log(f"Claude enabled (model: {CLAUDE_MODEL})")

    _start_callback_server()
    board_register()
    run_schedule()  # send initial content immediately

    while True:
        # Drain event queue (filled by callback server thread)
        while True:
            try:
                event = _event_queue.get_nowait()
                handle_event(event)
            except queue.Empty:
                break

        run_schedule()
        time.sleep(60)

if __name__ == "__main__":
    main()
