"""
memory/memory_manager.py  ─  JARVIS Unified Memory System
ONE file handles everything: facts, reminders, session tracking.

Saves to:
  config/memory.json    ← personal facts about the user
  config/reminders.json ← all reminders (persist across reboots)
  config/session.json   ← last-open date (triggers morning brief)
"""

import json
import threading
import time
from datetime import datetime, date, timedelta
from pathlib import Path
import sys

# ── Resolve project root ──────────────────────────────────────────────────────
def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    here = Path(__file__).resolve()
    # memory/memory_manager.py → go up to project root
    return here.parent.parent if here.parent.name == "memory" else here.parent

BASE_DIR      = _get_base_dir()
CONFIG_DIR    = BASE_DIR / "config"
MEMORY_FILE   = CONFIG_DIR / "memory.json"
REMINDER_FILE = CONFIG_DIR / "reminders.json"
SESSION_FILE  = CONFIG_DIR / "session.json"

_lock = threading.Lock()

# ══════════════════════════════════════════════════════════════════════════════
#  LOW-LEVEL I/O
# ══════════════════════════════════════════════════════════════════════════════

def _ensure():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

def _read_json(path: Path, default):
    _ensure()
    if not path.exists():
        return default
    try:
        with _lock:
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def _write_json(path: Path, data) -> None:
    _ensure()
    tmp = path.with_suffix(".tmp")
    with _lock:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

# ══════════════════════════════════════════════════════════════════════════════
#  PERSONAL MEMORY
# ══════════════════════════════════════════════════════════════════════════════

_CATS = ["identity","preferences","projects","relationships","wishes","notes"]
MAX_VAL   = 380
MAX_CHARS = 2400

def load_memory() -> dict:
    data = _read_json(MEMORY_FILE, {})
    if not isinstance(data, dict):
        data = {}
    for k in _CATS:
        data.setdefault(k, {})
    return data

def _trim(mem: dict) -> dict:
    if len(json.dumps(mem, ensure_ascii=False)) <= MAX_CHARS:
        return mem
    entries = []
    for cat, items in mem.items():
        if not isinstance(items, dict):
            continue
        for key, val in items.items():
            ts = val.get("saved_at","0") if isinstance(val,dict) else "0"
            entries.append((cat,key,ts))
    entries.sort(key=lambda x: x[2])
    for cat, key, _ in entries:
        if len(json.dumps(mem, ensure_ascii=False)) <= MAX_CHARS:
            break
        mem[cat].pop(key, None)
    return mem

def save_memory(data: dict) -> None:
    _write_json(MEMORY_FILE, _trim(data))

def update_memory(updates: dict) -> None:
    """
    Merge facts into memory.
    Accepts: {"category": {"key": "value"}}
          or {"category": {"key": {"value": "...", "note": "..."}}}
    """
    mem = load_memory()
    now = datetime.now().isoformat(timespec="seconds")
    changed = False
    for category, items in updates.items():
        if not isinstance(items, dict):
            continue
        if category not in mem:
            mem[category] = {}
        for key, val in items.items():
            if isinstance(val, dict):
                raw  = str(val.get("value","")).strip()
                note = str(val.get("note",""))
            else:
                raw, note = str(val).strip(), ""
            if not raw:
                continue
            if len(raw) > MAX_VAL:
                raw = raw[:MAX_VAL] + "…"
            entry = {"value": raw, "note": note, "saved_at": now}
            old = mem[category].get(key)
            if not isinstance(old, dict) or old.get("value") != raw:
                mem[category][key] = entry
                changed = True
    if changed:
        save_memory(mem)
        print(f"[Memory] 💾 Saved: {list(updates.keys())}")

def forget_memory(category: str, key: str) -> bool:
    mem = load_memory()
    if key in mem.get(category, {}):
        del mem[category][key]
        save_memory(mem)
        return True
    return False

# aliases kept for backward compat
forget = forget_memory

def remember(key: str, value: str, category: str = "notes") -> str:
    if category not in _CATS:
        category = "notes"
    update_memory({category: {key: value}})
    return f"Remembered: {category}/{key} = {value}"

def get_user_name(memory: dict | None = None) -> str:
    if memory is None:
        memory = load_memory()
    e = memory.get("identity", {}).get("name")
    if isinstance(e, dict):
        return e.get("value","Sir") or "Sir"
    return str(e) if e else "Sir"

def format_memory_for_prompt(memory: dict) -> str:
    labels = {
        "identity":      "USER IDENTITY",
        "preferences":   "PREFERENCES",
        "projects":      "ACTIVE PROJECTS",
        "relationships": "RELATIONSHIPS",
        "wishes":        "PLANS & WISHES",
        "notes":         "NOTES",
    }
    lines = ["[WHAT YOU KNOW ABOUT THIS PERSON — use naturally, never recite like a list]"]
    has_any = False
    for cat, label in labels.items():
        items = memory.get(cat, {})
        if not items:
            continue
        lines.append(f"\n{label}:")
        for key, entry in list(items.items())[:15]:
            val = entry.get("value") if isinstance(entry, dict) else str(entry)
            if val:
                has_any = True
                lines.append(f"  • {key.replace('_',' ').title()}: {val}")
    if not has_any:
        return ""
    result = "\n".join(lines)
    if len(result) > 2200:
        result = result[:2197] + "…"
    return result + "\n\n"

# ── Extraction helpers ────────────────────────────────────────────────────────

def should_extract_memory(user_text: str, jarvis_text: str, api_key: str) -> bool:
    triggers = [
        "my name","i am","i'm","i work","i live","i like","i love",
        "i hate","i prefer","my favorite","i study","my job","my project",
        "i'm building","i plan to","i want to","my sister","my brother",
        "my wife","my husband","my friend","i usually","i always",
    ]
    combined = (user_text + " " + jarvis_text).lower()
    return any(t in combined for t in triggers)

def extract_memory(user_text: str, jarvis_text: str, api_key: str) -> dict:
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = (
            "Extract personal facts from this conversation as JSON. "
            "Only include facts explicitly stated by the user. "
            "Return ONLY valid JSON, no markdown:\n"
            '{"category": {"key": "value"}}\n'
            "Categories: identity, preferences, projects, relationships, wishes, notes\n"
            "Return {} if nothing worth saving.\n\n"
            f"User: {user_text}\nAssistant: {jarvis_text}"
        )
        resp = model.generate_content(prompt)
        text = resp.text.strip().strip("```json").strip("```").strip()
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"[Memory] extract error: {e}")
        return {}

# ══════════════════════════════════════════════════════════════════════════════
#  REMINDERS  (fully persistent)
# ══════════════════════════════════════════════════════════════════════════════

def _load_reminders() -> list:
    data = _read_json(REMINDER_FILE, [])
    return data if isinstance(data, list) else []

def _save_reminders(r: list) -> None:
    _write_json(REMINDER_FILE, r)

def save_reminder(date_str: str, time_str: str, message: str,
                  repeat: str = "none") -> str:
    """Save a reminder and return its ID."""
    reminders = _load_reminders()
    rid = f"rem_{int(time.time())}"
    reminders.append({
        "id":      rid,
        "date":    date_str,
        "time":    time_str,
        "message": message,
        "repeat":  repeat,
        "status":  "pending",
        "created": datetime.now().isoformat(timespec="seconds"),
    })
    _save_reminders(reminders)
    print(f"[Reminders] 💾 Saved '{message}' on {date_str} at {time_str}")
    return rid

def get_todays_reminders() -> list:
    today = date.today().isoformat()
    result = [r for r in _load_reminders()
              if r.get("date") == today and r.get("status") == "pending"]
    result.sort(key=lambda r: r.get("time","00:00"))
    return result

def get_upcoming_reminders(days: int = 7) -> list:
    today  = date.today()
    cutoff = today + timedelta(days=days)
    result = []
    for r in _load_reminders():
        if r.get("status") != "pending":
            continue
        try:
            if today <= date.fromisoformat(r["date"]) <= cutoff:
                result.append(r)
        except Exception:
            pass
    result.sort(key=lambda r: (r.get("date",""), r.get("time","")))
    return result

def get_all_reminders() -> list:
    return _load_reminders()

def mark_reminder_done(rid: str) -> bool:
    reminders = _load_reminders()
    for r in reminders:
        if r["id"] == rid:
            r["status"]  = "done"
            r["done_at"] = datetime.now().isoformat(timespec="seconds")
            _save_reminders(reminders)
            return True
    return False

def delete_reminder(rid: str) -> bool:
    reminders = _load_reminders()
    new = [r for r in reminders if r["id"] != rid]
    if len(new) < len(reminders):
        _save_reminders(new)
        return True
    return False

def _fmt12(t: str) -> str:
    try:
        h, m = map(int, t.split(":"))
        return f"{h%12 or 12}:{m:02d} {'AM' if h<12 else 'PM'}"
    except Exception:
        return t

def format_reminders_for_briefing(reminders: list) -> str:
    if not reminders:
        return "You have no reminders for today."
    parts = [f"{r['message']} at {_fmt12(r.get('time',''))}" for r in reminders]
    if len(parts) == 1:
        return f"One reminder today: {parts[0]}."
    return "Today's reminders — " + "; ".join(parts) + "."

# ══════════════════════════════════════════════════════════════════════════════
#  SESSION  (first-launch-of-day detection)
# ══════════════════════════════════════════════════════════════════════════════

def is_first_session_today() -> bool:
    session = _read_json(SESSION_FILE, {})
    return session.get("last_date","") != date.today().isoformat()

def mark_session_today() -> None:
    session = _read_json(SESSION_FILE, {})
    session["last_date"]      = date.today().isoformat()
    session["last_launch"]    = datetime.now().isoformat(timespec="seconds")
    session["launches_today"] = session.get("launches_today", 0) + 1
    _write_json(SESSION_FILE, session)
