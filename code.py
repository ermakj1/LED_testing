# MatrixPortal S3 - scrolling message queue with HTTP API
#
# POST /add      category-specific JSON payload (see send_message.py)
# POST /clear    clears the queue
# POST /register {"url": "..."} — openclaw self-registration
# GET  /         returns current queue as JSON
#
# UP button: skip current message
# DOWN button: clear queue
#
# PIR sensor on A1: display sleeps after SLEEP_TIMEOUT_SECONDS of no motion,
# greets with "Good morning/afternoon/evening" on next detection.

import os
import time
import rtc
import json
import board
import wifi
import mdns
import socketpool
import ssl
import digitalio
import displayio
import framebufferio
import rgbmatrix
import adafruit_ntp
import adafruit_requests
import adafruit_connection_manager
from adafruit_httpserver import Server, Request, Response
import renderers

PANEL_WIDTH  = 64
PANEL_HEIGHT = 32
MAX_QUEUE    = 20
DEFAULT_TTL_MINUTES   = 60
SLEEP_TIMEOUT_SECONDS = 300  # 5 minutes of no motion → sleep

# --- Display ---

displayio.release_displays()

matrix = rgbmatrix.RGBMatrix(
    width=PANEL_WIDTH,
    height=PANEL_HEIGHT,
    bit_depth=3,
    rgb_pins=[
        board.MTX_R1, board.MTX_G1, board.MTX_B1,
        board.MTX_R2, board.MTX_G2, board.MTX_B2,
    ],
    addr_pins=[board.MTX_ADDRA, board.MTX_ADDRB, board.MTX_ADDRC, board.MTX_ADDRD],
    clock_pin=board.MTX_CLK,
    latch_pin=board.MTX_LAT,
    output_enable_pin=board.MTX_OE,
)

display = framebufferio.FramebufferDisplay(matrix, auto_refresh=True)

# --- Buttons ---

btn_up = digitalio.DigitalInOut(board.BUTTON_UP)
btn_up.switch_to_input(pull=digitalio.Pull.UP)

btn_down = digitalio.DigitalInOut(board.BUTTON_DOWN)
btn_down.switch_to_input(pull=digitalio.Pull.UP)

# --- PIR ---

pir = digitalio.DigitalInOut(board.A1)
pir.switch_to_input()

last_motion_ref = [time.monotonic()]  # mutable so renderers can update it
asleep = False

# --- WiFi + NTP ---

print("Connecting to WiFi...")
wifi.radio.connect(
    os.getenv("CIRCUITPY_WIFI_SSID"),
    os.getenv("CIRCUITPY_WIFI_PASSWORD"),
)
print(f"Connected: {wifi.radio.ipv4_address}")

pool = socketpool.SocketPool(wifi.radio)

tz_offset = int(os.getenv("TIMEZONE_OFFSET", 0))
ntp = adafruit_ntp.NTP(pool, tz_offset=tz_offset, socket_timeout=10)
try:
    rtc.RTC().datetime = ntp.datetime
    t = time.localtime()
    print(f"Time synced: {t.tm_hour:02}:{t.tm_min:02}")
except Exception as e:
    print(f"NTP sync failed: {e}")

mdns_server = mdns.Server(wifi.radio)
mdns_server.hostname = "matrixportal"
mdns_server.advertise_service(service_type="_http", protocol="_tcp", port=80)

server = Server(pool)

# --- Outbound (notify openclaw) ---

_rm = adafruit_connection_manager.get_radio_socketpool(wifi.radio)
_requests = adafruit_requests.Session(_rm, adafruit_connection_manager.get_radio_ssl_context(wifi.radio))
callback_url = None

def notify_openclaw(event):
    if not callback_url:
        return
    try:
        _requests.post(callback_url, json={"event": event})
    except Exception as e:
        print(f"notify_openclaw failed: {e}")

# --- Message queue ---

message_queue = []
_deleted_ids  = set()
_next_id = 0

def _new_id():
    global _next_id
    _next_id += 1
    return _next_id

def purge_expired():
    now = time.monotonic()
    expired = [m for m in message_queue if now >= m["expires_at"]]
    for m in expired:
        message_queue.remove(m)
    if expired:
        print(f"Purged {len(expired)} expired, {len(message_queue)} remaining")

@server.route("/add", "POST")
def add_message(request: Request):
    try:
        data = json.loads(request.body)
        category = str(data.get("category", "")).lower()
        ttl = float(data.get("ttl_minutes", DEFAULT_TTL_MINUTES))
        purge_expired()
        if len(message_queue) >= MAX_QUEUE:
            return Response(request, '{"ok":false,"reason":"queue full"}', content_type="application/json", status=(429, "Too Many Requests"))
        msg = dict(data)
        msg["category"] = category
        msg["expires_at"] = time.monotonic() + ttl * 60
        msg["id"] = _new_id()
        message_queue.append(msg)
        body = json.dumps({"ok": True, "queued": len(message_queue), "ttl_minutes": ttl})
        return Response(request, body, content_type="application/json")
    except Exception as e:
        return Response(request, json.dumps({"ok": False, "reason": str(e)}), content_type="application/json", status=(400, "Bad Request"))

@server.route("/register", "POST")
def register(request: Request):
    global callback_url
    try:
        data = json.loads(request.body)
        url = str(data.get("url", "")).strip()
        if not url:
            return Response(request, '{"ok":false,"reason":"missing url"}', content_type="application/json", status=(400, "Bad Request"))
        callback_url = url
        print(f"Registered callback: {callback_url}")
        return Response(request, '{"ok":true}', content_type="application/json")
    except Exception as e:
        return Response(request, json.dumps({"ok": False, "reason": str(e)}), content_type="application/json", status=(400, "Bad Request"))

@server.route("/ui", "GET")
def serve_ui(request: Request):
    try:
        with open("/ui.html", "r") as f:
            html = f.read()
        return Response(request, html, content_type="text/html")
    except Exception as e:
        return Response(request, f"<h1>Error loading UI: {e}</h1>", content_type="text/html")

@server.route("/delete", "POST")
def delete_message(request: Request):
    try:
        data = json.loads(request.body)
        msg_id = int(data.get("id"))
        _deleted_ids.add(msg_id)
        for m in message_queue:
            if m.get("id") == msg_id:
                message_queue.remove(m)
        return Response(request, '{"ok":true}', content_type="application/json")
    except Exception as e:
        return Response(request, json.dumps({"ok": False, "reason": str(e)}), content_type="application/json", status=(400, "Bad Request"))

@server.route("/clear", "POST")
def clear_queue(request: Request):
    message_queue.clear()
    return Response(request, '{"ok":true}', content_type="application/json")

@server.route("/", "GET")
def status(request: Request):
    now = time.monotonic()
    queue_out = [
        {k: v for k, v in m.items() if k != "expires_at"} |
        {"expires_in_minutes": round((m["expires_at"] - now) / 60, 1)}
        for m in message_queue
    ]
    body = json.dumps({"count": len(queue_out), "queue": queue_out})
    return Response(request, body, content_type="application/json")

server.start(str(wifi.radio.ipv4_address), port=80)
print(f"Listening at http://matrixportal.local  ({wifi.radio.ipv4_address})")

# --- Renderers init ---

renderers.init(display, server, pir, btn_up, btn_down, last_motion_ref, SLEEP_TIMEOUT_SECONDS)

# --- Helpers ---

def clear_display():
    display.root_group = displayio.Group()

def greeting_text():
    hour = time.localtime().tm_hour
    if 5 <= hour < 12:  return "Good morning!"
    if 12 <= hour < 18: return "Good afternoon!"
    return "Good evening!"

# --- Main loop ---

clear_display()
print("Ready")

while True:
    server.poll()

    if pir.value:
        if asleep:
            print("Motion detected — waking up")
            asleep = False
            notify_openclaw("person_detected")
            result = renderers.render_greeting(greeting_text())
            clear_display()
            if result == "sleep":
                asleep = True
            elif result == "clear":
                message_queue.clear()
                time.sleep(0.3)
        last_motion_ref[0] = time.monotonic()

    if not asleep and time.monotonic() - last_motion_ref[0] > SLEEP_TIMEOUT_SECONDS:
        print("No motion — sleeping")
        clear_display()
        asleep = True

    if asleep:
        time.sleep(0.1)
        continue

    if not btn_down.value:
        message_queue.clear()
        print("Queue cleared by button")
        time.sleep(0.3)
        continue

    purge_expired()

    if message_queue:
        msg = message_queue.pop(0)
        if time.monotonic() >= msg["expires_at"]:
            print(f"Skipping expired: {msg}")
            continue
        print(f"Rendering [{msg.get('category','')}]")
        result = renderers.render(msg)
        clear_display()
        if result == "sleep":
            print("No motion mid-render — sleeping")
            asleep = True
        elif result == "clear":
            message_queue.clear()
            print("Queue cleared by button")
            time.sleep(0.3)
        elif result == "done":
            if time.monotonic() < msg["expires_at"] and msg.get("id") not in _deleted_ids:
                message_queue.append(msg)
    else:
        result = renderers.render_clock()
        if result == "clear":
            message_queue.clear()
        elif result == "sleep":
            clear_display()
            asleep = True
