#!/usr/bin/env python3
"""
Watchdog: manages LED feed scripts as subprocesses.

- Restarts any feed that crashes (with a short backoff)
- Polls git for new commits and restarts all feeds after a pull

Usage:
    python3 watchdog.py                     # run all feeds, check git every 2 min
    python3 watchdog.py --git-interval 60   # check git every 60 seconds
    python3 watchdog.py --no-git            # skip git polling (useful for testing)
"""

import argparse
import subprocess
import sys
import time
import logging
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

REPO_DIR = Path(__file__).parent.parent.resolve()  # scripts/ → repo root

# Each entry: (display name, command list relative to REPO_DIR)
FEEDS = [
    ("stock",      [sys.executable, "feeds/stock.py"]),
    ("weather",    [sys.executable, "feeds/weather.py"]),
    ("jokes",      [sys.executable, "feeds/jokes.py"]),
    ("animations", [sys.executable, "feeds/animations.py"]),
]

DEFAULT_GIT_INTERVAL = 900   # seconds between git fetch checks (15 min)
RESTART_DELAY        = 5     # seconds to wait before restarting a crashed feed

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("watchdog")

# ── Git helpers ───────────────────────────────────────────────────────────────

def git(*args):
    """Run a git command in REPO_DIR. Returns (returncode, stdout, stderr)."""
    result = subprocess.run(
        ["git"] + list(args),
        cwd=REPO_DIR,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def has_updates():
    """Fetch from origin, return True if remote has commits we don't have."""
    rc, _, err = git("fetch")
    if rc != 0:
        log.warning(f"git fetch failed — {err or 'no error detail'}")
        return False
    rc, output, _ = git("rev-list", "HEAD..@{u}", "--count")
    if rc != 0:
        return False
    try:
        return int(output) > 0
    except ValueError:
        return False


def pull():
    """Pull latest changes. Returns True on success."""
    rc, out, err = git("pull", "--ff-only")
    if rc == 0:
        log.info(f"git pull: {out}")
        return True
    log.error(f"git pull failed: {out or err}")
    return False

# ── Process management ────────────────────────────────────────────────────────

class ManagedProcess:
    def __init__(self, name, cmd):
        self.name = name
        self.cmd = cmd
        self.proc = None
        self.restart_at = 0   # epoch time; 0 means "start immediately"

    def start(self):
        log.info(f"Starting {self.name}")
        self.proc = subprocess.Popen(self.cmd, cwd=REPO_DIR)

    def stop(self):
        if self.proc and self.proc.poll() is None:
            log.info(f"Stopping {self.name} (pid {self.proc.pid})")
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def tick(self):
        """Called every loop iteration — starts or restarts as needed."""
        if self.proc is None:
            if time.time() >= self.restart_at:
                self.start()
            return
        rc = self.proc.poll()
        if rc is not None:
            log.warning(f"{self.name} exited (code {rc}), restarting in {RESTART_DELAY}s")
            self.proc = None
            self.restart_at = time.time() + RESTART_DELAY

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="LED display feed watchdog")
    parser.add_argument(
        "--git-interval", type=int, default=DEFAULT_GIT_INTERVAL,
        help=f"Seconds between git update checks (default: {DEFAULT_GIT_INTERVAL})",
    )
    parser.add_argument(
        "--no-git", action="store_true",
        help="Disable git polling",
    )
    args = parser.parse_args()

    processes = [ManagedProcess(name, cmd) for name, cmd in FEEDS]

    log.info(f"Starting watchdog in {REPO_DIR}")
    if not args.no_git:
        log.info(f"Git polling every {args.git_interval}s")

    last_git_check = time.time()

    try:
        while True:
            # Restart any crashed feeds
            for p in processes:
                p.tick()

            # Check for git updates
            if not args.no_git and (time.time() - last_git_check) >= args.git_interval:
                last_git_check = time.time()
                if has_updates():
                    log.info("New commits found — stopping feeds, pulling, restarting")
                    for p in processes:
                        p.stop()
                    pull()
                    # tick() will restart them on the next loop iteration
                    for p in processes:
                        p.restart_at = 0

            time.sleep(5)

    except KeyboardInterrupt:
        log.info("Shutting down")
        for p in processes:
            p.stop()


if __name__ == "__main__":
    main()
