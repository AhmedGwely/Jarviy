"""
setup_autostart.py  ─  Run this ONCE to make JARVIS launch at Windows login.

Usage (run from your project folder):
    python setup_autostart.py            ← install
    python setup_autostart.py remove     ← uninstall
    python setup_autostart.py status     ← check
"""

import os
import sys
import subprocess
from pathlib import Path


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR   = get_base_dir()
MAIN_PY    = BASE_DIR / "launcher.py"
PYTHON_EXE = sys.executable
TASK_NAME  = "JARVIS_AI_Assistant"


# ── Task Scheduler (ONLY method used) ─────────────────────────────────────────

def _install_task() -> bool:
    xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>JARVIS AI Autostart</Description>
  </RegistrationInfo>

  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <Delay>PT10S</Delay>
    </LogonTrigger>
  </Triggers>

  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>

  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
  </Settings>

  <Actions>
    <Exec>
      <Command>{PYTHON_EXE}</Command>
      <Arguments>"{MAIN_PY}"</Arguments>
      <WorkingDirectory>{BASE_DIR}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>"""

    xml_path = BASE_DIR / "_jarvis_task.xml"

    try:
        xml_path.write_text(xml, encoding="utf-16")

        r = subprocess.run(
            ["schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(xml_path), "/F"],
            capture_output=True,
            text=True
        )

        xml_path.unlink(missing_ok=True)

        return r.returncode == 0

    except Exception as e:
        xml_path.unlink(missing_ok=True)
        print(f"  Task error: {e}")
        return False


def _remove_task() -> bool:
    r = subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True,
        text=True
    )
    return r.returncode == 0


def _task_exists() -> bool:
    r = subprocess.run(
        ["schtasks", "/Query", "/TN", TASK_NAME],
        capture_output=True,
        text=True
    )
    return r.returncode == 0


# ── CLI ───────────────────────────────────────────────────────────────────────

def install():
    print(f"\n🚀 Installing JARVIS autostart...\n")
    print(f"  Python : {PYTHON_EXE}")
    print(f"  Script : {MAIN_PY}\n")

    if not MAIN_PY.exists():
        print(f"❌ launcher.py not found at {MAIN_PY}")
        print("   Run this script from inside your JARVIS project folder.")
        return

    print("  Installing via Task Scheduler...", end=" ")

    if _install_task():
        print("✅")
        print("\n✅ Done. JARVIS will start automatically at login.\n")
    else:
        print("❌ Failed. Try running as Administrator.\n")


def remove():
    print("\n🗑️  Removing JARVIS autostart...")

    if _remove_task():
        print("✅ Removed Task Scheduler entry.")
    else:
        print("⚠️  No Task Scheduler entry found.")


def status():
    print("\n📋 JARVIS autostart status:")
    print(f"  Task Scheduler : {'✅' if _task_exists() else '❌'}\n")


if __name__ == "__main__":
    cmd = (sys.argv[1].lower() if len(sys.argv) > 1 else "install")

    if cmd == "remove":
        remove()
    elif cmd == "status":
        status()
    else:
        install()