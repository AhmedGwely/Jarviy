"""
core/morning_brief.py  ─  JARVIS Morning Briefing

Called once per day on first launch.
Speaks: greeting + laptop health + today's reminders + active projects.
Uses only stdlib + psutil + nvidia-smi (no extra deps).
"""

import subprocess
import time
from datetime import datetime, date
from pathlib import Path
import sys


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    here = Path(__file__).resolve()
    return here.parent.parent if here.parent.name == "core" else here.parent

sys.path.insert(0, str(_get_base_dir()))


# ── Small hardware helpers ─────────────────────────────────────────────────────

def _ps(cmd: str, timeout: int = 6) -> str:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=timeout
        )
        return (r.stdout or "").strip()
    except Exception:
        return ""

def _cmd(args: list, timeout: int = 5) -> str:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "").strip()
    except Exception:
        return ""

def _try_import(name: str):
    try:
        import importlib
        return importlib.import_module(name)
    except ImportError:
        return None


def _battery_line() -> str:
    """Return a short battery status string."""
    psutil = _try_import("psutil")
    if psutil:
        try:
            b = psutil.sensors_battery()
            if b:
                pct    = int(b.percent)
                status = "charging" if b.power_plugged else "on battery"
                warn   = ""
                if not b.power_plugged and pct < 20:
                    warn = " — I recommend plugging in soon"
                return f"battery at {pct}%, {status}{warn}"
        except Exception:
            pass

    # PowerShell fallback
    out = _ps(
        "$b=Get-WmiObject Win32_Battery -EA SilentlyContinue;"
        "if($b){Write-Output \"$($b.EstimatedChargeRemaining)|$($b.BatteryStatus)\"}"
    )
    if "|" in out:
        pct, code = out.split("|", 1)
        status_map = {"1":"on battery","2":"plugged in","3":"fully charged","6":"charging"}
        status = status_map.get(code.strip(), "unknown status")
        return f"battery at {pct.strip()}%, {status}"
    return ""


def _cpu_line() -> str:
    """Return CPU load string."""
    psutil = _try_import("psutil")
    if psutil:
        try:
            load = psutil.cpu_percent(interval=0.4)
            freq = psutil.cpu_freq()
            if freq:
                return f"CPU at {load:.0f}% load, {freq.current:.0f} MHz"
            return f"CPU load {load:.0f}%"
        except Exception:
            pass

    # WMI fallback for CPU temp
    out = _ps(
        "$z=Get-WmiObject -Namespace 'root\\wmi' -Class MSAcpi_ThermalZoneTemperature -EA SilentlyContinue;"
        "if($z){$z|ForEach-Object{[math]::Round(($_.CurrentTemperature/10)-273.15,1)}}"
    )
    if out:
        vals = []
        for tok in out.split():
            try:
                v = float(tok)
                if 0 < v < 120:
                    vals.append(v)
            except ValueError:
                pass
        if vals:
            return f"CPU temperature {max(vals):.0f}°C"
    return ""


def _gpu_line() -> str:
    """Return GPU temp string via nvidia-smi."""
    out = _cmd([
        "nvidia-smi",
        "--query-gpu=temperature.gpu,fan.speed",
        "--format=csv,noheader,nounits"
    ])
    if out and not out.lower().startswith("error"):
        parts = [p.strip() for p in out.split(",")]
        if parts[0].isdigit():
            t = int(parts[0])
            warn = " — running warm" if t > 80 else ""
            fan  = f", fan at {parts[1]}%" if len(parts) > 1 and parts[1].isdigit() else ""
            return f"GPU at {t}°C{fan}{warn}"
    return ""


def _ram_line() -> str:
    psutil = _try_import("psutil")
    if psutil:
        try:
            m = psutil.virtual_memory()
            return f"RAM {m.used/1024**3:.1f} of {m.total/1024**3:.1f} GB used ({m.percent:.0f}%)"
        except Exception:
            pass
    return ""


def _uptime_line() -> str:
    psutil = _try_import("psutil")
    if psutil:
        try:
            secs = time.time() - psutil.boot_time()
            h = int(secs // 3600)
            m = int((secs % 3600) // 60)
            if h == 0:
                return f"system up {m} minutes"
            return f"system up {h}h {m}m"
        except Exception:
            pass
    return ""


def _fmt12(t: str) -> str:
    try:
        h, m = map(int, t.split(":"))
        return f"{h%12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"
    except Exception:
        return t


# ── Main builder ──────────────────────────────────────────────────────────────

def build_morning_brief(user_name: str, todays_reminders: list, memory: dict) -> str:
    """
    Build the spoken morning briefing string.
    Combines: greeting, hardware health, today's reminders, active projects.
    """
    hour = datetime.now().hour
    if   5  <= hour < 12: greeting = "Good morning"
    elif 12 <= hour < 17: greeting = "Good afternoon"
    elif 17 <= hour < 21: greeting = "Good evening"
    else:                 greeting = "Good evening"

    today_str = date.today().strftime("%A, %B %d")
    sentences = []

    # ── Greeting ──────────────────────────────────────────────────────────────
    sentences.append(f"{greeting}, {user_name}. Today is {today_str}.")

    # ── Laptop health — collect all available lines ────────────────────────────
    health = []
    bat = _battery_line()
    if bat:
        health.append(bat)
    cpu = _cpu_line()
    if cpu:
        health.append(cpu)
    gpu = _gpu_line()
    if gpu:
        health.append(gpu)
    ram = _ram_line()
    if ram:
        health.append(ram)
    upt = _uptime_line()
    if upt:
        health.append(upt)

    if health:
        sentences.append("Laptop status: " + ", ".join(health) + ".")
    else:
        sentences.append("Laptop hardware sensors are offline.")

    # ── Today's reminders ─────────────────────────────────────────────────────
    if not todays_reminders:
        sentences.append("You have no reminders set for today.")
    elif len(todays_reminders) == 1:
        r = todays_reminders[0]
        sentences.append(
            f"You have one reminder today: {r['message']} at {_fmt12(r.get('time',''))}."
        )
    else:
        sentences.append(f"You have {len(todays_reminders)} reminders today.")
        # Read up to 5
        for r in todays_reminders[:5]:
            sentences.append(
                f"{r['message']} at {_fmt12(r.get('time',''))}."
            )

    # ── Active projects from memory ───────────────────────────────────────────
    projects = memory.get("projects", {})
    if projects:
        names = []
        for k, v in list(projects.items())[:3]:
            val = v.get("value", k) if isinstance(v, dict) else str(v)
            names.append(val)
        sentences.append("Active projects: " + ", ".join(names) + ".")

    # ── Closing ───────────────────────────────────────────────────────────────
    sentences.append("All systems online. How can I assist you today?")

    return " ".join(sentences)
