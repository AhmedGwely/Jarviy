# 🤖 Jarviy

### Advanced Cross-Platform AI Desktop Assistant

> 📺 Demo / Setup Video: https://youtu.be/3dqgUsonmn8?si=eh_McOF5V8bduTo1

Jarviy is a real-time AI desktop assistant capable of voice interaction, system control, visual understanding, and autonomous task execution.

It is designed as a local-first intelligent system that integrates deeply with the operating system to provide a unified AI control layer.

---

## 📌 Origin

Jarviy is built upon the original AI assistant concept developed by **FatihMakes**:

🔗 https://github.com/FatihMakes/Jarvis-MK37

This project extends and restructures the original system with improvements in architecture, usability, memory handling, and system-level automation.

---

## 🚀 Core Capabilities

### 🧠 AI Intelligence
- Gemini 2.5 Flash Native Audio integration (real-time conversation)
- Persistent long-term memory system
- Context-aware session resumption
- Multi-tool reasoning and execution system

---

### 🖥️ System Control
- Full OS control (apps, files, processes, settings)
- CPU/GPU monitoring (ASUS hardware integration)
- Power profiles (silent / balanced / turbo)
- Brightness, volume, WiFi, shutdown, restart
- Keyboard + mouse automation

---

### 📁 File & Application Management
- Open, create, delete, move, rename files
- Browser automation (Chrome, Edge, Firefox, Brave)
- Code generation and editing system
- Multi-file project generation

---

### 🌐 Communication & Web
- WhatsApp & Telegram messaging
- YouTube control (search, play, summarize)
- Google Flights search
- Web search and information retrieval
- Weather reports

---

### 🎯 Productivity System
- Task queue with priority execution
- Morning briefing system
- Reminder system (daily / weekly / persistent)
- Session-based workflow execution

---

### 🎨 UI / UX System
- Glassmorphism futuristic interface
- Animated holographic design (arcs, waveforms, gradients)
- Real-time status indicators:
  - IDLE / LISTENING / THINKING / SPEAKING / MUTED
- Mic button with animation + F4 toggle
- Live system log console

---

## 🆕 Improvements Added in Jarviy

Compared to the original system, Jarviy introduces:

### ⚙️ Architecture Improvements
- Refactored tool-based modular system (20+ tools structured cleanly)
- Multi-threaded execution (UI / AI / system parallelism)
- Async processing for non-blocking performance

### 🧠 Intelligence Enhancements
- Improved memory system (structured long-term storage)
- Better context handling across sessions
- More reliable task execution flow

### 🖥️ System Enhancements
- Expanded OS control functions (power, apps, hardware monitoring)
- Improved automation stability
- Enhanced browser + file handling system

### ⚡ Performance Improvements
- Faster response time from optimized pipeline
- Reduced lag in voice-to-action execution
- Better task queue execution system

### 🔧 Stability Fixes
- Improved error handling in core actions
- Reduced crash points in tool execution layer
- Safer system command execution flow

---

## ⚠️ Known Limitations

Jarviy still has some constraints:

### 🌐 System Limitations
- No mobile or web version
- No multi-user support
- No offline LLM fallback
- Requires internet for Gemini API

### 🖥️ Platform Limitations
- Windows-optimized paths in some modules
- Limited macOS/Linux testing

### 🔒 Missing Features
- No wake-word activation
- No calendar/email integration
- No smart home/IoT support
- No OCR or translation system
- No clipboard manager

### 🎨 UI Limitations
- Fixed window size (not fully responsive)
- No theme switching
- No tray support
- No draggable layout system

---

## ⚡ Quick Start

```bash
git clone https://github.com/YOUR_USERNAME/Jarviy.git
cd Jarviy
pip install -r requirements.txt
playwright install
python main.py