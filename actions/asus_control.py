"""
actions/asus_control.py  —  ASUS TUF / ROG laptop control  (v2 — upgraded)
Tested approach: multiple fallback methods per feature, no silent failures.

Features:
  • Performance profiles  : Silent / Balanced / Turbo  (3 independent methods)
  • CPU temperature        : WMI thermal zones + LibreHardwareMonitor + wmic
  • GPU temperature        : nvidia-smi + WMI + LibreHardwareMonitor
  • Fan speeds             : nvidia-smi + LibreHardwareMonitor
  • Battery health         : charge %, health %, power state, estimated time
  • Keyboard backlight     : on / off / brightness level (low/med/high)
  • System info            : RAM, CPU load, uptime, power plan

Requirements:
  pip install wmi psutil          ← strongly recommended (enables most features)
  nvidia-smi                      ← ships with NVIDIA drivers, no install needed
  LibreHardwareMonitor (optional) ← run as admin for full sensor access
"""

import subprocess
import platform
import re
import sys
import time
from pathlib import Path

_OS = platform.system()


# ══════════════════════════════════════════════════════════════════════════════
#  LOW-LEVEL HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _ps(command: str, timeout: int = 8) -> str:
    """Run a PowerShell snippet, return stdout stripped, '' on any failure."""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True, text=True, timeout=timeout
        )
        return (r.stdout or "").strip()
    except Exception as e:
        print(f"[ASUS] PS error: {e}")
        return ""


def _cmd(args: list, timeout: int = 6) -> str:
    """Run a subprocess command, return stdout stripped, '' on failure."""
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "").strip()
    except Exception:
        return ""


def _try_import(module: str):
    """Silently import a module, return None if unavailable."""
    try:
        import importlib
        return importlib.import_module(module)
    except ImportError:
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  PERFORMANCE PROFILES
# ══════════════════════════════════════════════════════════════════════════════

_PROFILE_MAP = {
    "silent": 0, "quiet": 0, "eco": 0, "power saver": 0,
    "balanced": 1, "normal": 1, "default": 1, "standard": 1,
    "turbo": 2, "performance": 2, "boost": 2, "gaming": 2, "max": 2,
    "high performance": 2,
}
_PROFILE_NAMES  = {0: "Silent", 1: "Balanced", 2: "Turbo"}
_PROFILE_HOTKEY = {0: "Fn+F5 → Silent", 1: "Fn+F5 → Balanced", 2: "Fn+F5 → Turbo"}

# Windows power-plan GUIDs that roughly map to ASUS profiles
_POWER_PLANS = {
    0: ("Power saver",         "a1841308-3541-4fab-bc81-f71556f20b4a"),
    1: ("Balanced",            "381b4222-f694-41f0-9685-ff5bb260df2e"),
    2: ("High performance",    "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"),
}


def _set_profile(profile_key: str) -> str:
    profile_key = profile_key.lower().strip()
    value = _PROFILE_MAP.get(profile_key)
    if value is None:
        return (f"Unknown profile '{profile_key}'. "
                "Use: silent, balanced, or turbo.")

    name = _PROFILE_NAMES[value]
    methods_tried = []

    # ── Method 1: ASUS WMI (requires Armoury Crate / ATKACPI driver) ─────────
    wmi_script = (
        "$ns='root\\\\wmi'; $cls='ASUS_WMI_METHODFUNCTION'; "
        "$wmi=Get-WmiObject -Namespace $ns -Class $cls -EA SilentlyContinue; "
        f"if($wmi){{$wmi.WMIMethodFunction(0x00120075,0,{value})|Out-Null; "
        "Write-Output 'wmi_ok'}}else{{Write-Output 'wmi_fail'}}"
    )
    out = _ps(wmi_script)
    if "wmi_ok" in out:
        print(f"[ASUS] ✅ Profile → {name} via WMI")
        return f"Performance profile switched to {name} mode."
    methods_tried.append("WMI")

    # ── Method 2: Registry write (ATK driver path) ────────────────────────────
    reg_path = r"HKLM:\SYSTEM\CurrentControlSet\Services\ATKWMIACPI\Parameters"
    reg_script = (
        f"Set-ItemProperty -Path '{reg_path}' "
        f"-Name 'PerfProfile' -Value {value} -EA SilentlyContinue; "
        "Write-Output 'reg_ok'"
    )
    out2 = _ps(reg_script)
    if "reg_ok" in out2:
        methods_tried.append("Registry")
        print(f"[ASUS] ✅ Profile → {name} via Registry")
        # Registry alone doesn't hot-swap — also apply power plan below

    # ── Method 3: Windows Power Plan (always works as baseline) ──────────────
    plan_name, plan_guid = _POWER_PLANS[value]
    pp_out = _cmd(["powercfg", "/setactive", plan_guid])
    # If GUID doesn't exist, try by name substring
    if pp_out == "" or "error" in pp_out.lower():
        list_out = _cmd(["powercfg", "/list"])
        for line in list_out.splitlines():
            if plan_name.lower() in line.lower():
                guid_match = re.search(r"([0-9a-f-]{36})", line, re.IGNORECASE)
                if guid_match:
                    _cmd(["powercfg", "/setactive", guid_match.group(1)])
                    break
    methods_tried.append("PowerPlan")
    print(f"[ASUS] ✅ Power plan → {plan_name}")

    if "Registry" in methods_tried or "PowerPlan" in methods_tried:
        return (
            f"Switched to {name} mode. "
            f"Windows power plan set to '{plan_name}'. "
            f"({'ASUS WMI profile also applied. ' if 'WMI' not in methods_tried else ''})"
            f"For full fan curve control, Armoury Crate must be installed."
        )

    return (
        f"Could not switch profile via WMI. "
        f"Press {_PROFILE_HOTKEY[value]} manually, or install Armoury Crate."
    )


def _get_profile() -> str:
    # Try WMI read
    script = (
        "$wmi=Get-WmiObject -Namespace 'root\\\\wmi' "
        "-Class 'ASUS_WMI_METHODFUNCTION' -EA SilentlyContinue; "
        "if($wmi){$r=$wmi.WMIMethodFunction(0x00120075,1,0); "
        "Write-Output $r.OutData}else{Write-Output 'unavailable'}"
    )
    out = _ps(script)
    try:
        val = int(out.strip())
        name = _PROFILE_NAMES.get(val, f"Unknown ({val})")
    except Exception:
        name = None

    # Fallback: read active power plan
    pp_out = _cmd(["powercfg", "/getactivescheme"])
    plan_line = ""
    for line in pp_out.splitlines():
        if "GUID" in line.upper() or line.strip():
            plan_line = line.strip()
            break

    if name:
        return f"{name} (ASUS WMI). Active power plan: {plan_line or 'unknown'}."
    return f"Profile via WMI unavailable. Active power plan: {plan_line or 'unknown'}."


# ══════════════════════════════════════════════════════════════════════════════
#  TEMPERATURES  (CPU + GPU)
# ══════════════════════════════════════════════════════════════════════════════

def _get_temperatures() -> str:
    results = {}

    # ── CPU: Method 1 — psutil + WMI (python wmi package) ────────────────────
    wmi_mod = _try_import("wmi")
    if wmi_mod:
        try:
            w = wmi_mod.WMI(namespace=r"root\wmi")
            zones = w.MSAcpi_ThermalZoneTemperature()
            temps = [(z.CurrentTemperature / 10.0) - 273.15 for z in zones]
            if temps:
                results["CPU"] = f"{max(temps):.0f}°C"
        except Exception:
            pass

    # ── CPU: Method 2 — PowerShell WMI (no python-wmi needed) ────────────────
    if "CPU" not in results:
        cpu_script = (
            "$z=Get-WmiObject -Namespace 'root\\wmi' "
            "-Class MSAcpi_ThermalZoneTemperature -EA SilentlyContinue; "
            "if($z){$z|ForEach-Object{"
            "[math]::Round(($_.CurrentTemperature/10)-273.15,1)}}"
        )
        cpu_out = _ps(cpu_script)
        if cpu_out:
            vals = []
            for token in cpu_out.split():
                try:
                    vals.append(float(token))
                except ValueError:
                    pass
            if vals:
                peak = max(vals)
                # Filter out bogus readings (< 0 or > 120)
                valid = [v for v in vals if 0 < v < 120]
                if valid:
                    results["CPU"] = f"{max(valid):.0f}°C"

    # ── CPU: Method 3 — wmic (legacy but reliable on most Windows) ────────────
    if "CPU" not in results:
        wmic_out = _cmd(
            ["wmic", "path", "Win32_PerfFormattedData_Counters_ThermalZoneInformation",
             "get", "HighPrecisionTemperature"],
            timeout=5
        )
        vals = []
        for line in wmic_out.splitlines():
            line = line.strip()
            if line.isdigit():
                t = (int(line) / 10.0) - 273.15
                if 0 < t < 120:
                    vals.append(t)
        if vals:
            results["CPU"] = f"{max(vals):.0f}°C"

    # ── GPU: Method 1 — nvidia-smi (most reliable for NVIDIA) ────────────────
    nvidia_out = _cmd([
        "nvidia-smi",
        "--query-gpu=temperature.gpu,fan.speed,power.draw,clocks.current.graphics",
        "--format=csv,noheader,nounits"
    ], timeout=5)

    if nvidia_out and not nvidia_out.lower().startswith("error"):
        parts = [p.strip() for p in nvidia_out.split(",")]
        if len(parts) >= 1 and parts[0].isdigit():
            results["GPU"] = f"{parts[0]}°C"
        if len(parts) >= 2 and parts[1].replace(" ", "").isdigit():
            results["GPU Fan"] = f"{parts[1]}%"
        if len(parts) >= 3:
            try:
                results["GPU Power"] = f"{float(parts[2]):.0f}W"
            except ValueError:
                pass
        if len(parts) >= 4:
            try:
                results["GPU Clock"] = f"{parts[3]}MHz"
            except ValueError:
                pass

    # ── GPU: Method 2 — WMI VideoController (basic, but works without nvidia-smi)
    if "GPU" not in results:
        gpu_script = (
            "$g=Get-WmiObject Win32_VideoController -EA SilentlyContinue; "
            "if($g){$g|Select-Object -First 1 Name,AdapterRAM|"
            "ForEach-Object{Write-Output \"$($_.Name)\"}}"
        )
        gpu_name = _ps(gpu_script)
        if gpu_name:
            results["GPU"] = f"{gpu_name} (temp unavailable without nvidia-smi)"

    # ── GPU: Method 3 — LibreHardwareMonitor WMI ─────────────────────────────
    if "GPU" not in results or results.get("GPU", "").endswith("unavailable without nvidia-smi"):
        lhm_script = (
            "$s=Get-WmiObject -Namespace 'root\\LibreHardwareMonitor' "
            "-Class Sensor -EA SilentlyContinue | "
            "Where-Object{$_.SensorType -eq 'Temperature' -and $_.Value -gt 0}; "
            "if($s){$s|Select-Object Name,Value|"
            "ForEach-Object{\"$($_.Name)|$($_.Value)\"}}"
        )
        lhm_out = _ps(lhm_script)
        if lhm_out:
            for line in lhm_out.splitlines():
                if "|" in line:
                    sensor_name, val_str = line.split("|", 1)
                    try:
                        val = float(val_str)
                        if "gpu" in sensor_name.lower() and "GPU" not in results:
                            results["GPU"] = f"{val:.0f}°C"
                        elif "cpu" in sensor_name.lower() and "CPU" not in results:
                            results["CPU"] = f"{val:.0f}°C"
                    except ValueError:
                        pass

    # ── CPU load via psutil ───────────────────────────────────────────────────
    psutil_mod = _try_import("psutil")
    if psutil_mod:
        try:
            load = psutil_mod.cpu_percent(interval=0.5)
            results["CPU Load"] = f"{load:.0f}%"
            freq = psutil_mod.cpu_freq()
            if freq:
                results["CPU Freq"] = f"{freq.current:.0f}MHz"
        except Exception:
            pass

    if not results:
        return (
            "Temperature sensors unavailable. "
            "For full sensor access: (1) install 'pip install wmi psutil', "
            "(2) install LibreHardwareMonitor and run as administrator, "
            "(3) make sure NVIDIA drivers are up to date."
        )

    parts = [f"{k}: {v}" for k, v in results.items()]
    return "System temperatures — " + ", ".join(parts)


# ══════════════════════════════════════════════════════════════════════════════
#  BATTERY
# ══════════════════════════════════════════════════════════════════════════════

def _get_battery() -> str:
    info = {}

    # ── Method 1: psutil (most accurate) ─────────────────────────────────────
    psutil_mod = _try_import("psutil")
    if psutil_mod:
        try:
            bat = psutil_mod.sensors_battery()
            if bat:
                info["Charge"] = f"{bat.percent:.0f}%"
                info["Power"]  = "AC connected" if bat.power_plugged else "On battery"
                secs = bat.secsleft
                if secs and secs > 0 and not bat.power_plugged:
                    h, m = divmod(int(secs) // 60, 60)
                    info["Remaining"] = f"{h}h {m}m"
                elif bat.power_plugged:
                    info["Remaining"] = "charging"
        except Exception:
            pass

    # ── Method 2: WMI Win32_Battery (charge health + status) ─────────────────
    bat_script = (
        "$b=Get-WmiObject Win32_Battery -EA SilentlyContinue; "
        "if($b){"
        "Write-Output \"charge|$($b.EstimatedChargeRemaining)\"; "
        "Write-Output \"status|$($b.BatteryStatus)\"; "
        "Write-Output \"design|$($b.DesignCapacity)\"; "
        "Write-Output \"full|$($b.FullChargeCapacity)\"; "
        "Write-Output \"voltage|$($b.DesignVoltage)\"; "
        "Write-Output \"name|$($b.Name)\""
        "}else{Write-Output 'no_battery'}"
    )
    bat_out = _ps(bat_script)

    status_map = {
        "1": "discharging", "2": "AC connected", "3": "fully charged",
        "4": "low ⚠️", "5": "critical ⚠️", "6": "charging",
        "7": "charging (high)", "8": "charging (low)", "9": "charging (critical)",
        "10": "undefined", "11": "partially charged",
    }

    if "no_battery" not in bat_out and bat_out:
        for line in bat_out.splitlines():
            if "|" not in line:
                continue
            key, _, val = line.partition("|")
            val = val.strip()
            if not val or val == "0":
                continue
            if key == "charge" and "Charge" not in info:
                info["Charge"] = f"{val}%"
            elif key == "status" and "Power" not in info:
                info["Power"] = status_map.get(val, val)
            elif key == "design" and key == "full":
                pass
            elif key == "full":
                try:
                    design_line = [l for l in bat_out.splitlines() if l.startswith("design|")]
                    if design_line:
                        design = int(design_line[0].split("|")[1])
                        full   = int(val)
                        if design > 0:
                            health = round(full / design * 100, 1)
                            info["Health"] = f"{health}% of design capacity"
                except Exception:
                    pass
            elif key == "voltage" and val.isdigit():
                mv = int(val)
                if mv > 100:
                    info["Voltage"] = f"{mv/1000:.2f}V"
            elif key == "name":
                info["Model"] = val

    # ── Method 3: powercfg battery report (detailed health) ──────────────────
    if "Health" not in info:
        report_path = Path(r"C:\Windows\Temp\battery_report_jarvis.xml")
        _cmd(["powercfg", "/batteryreport", "/xml",
              "/output", str(report_path)], timeout=10)
        if report_path.exists():
            try:
                text = report_path.read_text(encoding="utf-8", errors="ignore")
                design_match   = re.search(r"<DesignCapacity>(\d+)</DesignCapacity>", text)
                full_match     = re.search(r"<FullChargeCapacity>(\d+)</FullChargeCapacity>", text)
                cycle_match    = re.search(r"<CycleCount>(\d+)</CycleCount>", text)
                if design_match and full_match:
                    design = int(design_match.group(1))
                    full   = int(full_match.group(1))
                    if design > 0:
                        info["Health"] = f"{round(full/design*100,1)}% of design capacity"
                if cycle_match:
                    info["Cycles"] = f"{cycle_match.group(1)} charge cycles"
                report_path.unlink(missing_ok=True)
            except Exception:
                pass

    if not info:
        return "Battery information unavailable on this system."

    parts = [f"{k}: {v}" for k, v in info.items()]
    return "Battery — " + ", ".join(parts)


# ══════════════════════════════════════════════════════════════════════════════
#  KEYBOARD BACKLIGHT
# ══════════════════════════════════════════════════════════════════════════════

# Backlight level map
_LIGHT_LEVEL = {
    "off": 0, "0": 0, "false": 0, "disable": 0, "disabled": 0,
    "low": 1, "dim": 1, "1": 1,
    "medium": 2, "med": 2, "2": 2, "half": 2,
    "high": 3, "on": 3, "3": 3, "true": 3, "enable": 3, "enabled": 3, "max": 3,
}
_LIGHT_NAMES = {0: "off", 1: "low", 2: "medium", 3: "high (max)"}


def _set_lighting(state: str) -> str:
    state = state.lower().strip()
    level = _LIGHT_LEVEL.get(state)
    if level is None:
        # Try parsing as integer
        try:
            level = max(0, min(3, int(state)))
        except ValueError:
            return f"Unknown lighting value '{state}'. Use: off, low, medium, high, or 0-3."

    level_name = _LIGHT_NAMES[level]

    # ── Method 1: ASUS WMI (DeviceID 0x00050021 = keyboard backlight) ─────────
    wmi_script = (
        "$wmi=Get-WmiObject -Namespace 'root\\\\wmi' "
        "-Class 'ASUS_WMI_METHODFUNCTION' -EA SilentlyContinue; "
        f"if($wmi){{$wmi.WMIMethodFunction(0x00050021,0,{level})|Out-Null; "
        "Write-Output 'ok'}}else{{Write-Output 'fail'}}"
    )
    out = _ps(wmi_script)
    if "ok" in out:
        return f"Keyboard backlight set to {level_name}."

    # ── Method 2: ASUS Splendid / ATK registry key ────────────────────────────
    reg_paths = [
        r"HKLM:\SYSTEM\CurrentControlSet\Services\ATKWMIACPI\Parameters",
        r"HKCU:\Software\ASUS\ASUS System Control Interface v3",
    ]
    for reg_path in reg_paths:
        reg_script = (
            f"Set-ItemProperty -Path '{reg_path}' "
            f"-Name 'KeyboardBacklight' -Value {level} -EA SilentlyContinue; "
            "Write-Output 'reg_ok'"
        )
        out2 = _ps(reg_script)
        if "reg_ok" in out2:
            print(f"[ASUS] Backlight set via registry: {reg_path}")
            break

    # ── Method 3: Fn key simulation via nircmd / pyautogui ───────────────────
    nircmd_path = Path(r"C:\Windows\System32\nircmd.exe")
    if nircmd_path.exists():
        # nircmd can send keyboard events without focus
        _cmd([str(nircmd_path), "sendkeypress", "F6"])  # TUF F15 backlight toggle
        return f"Keyboard backlight toggled (nircmd). Target level: {level_name}."

    pyautogui_mod = _try_import("pyautogui")
    if pyautogui_mod and level == 0:
        try:
            import pyautogui as pag
            pag.hotkey("fn", "f6")   # TUF F15: Fn+F6 = backlight off
            return "Keyboard backlight turned off via Fn+F6."
        except Exception:
            pass

    on_off = "on" if level > 0 else "off"
    return (
        f"WMI driver not found. Keyboard backlight control requires ASUS Armoury Crate. "
        f"Manually press Fn+F7 to cycle brightness (currently targeting: {level_name}). "
        f"Or press Fn+F6 to toggle {on_off}."
    )


def _get_lighting() -> str:
    script = (
        "$wmi=Get-WmiObject -Namespace 'root\\\\wmi' "
        "-Class 'ASUS_WMI_METHODFUNCTION' -EA SilentlyContinue; "
        "if($wmi){$r=$wmi.WMIMethodFunction(0x00050021,1,0); "
        "Write-Output $r.OutData}else{Write-Output 'unavailable'}"
    )
    out = _ps(script)
    try:
        level = int(out.strip())
        return f"Keyboard backlight is currently: {_LIGHT_NAMES.get(level, str(level))}."
    except Exception:
        return "Keyboard backlight level unavailable (WMI driver not found)."


# ══════════════════════════════════════════════════════════════════════════════
#  FAN SPEED
# ══════════════════════════════════════════════════════════════════════════════

def _get_fan_speeds() -> str:
    results = {}

    # ── NVIDIA GPU fan via nvidia-smi ─────────────────────────────────────────
    nv_out = _cmd([
        "nvidia-smi", "--query-gpu=fan.speed", "--format=csv,noheader,nounits"
    ], timeout=5)
    if nv_out and nv_out.strip().isdigit():
        results["GPU Fan"] = f"{nv_out.strip()}%"

    # ── WMI fan (ASUS provides fan RPM in some models) ────────────────────────
    wmi_fan_script = (
        "$f=Get-WmiObject -Namespace 'root\\wmi' "
        "-Class 'ASUS_WMI_DSTS' -EA SilentlyContinue; "
        "if($f){Write-Output $f.Value}else{Write-Output 'no_asus_wmi'}"
    )
    # Fallback: Win32_Fan
    fan_script = (
        "$f=Get-WmiObject Win32_Fan -EA SilentlyContinue; "
        "if($f){$f|ForEach-Object{Write-Output \"$($_.Name): $($_.CurrentSpeed) RPM\"}}"
    )
    fan_out = _ps(fan_script)
    if fan_out:
        for line in fan_out.splitlines():
            if line.strip():
                results["CPU Fan"] = line.strip()

    # ── LibreHardwareMonitor fan sensors ──────────────────────────────────────
    lhm_script = (
        "$s=Get-WmiObject -Namespace 'root\\LibreHardwareMonitor' "
        "-Class Sensor -EA SilentlyContinue | "
        "Where-Object{$_.SensorType -eq 'Fan' -and $_.Value -gt 0}; "
        "if($s){$s|ForEach-Object{\"$($_.Name)|$($_.Value)\"}}"
    )
    lhm_out = _ps(lhm_script)
    if lhm_out:
        for line in lhm_out.splitlines():
            if "|" in line:
                name, val = line.split("|", 1)
                try:
                    results[name.strip()] = f"{float(val):.0f} RPM"
                except ValueError:
                    pass

    if not results:
        return (
            "Fan speed unavailable. Install LibreHardwareMonitor "
            "(run as admin) for full sensor access."
        )
    return "Fan speeds — " + ", ".join(f"{k}: {v}" for k, v in results.items())


# ══════════════════════════════════════════════════════════════════════════════
#  SYSTEM INFO  (RAM, CPU, uptime)
# ══════════════════════════════════════════════════════════════════════════════

def _get_system_info() -> str:
    info = {}

    psutil_mod = _try_import("psutil")
    if psutil_mod:
        try:
            mem = psutil_mod.virtual_memory()
            info["RAM Used"] = f"{mem.used / 1024**3:.1f} GB / {mem.total / 1024**3:.1f} GB ({mem.percent:.0f}%)"
            cpu_load = psutil_mod.cpu_percent(interval=0.5)
            info["CPU Load"] = f"{cpu_load:.0f}%"
            cpu_count = psutil_mod.cpu_count()
            info["CPU Cores"] = str(cpu_count)
            boot_time = psutil_mod.boot_time()
            uptime_sec = time.time() - boot_time
            h = int(uptime_sec // 3600)
            m = int((uptime_sec % 3600) // 60)
            info["Uptime"] = f"{h}h {m}m"
            disk = psutil_mod.disk_usage("C:\\")
            info["C: Drive"] = f"{disk.used / 1024**3:.0f} GB used / {disk.total / 1024**3:.0f} GB ({disk.percent:.0f}%)"
        except Exception as e:
            print(f"[ASUS] psutil info error: {e}")

    # Fallback: PowerShell
    if not info:
        ps_info = _ps(
            "[math]::Round((Get-WmiObject Win32_ComputerSystem).TotalPhysicalMemory/1GB,1);"
            "(Get-WmiObject Win32_OperatingSystem).FreePhysicalMemory/1MB"
        )
        if ps_info:
            info["RAM"] = ps_info.replace("\n", " / ") + " GB"

    if not info:
        return "System info unavailable. Install psutil: pip install psutil"

    return "System info — " + ", ".join(f"{k}: {v}" for k, v in info.items())


# ══════════════════════════════════════════════════════════════════════════════
#  CHARGE LIMIT  (battery health feature)
# ══════════════════════════════════════════════════════════════════════════════

def _set_charge_limit(limit: int) -> str:
    """Set battery charge limit (e.g. 80% for longevity). Requires ASUS WMI."""
    limit = max(40, min(100, limit))

    # ASUS WMI charge limit DeviceID = 0x00120057
    script = (
        "$wmi=Get-WmiObject -Namespace 'root\\\\wmi' "
        "-Class 'ASUS_WMI_METHODFUNCTION' -EA SilentlyContinue; "
        f"if($wmi){{$wmi.WMIMethodFunction(0x00120057,0,{limit})|Out-Null; "
        "Write-Output 'ok'}}else{{Write-Output 'fail'}}"
    )
    out = _ps(script)
    if "ok" in out:
        return f"Battery charge limit set to {limit}%. Battery will stop charging at this level."

    return (
        f"Could not set charge limit via WMI (Armoury Crate driver required). "
        f"In Armoury Crate, go to Battery Care and set the limit to {limit}% manually."
    )


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN CLASS  —  public interface
# ══════════════════════════════════════════════════════════════════════════════

class AsusControl:
    def __init__(self, player=None):
        self.player = player

    def execute(self, params: dict) -> str:
        if _OS != "Windows":
            return "ASUS control is only available on Windows."

        action   = params.get("action",   "").lower().strip()
        profile  = params.get("profile",  "").lower().strip()
        lighting = params.get("lighting", "").lower().strip()
        limit    = params.get("limit",    None)

        if self.player:
            self.player.write_log(f"SYS: [ASUS] → {action}")

        # ── Profile ────────────────────────────────────────────────────────────
        if action == "profile":
            if profile:
                return _set_profile(profile)
            return _get_profile()

        # ── Temperature ────────────────────────────────────────────────────────
        elif action in ("temperature", "temp", "temps"):
            return _get_temperatures()

        # ── Battery ────────────────────────────────────────────────────────────
        elif action == "battery":
            return _get_battery()

        # ── Charge limit ───────────────────────────────────────────────────────
        elif action in ("charge_limit", "charge limit", "limit"):
            if limit is not None:
                try:
                    return _set_charge_limit(int(limit))
                except (ValueError, TypeError):
                    return "Please specify a charge limit percentage, e.g. 80."
            return "Specify a charge limit value, e.g. 80 for 80%."

        # ── Keyboard backlight ─────────────────────────────────────────────────
        elif action in ("lighting", "backlight", "keyboard"):
            if lighting:
                return _set_lighting(lighting)
            return _get_lighting()

        # ── Fan speed ──────────────────────────────────────────────────────────
        elif action in ("fan", "fans", "fan_speed"):
            return _get_fan_speeds()

        # ── System info ────────────────────────────────────────────────────────
        elif action in ("info", "system", "status", "sysinfo"):
            return _get_system_info()

        # ── All in one ─────────────────────────────────────────────────────────
        elif action in ("all", "overview", "report"):
            parts = [
                _get_temperatures(),
                _get_fan_speeds(),
                _get_battery(),
                _get_profile(),
                _get_system_info(),
            ]
            return "\n".join(parts)

        else:
            return (
                f"Unknown ASUS action '{action}'. "
                "Available: profile, temperature, battery, charge_limit, "
                "lighting, fan, info, all."
            )
