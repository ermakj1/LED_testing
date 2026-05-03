import os
import sys
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
        except (ProcessLookupError, OSError, ValueError):
            pass  # stale lock, overwrite it

    lock_path.write_text(str(os.getpid()))

    import atexit
    atexit.register(lambda: lock_path.unlink(missing_ok=True))
