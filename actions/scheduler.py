"""
actions/scheduler.py  —  JARVIS smart task scheduler

Lets Jarvis execute any action at a specific time or after a delay.
Voice examples:
  "Remind me at 3pm to drink water"
  "Open Spotify in 10 minutes"
  "Every day at 9am check the weather"
  "Turn off the lights in 30 minutes"

Requirements:
  pip install apscheduler

Natural language time parsing is built-in (no extra library needed).
Falls back to APScheduler's cron/interval/date triggers.
"""

import re
import uuid
import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
import sys

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron   import CronTrigger
    from apscheduler.triggers.date   import DateTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    _APScheduler = True
except ImportError:
    _APScheduler = False
    print("[Scheduler] ⚠️  APScheduler not installed. Run: pip install apscheduler")


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

_TASKS_FILE = _get_base_dir() / "memory" / "scheduled_tasks.json"


# ── Natural language time parser ───────────────────────────────────────────────

def _parse_when(when_str: str) -> tuple[datetime | None, bool, str | None]:
    """
    Parse a natural language time string.
    Returns (run_at: datetime | None, is_recurring: bool, cron_expr: str | None)

    Examples:
      "in 10 minutes"        → (now+10min, False, None)
      "at 14:30"             → (today 14:30, False, None)
      "3pm"                  → (today 15:00, False, None)
      "tomorrow at 9am"      → (tomorrow 09:00, False, None)
      "every day at 9am"     → (None, True, "0 9 * * *")
      "every hour"           → (None, True, "0 * * * *")
      "every 30 minutes"     → (None, True, interval:30min)
    """
    if not when_str:
        return None, False, None

    s   = when_str.lower().strip()
    now = datetime.now()

    # ── Recurring patterns ─────────────────────────────────────────────────────
    # "every day at HH:MM" / "every morning at 9"
    m = re.search(r"every\s+day\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", s)
    if m:
        h, mn, ampm = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        h = _to_24h(h, ampm)
        return None, True, f"{mn} {h} * * *"

    # "every weekday at HH"
    m = re.search(r"every\s+weekday\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", s)
    if m:
        h, mn, ampm = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        h = _to_24h(h, ampm)
        return None, True, f"{mn} {h} * * 1-5"

    # "every N minutes"
    m = re.search(r"every\s+(\d+)\s+minutes?", s)
    if m:
        return None, True, f"interval:{m.group(1)}m"

    # "every N hours"
    m = re.search(r"every\s+(\d+)\s+hours?", s)
    if m:
        return None, True, f"interval:{m.group(1)}h"

    # "every hour"
    if re.search(r"every\s+hour\b", s):
        return None, True, "0 * * * *"

    # "every morning" → 8am
    if re.search(r"every\s+morning\b", s):
        return None, True, "0 8 * * *"

    # "every evening" → 6pm
    if re.search(r"every\s+evening\b", s):
        return None, True, "0 18 * * *"

    # ── One-time patterns ──────────────────────────────────────────────────────
    # "in N minutes"
    m = re.search(r"in\s+(\d+)\s+minutes?", s)
    if m:
        return now + timedelta(minutes=int(m.group(1))), False, None

    # "in N hours"
    m = re.search(r"in\s+(\d+)\s+hours?", s)
    if m:
        return now + timedelta(hours=int(m.group(1))), False, None

    # "in N seconds"
    m = re.search(r"in\s+(\d+)\s+seconds?", s)
    if m:
        return now + timedelta(seconds=int(m.group(1))), False, None

    # "at HH:MM" or "at HH:MM am/pm"
    m = re.search(r"at\s+(\d{1,2}):(\d{2})\s*(am|pm)?", s)
    if m:
        h, mn, ampm = int(m.group(1)), int(m.group(2)), m.group(3)
        h  = _to_24h(h, ampm)
        dt = now.replace(hour=h, minute=mn, second=0, microsecond=0)
        if dt <= now:
            dt += timedelta(days=1)
        return dt, False, None

    # "at Hpm" or "Hpm" (no colon)
    m = re.search(r"(?:at\s+)?(\d{1,2})\s*(am|pm)\b", s)
    if m:
        h, ampm = int(m.group(1)), m.group(2)
        h  = _to_24h(h, ampm)
        dt = now.replace(hour=h, minute=0, second=0, microsecond=0)
        if dt <= now:
            dt += timedelta(days=1)
        return dt, False, None

    # "tomorrow at ..."
    m = re.search(r"tomorrow\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", s)
    if m:
        h, mn, ampm = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        h  = _to_24h(h, ampm)
        dt = (now + timedelta(days=1)).replace(hour=h, minute=mn, second=0, microsecond=0)
        return dt, False, None

    # "YYYY-MM-DD HH:MM"
    m = re.search(r"(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})", s)
    if m:
        try:
            dt = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M")
            return dt, False, None
        except ValueError:
            pass

    return None, False, None


def _to_24h(h: int, ampm: str | None) -> int:
    if ampm == "pm" and h != 12:
        return h + 12
    if ampm == "am" and h == 12:
        return 0
    return h


# ── Persistence ────────────────────────────────────────────────────────────────

def _load_tasks() -> dict:
    try:
        if _TASKS_FILE.exists():
            return json.loads(_TASKS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def _save_tasks(tasks: dict):
    try:
        _TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TASKS_FILE.write_text(json.dumps(tasks, indent=2, default=str), encoding="utf-8")
    except Exception as e:
        print(f"[Scheduler] save_tasks failed: {e}")


# ── Main scheduler class ───────────────────────────────────────────────────────

class JarvisScheduler:
    def __init__(self, speak_fn=None, player=None):
        self.speak  = speak_fn
        self.player = player
        self._tasks = _load_tasks()
        self._lock  = threading.Lock()

        if _APScheduler:
            self._sched = BackgroundScheduler(
                job_defaults={"misfire_grace_time": 60},
                timezone="local"
            )
        else:
            self._sched = None

    def start(self):
        if self._sched and not self._sched.running:
            self._sched.start()
            self._restore_jobs()
            print("[Scheduler] ✅ Started.")

    def shutdown(self):
        if self._sched and self._sched.running:
            self._sched.shutdown(wait=False)

    def _restore_jobs(self):
        """Re-register persisted recurring jobs after restart."""
        with self._lock:
            for task_id, meta in list(self._tasks.items()):
                if not meta.get("recurring"):
                    continue
                cron = meta.get("cron", "")
                task_text = meta.get("task", "")
                try:
                    self._register_job(task_id, task_text, cron, recurring=True)
                    print(f"[Scheduler] Restored recurring job {task_id}: {task_text}")
                except Exception as e:
                    print(f"[Scheduler] Failed to restore {task_id}: {e}")

    def _make_callback(self, task_id: str, task_text: str, speak_reminder: bool, recurring: bool):
        def callback():
            print(f"[Scheduler] 🔔 Firing: {task_text}")
            if self.player:
                self.player.write_log(f"SYS: Scheduled task — {task_text}")
            if speak_reminder and self.speak:
                self.speak(f"Sir, scheduled reminder: {task_text}")
            if not recurring:
                with self._lock:
                    self._tasks.pop(task_id, None)
                    _save_tasks(self._tasks)
        return callback

    def _register_job(self, task_id: str, task_text: str, trigger_spec,
                      recurring: bool, speak_reminder: bool = True):
        """Add a job to APScheduler."""
        if not self._sched:
            return

        cb = self._make_callback(task_id, task_text, speak_reminder, recurring)

        if isinstance(trigger_spec, datetime):
            self._sched.add_job(cb, DateTrigger(run_date=trigger_spec), id=task_id, replace_existing=True)

        elif isinstance(trigger_spec, str):
            if trigger_spec.startswith("interval:"):
                # e.g. "interval:30m" or "interval:2h"
                val = trigger_spec[9:]
                if val.endswith("m"):
                    self._sched.add_job(cb, IntervalTrigger(minutes=int(val[:-1])), id=task_id, replace_existing=True)
                elif val.endswith("h"):
                    self._sched.add_job(cb, IntervalTrigger(hours=int(val[:-1])), id=task_id, replace_existing=True)
            else:
                # standard cron: "0 9 * * *"
                parts = trigger_spec.split()
                if len(parts) == 5:
                    mn, h, dom, mo, dow = parts
                    self._sched.add_job(
                        cb,
                        CronTrigger(minute=mn, hour=h, day=dom, month=mo, day_of_week=dow),
                        id=task_id, replace_existing=True
                    )

    def execute(self, params: dict) -> str:
        action       = params.get("action", "add").lower().strip()
        task_text    = params.get("task", "").strip()
        when_str     = params.get("when", "").strip()
        repeat       = params.get("repeat", False)
        task_id      = params.get("task_id", "").strip()
        speak_remind = params.get("speak_reminder", True)

        if self.player:
            self.player.write_log(f"[Scheduler] {action}")

        if action == "add":
            return self._add_task(task_text, when_str, repeat, speak_remind)

        elif action == "list":
            return self._list_tasks()

        elif action == "cancel":
            if not task_id:
                return "Please provide a task_id to cancel."
            return self._cancel_task(task_id)

        elif action == "cancel_all":
            return self._cancel_all()

        else:
            return f"Unknown scheduler action '{action}'. Use: add, list, cancel, cancel_all."

    def _add_task(self, task_text: str, when_str: str, repeat: bool, speak_reminder: bool) -> str:
        if not task_text:
            return "No task specified. What should I do?"
        if not when_str:
            return f"When should I do '{task_text}'? Please specify a time."

        run_at, is_recurring, cron = _parse_when(when_str)

        # If user said "repeat" explicitly, treat as recurring
        if repeat:
            is_recurring = True

        task_id = str(uuid.uuid4())[:8]

        if not _APScheduler:
            # Fallback: use Python threading.Timer for one-shot tasks
            if run_at:
                delay = (run_at - datetime.now()).total_seconds()
                if delay > 0:
                    def fire():
                        if self.speak:
                            self.speak(f"Sir, scheduled reminder: {task_text}")
                        if self.player:
                            self.player.write_log(f"SYS: Reminder — {task_text}")
                    t = threading.Timer(delay, fire)
                    t.daemon = True
                    t.start()
                    with self._lock:
                        self._tasks[task_id] = {"task": task_text, "when": str(run_at), "recurring": False}
                        _save_tasks(self._tasks)
                    return f"Reminder set for {run_at.strftime('%I:%M %p')} — '{task_text}'. (ID: {task_id})"
            return "APScheduler not installed. Run: pip install apscheduler"

        if is_recurring:
            trigger_spec = cron
            if not trigger_spec:
                return f"Could not parse '{when_str}' as a recurring schedule."
            self._register_job(task_id, task_text, trigger_spec, recurring=True, speak_reminder=speak_reminder)
            with self._lock:
                self._tasks[task_id] = {"task": task_text, "cron": trigger_spec, "recurring": True}
                _save_tasks(self._tasks)
            return f"Recurring task scheduled — '{task_text}' ({when_str}). ID: {task_id}"

        else:
            if not run_at:
                return f"Could not understand the time '{when_str}'. Try '3pm', 'in 10 minutes', or 'tomorrow at 9am'."
            if run_at <= datetime.now():
                return f"That time is in the past. Did you mean tomorrow?"
            self._register_job(task_id, task_text, run_at, recurring=False, speak_reminder=speak_reminder)
            with self._lock:
                self._tasks[task_id] = {"task": task_text, "when": str(run_at), "recurring": False}
                _save_tasks(self._tasks)
            time_str = run_at.strftime("%I:%M %p")
            if run_at.date() != datetime.now().date():
                time_str = run_at.strftime("%A at %I:%M %p")
            return f"Got it. I'll remind you {time_str} — '{task_text}'. (ID: {task_id})"

    def _list_tasks(self) -> str:
        with self._lock:
            tasks = dict(self._tasks)
        if not tasks:
            return "No scheduled tasks."
        lines = ["Scheduled tasks:"]
        for tid, meta in tasks.items():
            kind = "recurring" if meta.get("recurring") else "one-time"
            when = meta.get("cron") or meta.get("when", "?")
            lines.append(f"  [{tid}] {meta.get('task', '?')} — {kind} ({when})")
        return "\n".join(lines)

    def _cancel_task(self, task_id: str) -> str:
        with self._lock:
            if task_id not in self._tasks:
                return f"No task found with ID '{task_id}'."
            task_text = self._tasks[task_id].get("task", "unknown")
            del self._tasks[task_id]
            _save_tasks(self._tasks)
        if self._sched:
            try:
                self._sched.remove_job(task_id)
            except Exception:
                pass
        return f"Task '{task_text}' (ID: {task_id}) cancelled."

    def _cancel_all(self) -> str:
        with self._lock:
            count = len(self._tasks)
            self._tasks.clear()
            _save_tasks(self._tasks)
        if self._sched:
            try:
                self._sched.remove_all_jobs()
            except Exception:
                pass
        return f"All {count} scheduled tasks cancelled."
