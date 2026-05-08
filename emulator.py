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
  background: #111;
  color: #bbb;
  font-family: 'Courier New', monospace;
  padding: 14px;
  min-height: 100vh;
}
h1 { font-size: 12px; color: #4fc; letter-spacing: 1px; margin-bottom: 12px; }
.layout { display: flex; gap: 16px; align-items: flex-start; }
#display-area { flex-shrink: 0; }
#display-wrap {
  border: 1px solid #1e1e1e;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 0 40px rgba(0,255,180,0.05), 0 2px 20px rgba(0,0,0,0.6);
}
canvas { display: block; }
#controls {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
}
button {
  background: #1c1c1c;
  border: 1px solid #2a2a2a;
  color: #888;
  padding: 3px 10px;
  border-radius: 3px;
  cursor: pointer;
  font-family: 'Courier New', monospace;
  font-size: 11px;
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
  background: #161616;
  border: 1px solid #202020;
  border-left: 3px solid #2a2a2a;
  padding: 5px 8px;
  margin-bottom: 3px;
  border-radius: 2px;
  cursor: pointer;
  font-size: 11px;
  transition: border-color 0.1s, background 0.1s;
}
.qi:hover { background: #1a1a1a; border-left-color: #4fc; }
.qi.active { border-left-color: #4fc; background: #0d1a14; }
.qi-cat  { font-weight: bold; font-size: 10px; letter-spacing: 0.5px; text-transform: uppercase; }
.qi-sum  { color: #666; margin-top: 1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.qi-ttl  { color: #333; font-size: 10px; margin-top: 2px; }
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
// ─── Canvas setup ─────────────────────────────────────────────────────────────
const canvas = document.getElementById('led');
const ctx    = canvas.getContext('2d');
const W = 640, H = 320, LED_W = 64, LED_H = 32, S = 10;

// Pre-render background (dark LED grid) to an offscreen canvas
const bgOff = document.createElement('canvas');
bgOff.width = W; bgOff.height = H;
{
  const bc = bgOff.getContext('2d');
  bc.fillStyle = '#000';
  bc.fillRect(0, 0, W, H);
  bc.fillStyle = '#0c0c0c';
  for (let y = 0; y < LED_H; y++)
    for (let x = 0; x < LED_W; x++) {
      bc.beginPath();
      bc.arc(x*S + S/2, y*S + S/2, 3.1, 0, Math.PI*2);
      bc.fill();
    }
}

// ─── State ────────────────────────────────────────────────────────────────────
let queue = [], idx = 0, autoAdv = true;
let frame = 0, msgStartFrame = 0, scrollPos = 0;
const FPS            = 30;
const FRAMES_PER_MSG = FPS * 8;   // 8 s per message
const SCROLL_PX      = 1.5;       // px per frame

// ─── Draw primitives ─────────────────────────────────────────────────────────
function bg(tint) {
  ctx.drawImage(bgOff, 0, 0);
  if (tint) { ctx.fillStyle = tint; ctx.fillRect(0, 0, W, H); }
}

function glow(color, blur) { ctx.shadowColor = color; ctx.shadowBlur = blur ?? 8; }
function noGlow()           { ctx.shadowBlur = 0; }

function txt(str, x, y, color, size, align) {
  ctx.font          = `bold ${size}px "Courier New", monospace`;
  ctx.fillStyle     = color;
  ctx.textAlign     = align ?? 'center';
  ctx.textBaseline  = 'middle';
  glow(color);
  ctx.fillText(str, x, y);
  noGlow();
}

function scrollTxt(str, y, color, size) {
  ctx.save();
  ctx.beginPath();
  ctx.rect(0, y - size * 0.9, W, size * 2.0);
  ctx.clip();
  ctx.font         = `${size}px "Courier New", monospace`;
  ctx.fillStyle    = color;
  ctx.textAlign    = 'left';
  ctx.textBaseline = 'middle';
  glow(color, 5);
  ctx.fillText(str, W - scrollPos, y);
  noGlow();
  ctx.restore();
  // Auto-reset when text has fully scrolled off left edge
  const tw = ctx.measureText(str).width;
  if (scrollPos > W + tw + 20) scrollPos = 0;
}

// ─── Clock (shown when queue empty) ──────────────────────────────────────────
function clockColor() {
  const h = new Date().getHours();
  if (h >=  5 && h <  8) return '#ff6600';   // dawn — orange
  if (h >=  8 && h < 17) return '#ffffff';   // day  — white
  if (h >= 17 && h < 20) return '#ff8800';   // dusk — amber
  return '#4466ff';                            // night — blue
}

function renderClock() {
  bg();
  const now  = new Date();
  const h    = now.getHours() % 12 || 12;
  const min  = String(now.getMinutes()).padStart(2, '0');
  const DAYS = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  const MONS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const timeStr = `${h}:${min}`;
  const dateStr = `${DAYS[now.getDay()]} ${MONS[now.getMonth()]} ${now.getDate()}`;
  const cc  = clockColor();
  txt(timeStr, W/2, H*0.38, cc,        80);
  txt(dateStr, W/2, H*0.72, '#2a2a2a', 24);
  // Seconds progress bar (bottom row)
  const barW = Math.max(1, Math.round(now.getSeconds() * W / 60));
  const r = (parseInt(cc.slice(1,3),16) >> 2).toString(16).padStart(2,'0');
  const g = (parseInt(cc.slice(3,5),16) >> 2).toString(16).padStart(2,'0');
  const b = (parseInt(cc.slice(5,7),16) >> 2).toString(16).padStart(2,'0');
  ctx.fillStyle = `#${r}${g}${b}`;
  ctx.fillRect(0, H - S, barW, S);
}

// ─── Weather ─────────────────────────────────────────────────────────────────
function renderWeather(msg) {
  bg('rgba(0,8,22,0.5)');
  const cond   = (msg.condition || '').toLowerCase();
  const high   = msg.high, low = msg.low, precip = msg.precip;
  const city   = msg.city || '';
  const iFrame = Math.floor(frame / 3);

  // Animated icon occupies left 32 LEDs (320px)
  drawWeatherIcon(cond, iFrame);

  // Text on right half
  const tx = 32*S + (32*S)/2;   // center of right half
  if (city) {
    txt(city.substring(0,8),        tx, H*0.15, '#cccccc', 22, 'center');
    if (high   != null) txt(`H:${Math.round(high)}`,   tx, H*0.47, '#ff8844', 26, 'center');
    if (low    != null) txt(`L:${Math.round(low)}`,    tx, H*0.75, '#4499ff', 26, 'center');
  } else {
    if (high   != null) txt(`H:${Math.round(high)}`,   tx, H*0.18, '#ff8844', 26, 'center');
    if (low    != null) txt(`L:${Math.round(low)}`,    tx, H*0.50, '#4499ff', 26, 'center');
    if (precip != null) txt(`${Math.round(precip)}%`,  tx, H*0.82, '#44ccff', 24, 'center');
  }
}

function drawWeatherIcon(cond, fr) {
  const cx = 160, cy = H/2, r = 70;
  if (cond.includes('sun') || cond.includes('clear') || cond.includes('fair')) {
    // Sun core
    const g = ctx.createRadialGradient(cx,cy,0, cx,cy,r);
    g.addColorStop(0,'#ffee00'); g.addColorStop(1,'#ff7700');
    ctx.fillStyle = g; glow('#ffaa00', 20);
    ctx.beginPath(); ctx.arc(cx,cy,r,0,Math.PI*2); ctx.fill(); noGlow();
    // Rays
    for (let i=0; i<8; i++) {
      const a = (i/8*Math.PI*2) + fr*0.05;
      ctx.strokeStyle = (i+fr)%2===0 ? '#ffdd00' : '#ff8800';
      ctx.lineWidth = 3; glow('#ffaa00',6);
      ctx.beginPath();
      ctx.moveTo(cx+Math.cos(a)*r*1.2, cy+Math.sin(a)*r*1.2);
      ctx.lineTo(cx+Math.cos(a)*r*1.7, cy+Math.sin(a)*r*1.7);
      ctx.stroke(); noGlow();
    }
  } else if (cond.includes('rain') || cond.includes('shower') || cond.includes('drizzle')) {
    cloud(cx, cy-20, r*0.9, '#777');
    for (let d=0; d<7; d++) {
      const rx = 30 + d*40;
      const ry = cy+30 + ((fr*3 + d*19) % 120);
      ctx.fillStyle='#4488ff'; ctx.fillRect(rx,ry,2,8);
      ctx.fillStyle='#7799ff'; ctx.fillRect(rx,ry-4,2,3);
    }
  } else if (cond.includes('snow') || cond.includes('blizzard')) {
    cloud(cx, cy-20, r*0.9, '#aaa');
    for (let d=0; d<6; d++) {
      const side = (fr%8<4)?1:-1;
      const rx = 25 + d*45 + side*(fr%4);
      const ry = cy+20 + ((fr + d*23) % 130);
      ctx.fillStyle='#ddeeff'; glow('#88ccff',4);
      ctx.fillRect(rx, ry, 4, 4); noGlow();
    }
  } else if (cond.includes('storm') || cond.includes('thunder')) {
    cloud(cx, cy-15, r*0.9, '#555');
    for (let d=0; d<5; d++) {
      const rx = 35 + d*45;
      const ry = cy+20 + ((fr*3 + d*19) % 100);
      ctx.fillStyle='#3377ff'; ctx.fillRect(rx,ry,2,8);
    }
    if (fr%24 < 3) {
      ctx.strokeStyle='#ffffaa'; ctx.lineWidth=2; glow('#fff',12);
      ctx.beginPath(); ctx.moveTo(cx,cy-5);
      ctx.lineTo(cx-8,cy+12); ctx.lineTo(cx,cy+12); ctx.lineTo(cx-6,cy+26);
      ctx.stroke(); noGlow();
    }
  } else {
    // Cloud
    cloud(cx, cy, r*0.9, fr%8<4 ? '#999' : '#777');
  }
}

function cloud(cx, cy, r, color) {
  ctx.fillStyle = color; glow(color, 8);
  ctx.beginPath();
  ctx.arc(cx-r*0.3, cy+r*0.1, r*0.5, 0, Math.PI*2);
  ctx.arc(cx+r*0.3, cy+r*0.1, r*0.5, 0, Math.PI*2);
  ctx.arc(cx,       cy-r*0.1, r*0.6, 0, Math.PI*2);
  ctx.fill();
  ctx.fillRect(cx-r*0.8, cy+r*0.1, r*1.6, r*0.5);
  noGlow();
}

// ─── Stock ───────────────────────────────────────────────────────────────────
function renderStock(msg) {
  const sym    = (msg.symbol || msg.ticker || '???').toUpperCase();
  const price  = parseFloat(msg.price  || 0);
  const change = parseFloat(msg.change || msg.change_pct || 0);
  const isUp   = change >= 0;
  const cc     = isUp ? '#00ff44' : '#ff3300';

  bg(isUp ? 'rgba(0,22,0,0.55)' : 'rgba(22,0,0,0.55)');

  // Toggle $ vs % every ~3 s (90 frames)
  const showPct  = Math.floor(frame / 90) % 2 === 0;
  const prev     = price / (1 + change/100) || price;
  const dollarCh = Math.abs(price - prev);
  const sign     = isUp ? '+' : '-';
  const chgStr   = showPct
    ? `${sign}${Math.abs(change).toFixed(2)}%`
    : `${sign}$${dollarCh.toFixed(2)}`;

  txt(sym,              W/2, H*0.21, '#ffffff', 32);
  txt(`$${price.toFixed(2)}`, W/2, H*0.51, '#aaaaaa', 42);
  txt(chgStr,           W/2, H*0.80, cc,        30);
}

// ─── Bitcoin ─────────────────────────────────────────────────────────────────
function renderBitcoin(msg) {
  const price  = parseFloat(msg.price_usd || 0);
  const change = parseFloat(msg.change_pct_24h || 0);
  const isUp   = change >= 0;
  const cc     = isUp ? '#00ff44' : '#ff3300';
  const chgStr = `${isUp?'+':''}${change.toFixed(2)}%`;
  const priceStr = '$' + price.toLocaleString('en-US',{maximumFractionDigits:0});

  bg('rgba(20,10,0,0.55)');
  txt('BTC',    W/2, H*0.22, '#ff9922', 30);
  txt(priceStr, W/2, H*0.51, '#dddddd', 42);
  txt(chgStr,   W/2, H*0.80, cc,        30);
}

// ─── Word of the Day ─────────────────────────────────────────────────────────
function renderWord(msg) {
  bg('rgba(0,8,14,0.55)');
  const word = (msg.word || 'WORD').toUpperCase().substring(0,10);
  const pos  = msg.pos ? `(${msg.pos})` : '';
  const defn = msg.definition || '';
  txt(word, W/2, H*0.21, '#00ccff', 38);
  if (pos) txt(pos, W/2, H*0.42, '#666666', 20);
  scrollTxt(defn, H*0.70, '#cccccc', 22);
}

// ─── This Day in History ──────────────────────────────────────────────────────
function renderHistory(msg) {
  bg('rgba(10,7,0,0.55)');
  const year = msg.year ? `In ${msg.year}:` : 'On this day:';
  const text = msg.text || '';
  txt(year, W/2, H*0.25, '#ffaa00', 34);
  scrollTxt(text, H*0.62, '#eeeebb', 22);
}

// ─── Countdown ───────────────────────────────────────────────────────────────
function renderCountdown(msg) {
  bg('rgba(6,0,14,0.55)');
  const name  = (msg.name || 'Event').substring(0,10).toUpperCase();
  const days  = parseInt(msg.days  ?? 0);
  const hours = parseInt(msg.hours ?? 0);

  let numColor;
  if      (days === 0)  numColor = '#ff4400';
  else if (days <= 7)   numColor = '#ffaa00';
  else if (days <= 30)  numColor = '#ffff00';
  else                  numColor = '#00aaff';

  const countStr = days === 0 ? 'TODAY!'
                 : (days === 1 && hours > 0) ? `${hours}h`
                 : `${days}d`;

  txt(name,      W/2, H*0.24, '#bbbbbb', 26);
  txt(countStr,  W/2, H*0.55, numColor,  72);
  if (hours > 0 && days <= 1) txt(`${hours} hours`, W/2, H*0.82, '#ff8800', 22);
}

// ─── Bitmap (NASA APOD / image feed) ─────────────────────────────────────────
const _imgCache = {};
function renderBitmap(msg) {
  const path = msg.path || '';
  if (!path) { bg(); txt('[NO IMAGE]', W/2, H/2, '#333', 22); return; }

  if (!_imgCache[path]) {
    const img = new Image();
    img.onload  = () => { _imgCache[path] = img; };
    img.onerror = () => { _imgCache[path] = 'error'; };
    img.src = `/img?path=${encodeURIComponent(path)}`;
    bg(); txt('Loading…', W/2, H/2, '#333', 22);
    return;
  }
  if (_imgCache[path] === 'error') {
    bg(); txt('[IMAGE ERROR]', W/2, H/2, '#ff4444', 22);
    return;
  }
  bg();
  ctx.drawImage(_imgCache[path], 0, 0, W, H);
  if (msg.caption) {
    ctx.fillStyle = 'rgba(0,0,0,0.65)';
    ctx.fillRect(0, H*0.85, W, H*0.15);
    txt(msg.caption.substring(0,18), W/2, H*0.93, '#ffffff', 20);
  }
}

// ─── Generic fallback ────────────────────────────────────────────────────────
function renderGeneric(msg) {
  bg();
  const cat = (msg.category || 'msg').toUpperCase();
  txt(cat, W/2, H*0.28, '#888888', 28);
  const t = msg.text || JSON.stringify(msg).substring(0,50);
  scrollTxt(t, H*0.62, '#555555', 18);
}

// ─── No messages ─────────────────────────────────────────────────────────────
function renderEmpty() {
  renderClock();
  ctx.font      = '10px monospace';
  ctx.fillStyle = '#1e1e1e';
  ctx.textAlign = 'right'; ctx.textBaseline = 'bottom';
  ctx.fillText('no feed data', W-4, H-4);
}

// ─── Dispatch ────────────────────────────────────────────────────────────────
function renderMsg(msg) {
  scrollPos += SCROLL_PX;
  switch (msg.category) {
    case 'weather':   renderWeather(msg);   break;
    case 'stock':     renderStock(msg);     break;
    case 'bitcoin':   renderBitcoin(msg);   break;
    case 'word':      renderWord(msg);      break;
    case 'history':   renderHistory(msg);   break;
    case 'countdown': renderCountdown(msg); break;
    case 'bitmap':    renderBitmap(msg);    break;
    default:          renderGeneric(msg);   break;
  }
  // Subtle category tag
  ctx.font = '9px monospace'; ctx.fillStyle = '#1e1e1e';
  ctx.textAlign = 'left'; ctx.textBaseline = 'top';
  ctx.fillText(`[${msg.category || '?'}]`, 4, 4);
}

// ─── Main animation loop ──────────────────────────────────────────────────────
function tick() {
  frame++;
  if (queue.length === 0) {
    renderEmpty();
  } else {
    if (idx >= queue.length) idx = 0;
    if (autoAdv && (frame - msgStartFrame) >= FRAMES_PER_MSG) {
      idx = (idx + 1) % queue.length;
      msgStartFrame = frame;
      scrollPos = 0;
    }
    renderMsg(queue[idx]);
  }
  updateSidebar();
  requestAnimationFrame(tick);
}

// ─── Sidebar ─────────────────────────────────────────────────────────────────
const CAT_COLOR = {
  weather:'#4499ff', stock:'#00ff44', bitcoin:'#ff9922',
  word:'#00ccff', history:'#ffaa00', countdown:'#aaaaff', bitmap:'#ff88ff',
};
function catColor(c) { return CAT_COLOR[c] || '#666'; }

function summary(m) {
  const c = m.category || '';
  if (c === 'stock')     return `${(m.symbol||m.ticker||'').toUpperCase()} $${parseFloat(m.price||0).toFixed(2)}`;
  if (c === 'weather')   return `H:${Math.round(m.high||0)} L:${Math.round(m.low||0)}${m.city?' '+m.city:''}`;
  if (c === 'bitcoin')   return `$${parseFloat(m.price_usd||0).toLocaleString('en-US',{maximumFractionDigits:0})}`;
  if (c === 'word')      return m.word || '';
  if (c === 'history')   return `${m.year}: ${(m.text||'').substring(0,22)}`;
  if (c === 'countdown') return `${m.name}: ${m.days}d`;
  if (c === 'bitmap')    return m.caption || m.path || '';
  return (m.text || '').substring(0,30);
}

function updateSidebar() {
  document.getElementById('q-header').textContent =
    `QUEUE  ${queue.length} message${queue.length!==1?'s':''}`;
  const el = document.getElementById('q-list');
  if (!queue.length) {
    el.innerHTML = '<div id="q-empty">no messages — showing clock</div>';
    document.getElementById('msg-info').textContent = '';
    return;
  }
  const now = Date.now() / 1000;
  el.innerHTML = queue.map((m, i) => {
    const cc  = catColor(m.category);
    const rem = m.ttl_minutes
      ? `${Math.max(0, m.ttl_minutes - Math.round((now - (m._added||0))/60))}m left`
      : '';
    return `<div class="qi${i===idx?' active':''}" onclick="jumpTo(${i})">
      <div class="qi-cat" style="color:${cc}">${m.category||'?'}</div>
      <div class="qi-sum">${summary(m)}</div>
      ${rem ? `<div class="qi-ttl">${rem}</div>` : ''}
    </div>`;
  }).join('');
  document.getElementById('msg-info').textContent = `${idx+1} / ${queue.length}`;
}

// ─── Controls ────────────────────────────────────────────────────────────────
function jumpTo(i)  { idx=i; msgStartFrame=frame; scrollPos=0; }
function prevMsg()  { idx=(idx-1+Math.max(1,queue.length))%Math.max(1,queue.length); msgStartFrame=frame; scrollPos=0; }
function nextMsg()  { idx=(idx+1)%Math.max(1,queue.length); msgStartFrame=frame; scrollPos=0; }
function toggleAuto() {
  autoAdv = !autoAdv;
  document.getElementById('btn-auto').classList.toggle('on', autoAdv);
}
async function clearQueue() {
  await fetch('/queue/clear', {method:'POST'});
  queue=[]; idx=0; scrollPos=0;
}

// ─── Polling ─────────────────────────────────────────────────────────────────
let _prevSig = '';
async function pollQueue() {
  try {
    const r    = await fetch('/queue');
    const data = await r.json();
    const newQ = data.queue || [];
    const sig  = JSON.stringify(newQ.map(m => [m._id, m._added]));
    if (sig !== _prevSig) {
      const curId = queue[idx]?._id;
      queue = newQ;
      const ni = queue.findIndex(m => m._id === curId);
      if (ni >= 0) idx = ni;
      else if (idx >= queue.length) idx = 0;
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
