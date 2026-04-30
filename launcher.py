"""
launcher.py  —  JARVIS crash-recovery launcher

Run this instead of main.py:
    python launcher.py

Features:
  - Auto-restarts Jarvis if it crashes
  - Logs every crash with timestamp and traceback to logs/crash.log
  - Max 10 restarts within 60 seconds (prevents infinite crash loops)
  - Clean exit (code 0) is respected — no restart
  - Prints uptime and crash count in the terminal
"""

import subprocess
import sys
import time
import os
from pathlib import Path
from datetime import datetime
from collections import deque

BASE_DIR  = Path(__file__).resolve().parent
LOG_DIR   = BASE_DIR / "logs"
LOG_FILE  = LOG_DIR / "crash.log"
MAIN      = BASE_DIR / "main.py"

MAX_RESTARTS_PER_MINUTE = 10
RESTART_DELAY_S         = 3     # seconds between restarts
CRASH_WINDOW_S          = 60    # rolling window for rate limiting

LOG_DIR.mkdir(exist_ok=True)


def _log(msg: str):
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _uptime_str(start: float) -> str:
    secs  = int(time.time() - start)
    h, r  = divmod(secs, 3600)
    m, s  = divmod(r, 60)
    if h:   return f"{h}h {m}m {s}s"
    if m:   return f"{m}m {s}s"
    return f"{s}s"


def main():
    _log("=" * 60)
    _log("JARVIS launcher started.")
    _log(f"Python: {sys.executable}")
    _log(f"Entry:  {MAIN}")
    _log("=" * 60)

    if not MAIN.exists():
        _log(f"ERROR: main.py not found at {MAIN}")
        sys.exit(1)

    crash_times: deque[float] = deque()
    total_crashes = 0
    launch_time   = time.time()

    while True:
        now = time.time()

        # Prune crash timestamps older than the window
        while crash_times and now - crash_times[0] > CRASH_WINDOW_S:
            crash_times.popleft()

        # Rate limit: too many crashes in a short time = something is fundamentally broken
        if len(crash_times) >= MAX_RESTARTS_PER_MINUTE:
            _log(
                f"FATAL: {MAX_RESTARTS_PER_MINUTE} crashes within {CRASH_WINDOW_S}s. "
                f"Stopping to prevent crash loop. Check logs/crash.log for details."
            )
            _log(f"Total crashes this session: {total_crashes}")
            _log(f"Total uptime:               {_uptime_str(launch_time)}")
            sys.exit(2)

        start = time.time()
        _log(f"Starting JARVIS (crash #{total_crashes} so far)...")

        try:
            result = subprocess.run(
                [sys.executable, str(MAIN)],
                cwd=str(BASE_DIR),
            )
        except KeyboardInterrupt:
            _log("KeyboardInterrupt — shutting down launcher.")
            break
        except Exception as e:
            _log(f"Failed to launch main.py: {e}")
            result = type("R", (), {"returncode": -1})()

        uptime = _uptime_str(start)

        if result.returncode == 0:
            _log(f"JARVIS exited cleanly after {uptime}. Launcher done.")
            break

        total_crashes += 1
        crash_times.append(time.time())

        _log(
            f"JARVIS crashed (exit code {result.returncode}) "
            f"after {uptime}. "
            f"Crash #{total_crashes} — restarting in {RESTART_DELAY_S}s..."
        )

        try:
            time.sleep(RESTART_DELAY_S)
        except KeyboardInterrupt:
            _log("KeyboardInterrupt during restart delay — shutting down.")
            break

    _log(f"Launcher exited. Total uptime: {_uptime_str(launch_time)}, total crashes: {total_crashes}")


if __name__ == "__main__":
    main()
