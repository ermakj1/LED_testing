import os
import sys
import socket
import urllib.error
from pathlib import Path

def single_instance(name):
    """Exit if another instance of this feed is already running."""
    lock_path = Path(__file__).parent / f".{name}.lock"

    if lock_path.exists():
        try:
            pid = int(lock_path.read_text().strip())
            os.kill(pid, 0)  # raises if process is gone
            print(f"{name} already running (pid {pid}) — exiting")
            sys.exit(0)
        except (ProcessLookupError, OSError, ValueError, SystemError):
            pass  # stale lock, overwrite it

    lock_path.write_text(str(os.getpid()))

    import atexit
    atexit.register(lambda: lock_path.unlink(missing_ok=True))


def is_network_error(e):
    """Return a friendly message if e looks like a board-unreachable error, else None."""
    msg = str(e).lower()
    # Unwrap URLError to check the underlying reason
    reason = getattr(e, "reason", e)
    if isinstance(reason, socket.gaierror) or "no address associated with hostname" in msg or "name or service not known" in msg:
        return "Board unreachable — possibly on wrong network (can't resolve hostname)"
    if isinstance(reason, (ConnectionRefusedError, TimeoutError)) or isinstance(e, (ConnectionRefusedError, TimeoutError)):
        return "Board unreachable — connection refused or timed out (board may be rebooting)"
    if "timed out" in msg or "connection refused" in msg:
        return "Board unreachable — connection refused or timed out (board may be rebooting)"
    return None
