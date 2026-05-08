#!/usr/bin/env python3
"""
LED Matrix Emulator — mirrors the board's HTTP API and renders a 64×32
display in the browser.

Usage:
    python3 emulator.py [--port 8080]

Then open http://localhost:8080/emulator

To route all feeds here instead of the real board, set:
    "board_url": "http://localhost:8080"
in feeds/config.json (or the web UI's Settings tab).
"""

import argparse
import json
import time
import uuid
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

_lock    = threading.Lock()
_queue   = []      # list of message dicts
_uploads = {}      # board_path (str) -> bytes


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _expired(msg):
    ttl   = msg.get("ttl_minutes")
    added = msg.get("_added", 0)
    return ttl is not None and (time.time() - added) > ttl * 60

def _clean():
    global _queue
    _queue = [m for m in _queue if not _expired(m)]

def _json(handler, data, status=200):
    body = json.dumps(data).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", len(body))
    handler.end_headers()
    handler.wfile.write(body)

def _read_body(handler):
    length = int(handler.headers.get("Content-Length", 0))
    return handler.rfile.read(length) if length else b""


# ─── Request handler ──────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass  # silence per-request access log

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path

        if path == "/" or path == "":
            with _lock:
                _clean()
                _json(self, {"status": "emulator", "queue_size": len(_queue)})

        elif path == "/queue":
            with _lock:
                _clean()
                _json(self, {"queue": list(_queue)})

        elif path == "/img":
            qs   = parse_qs(parsed.query)
            key  = qs.get("path", [""])[0]
            with _lock:
                data = _uploads.get(key)
            if data:
                self.send_response(200)
                self.send_header("Content-Type", "image/bmp")
                self.send_header("Content-Length", len(data))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404)
                self.end_headers()

        elif path == "/emulator":
            body = HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/add":
            raw = _read_body(self)
            try:
                msg = json.loads(raw)
            except Exception:
                msg = {}
            msg["_added"] = time.time()
            msg["_id"]    = str(uuid.uuid4())[:8]

            cat    = msg.get("category", "")
            ticker = msg.get("ticker") or msg.get("symbol")
            name   = msg.get("name")
            key    = (cat, ticker or name or "")

            with _lock:
                _clean()
                _queue[:] = [
                    m for m in _queue
                    if (m.get("category"),
                        m.get("ticker") or m.get("symbol") or m.get("name") or "") != key
                ]
                _queue.append(msg)
            _json(self, {"ok": True, "queue_size": len(_queue)})

        elif path == "/upload":
            board_path = self.headers.get("X-Path", "/img.bmp")
            data = _read_body(self)
            with _lock:
                _uploads[board_path] = data
            _json(self, {"ok": True, "path": board_path})

        elif path == "/queue/clear":
            with _lock:
                _queue.clear()
            _json(self, {"ok": True})

        else:
            self.send_response(404)
            self.end_headers()


# ─── Embedded UI ──────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>LED Matrix Emulator</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #111; color: #bbb;
  font-family: 'Courier New', monospace;
  padding: 14px; min-height: 100vh;
}
h1 { font-size: 12px; color: #4fc; letter-spacing: 1px; margin-bottom: 12px; }
.layout { display: flex; gap: 16px; align-items: flex-start; }
#display-area { flex-shrink: 0; }
#display-wrap {
  border: 1px solid #1e1e1e; border-radius: 8px; overflow: hidden;
  box-shadow: 0 0 40px rgba(0,255,180,0.05), 0 2px 20px rgba(0,0,0,0.6);
}
canvas { display: block; }
#controls { margin-top: 8px; display: flex; align-items: center; gap: 6px; }
button {
  background: #1c1c1c; border: 1px solid #2a2a2a; color: #888;
  padding: 3px 10px; border-radius: 3px; cursor: pointer;
  font-family: 'Courier New', monospace; font-size: 11px;
  transition: color 0.1s, border-color 0.1s;
}
button:hover { color: #ccc; border-color: #444; }
button.on { border-color: #4fc; color: #4fc; }
#btn-clear { color: #633; border-color: #2a1a1a; }
#btn-clear:hover { color: #f66; border-color: #633; }
#msg-info { font-size: 11px; color: #444; margin-left: 4px; }
#sidebar { flex: 1; min-width: 200px; max-width: 280px; }
#q-header { font-size: 10px; color: #444; margin-bottom: 6px; letter-spacing: 1px; }
.qi {
  background: #161616; border: 1px solid #202020; border-left: 3px solid #2a2a2a;
  padding: 5px 8px; margin-bottom: 3px; border-radius: 2px; cursor: pointer;
  font-size: 11px; transition: border-color 0.1s, background 0.1s;
}
.qi:hover { background: #1a1a1a; border-left-color: #4fc; }
.qi.active { border-left-color: #4fc; background: #0d1a14; }
.qi-cat { font-weight: bold; font-size: 10px; letter-spacing: 0.5px; text-transform: uppercase; }
.qi-sum { color: #666; margin-top: 1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.qi-ttl { color: #333; font-size: 10px; margin-top: 2px; }
#q-empty { color: #2a2a2a; font-size: 11px; padding: 12px 0; }
</style>
</head>
<body>
<h1>&#9632; LED MATRIX EMULATOR &nbsp; 64&times;32</h1>
<div class="layout">
  <div id="display-area">
    <div id="display-wrap">
      <canvas id="led" width="640" height="320"></canvas>
    </div>
    <div id="controls">
      <button onclick="prevMsg()">&#9664;</button>
      <button onclick="nextMsg()">&#9654;</button>
      <button id="btn-auto" class="on" onclick="toggleAuto()">AUTO</button>
      <button id="btn-clear" onclick="clearQueue()">CLEAR</button>
      <span id="msg-info"></span>
    </div>
  </div>
  <div id="sidebar">
    <div id="q-header">QUEUE</div>
    <div id="q-list"></div>
  </div>
</div>

<script>
// ─── Two-canvas architecture ──────────────────────────────────────────────────
//  brd  (64×32)  = board-resolution canvas — we draw here in real board coords
//  led  (640×320) = main display — flush() reads brd pixels → LED dot per pixel
const led  = document.getElementById('led');
const ctx  = led.getContext('2d');
const S    = 10;   // scale: 1 board pixel = 10×10 px on led canvas

const brd  = document.createElement('canvas');
brd.width  = 64; brd.height = 32;
const bctx = brd.getContext('2d', {willReadFrequently: true});
bctx.imageSmoothingEnabled = false;

// Pre-rendered dark LED grid (unlit dots) — drawn once, reused every frame
const bgOff = document.createElement('canvas');
bgOff.width = 640; bgOff.height = 320;
{
  const bc = bgOff.getContext('2d');
  bc.fillStyle = '#000'; bc.fillRect(0, 0, 640, 320);
  bc.fillStyle = '#0b0b0b';
  for (let y = 0; y < 32; y++)
    for (let x = 0; x < 64; x++) {
      bc.beginPath();
      bc.arc(x*S + S/2, y*S + S/2, 3.5, 0, Math.PI*2);
      bc.fill();
    }
}

// ─── Board drawing primitives ─────────────────────────────────────────────────
// Coordinates are in board pixels (0–63 x, 0–31 y).
// bText y = center of text, matching CircuitPython label.y convention.
// Scale 1 → ~6×8 px chars (terminalio font); scale 2 → ~12×16 px chars.

function bClear(color) { bctx.fillStyle = color || '#000'; bctx.fillRect(0,0,64,32); }
function bFill(color, x, y, w, h) { bctx.fillStyle = color; bctx.fillRect(x,y,w,h); }

function bText(str, x, y, color, scale) {
  scale = scale || 1;
  bctx.save();
  // Stretch horizontally 1.2× so 5px-wide browser chars → ~6px (terminalio width)
  bctx.scale(1.2, 1);
  bctx.font = `${8 * scale}px 'Courier New', monospace`;
  bctx.fillStyle = color;
  bctx.textAlign = 'left';
  bctx.textBaseline = 'middle';
  bctx.fillText(str, x / 1.2, y);
  bctx.restore();
}

function bTextC(str, y, color, scale) {
  scale = scale || 1;
  const x = Math.floor((64 - str.length * 6 * scale) / 2);
  bText(str, Math.max(0, x), y, color, scale);
}

// Scrolling text clipped to display width; returns text width in board pixels.
function bScroll(str, y, color, boardPx) {
  bctx.save();
  bctx.beginPath(); bctx.rect(0, y - 4, 64, 9); bctx.clip();
  bctx.scale(1.2, 1);
  bctx.font = "8px 'Courier New', monospace";
  bctx.fillStyle = color;
  bctx.textAlign = 'left'; bctx.textBaseline = 'middle';
  bctx.fillText(str, (64 - boardPx) / 1.2, y);
  bctx.restore();
  return str.length * 6;   // estimated board-pixel width
}

// ─── Flush: board pixels → LED dots ──────────────────────────────────────────
function flush() {
  ctx.drawImage(bgOff, 0, 0);
  const px = bctx.getImageData(0, 0, 64, 32).data;

  // Batch pixels by quantized color for performance (one path per color group)
  const groups = new Map();
  for (let y = 0; y < 32; y++) {
    for (let x = 0; x < 64; x++) {
      const i = (y * 64 + x) * 4;
      const r = px[i], g = px[i+1], b = px[i+2], a = px[i+3];
      if (r + g + b < 18 && a < 30) continue;
      const key = ((r & 0xF8) << 16) | ((g & 0xF8) << 8) | (b & 0xF8);
      if (!groups.has(key)) groups.set(key, {r: r&0xF8, g: g&0xF8, b: b&0xF8, pts: []});
      const p = groups.get(key).pts;
      p.push(x * S + S/2, y * S + S/2);
    }
  }
  for (const {r, g, b, pts} of groups.values()) {
    const col = `rgb(${r},${g},${b})`;
    ctx.fillStyle = col; ctx.shadowColor = col; ctx.shadowBlur = 4;
    ctx.beginPath();
    for (let i = 0; i < pts.length; i += 2) {
      ctx.moveTo(pts[i] + 4, pts[i+1]);   // moveTo prevents connecting lines
      ctx.arc(pts[i], pts[i+1], 4, 0, Math.PI * 2);
    }
    ctx.fill();
  }
  ctx.shadowBlur = 0;
}

// ─── State ────────────────────────────────────────────────────────────────────
let queue = [], idx = 0, autoAdv = true;
let frame = 0, msgStartFrame = 0, scrollPx = 0;
const FPS = 30, FRAMES_PER_MSG = FPS * 8;
const _imgCache = {};
const DAYS = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
const MONS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

// ─── Clock color (time-of-day, matching renderers.py _clock_color) ────────────
function clockColor() {
  const h = new Date().getHours();
  if (h >= 5  && h < 8)  return '#ff6600';  // dawn
  if (h >= 8  && h < 17) return '#ffffff';  // day
  if (h >= 17 && h < 20) return '#ff8800';  // dusk
  return '#4466ff';                           // night
}

// ─── Renderers — y values match renderers.py exactly ─────────────────────────

function renderClock() {
  bClear('#000');
  const now     = new Date();
  const h       = now.getHours() % 12 || 12;
  const timeStr = `${h}:${String(now.getMinutes()).padStart(2,'0')}`;
  const dateStr = `${DAYS[now.getDay()]} ${MONS[now.getMonth()]} ${now.getDate()}`;
  const cc      = clockColor();

  // time_grp.y=10 scale=2 → group top at y=10, char height=16, center=18
  bTextC(timeStr, 18, cc, 2);
  // date_lbl.y=25 scale=1
  bTextC(dateStr, 25, '#2e2e2e', 1);
  // Seconds bar at bottom row (y=31)
  const barW = Math.max(1, Math.floor(now.getSeconds() * 64 / 60));
  const dr = (parseInt(cc.slice(1,3),16)>>2), dg = (parseInt(cc.slice(3,5),16)>>2), db = (parseInt(cc.slice(5,7),16)>>2);
  bFill(`rgb(${dr},${dg},${db})`, 0, 31, barW, 1);
  flush();
}

function renderWeather(msg) {
  bClear('#000a18');
  const cond   = (msg.condition || '').toLowerCase();
  const high   = msg.high, low = msg.low, precip = msg.precip, city = msg.city || '';
  const ifr    = Math.floor(frame / 3);

  // Icon: 16×16 source at scale=2 → occupies board columns 0–31
  drawWeatherIconBrd(cond, ifr);

  // Text on right half (text_x=34 in renderers.py)
  if (city) {
    bText(city.substring(0,5),       34, 5,  '#cccccc', 1);
    if (high   != null) bText(`H:${Math.round(high)}`, 34, 15, '#ff8844', 1);
    if (low    != null) bText(`L:${Math.round(low)}`,  34, 25, '#4499ff', 1);
  } else {
    if (high   != null) bText(`H:${Math.round(high)}`,  34, 5,  '#ff8844', 1);
    if (low    != null) bText(`L:${Math.round(low)}`,   34, 15, '#4499ff', 1);
    if (precip != null) bText(`${Math.round(precip)}%`, 34, 25, '#44ccff', 1);
  }
  flush();
}

// Weather icon: 16×16 source pixels each drawn 2×2 board px (= 32×32 board area)
function drawWeatherIconBrd(cond, fr) {
  const p2 = (sx, sy, c) => {
    if (sx>=0 && sx<16 && sy>=0 && sy<16) bFill(c, sx*2, sy*2, 2, 2);
  };
  const CLOUD = [[4,2],[5,2],[6,2],[7,2],[3,3],[4,3],[5,3],[6,3],[7,3],[8,3],[9,3],
                 [2,4],[3,4],[4,4],[5,4],[6,4],[7,4],[8,4],[9,4],[10,4],[11,4],
                 [2,5],[3,5],[4,5],[5,5],[6,5],[7,5],[8,5],[9,5],[10,5],[11,5]];

  if (cond.includes('sun') || cond.includes('clear') || cond.includes('fair')) {
    for (let sy=0; sy<16; sy++) for (let sx=0; sx<16; sx++) {
      const d = Math.sqrt((sx-7.5)**2 + (sy-7.5)**2);
      if      (d <= 3.5) p2(sx, sy, '#ffee00');
      else if (d <= 4.5) p2(sx, sy, '#ff8800');
    }
    const rays = [[7,1],[11,2],[13,6],[12,10],[8,13],[4,11],[2,7],[3,3]];
    for (let i=0; i<rays.length; i++) p2(rays[i][0], rays[i][1], (i+fr)%2===0 ? '#ffdd00':'#ff5500');

  } else if (cond.includes('rain') || cond.includes('shower') || cond.includes('drizzle')) {
    for (const [x,y] of CLOUD) p2(x, y, '#777');
    for (let d=0; d<7; d++) {
      const ry = 9 + ((Math.floor(fr/2)+d*3) % 7);
      p2(1+d*2, ry, '#4488ff'); if(ry>0) p2(1+d*2, ry-1, '#8899ff');
    }
  } else if (cond.includes('snow') || cond.includes('blizzard')) {
    for (const [x,y] of CLOUD) p2(x, y, '#aaa');
    for (let d=0; d<6; d++) {
      const side = Math.floor(fr/4)%2===0?1:-1;
      const sx = Math.max(0, 1+d*2 + (Math.floor(fr/8)%2)*side);
      const sy = 9 + ((Math.floor(fr/3)+d*4) % 7);
      if (sx<16) p2(sx, sy, '#ddeeff');
    }
  } else if (cond.includes('storm') || cond.includes('thunder')) {
    const SC = [[4,1],[5,1],[6,1],[7,1],[3,2],[4,2],[5,2],[6,2],[7,2],[8,2],[9,2],
                [2,3],[3,3],[4,3],[5,3],[6,3],[7,3],[8,3],[9,3],[10,3],[11,3]];
    for (const [x,y] of SC) p2(x, y, '#555');
    for (let d=0; d<5; d++) { const ry=8+((Math.floor(fr/2)+d*3)%6); p2(2+d*2,ry,'#4488ff'); }
    if (fr%24<3) for (const [x,y] of [[6,8],[5,9],[6,9],[5,10],[6,10],[5,11]]) p2(x,y,'#ffffaa');
  } else {
    // cloud
    const cc2 = Math.floor(fr/4)%2===0 ? '#888':'#666';
    const CCLOUD = [[4,3],[5,3],[6,3],[7,3],[3,4],[4,4],[5,4],[6,4],[7,4],[8,4],[9,4],
                    [2,5],[3,5],[4,5],[5,5],[6,5],[7,5],[8,5],[9,5],[10,5],[11,5],
                    [2,6],[3,6],[4,6],[5,6],[6,6],[7,6],[8,6],[9,6],[10,6],[11,6]];
    for (const [x,y] of CCLOUD) p2(x, y, cc2);
  }
}

function renderStock(msg) {
  const sym    = (msg.symbol || msg.ticker || '???').toUpperCase();
  const price  = parseFloat(msg.price  || 0);
  const change = parseFloat(msg.change || msg.change_pct || 0);
  const isUp   = change >= 0;
  const chgC   = isUp ? '#00ff44' : '#ff3300';
  const sign   = isUp ? '+' : '-';
  const showPct = Math.floor(frame/90)%2===0;
  const dolCh  = Math.abs(price - (price/(1+change/100)||price));
  const chgStr = showPct ? `${sign}${Math.abs(change).toFixed(2)}%` : `${sign}$${dolCh.toFixed(2)}`;

  bClear(isUp ? '#001500' : '#150000');
  bText(sym,                   2, 6,  '#ffffff', 1);
  bText(`$${price.toFixed(2)}`,2, 16, '#aaaaaa', 1);
  bText(chgStr,                2, 26, chgC,      1);
  flush();
}

function renderBitcoin(msg) {
  const price  = parseFloat(msg.price_usd || 0);
  const change = parseFloat(msg.change_pct_24h || 0);
  const isUp   = change >= 0;
  const chgStr = `${isUp?'+':''}${change.toFixed(2)}%`;

  bClear('#000');
  bText('BTC', 2, 6, '#ff9922', 1);
  bTextC('$'+Math.round(price).toLocaleString('en-US'), 16, '#dddddd', 1);
  bTextC(chgStr, 26, isUp ? '#00ff44':'#ff3300', 1);
  flush();
}

function renderWord(msg) {
  bClear('#000a10');
  const word = (msg.word || 'WORD').toUpperCase().substring(0,10);
  const pos  = msg.pos ? `(${msg.pos})` : '';
  const defn = msg.definition || '';

  // word_lbl x=2 y=6; pos_lbl x=2 y=15 (from renderers.py)
  bText(word, 2, 6,  '#00ccff', 1);
  if (pos) bText(pos.substring(0,12), 2, 15, '#888888', 1);
  const tw = bScroll(defn, 24, '#cccccc', scrollPx);
  if (scrollPx > 64 + tw) scrollPx = 0;
  flush();
}

function renderHistory(msg) {
  bClear('#0a0800');
  const header = msg.year ? `In ${msg.year}:` : 'On this day:';

  bTextC(header, 7, '#ffaa00', 1);
  bFill('#331f00', 0, 13, 64, 1);   // divider line
  const tw = bScroll(msg.text || '', 22, '#eeeebb', scrollPx);
  if (scrollPx > 64 + tw) scrollPx = 0;
  flush();
}

function renderCountdown(msg) {
  bClear('#080010');
  const name  = (msg.name || 'Event').substring(0,10);
  const days  = parseInt(msg.days  ?? 0);
  const hours = parseInt(msg.hours ?? 0);
  const numC  = days===0 ? '#ff4400' : days<=7 ? '#ffaa00' : days<=30 ? '#ffff00' : '#00aaff';
  const cstr  = days===0 ? 'TODAY!' : (days===1&&hours>0) ? `${hours}h` : `${days}d`;

  // name_lbl y=6; count_grp.y=14 scale=2 → center at 14+8=22
  bTextC(name, 6, '#cccccc', 1);
  bTextC(cstr, 22, numC, 2);
  if (hours > 0 && days <= 1) bTextC(`${hours} hours`, 28, '#ff8800', 1);
  flush();
}

function renderBitmap(msg) {
  const path = msg.path || '';
  if (!path) { bClear(); flush(); return; }
  if (!_imgCache[path]) {
    const img = new Image();
    img.onload  = () => { _imgCache[path] = img; };
    img.onerror = () => { _imgCache[path] = 'error'; };
    img.src = `/img?path=${encodeURIComponent(path)}`;
    bClear(); bText('Loading', 2, 16, '#333', 1); flush(); return;
  }
  if (_imgCache[path]==='error') { bClear(); bText('ERR',2,16,'#f44',1); flush(); return; }
  bClear();
  bctx.drawImage(_imgCache[path], 0, 0, 64, 32);
  if (msg.caption) {
    bFill('rgba(0,0,0,0.7)', 0, 25, 64, 7);
    bText(msg.caption.substring(0,10), 1, 28, '#fff', 1);
  }
  flush();
}

function renderGeneric(msg) {
  bClear();
  bTextC((msg.category||'?').toUpperCase().substring(0,10), 8, '#888', 1);
  const t = msg.text || '';
  if (t) { const tw=bScroll(t,22,'#555',scrollPx); if(scrollPx>64+tw) scrollPx=0; }
  flush();
}

// ─── Main loop ────────────────────────────────────────────────────────────────
function tick() {
  frame++;
  scrollPx++;   // 1 board pixel per frame ≈ real board scroll speed (25 px/s)

  if (!queue.length) {
    renderClock();
  } else {
    if (idx >= queue.length) idx = 0;
    if (autoAdv && (frame - msgStartFrame) >= FRAMES_PER_MSG) {
      idx = (idx + 1) % queue.length;
      msgStartFrame = frame; scrollPx = 0;
    }
    const msg = queue[idx];
    switch(msg.category) {
      case 'weather':   renderWeather(msg);   break;
      case 'stock':     renderStock(msg);     break;
      case 'bitcoin':   renderBitcoin(msg);   break;
      case 'word':      renderWord(msg);      break;
      case 'history':   renderHistory(msg);   break;
      case 'countdown': renderCountdown(msg); break;
      case 'bitmap':    renderBitmap(msg);    break;
      default:          renderGeneric(msg);   break;
    }
  }
  updateSidebar();
  setTimeout(tick, 1000 / FPS);
}

// ─── Sidebar ──────────────────────────────────────────────────────────────────
const CAT_COLOR = {weather:'#4499ff',stock:'#00ff44',bitcoin:'#ff9922',
                   word:'#00ccff',history:'#ffaa00',countdown:'#aaaaff',bitmap:'#ff88ff'};

function summary(m) {
  const c = m.category||'';
  if (c==='stock')     return `${(m.symbol||m.ticker||'').toUpperCase()} $${parseFloat(m.price||0).toFixed(2)}`;
  if (c==='weather')   return `H:${Math.round(m.high||0)} L:${Math.round(m.low||0)}${m.city?' '+m.city:''}`;
  if (c==='bitcoin')   return '$'+parseFloat(m.price_usd||0).toLocaleString('en-US',{maximumFractionDigits:0});
  if (c==='word')      return m.word||'';
  if (c==='history')   return `${m.year}: ${(m.text||'').substring(0,22)}`;
  if (c==='countdown') return `${m.name}: ${m.days}d`;
  if (c==='bitmap')    return m.caption||m.path||'';
  return (m.text||'').substring(0,30);
}

function updateSidebar() {
  document.getElementById('q-header').textContent = `QUEUE  ${queue.length} message${queue.length!==1?'s':''}`;
  const el  = document.getElementById('q-list');
  if (!queue.length) {
    el.innerHTML = '<div id="q-empty">no messages — showing clock</div>';
    document.getElementById('msg-info').textContent = ''; return;
  }
  const now = Date.now()/1000;
  el.innerHTML = queue.map((m,i) => {
    const cc  = CAT_COLOR[m.category]||'#666';
    const rem = m.ttl_minutes ? `${Math.max(0,m.ttl_minutes-Math.round((now-(m._added||0))/60))}m left` : '';
    return `<div class="qi${i===idx?' active':''}" onclick="jumpTo(${i})">
      <div class="qi-cat" style="color:${cc}">${m.category||'?'}</div>
      <div class="qi-sum">${summary(m)}</div>
      ${rem?`<div class="qi-ttl">${rem}</div>`:''}
    </div>`;
  }).join('');
  document.getElementById('msg-info').textContent = `${idx+1} / ${queue.length}`;
}

// ─── Controls ────────────────────────────────────────────────────────────────
function jumpTo(i)    { idx=i; msgStartFrame=frame; scrollPx=0; }
function prevMsg()    { idx=(idx-1+Math.max(1,queue.length))%Math.max(1,queue.length); msgStartFrame=frame; scrollPx=0; }
function nextMsg()    { idx=(idx+1)%Math.max(1,queue.length); msgStartFrame=frame; scrollPx=0; }
function toggleAuto() { autoAdv=!autoAdv; document.getElementById('btn-auto').classList.toggle('on',autoAdv); }
async function clearQueue() { await fetch('/queue/clear',{method:'POST'}); queue=[];idx=0;scrollPx=0; }

// ─── Polling ─────────────────────────────────────────────────────────────────
let _prevSig = '';
async function pollQueue() {
  try {
    const data = await (await fetch('/queue')).json();
    const newQ = data.queue||[];
    const sig  = JSON.stringify(newQ.map(m=>[m._id,m._added]));
    if (sig !== _prevSig) {
      const curId = queue[idx]?._id;
      queue = newQ;
      const ni = queue.findIndex(m=>m._id===curId);
      if (ni>=0) idx=ni; else if (idx>=queue.length) idx=0;
      _prevSig = sig;
    }
  } catch(e) {}
  setTimeout(pollQueue, 1000);
}

pollQueue();
tick();
</script>
</body>
</html>"""


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LED Matrix Emulator")
    parser.add_argument("--port", type=int, default=8080,
                        help="Port to listen on (default: 8080, same as the board)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Host to bind to (default: 127.0.0.1)")
    args = parser.parse_args()

    server = HTTPServer((args.host, args.port), Handler)
    server.socket.setsockopt(__import__('socket').SOL_SOCKET,
                             __import__('socket').SO_REUSEADDR, 1)

    print()
    print(f"  LED Matrix Emulator")
    print(f"  Open: http://localhost:{args.port}/emulator")
    print()
    print(f"  To route feeds here instead of the board:")
    print(f'  Set "board_url": "http://localhost:{args.port}" in feeds/config.json')
    print()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
