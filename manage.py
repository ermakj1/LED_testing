#!/usr/bin/env python3
"""
Interactive manager for LED display feeds.

Starts all feed scripts as subprocesses and provides a menu to configure
each feed. Settings are saved to feeds/config.json.

Usage:
    python manage.py
"""

import json
import os
import sys
import time
import subprocess
import threading
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime

REPO_DIR      = Path(__file__).parent.resolve()
CONFIG_PATH   = REPO_DIR / "feeds" / "config.json"
RESTART_DELAY = 5

ALL_ANIM_TYPES = ["fireworks", "rainbow", "plasma", "fire", "life", "cube", "dvd", "dvd_text", "matrix"]

DEFAULT_CONFIG = {
    "board_url": "http://matrixportal.local:8080",
    "weather": {
        "interval_minutes": 30,
        "cities": [
            {"name": "Kirkland, WA, United States", "lat": 47.6815, "lon": -122.2087, "timezone": "America/Los_Angeles"}
        ]
    },
    "stock": {
        "interval_minutes": 5,
        "market_hours_only": True,
        "symbols": ["MSFT"]
    },
    "jokes": {
        "interval_minutes": 30,
        "enabled": True
    },
    "animations": {
        "interval_minutes": 20,
        "enabled": True,
        "types": list(ALL_ANIM_TYPES)
    }
}

# ── Config ────────────────────────────────────────────────────────────────────

def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return json.loads(json.dumps(DEFAULT_CONFIG))

def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

# ── Geocoding ─────────────────────────────────────────────────────────────────

def geocode(name):
    """Look up a city by name. Returns list of {name, lat, lon, timezone}."""
    url = (
        "https://geocoding-api.open-meteo.com/v1/search"
        f"?name={urllib.parse.quote(name)}&count=8&language=en&format=json"
    )
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            data = json.loads(r.read())
        results = []
        for r in data.get("results", []):
            label = r.get("name", "")
            if r.get("admin1"):
                label += f", {r['admin1']}"
            if r.get("country"):
                label += f", {r['country']}"
            results.append({
                "name":     label,
                "lat":      round(r["latitude"],  4),
                "lon":      round(r["longitude"], 4),
                "timezone": r.get("timezone", "UTC"),
            })
        return results
    except Exception as e:
        print(f"  Geocoding error: {e}")
        return []

# ── Process management ────────────────────────────────────────────────────────

class ManagedProcess:
    def __init__(self, name, cmd):
        self.name       = name
        self.cmd        = cmd
        self.proc       = None
        self.restart_at = 0

    def start(self):
        self.proc = subprocess.Popen(self.cmd, cwd=REPO_DIR)
        _log(f"Started {self.name} (pid {self.proc.pid})")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def restart(self):
        self.stop()
        self.restart_at = 0
        self.start()

    def tick(self):
        if self.proc is None:
            if time.time() >= self.restart_at:
                self.start()
            return
        rc = self.proc.poll()
        if rc is not None:
            _log(f"{self.name} exited (code {rc}), restarting in {RESTART_DELAY}s")
            self.proc = None
            self.restart_at = time.time() + RESTART_DELAY

    @property
    def status(self):
        if self.proc is None:
            return "stopped"
        if self.proc.poll() is None:
            return f"running  pid {self.proc.pid}"
        return f"exited ({self.proc.returncode})"


_processes: list[ManagedProcess] = []
_proc_lock = threading.Lock()

def _log(msg):
    print(f"\r[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def _build_processes():
    return [
        ManagedProcess("weather",    [sys.executable, "feeds/weather.py"]),
        ManagedProcess("stock",      [sys.executable, "feeds/stock.py"]),
        ManagedProcess("jokes",      [sys.executable, "feeds/jokes.py"]),
        ManagedProcess("animations", [sys.executable, "feeds/animations.py"]),
    ]

def _manager_loop(stop_event):
    while not stop_event.is_set():
        with _proc_lock:
            for p in _processes:
                p.tick()
        time.sleep(5)

def restart_feed(name):
    with _proc_lock:
        for p in _processes:
            if p.name == name:
                _log(f"Restarting {name}")
                p.restart()
                return

def restart_all():
    with _proc_lock:
        for p in _processes:
            p.restart()

# ── Menu helpers ──────────────────────────────────────────────────────────────

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def hr():
    print("  " + "─" * 38)

def header(title):
    print()
    hr()
    print(f"  {title}")
    hr()

def ask(text=""):
    try:
        return input(f"\n  {text}> ").strip()
    except (KeyboardInterrupt, EOFError):
        return "q"

def pause():
    try:
        input("\n  Press Enter to continue...")
    except (KeyboardInterrupt, EOFError):
        pass

# ── Weather menu ──────────────────────────────────────────────────────────────

def menu_weather(cfg):
    while True:
        wcfg     = cfg.setdefault("weather", {})
        cities   = wcfg.setdefault("cities", [])
        interval = wcfg.get("interval_minutes", 30)

        header("Weather Settings")
        if cities:
            for i, c in enumerate(cities, 1):
                print(f"  {i}. {c['name']}")
        else:
            print("  (no cities configured)")
        print(f"\n  Interval: every {interval} min")
        print("\n  [a] Add city   [r] Remove city   [i] Set interval   [b] Back")

        cmd = ask()
        if cmd in ("b", "q", ""):
            break
        elif cmd == "a":
            name = ask("City name (e.g. Seattle or Tokyo)")
            if not name:
                continue
            print("  Searching...", end="", flush=True)
            results = geocode(name)
            print()
            if not results:
                print("  No results found.")
                pause()
                continue
            for i, r in enumerate(results, 1):
                print(f"  {i}. {r['name']}  ({r['lat']}, {r['lon']})")
            choice = ask("Select number (Enter to cancel)")
            if choice.isdigit() and 1 <= int(choice) <= len(results):
                city = results[int(choice) - 1]
                cities.append(city)
                save_config(cfg)
                restart_feed("weather")
                print(f"  Added {city['name']}")
                pause()
        elif cmd == "r":
            if not cities:
                continue
            idx = ask("Remove number")
            if idx.isdigit() and 1 <= int(idx) <= len(cities):
                removed = cities.pop(int(idx) - 1)
                save_config(cfg)
                restart_feed("weather")
                print(f"  Removed {removed['name']}")
                pause()
        elif cmd == "i":
            val = ask("Interval in minutes")
            if val.isdigit() and int(val) > 0:
                wcfg["interval_minutes"] = int(val)
                save_config(cfg)
                restart_feed("weather")
                print(f"  Interval set to {val} min")
                pause()

# ── Stock menu ────────────────────────────────────────────────────────────────

def menu_stock(cfg):
    while True:
        scfg     = cfg.setdefault("stock", {})
        symbols  = scfg.setdefault("symbols", [])
        interval = scfg.get("interval_minutes", 5)
        mkt_only = scfg.get("market_hours_only", True)

        header("Stock Settings")
        if symbols:
            for i, s in enumerate(symbols, 1):
                print(f"  {i}. {s}")
        else:
            print("  (no symbols configured)")
        print(f"\n  Interval:     every {interval} min")
        print(f"  Market hours: {'9am–5pm only' if mkt_only else 'always on'}")
        print("\n  [a] Add symbol   [r] Remove symbol   [i] Set interval   [m] Toggle market hours   [b] Back")

        cmd = ask()
        if cmd in ("b", "q", ""):
            break
        elif cmd == "a":
            sym = ask("Symbol (e.g. AAPL)").upper()
            if sym and sym not in symbols:
                symbols.append(sym)
                save_config(cfg)
                restart_feed("stock")
                print(f"  Added {sym}")
                pause()
        elif cmd == "r":
            if not symbols:
                continue
            idx = ask("Remove number")
            if idx.isdigit() and 1 <= int(idx) <= len(symbols):
                removed = symbols.pop(int(idx) - 1)
                save_config(cfg)
                restart_feed("stock")
                print(f"  Removed {removed}")
                pause()
        elif cmd == "i":
            val = ask("Interval in minutes")
            if val.isdigit() and int(val) > 0:
                scfg["interval_minutes"] = int(val)
                save_config(cfg)
                restart_feed("stock")
                print(f"  Interval set to {val} min")
                pause()
        elif cmd == "m":
            scfg["market_hours_only"] = not mkt_only
            save_config(cfg)
            restart_feed("stock")

# ── Jokes menu ────────────────────────────────────────────────────────────────

def menu_jokes(cfg):
    while True:
        jcfg     = cfg.setdefault("jokes", {})
        enabled  = jcfg.get("enabled", True)
        interval = jcfg.get("interval_minutes", 30)

        header("Joke Settings")
        print(f"  Status:   {'enabled' if enabled else 'disabled'}")
        print(f"  Interval: every {interval} min")
        print("\n  [t] Toggle   [i] Set interval   [b] Back")

        cmd = ask()
        if cmd in ("b", "q", ""):
            break
        elif cmd == "t":
            jcfg["enabled"] = not enabled
            save_config(cfg)
            restart_feed("jokes")
        elif cmd == "i":
            val = ask("Interval in minutes")
            if val.isdigit() and int(val) > 0:
                jcfg["interval_minutes"] = int(val)
                save_config(cfg)
                restart_feed("jokes")
                pause()

# ── Animations menu ───────────────────────────────────────────────────────────

def menu_animations(cfg):
    while True:
        acfg     = cfg.setdefault("animations", {})
        enabled  = acfg.get("enabled", True)
        interval = acfg.get("interval_minutes", 20)
        types    = acfg.setdefault("types", list(ALL_ANIM_TYPES))

        header("Animation Settings")
        print(f"  Status:   {'enabled' if enabled else 'disabled'}")
        print(f"  Interval: every {interval} min")
        print(f"  Active:   {', '.join(types) if types else '(none)'}")
        print("\n  [t] Toggle   [i] Set interval   [e] Edit types   [b] Back")

        cmd = ask()
        if cmd in ("b", "q", ""):
            break
        elif cmd == "t":
            acfg["enabled"] = not enabled
            save_config(cfg)
            restart_feed("animations")
        elif cmd == "i":
            val = ask("Interval in minutes")
            if val.isdigit() and int(val) > 0:
                acfg["interval_minutes"] = int(val)
                save_config(cfg)
                restart_feed("animations")
                pause()
        elif cmd == "e":
            while True:
                print()
                for i, t in enumerate(ALL_ANIM_TYPES, 1):
                    mark = "x" if t in types else " "
                    print(f"  {i}. [{mark}] {t}")
                print("\n  Enter number to toggle, Enter when done")
                val = ask("Toggle")
                if not val:
                    break
                if val.isdigit() and 1 <= int(val) <= len(ALL_ANIM_TYPES):
                    t = ALL_ANIM_TYPES[int(val) - 1]
                    if t in types:
                        types.remove(t)
                    else:
                        types.append(t)
            save_config(cfg)
            restart_feed("animations")

# ── Board settings ────────────────────────────────────────────────────────────

def menu_board(cfg):
    header("Board Settings")
    print(f"  URL: {cfg.get('board_url', '')}")
    print("\n  [u] Set URL   [b] Back")

    cmd = ask()
    if cmd == "u":
        url = ask("Board URL (e.g. http://192.168.1.50:8080)")
        if url:
            cfg["board_url"] = url.rstrip("/")
            save_config(cfg)
            restart_all()
            print("  Saved. Restarting all feeds.")
            pause()

# ── Status ────────────────────────────────────────────────────────────────────

def menu_status():
    header("Feed Status")
    with _proc_lock:
        for p in _processes:
            print(f"  {p.name:<12} {p.status}")
    pause()

# ── Main menu ─────────────────────────────────────────────────────────────────

def main_menu(cfg):
    while True:
        clear()
        print("\n  LED Display Manager")
        hr()

        with _proc_lock:
            statuses = {
                p.name: "running" if (p.proc and p.proc.poll() is None) else "stopped"
                for p in _processes
            }

        for name, st in statuses.items():
            mark = "✓" if st == "running" else "✗"
            print(f"  {mark} {name}")

        print()
        print("  [1] Weather settings")
        print("  [2] Stock settings")
        print("  [3] Joke settings")
        print("  [4] Animation settings")
        print("  [5] Board URL")
        print("  [s] Status")
        print("  [r] Restart all feeds")
        print("  [q] Quit  (feeds keep running)")

        cmd = ask()
        if cmd == "1":
            menu_weather(cfg)
        elif cmd == "2":
            menu_stock(cfg)
        elif cmd == "3":
            menu_jokes(cfg)
        elif cmd == "4":
            menu_animations(cfg)
        elif cmd == "5":
            menu_board(cfg)
        elif cmd == "s":
            menu_status()
        elif cmd == "r":
            restart_all()
            print("  Restarting all feeds...")
            time.sleep(1)
        elif cmd in ("q", ""):
            break

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    global _processes

    cfg = load_config()
    save_config(cfg)  # write file with defaults if it didn't exist

    _processes = _build_processes()

    stop_event = threading.Event()
    threading.Thread(target=_manager_loop, args=(stop_event,), daemon=True).start()

    print("Starting feeds...", flush=True)
    time.sleep(1)

    try:
        main_menu(cfg)
    finally:
        stop_event.set()
        print("\nStopping feeds...")
        with _proc_lock:
            for p in _processes:
                p.stop()
        print("Done.")

if __name__ == "__main__":
    main()
