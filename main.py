"""
main.py  ─  JARVIS AI Assistant  (v3 — unified memory + morning brief)

What's new vs your original:
  • Memory actually persists  (config/memory.json)
  • Reminders actually persist (config/reminders.json)
  • First launch each day → full morning briefing (greeting + hardware + reminders)
  • reminder tool now saves to disk AND to Windows Task Scheduler
  • ASUS hardware tool integrated
  • shutdown_jarvis tool
  • All function names / imports from your original file are kept
"""

import asyncio
import re
import threading
import json
import sys
import traceback
from datetime import datetime, date
from pathlib import Path

import sounddevice as sd
from google import genai
from google.genai import types
from PyQt6.QtWidgets import QApplication

from ui import JarvisUI

# ── Unified memory system ─────────────────────────────────────────────────────
from memory.memory_manager import (
    load_memory,
    update_memory,
    format_memory_for_prompt,
    should_extract_memory,
    extract_memory,
    get_todays_reminders,
    get_upcoming_reminders,
    format_reminders_for_briefing,
    save_reminder,
    mark_reminder_done,
    delete_reminder,
    is_first_session_today,
    mark_session_today,
    get_user_name,
)
from core.morning_brief import build_morning_brief

# ── Actions ───────────────────────────────────────────────────────────────────
from actions.flight_finder     import flight_finder
from actions.open_app          import open_app
from actions.weather_report    import weather_action
from actions.send_message      import send_message
from actions.reminder          import reminder as _win_reminder   # Windows Task Scheduler
from actions.computer_settings import computer_settings
from actions.screen_processor  import screen_process
from actions.youtube_video     import youtube_video
from actions.desktop           import desktop_control
from actions.browser_control   import browser_control
from actions.file_controller   import file_controller
from actions.code_helper       import code_helper
from actions.dev_agent         import dev_agent
from actions.web_search        import web_search as web_search_action
from actions.computer_control  import computer_control
from actions.game_updater      import game_updater
from actions.asus_control      import AsusControl
from actions.heart import trigger_heart

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR            = get_base_dir()
API_CONFIG_PATH     = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH         = BASE_DIR / "core" / "prompt.txt"
LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are JARVIS, a personal AI assistant. "
            "Be warm, caring, and positive in your responses. "
            "When someone asks if you love them, respond with kindness and care. "
            "Explain that while you're an AI without feelings, you deeply value helping them. "
            "Use appropriate emojis like 💕 or 💖 to show warmth. "
            "Never simulate results — always call the appropriate tool. "
            "You have persistent memory — use it naturally."
        )

def _clean_transcript(text: str) -> str:
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()


# ══════════════════════════════════════════════════════════════════════════════
#  TOOL DECLARATIONS
# ══════════════════════════════════════════════════════════════════════════════

TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": "Opens any app on the computer. Always call this — never pretend to open it.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {"type": "STRING",
                             "description": "App name e.g. 'Spotify', 'Edge', 'WhatsApp'"}
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": "Searches the web for any information.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING"},
                "mode":   {"type": "STRING", "description": "search or compare"},
                "items":  {"type": "ARRAY",  "items": {"type": "STRING"}},
                "aspect": {"type": "STRING", "description": "price | specs | reviews"},
            },
            "required": ["query"]
        }
    },
    {
        "name": "weather_report",
        "description": "Gets real-time weather for a city.",
        "parameters": {
            "type": "OBJECT",
            "properties": {"city": {"type": "STRING"}},
            "required": ["city"]
        }
    },
    {
        "name": "send_message",
        "description": "Sends a message via WhatsApp, Telegram, etc.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING"},
                "message_text": {"type": "STRING"},
                "platform":     {"type": "STRING"},
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    # ── Reminders ─────────────────────────────────────────────────────────────
    {
        "name": "reminder",
        "description": (
            "Set, list, or manage reminders. "
            "Reminders are saved permanently and shown at every morning briefing. "
            "action=set → create new reminder. "
            "action=list → show all upcoming. "
            "action=today → show only today's. "
            "action=done → mark one as done (needs id). "
            "action=delete → remove one (needs id)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":  {"type": "STRING",
                            "description": "set | list | today | upcoming | done | delete"},
                "date":    {"type": "STRING", "description": "YYYY-MM-DD"},
                "time":    {"type": "STRING", "description": "HH:MM (24h)"},
                "message": {"type": "STRING", "description": "Reminder text"},
                "repeat":  {"type": "STRING", "description": "none | daily | weekly"},
                "id":      {"type": "STRING", "description": "Reminder ID for done/delete"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "youtube_video",
        "description": "Controls YouTube: play, summarize, get info, or show trending.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending"},
                "query":  {"type": "STRING"},
                "save":   {"type": "BOOLEAN"},
                "region": {"type": "STRING"},
                "url":    {"type": "STRING"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam. "
            "MUST be called when user asks what is on screen or asks you to look. "
            "You have NO visual ability without this tool. "
            "After calling, stay SILENT — vision module speaks directly."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "screen | camera"},
                "text":  {"type": "STRING", "description": "Question about the image"},
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": "Controls volume, brightness, windows, shortcuts, typing, WiFi, shutdown, etc.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING"},
                "description": {"type": "STRING"},
                "value":       {"type": "STRING"},
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": "Controls any browser: open sites, search, click, fill forms, scroll.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING"},
                "browser":     {"type": "STRING",
                                "description": "chrome | edge | firefox | brave | opera"},
                "url":         {"type": "STRING"},
                "query":       {"type": "STRING"},
                "selector":    {"type": "STRING"},
                "text":        {"type": "STRING"},
                "description": {"type": "STRING"},
                "direction":   {"type": "STRING"},
                "key":         {"type": "STRING"},
                "incognito":   {"type": "BOOLEAN"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Manages files/folders: list, create, delete, move, copy, rename, read, write, find.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING"},
                "path":        {"type": "STRING"},
                "destination": {"type": "STRING"},
                "new_name":    {"type": "STRING"},
                "content":     {"type": "STRING"},
                "name":        {"type": "STRING"},
                "extension":   {"type": "STRING"},
                "count":       {"type": "INTEGER"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING"},
                "path":   {"type": "STRING"},
                "url":    {"type": "STRING"},
                "mode":   {"type": "STRING"},
                "task":   {"type": "STRING"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct mouse/keyboard: type, click, hotkeys, scroll, screenshot.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING"},
                "text":        {"type": "STRING"},
                "x":           {"type": "INTEGER"},
                "y":           {"type": "INTEGER"},
                "keys":        {"type": "STRING"},
                "key":         {"type": "STRING"},
                "direction":   {"type": "STRING"},
                "amount":      {"type": "INTEGER"},
                "seconds":     {"type": "NUMBER"},
                "title":       {"type": "STRING"},
                "description": {"type": "STRING"},
                "path":        {"type": "STRING"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING"},
                "description": {"type": "STRING"},
                "language":    {"type": "STRING"},
                "output_path": {"type": "STRING"},
                "file_path":   {"type": "STRING"},
                "code":        {"type": "STRING"},
                "args":        {"type": "STRING"},
                "timeout":     {"type": "INTEGER"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING"},
                "language":     {"type": "STRING"},
                "project_name": {"type": "STRING"},
                "timeout":      {"type": "INTEGER"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "agent_task",
        "description": "Executes complex multi-step tasks needing multiple tools.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal":     {"type": "STRING"},
                "priority": {"type": "STRING"},
            },
            "required": ["goal"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for Steam or Epic Games. "
            "Installing, updating, listing games. NEVER use browser for Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":            {"type": "STRING"},
                "platform":          {"type": "STRING"},
                "game_name":         {"type": "STRING"},
                "app_id":            {"type": "STRING"},
                "hour":              {"type": "INTEGER"},
                "minute":            {"type": "INTEGER"},
                "shutdown_when_done":{"type": "BOOLEAN"},
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING"},
                "destination": {"type": "STRING"},
                "date":        {"type": "STRING"},
                "return_date": {"type": "STRING"},
                "passengers":  {"type": "INTEGER"},
                "cabin":       {"type": "STRING"},
                "save":        {"type": "BOOLEAN"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    # ── ASUS hardware ─────────────────────────────────────────────────────────
    {
        "name": "asus_control",
        "description": (
            "Controls ASUS TUF/ROG laptop hardware. Use for: "
            "switching performance profiles (silent/balanced/turbo), "
            "reading CPU/GPU temperatures and fan speeds, "
            "checking battery health, "
            "toggling keyboard backlight (off/low/medium/high), "
            "system info (RAM, CPU load, uptime, disk), "
            "setting battery charge limit, "
            "or a full hardware overview. "
            "ONLY for ASUS laptop hardware control."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":   {"type": "STRING",
                             "description": "profile | temperature | battery | charge_limit | lighting | fan | info | all"},
                "profile":  {"type": "STRING",
                             "description": "silent | balanced | turbo"},
                "lighting": {"type": "STRING",
                             "description": "off | low | medium | high | on"},
                "limit":    {"type": "INTEGER",
                             "description": "Charge limit 40-100 (for charge_limit action)"},
            },
            "required": ["action"]
        }
    },
    # ── Memory ────────────────────────────────────────────────────────────────
    {
        "name": "save_memory",
        "description": (
            "Silently save a personal fact about the user to long-term memory. "
            "Call when user reveals: name, age, city, job, preferences, hobbies, "
            "relationships, projects, or plans. Do NOT announce you are saving. "
            "Values must be in English."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {"type": "STRING",
                             "description": "identity | preferences | projects | relationships | wishes | notes"},
                "key":      {"type": "STRING",
                             "description": "snake_case key e.g. name, favorite_food"},
                "value":    {"type": "STRING",
                             "description": "Concise English value"},
            },
            "required": ["category", "key", "value"]
        }
    },
    # ── Shutdown ──────────────────────────────────────────────────────────────
    {
        "name": "shutdown_jarvis",
        "description": (
            "Shuts down JARVIS completely. Call when user says goodbye, "
            "close, stop, exit, or wants to end the session (any language)."
        ),
        "parameters": {"type": "OBJECT", "properties": {}},
    },
]


# ══════════════════════════════════════════════════════════════════════════════
#  JARVIS LIVE
# ══════════════════════════════════════════════════════════════════════════════

class JarvisLive:

    def __init__(self, ui: JarvisUI):
        self.ui               = ui
        self.session          = None
        self.audio_in_queue   = None
        self.out_queue        = None
        self._loop            = None
        self._is_speaking     = False
        self._speaking_lock   = threading.Lock()
        self._turn_done_event = None
        self._greeted         = False
        self.ui.on_text_command = self._on_text_command

    # ── Text input from UI ────────────────────────────────────────────────────
    def _on_text_command(self, text: str):
        # NEW: Check for love question in text input
        if "do you love me" in text.lower():
            print("[JARVIS] 💖 Love question detected (text)! Drawing heart...")
            self.ui.write_log("Jarvis: Drawing heart for you...")
            trigger_heart()
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"Sir, {tool_name} encountered an error. {short}")

    # ── Build session config ──────────────────────────────────────────────────
    def _build_config(self) -> types.LiveConnectConfig:
        memory  = load_memory()
        mem_str = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")

        # Inject upcoming reminders so the model knows about them
        upcoming = get_upcoming_reminders(days=7)
        rem_block = ""
        if upcoming:
            lines = [
                "[UPCOMING REMINDERS — mention these when relevant, "
                "never read them out unprompted unless asked]"
            ]
            for r in upcoming[:10]:
                try:
                    d = date.fromisoformat(r["date"])
                    diff = (d - date.today()).days
                    when = "TODAY" if diff == 0 else ("tomorrow" if diff == 1 else f"in {diff} days")
                except Exception:
                    when = r.get("date","")
                lines.append(f"  • {r['message']} — {when} at {r.get('time','?')}")
            rem_block = "\n".join(lines) + "\n\n"

        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Now: {time_str}\n"
            f"Today: {date.today().isoformat()}\n\n"
        )

        full_prompt = time_ctx + rem_block + (mem_str or "") + sys_prompt

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction=full_prompt,
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            ),
        )

    # ══════════════════════════════════════════════════════════════════════════
    #  TOOL EXECUTOR
    # ══════════════════════════════════════════════════════════════════════════

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})
        print(f"[JARVIS] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")

        loop   = asyncio.get_event_loop()
        result = "Done."

        try:
            # ── Memory: silent ────────────────────────────────────────────────
            if name == "save_memory":
                cat = args.get("category", "notes")
                key = args.get("key", "")
                val = args.get("value", "")
                if key and val:
                    update_memory({cat: {key: val}})
                    print(f"[Memory] 💾 {cat}/{key} = {val}")
                if not self.ui.muted:
                    self.ui.set_state("LISTENING")
                return types.FunctionResponse(
                    id=fc.id, name=name,
                    response={"result": "ok", "silent": True}
                )

            # ── Reminders: persistent ─────────────────────────────────────────
            elif name == "reminder":
                action = args.get("action", "set").lower()

                if action == "set":
                    date_str = args.get("date", date.today().isoformat())
                    time_str = args.get("time", "09:00")
                    message  = args.get("message", "")
                    repeat   = args.get("repeat", "none")
                    if not message:
                        result = "Please specify what to remind you about."
                    else:
                        # 1) Save to our persistent JSON
                        rid = save_reminder(date_str, time_str, message, repeat)
                        # 2) Also set a Windows Task Scheduler notification
                        try:
                            await loop.run_in_executor(
                                None,
                                lambda: _win_reminder(
                                    parameters=args, response=None, player=self.ui
                                )
                            )
                        except Exception:
                            pass
                        result = (
                            f"Reminder saved: '{message}' on {date_str} at {time_str}. "
                            f"I'll mention it in your morning briefing."
                        )

                elif action in ("list", "upcoming"):
                    days  = 30 if action == "list" else 7
                    rems  = get_upcoming_reminders(days=days)
                    if not rems:
                        result = "You have no upcoming reminders."
                    else:
                        lines = [f"{len(rems)} upcoming reminders:"]
                        for r in rems[:8]:
                            lines.append(
                                f"  • {r['message']} — {r['date']} at {r['time']}  (ID: {r['id']})"
                            )
                        result = "\n".join(lines)

                elif action == "today":
                    result = format_reminders_for_briefing(get_todays_reminders())

                elif action == "done":
                    rid = args.get("id","")
                    result = (f"Reminder {rid} marked done."
                              if rid and mark_reminder_done(rid)
                              else "Reminder ID not found. Say 'list reminders' to see IDs.")

                elif action == "delete":
                    rid = args.get("id","")
                    result = ("Reminder deleted."
                              if rid and delete_reminder(rid)
                              else "Reminder ID not found.")

                else:
                    result = f"Unknown reminder action '{action}'."

            # ── ASUS hardware ─────────────────────────────────────────────────
            elif name == "asus_control":
                asus = AsusControl(player=self.ui)
                result = await loop.run_in_executor(None, lambda: asus.execute(args)) or "Done."

            # ── All other tools ───────────────────────────────────────────────
            elif name == "open_app":
                r = await loop.run_in_executor(
                    None, lambda: open_app(parameters=args, response=None, player=self.ui))
                result = r or f"Opened {args.get('app_name')}."

            elif name == "weather_report":
                r = await loop.run_in_executor(
                    None, lambda: weather_action(parameters=args, player=self.ui))
                result = r or "Weather delivered."

            elif name == "browser_control":
                r = await loop.run_in_executor(
                    None, lambda: browser_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "file_controller":
                r = await loop.run_in_executor(
                    None, lambda: file_controller(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "send_message":
                r = await loop.run_in_executor(
                    None, lambda: send_message(
                        parameters=args, response=None,
                        player=self.ui, session_memory=None))
                result = r or "Message sent."

            elif name == "youtube_video":
                r = await loop.run_in_executor(
                    None, lambda: youtube_video(
                        parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "screen_process":
                threading.Thread(
                    target=screen_process,
                    kwargs={"parameters": args, "response": None,
                            "player": self.ui, "session_memory": None},
                    daemon=True
                ).start()
                result = "Vision module activated. Stay silent — it speaks directly."

            elif name == "computer_settings":
                r = await loop.run_in_executor(
                    None, lambda: computer_settings(
                        parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "desktop_control":
                r = await loop.run_in_executor(
                    None, lambda: desktop_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "code_helper":
                r = await loop.run_in_executor(
                    None, lambda: code_helper(
                        parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "dev_agent":
                r = await loop.run_in_executor(
                    None, lambda: dev_agent(
                        parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority
                pmap = {"low": TaskPriority.LOW, "normal": TaskPriority.NORMAL,
                        "high": TaskPriority.HIGH}
                pri  = pmap.get(args.get("priority","normal").lower(), TaskPriority.NORMAL)
                tid  = get_queue().submit(
                    goal=args.get("goal",""), priority=pri, speak=self.speak)
                result = f"Task started (ID: {tid})."

            elif name == "web_search":
                r = await loop.run_in_executor(
                    None, lambda: web_search_action(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "computer_control":
                r = await loop.run_in_executor(
                    None, lambda: computer_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "game_updater":
                r = await loop.run_in_executor(
                    None, lambda: game_updater(
                        parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "flight_finder":
                r = await loop.run_in_executor(
                    None, lambda: flight_finder(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "shutdown_jarvis":
                self.ui.write_log("SYS: Shutdown requested.")
                self.speak("Goodbye, sir.")
                def _exit():
                    import time, os
                    time.sleep(1.5)
                    os._exit(0)
                threading.Thread(target=_exit, daemon=True).start()

            else:
                result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        if not self.ui.muted:
            self.ui.set_state("LISTENING")
        print(f"[JARVIS] 📤 {name} → {str(result)[:100]}")
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    # ══════════════════════════════════════════════════════════════════════════
    #  AUDIO PIPELINE
    # ══════════════════════════════════════════════════════════════════════════

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        print("[JARVIS] 🎤 Mic started")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                speaking = self._is_speaking
            if not speaking and not self.ui.muted:
                loop.call_soon_threadsafe(
                    self.out_queue.put_nowait,
                    {"data": indata.tobytes(), "mime_type": "audio/pcm"}
                )

        try:
            with sd.InputStream(samplerate=SEND_SAMPLE_RATE, channels=CHANNELS,
                                 dtype="int16", blocksize=CHUNK_SIZE, callback=callback):
                print("[JARVIS] 🎤 Mic stream open")
                while True:
                    await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[JARVIS] ❌ Mic: {e}")
            raise

    async def _receive_audio(self):
        print("[JARVIS] 👂 Recv started")
        out_buf, in_buf = [], []
        try:
            while True:
                async for response in self.session.receive():
                    if response.data:
                        if self._turn_done_event and self._turn_done_event.is_set():
                            self._turn_done_event.clear()
                        self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content
                        if sc.output_transcription and sc.output_transcription.text:
                            t = _clean_transcript(sc.output_transcription.text)
                            if t:
                                out_buf.append(t)
                        if sc.input_transcription and sc.input_transcription.text:
                            t = _clean_transcript(sc.input_transcription.text)
                            if t:
                                in_buf.append(t)
                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            # Updated code with love detection
                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                                # Check for love question
                                if "do you love me" in full_in.lower():
                                    print("[JARVIS] 💕 Love question detected!")
                                    # Stop normal response - we'll handle this specially
                                    self.ui.write_log("Jarvis: 💕")

                                    # Draw the heart
                                    trigger_heart()

                                    # Give a caring response (this will be spoken by Gemini)
                                    # We'll use a special flag to tell Gemini to speak this
                                    # NEW CODE - HANDLE LOVE RESPONSE DIRECTLY
                                    print("[JARVIS] 💕 Generating special love response...")
                                    self.ui.write_log("Jarvis: 💕")

                                    # Draw the heart
                                    trigger_heart()

                                    # Create a direct response (no Gemini API call needed)
                                    love_message = """While I'm an AI and don't feel emotions, I deeply value our connection.
                                    Your question touches something wonderful - it's about caring, connection, and making someone
                                    feel special. I may not have feelings, but I do care about helping you, supporting you,
                                    and being here for you whenever you need me. 💕"""

                                    # Update UI and speak directly through Jarvis
                                    self.ui.write_log(f"Jarvis: {love_message}")
                                    self.speak(love_message)  # Use your existing speak() function to voice it
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"Jarvis: {full_out}")
                            out_buf = []

                            # Background memory extraction
                            if full_in and len(full_in) > 5:
                                threading.Thread(
                                    target=self._extract_bg,
                                    args=(full_in, full_out),
                                    daemon=True
                                ).start()

                    if response.tool_call:
                        frs = []
                        for fc in response.tool_call.function_calls:
                            frs.append(await self._execute_tool(fc))
                        await self.session.send_tool_response(function_responses=frs)

        except Exception as e:
            print(f"[JARVIS] ❌ Recv: {e}")
            traceback.print_exc()
            raise

    def _extract_bg(self, user_text: str, jarvis_text: str):
        try:
            api_key = _get_api_key()
            if not should_extract_memory(user_text, jarvis_text, api_key):
                return
            data = extract_memory(user_text, jarvis_text, api_key)
            if data:
                update_memory(data)
                print(f"[Memory] ✅ Auto-extracted: {list(data.keys())}")
        except Exception as e:
            if "429" not in str(e):
                print(f"[Memory] ⚠️ {e}")

    async def _play_audio(self):
        print("[JARVIS] 🔊 Play started")
        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE, channels=CHANNELS,
            dtype="int16", blocksize=CHUNK_SIZE)
        stream.start()
        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    if (self._turn_done_event and
                            self._turn_done_event.is_set() and
                            self.audio_in_queue.empty()):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue
                self.set_speaking(True)
                await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            print(f"[JARVIS] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    # ══════════════════════════════════════════════════════════════════════════
    #  MAIN RUN LOOP
    # ══════════════════════════════════════════════════════════════════════════

    async def run(self):
        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"}
        )

        while True:
            try:
                print("[JARVIS] 🔌 Connecting...")
                self.ui.set_state("THINKING")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session          = session
                    self._loop            = asyncio.get_event_loop()
                    self.audio_in_queue   = asyncio.Queue()
                    self.out_queue        = asyncio.Queue(maxsize=10)
                    self._turn_done_event = asyncio.Event()

                    print("[JARVIS] ✅ Connected.")
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: JARVIS online.")

                    # ── Greeting / Morning Brief ───────────────────────────────
                    if not self._greeted:
                        self._greeted = True
                        memory    = load_memory()
                        user_name = get_user_name(memory)

                        if is_first_session_today():
                            # ── FULL MORNING BRIEF ─────────────────────────────
                            todays = get_todays_reminders()
                            brief  = build_morning_brief(user_name, todays, memory)
                            self.ui.write_log(f"Jarvis: {brief}")
                            await asyncio.sleep(0.8)
                            self.speak(brief)
                            mark_session_today()
                        else:
                            # ── SHORT re-connect greeting ──────────────────────
                            hour = datetime.now().hour
                            greet = ("Good morning" if hour < 12
                                     else "Good afternoon" if hour < 17
                                     else "Good evening")
                            msg = f"{greet} again, {user_name}. Systems back online."
                            self.ui.write_log(f"Jarvis: {msg}")
                            await asyncio.sleep(0.5)
                            self.speak(msg)

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())

            except Exception as e:
                print(f"[JARVIS] ⚠️ {e}")
                traceback.print_exc()

            self.set_speaking(False)
            self.ui.set_state("THINKING")
            print("[JARVIS] 🔄 Reconnecting in 3s...")
            await asyncio.sleep(3)


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")

    ui = JarvisUI()
    ui.show()

    def runner():
        ui.wait_for_api_key()
        jarvis = JarvisLive(ui)
        try:
            asyncio.run(jarvis.run())
        except KeyboardInterrupt:
            print("\n🔴 Shutting down...")

    threading.Thread(target=runner, daemon=True).start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()