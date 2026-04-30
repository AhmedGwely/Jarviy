"""
MARK XXXV — PyQt6 JARVIS UI
Matches reference: glassmorphism floating card, smooth sine waveform,
holographic arc, large mic button — Apple Siri / Vision Pro aesthetic.

Fully compatible drop-in replacement for the Tkinter ui.py used by
Jarvis-MK37/main.py.  All public attributes and methods are preserved:

  JarvisUI(face_path, size=None)
  ui.root            — QApplication event-loop shim (exposes .mainloop())
  ui.muted           — bool
  ui.speaking        — bool
  ui.on_text_command — callable or None
  ui.set_state(state)
  ui.write_log(text)
  ui.start_speaking()
  ui.stop_speaking()
  ui.wait_for_api_key()

The OS-selector setup dialog is preserved so api_keys.json is still written
with both "gemini_api_key" AND "os_system", keeping main.py happy.
"""

import os, json, time, math, random, threading, platform
import sys
from pathlib import Path
from collections import deque

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTextEdit, QFrame, QLabel, QSizePolicy,
    QButtonGroup, QRadioButton,
)
from PyQt6.QtCore import (
    Qt, QTimer, QPointF, QRectF, QSize, QRect,
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont,
    QRadialGradient, QLinearGradient, QPaintEvent, QResizeEvent,
    QPainterPath, QFontMetrics,
)


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR   = get_base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"

SYSTEM_NAME = "J.A.R.V.I.S"
MODEL_BADGE = "MARK XXXV"

# ── Palette ───────────────────────────────────────────────────────────────────
BG_DARK  = QColor(4,   8,  20)
BG_MID   = QColor(6,  14,  34)
ACCENT   = QColor(80,  140, 255)
CYAN     = QColor(0,   200, 255)
TEXT_HI  = QColor(220, 235, 255)
TEXT_MID = QColor(140, 170, 210)
TEXT_DIM = QColor(70,  95,  140)
GREEN    = QColor(0,   220, 120)
ORANGE   = QColor(255, 150,  50)
RED      = QColor(255,  60,  80)
YELLOW   = QColor(255, 210,  50)
PURPLE   = QColor(160, 100, 255)

STATE_COLORS = {
    "IDLE":         (QColor(80,  130, 220), QColor(60,  100, 180)),
    "LISTENING":    (QColor(0,   200, 255), QColor(80,  160, 255)),
    "SPEAKING":     (QColor(255, 150,  50), QColor(255, 200,  80)),
    "THINKING":     (QColor(160, 100, 255), QColor(100, 140, 255)),
    "PROCESSING":   (QColor(100, 160, 255), QColor(140, 100, 255)),
    "MUTED":        (QColor(255,  60,  80), QColor(180,  40,  60)),
    "INITIALISING": (QColor(60,  100, 200), QColor(40,   80, 160)),
}


# ═══════════════════════════════════════════════════════════════════════════════
#  BACKGROUND
# ═══════════════════════════════════════════════════════════════════════════════
class BackgroundWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tick      = 0
        self.arc_alpha = 0.0
        self._timer    = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.start(20)

    def _step(self):
        self.tick += 1
        self.arc_alpha = min(1.0, self.arc_alpha + 0.015)
        self.update()

    def paintEvent(self, e: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        grad = QLinearGradient(0, 0, 0, H)
        grad.setColorAt(0.0, QColor(3,   7, 18))
        grad.setColorAt(0.55,QColor(5,  11, 28))
        grad.setColorAt(1.0, QColor(4,   9, 22))
        p.fillRect(self.rect(), QBrush(grad))

        rng = random.Random(42)
        for _ in range(130):
            sx = rng.randint(0, W); sy = rng.randint(0, H)
            sa = rng.uniform(0.05, 0.28)
            p.setPen(QColor(180, 210, 255, int(sa * 200)))
            p.drawPoint(sx, sy)

        cx = W // 2
        cy_arc = H + int(H * 0.06)
        for rx, ry, a_base, c1, c2 in [
            (int(W * 0.55), int(H * 0.65), 0.50,
             QColor(50,  90, 255), QColor(130, 170, 255)),
            (int(W * 0.40), int(H * 0.48), 0.38,
             QColor(80, 120, 255), QColor(180, 210, 255)),
        ]:
            for i in range(20, 0, -1):
                frac  = i / 20
                alpha = int(255 * a_base * frac * self.arc_alpha * 0.55)
                sp    = (20 - i) * 2.2
                c     = QColor(c1 if frac > 0.5 else c2)
                c.setAlpha(alpha)
                p.setPen(QPen(c, 1.0 + (1 - frac) * 2.2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QRect(
                    cx - rx - int(sp), cy_arc - ry - int(sp),
                    (rx + int(sp)) * 2, (ry + int(sp)) * 2
                ))

        for gx, ga, gc in [
            (int(W * 0.32), 0.22, QColor(50,  90, 255)),
            (int(W * 0.68), 0.22, QColor(50,  90, 255)),
            (W // 2,        0.10, QColor(100, 140, 255)),
        ]:
            gr = QRadialGradient(gx, H, int(H * 0.5))
            c0 = QColor(gc); c0.setAlpha(int(255 * ga * self.arc_alpha))
            gr.setColorAt(0, c0); gr.setColorAt(1, QColor(0,0,0,0))
            p.setBrush(QBrush(gr)); p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(self.rect())
        p.end()


# ═══════════════════════════════════════════════════════════════════════════════
#  WAVEFORM
# ═══════════════════════════════════════════════════════════════════════════════
class WaveformWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(100)
        self.setMaximumHeight(130)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.tick     = 0
        self.energy   = 0.12
        self.target_e = 0.12
        self.state    = "IDLE"
        self.wave_colors = STATE_COLORS["IDLE"]

        self.waves = [
            {"speed": 1.00, "freq": 1.00, "phase": 0.00, "amp_frac": 1.00},
            {"speed": 0.62, "freq": 1.60, "phase": 1.20, "amp_frac": 0.62},
            {"speed": 0.80, "freq": 0.72, "phase": 2.50, "amp_frac": 0.42},
        ]

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.start(14)

    def set_energy(self, v: float):
        self.target_e = max(0.0, min(1.0, v))

    def set_state(self, state: str):
        self.state = state
        self.wave_colors = STATE_COLORS.get(state, STATE_COLORS["IDLE"])

    def _step(self):
        self.tick += 1
        spd = 0.022 + self.energy * 0.055
        self.energy += (self.target_e - self.energy) * 0.055
        for w in self.waves:
            w["phase"] += w["speed"] * spd
        self.update()

    def paintEvent(self, e: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        cy     = H // 2
        energy = self.energy

        p.fillRect(self.rect(), QColor(0, 0, 0, 0))

        if energy > 0.05:
            gc = QRadialGradient(W // 2, cy, W * 0.52)
            c0 = QColor(self.wave_colors[0]); c0.setAlpha(int(50 * energy))
            gc.setColorAt(0, c0); gc.setColorAt(1, QColor(0,0,0,0))
            p.setBrush(QBrush(gc)); p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(self.rect())

        SAMPLES = 320
        for li, w in enumerate(self.waves):
            amp = max(1.5, H * 0.30 * energy * w["amp_frac"])
            c1, c2 = self.wave_colors

            if li == 0:
                col, lw, al = c1, 2.2 + energy * 1.0, int(210 * (0.55 + energy * 0.45))
            elif li == 1:
                col, lw, al = c2, 1.3 + energy * 0.7, int(150 * (0.38 + energy * 0.45))
            else:
                r = (c1.red()   + c2.red())   // 2
                g = (c1.green() + c2.green()) // 2
                b = (c1.blue()  + c2.blue())  // 2
                col, lw, al = QColor(r,g,b), 0.9, int(90 * (0.28 + energy * 0.40))

            path = QPainterPath()
            for i in range(SAMPLES + 1):
                t = i / SAMPLES
                x = t * W
                y = (cy
                     + amp * math.sin(w["freq"] * t * math.pi * 4 + w["phase"])
                     + amp * 0.28 * math.sin(w["freq"] * t * math.pi * 6.8 + w["phase"] * 1.35))
                if i == 0: path.moveTo(x, y)
                else:       path.lineTo(x, y)

            qc = QColor(col); qc.setAlpha(al)
            p.setPen(QPen(qc, lw, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

            if li == 0 and energy > 0.08:
                wc = QColor(255, 255, 255, int(70 * energy))
                p.setPen(QPen(wc, 0.9))
                p.drawPath(path)
        p.end()


# ═══════════════════════════════════════════════════════════════════════════════
#  MIC BUTTON
# ═══════════════════════════════════════════════════════════════════════════════
class MicButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(72, 72)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        self.pulse_r  = 0.0
        self.pulse_a  = 0.0
        self.active   = False
        self.muted    = False
        self._hovered = False
        self.state_col= QColor(255, 255, 255)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)
        self._timer.start(16)

    def set_active(self, active: bool, muted: bool = False):
        self.active    = active
        self.muted     = muted
        self.state_col = RED if muted else (QColor(120, 180, 255) if active else QColor(255, 255, 255))

    def _step(self):
        if self.active and not self.muted:
            self.pulse_r = (self.pulse_r + 0.028) % 1.0
            self.pulse_a = 1.0 - self.pulse_r
        else:
            self.pulse_a = max(0.0, self.pulse_a - 0.04)
        self.update()

    def enterEvent(self, e): self._hovered = True;  self.update()
    def leaveEvent(self, e): self._hovered = False; self.update()

    def paintEvent(self, e: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        cx, cy, R = W // 2, H // 2, 30

        p.fillRect(self.rect(), QColor(0,0,0,0))

        if self.pulse_a > 0.01:
            for ring in range(2):
                f  = (self.pulse_r + ring * 0.45) % 1.0
                rr = R + f * 28
                ra = int((1.0 - f) * self.pulse_a * 110)
                if ra > 4:
                    rc = QColor(self.state_col); rc.setAlpha(ra)
                    p.setPen(QPen(rc, 1.5)); p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawEllipse(QPointF(cx, cy), rr, rr)

        sg = QRadialGradient(cx, cy + 5, R + 16)
        sg.setColorAt(0, QColor(0,0,0,70)); sg.setColorAt(1, QColor(0,0,0,0))
        p.setBrush(QBrush(sg)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy + 5), R + 16, R + 16)

        fill = QRadialGradient(cx - 5, cy - 7, R * 2)
        if self._hovered:
            fill.setColorAt(0, QColor(225, 238, 255))
            fill.setColorAt(1, QColor(200, 220, 255))
        else:
            fill.setColorAt(0, QColor(245, 250, 255))
            fill.setColorAt(1, QColor(220, 232, 252))
        p.setBrush(QBrush(fill)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), R, R)

        ic = RED if self.muted else QColor(25, 38, 68)
        p.setPen(Qt.PenStyle.NoPen)
        cap = QPainterPath()
        cap.addRoundedRect(QRectF(cx - 5, cy - 11, 10, 14), 5, 5)
        p.fillPath(cap, QBrush(ic))
        p.setPen(QPen(ic, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        stand = QPainterPath()
        stand.moveTo(cx - 8, cy + 4)
        stand.arcTo(QRectF(cx - 8, cy - 2, 16, 14), 180, -180)
        p.drawPath(stand)
        p.drawLine(int(cx), int(cy + 11), int(cx), int(cy + 16))
        p.drawLine(int(cx - 5), int(cy + 16), int(cx + 5), int(cy + 16))
        p.end()


# ═══════════════════════════════════════════════════════════════════════════════
#  GLASS CARD
# ═══════════════════════════════════════════════════════════════════════════════
class GlassCard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.lower()

    def paintEvent(self, e: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H, R = self.width(), self.height(), 22

        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, W, H), R, R)

        grad = QLinearGradient(0, 0, 0, H)
        grad.setColorAt(0.0, QColor(18,  34,  80, 218))
        grad.setColorAt(0.4, QColor(12,  24,  60, 212))
        grad.setColorAt(1.0, QColor(7,   15,  44, 222))
        p.fillPath(path, QBrush(grad))

        bloom = QRadialGradient(W // 2, H, W * 0.75)
        bloom.setColorAt(0, QColor(40, 80, 200, 55))
        bloom.setColorAt(1, QColor(0, 0, 0, 0))
        p.fillPath(path, QBrush(bloom))

        hi = QLinearGradient(W * 0.15, 0, W * 0.85, 0)
        hi.setColorAt(0, QColor(255,255,255,0))
        hi.setColorAt(0.4, QColor(255,255,255,22))
        hi.setColorAt(0.6, QColor(255,255,255,22))
        hi.setColorAt(1, QColor(255,255,255,0))
        hi_path = QPainterPath()
        hi_path.addRoundedRect(QRectF(0, 0, W, 2.5), 2, 2)
        p.fillPath(hi_path, QBrush(hi))

        bd = QLinearGradient(0, 0, 0, H)
        bd.setColorAt(0, QColor(120, 160, 255, 75))
        bd.setColorAt(0.5, QColor(60, 100, 200, 35))
        bd.setColorAt(1, QColor(40,  80, 180, 60))
        p.setPen(QPen(QBrush(bd), 1.1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(0.6, 0.6, W - 1.2, H - 1.2), R, R)
        p.end()


# ═══════════════════════════════════════════════════════════════════════════════
#  STATUS PILL
# ═══════════════════════════════════════════════════════════════════════════════
class StatusPill(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(22)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._text  = "INITIALISING"
        self._color = ACCENT
        self._blink = True
        t = QTimer(self); t.timeout.connect(self._toggle); t.start(560)

    def _toggle(self):
        self._blink = not self._blink; self.update()

    def set_status(self, text: str, color: QColor):
        self._text = text; self._color = color; self.update()

    def paintEvent(self, e: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        font = QFont("Helvetica Neue", 8, QFont.Weight.Medium)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        p.setFont(font)
        fm  = QFontMetrics(font)
        tw  = fm.horizontalAdvance(f"●  {self._text}")
        pw  = tw + 22; px = (W - pw) // 2

        pill = QPainterPath()
        pill.addRoundedRect(QRectF(px, 1, pw, H - 2), (H-2)//2, (H-2)//2)
        bg = QColor(self._color); bg.setAlpha(20)
        bd = QColor(self._color); bd.setAlpha(65)
        p.fillPath(pill, QBrush(bg))
        p.setPen(QPen(bd, 0.8)); p.drawPath(pill)

        dot = "●" if self._blink else "○"
        p.setPen(self._color)
        p.drawText(QRectF(0, 0, W, H), Qt.AlignmentFlag.AlignCenter,
                   f"{dot}  {self._text}")
        p.end()


# ═══════════════════════════════════════════════════════════════════════════════
#  LOG TEXT
# ═══════════════════════════════════════════════════════════════════════════════
class LogWidget(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        f = QFont("Helvetica Neue", 11)
        if not f.exactMatch():
            f = QFont("Segoe UI", 11)
        self.setFont(f)
        self.setStyleSheet("""
            QTextEdit {
                background: transparent;
                color: rgba(200,225,255,225);
                border: none;
                padding: 4px 2px;
            }
            QScrollBar:vertical {
                background: transparent; width: 3px; border-radius: 2px;
            }
            QScrollBar::handle:vertical {
                background: rgba(80,120,200,100); border-radius: 2px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)


# ═══════════════════════════════════════════════════════════════════════════════
#  COMPAT SHIM  — lets main.py call  ui.root.mainloop()
# ═══════════════════════════════════════════════════════════════════════════════
class _RootShim:
    """Mimics the Tkinter root object that main.py expects."""
    def __init__(self, app: QApplication, win: QMainWindow):
        self._app = app
        self._win = win

    def mainloop(self):
        self._win.show()
        sys.exit(self._app.exec())


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN WINDOW  —  public API identical to the original Tkinter JarvisUI
# ═══════════════════════════════════════════════════════════════════════════════
class JarvisUI(QMainWindow):
    """
    Drop-in PyQt6 replacement.

    main.py creates:   ui = JarvisUI("face.png")
    then calls:        ui.root.mainloop()

    All other public methods / attributes are preserved unchanged.
    """

    def __init__(self, face_path=None, size=None):
        # One QApplication per process
        if QApplication.instance() is None:
            self._app = QApplication(sys.argv)
            self._app.setStyle("Fusion")
            from PyQt6.QtGui import QPalette
            pal = self._app.palette()
            pal.setColor(QPalette.ColorRole.Window,        BG_DARK)
            pal.setColor(QPalette.ColorRole.WindowText,    TEXT_HI)
            pal.setColor(QPalette.ColorRole.Base,          BG_MID)
            pal.setColor(QPalette.ColorRole.AlternateBase, BG_DARK)
            pal.setColor(QPalette.ColorRole.Text,          TEXT_HI)
            pal.setColor(QPalette.ColorRole.Button,        BG_MID)
            pal.setColor(QPalette.ColorRole.ButtonText,    TEXT_HI)
            self._app.setPalette(pal)
        else:
            self._app = QApplication.instance()

        super().__init__()
        self.setWindowTitle("J.A.R.V.I.S — MARK XXXV")
        self.setMinimumSize(680, 720)
        self.resize(800, 860)

        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width()  - self.width())  // 2,
            (screen.height() - self.height()) // 2,
        )

        # ── Background ────────────────────────────────────────────────
        self.bg = BackgroundWidget()
        self.setCentralWidget(self.bg)

        root_layout = QVBoxLayout(self.bg)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Top bar ───────────────────────────────────────────────────
        top_bar = QWidget()
        top_bar.setFixedHeight(52)
        top_bar.setStyleSheet("background: transparent;")
        tl = QHBoxLayout(top_bar)
        tl.setContentsMargins(22, 0, 22, 0)

        badge = QLabel(MODEL_BADGE)
        badge.setFont(self._mono(7, bold=True))
        badge.setStyleSheet("color: rgba(70,100,160,160); letter-spacing: 3px;")
        tl.addWidget(badge)
        tl.addStretch()

        sub = QLabel("JUST A RATHER VERY INTELLIGENT SYSTEM")
        sf = QFont("Helvetica Neue", 7)
        if not sf.exactMatch(): sf = QFont("Segoe UI", 7)
        sub.setFont(sf)
        sub.setStyleSheet("color: rgba(70,100,160,140); letter-spacing: 2px;")
        tl.addWidget(sub)
        tl.addStretch()

        self.time_label = QLabel(time.strftime("%H:%M:%S"))
        self.time_label.setFont(self._mono(11, bold=True))
        self.time_label.setStyleSheet("color: rgba(100,150,220,190);")
        tl.addWidget(self.time_label)

        root_layout.addWidget(top_bar)
        root_layout.addStretch(1)

        # ── Glass card ────────────────────────────────────────────────
        ch = QHBoxLayout()
        ch.setContentsMargins(0, 0, 0, 0)
        ch.addStretch(1)

        self._card_outer = QWidget()
        self._card_outer.setFixedWidth(430)
        self._card_outer.setSizePolicy(QSizePolicy.Policy.Fixed,
                                       QSizePolicy.Policy.Preferred)

        self._glass = GlassCard(self._card_outer)

        inner = QVBoxLayout(self._card_outer)
        inner.setContentsMargins(26, 22, 26, 22)
        inner.setSpacing(10)

        title_row = QHBoxLayout()
        title_lbl = QLabel(SYSTEM_NAME)
        tf = QFont("Helvetica Neue", 13, QFont.Weight.DemiBold)
        if not tf.exactMatch(): tf = QFont("Segoe UI", 13, QFont.Weight.DemiBold)
        title_lbl.setFont(tf)
        title_lbl.setStyleSheet(
            "color: rgba(150,190,255,210); letter-spacing: 3px; background: transparent;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        inner.addLayout(title_row)

        self.log_text = LogWidget()
        self.log_text.setMinimumHeight(110)
        self.log_text.setMaximumHeight(160)
        inner.addWidget(self.log_text)

        self.status_pill = StatusPill()
        inner.addWidget(self.status_pill)

        self.waveform = WaveformWidget()
        inner.addWidget(self.waveform)

        mic_row = QHBoxLayout()
        mic_row.addStretch()
        self.mic_btn = MicButton()
        self.mic_btn.clicked.connect(self._toggle_mute)
        mic_row.addWidget(self.mic_btn)
        mic_row.addStretch()
        inner.addLayout(mic_row)

        ir = QHBoxLayout(); ir.setSpacing(8)
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type a command…")
        self.input_field.setFont(self._sans(9))
        self.input_field.setFixedHeight(34)
        self.input_field.setStyleSheet("""
            QLineEdit {
                background: rgba(255,255,255,10);
                color: rgba(200,225,255,215);
                border: 1px solid rgba(80,120,200,55);
                border-radius: 17px;
                padding: 0 14px;
                selection-background-color: rgba(80,140,255,120);
            }
            QLineEdit:focus {
                border: 1px solid rgba(100,160,255,130);
                background: rgba(255,255,255,16);
            }
        """)
        self.input_field.returnPressed.connect(self._on_input_submit)
        ir.addWidget(self.input_field, stretch=1)

        send_btn = QPushButton("↑")
        send_btn.setFixedSize(34, 34)
        send_btn.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        send_btn.setStyleSheet("""
            QPushButton {
                background: rgba(80,130,255,55);
                color: rgba(160,200,255,215);
                border: 1px solid rgba(80,120,200,75);
                border-radius: 17px;
            }
            QPushButton:hover { background: rgba(80,140,255,130); color: white; }
            QPushButton:pressed { background: rgba(60,100,200,170); }
        """)
        send_btn.clicked.connect(self._on_input_submit)
        ir.addWidget(send_btn)
        inner.addLayout(ir)

        ch.addWidget(self._card_outer)
        ch.addStretch(1)
        root_layout.addLayout(ch)
        root_layout.addStretch(2)

        # ── Bottom bar ────────────────────────────────────────────────
        bot = QWidget(); bot.setFixedHeight(36)
        bot.setStyleSheet("background: transparent;")
        bl = QHBoxLayout(bot); bl.setContentsMargins(22, 0, 22, 0)

        self.mute_btn = QPushButton("● LIVE")
        self.mute_btn.setFixedSize(72, 22)
        self.mute_btn.setFont(self._mono(7, bold=True))
        self.mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mute_btn.setCheckable(True)
        self.mute_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: rgba(0,210,110,200);
                border: 1px solid rgba(0,150,80,90); border-radius: 11px; letter-spacing: 1px;
            }
            QPushButton:checked { color: rgba(255,60,80,200); border: 1px solid rgba(180,30,50,110); }
        """)
        self.mute_btn.clicked.connect(self._toggle_mute)
        bl.addWidget(self.mute_btn)
        bl.addStretch()

        footer = QLabel("FatihMakes Industries  ·  MARK XXXV  ·  CLASSIFIED")
        footer.setFont(self._mono(6))
        footer.setStyleSheet("color: rgba(45,70,115,140); letter-spacing: 1px;")
        bl.addWidget(footer)

        f4 = QLabel("[F4] MUTE")
        f4.setFont(self._mono(6))
        f4.setStyleSheet("color: rgba(35,55,95,110);")
        bl.addWidget(f4)

        root_layout.addWidget(bot)

        # ── State ─────────────────────────────────────────────────────
        self.speaking      = False
        self.muted         = False
        self._jarvis_state = "INITIALISING"
        self.status_text   = "INITIALISING"

        self.typing_queue  = deque()
        self.is_typing     = False
        self.on_text_command = None   # set by main.py → JarvisLive

        # Timers
        self._time_timer = QTimer(self)
        self._time_timer.timeout.connect(lambda: self.time_label.setText(
            time.strftime("%H:%M:%S")))
        self._time_timer.start(1000)

        self._card_outer.installEventFilter(self)

        # ── API key check ─────────────────────────────────────────────
        self._api_key_ready = self._api_keys_exist()
        if not self._api_key_ready:
            self._show_setup_ui()

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Compatibility shim so main.py can do  ui.root.mainloop()
        self.root = _RootShim(self._app, self)

    # ── Helpers ───────────────────────────────────────────────────────
    def _mono(self, size, bold=False):
        f = QFont("Consolas", size)
        if bold: f.setWeight(QFont.Weight.Bold)
        return f

    def _sans(self, size, bold=False):
        f = QFont("Helvetica Neue", size)
        if not f.exactMatch(): f = QFont("Segoe UI", size)
        if bold: f.setWeight(QFont.Weight.DemiBold)
        return f

    def eventFilter(self, obj, event):
        if obj is self._card_outer and event.type() == event.Type.Resize:
            self._glass.setGeometry(0, 0,
                                    self._card_outer.width(),
                                    self._card_outer.height())
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F4:
            self._toggle_mute()
        super().keyPressEvent(event)

    def _apply_state_visuals(self, state: str):
        m = {
            "MUTED":       ("MUTED",      RED,    0.04, False),
            "SPEAKING":    ("SPEAKING",   ORANGE, 0.86, True),
            "THINKING":    ("THINKING",   YELLOW, 0.50, False),
            "LISTENING":   ("LISTENING",  GREEN,  0.66, True),
            "PROCESSING":  ("PROCESSING", ACCENT, 0.44, True),
        }
        label, color, energy, active = m.get(state, ("ONLINE", CYAN, 0.16, False))
        if self.muted:
            label, color, energy, active = "MUTED", RED, 0.04, False

        self.status_pill.set_status(label, color)
        self.waveform.set_energy(energy)
        self.waveform.set_state(state if not self.muted else "MUTED")
        self.mic_btn.set_active(active and not self.muted, self.muted)

    # ── Public API ────────────────────────────────────────────────────
    def set_state(self, state: str):
        self._jarvis_state = state
        state_map = {
            "MUTED":      ("MUTED",      False),
            "SPEAKING":   ("SPEAKING",   True),
            "THINKING":   ("THINKING",   False),
            "LISTENING":  ("LISTENING",  False),
            "PROCESSING": ("PROCESSING", False),
        }
        self.status_text, self.speaking = state_map.get(state, ("ONLINE", False))
        self._apply_state_visuals(state)

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self.muted:
            self.set_state("LISTENING")

    def write_log(self, text: str):
        self.typing_queue.append(text)
        tl = text.lower()
        if tl.startswith("you:"):
            self.set_state("PROCESSING")
        elif tl.startswith("jarvis:") or tl.startswith("ai:"):
            self.set_state("SPEAKING")
        if not self.is_typing:
            self._start_typing()

    def wait_for_api_key(self):
        """Blocks the calling thread until API key setup is complete."""
        while not self._api_key_ready:
            time.sleep(0.1)

    # ── Private ───────────────────────────────────────────────────────
    def _toggle_mute(self):
        self.muted = not self.muted
        self.mute_btn.setChecked(self.muted)
        self.mute_btn.setText("● MUTED" if self.muted else "● LIVE")
        if self.muted:
            self.set_state("MUTED")
            self.write_log("SYS: Microphone muted.")
        else:
            self.set_state("LISTENING")
            self.write_log("SYS: Microphone active.")

    def _on_input_submit(self):
        text = self.input_field.text().strip()
        if not text:
            return
        self.input_field.clear()
        self.write_log(f"You: {text}")
        if self.on_text_command:
            threading.Thread(target=self.on_text_command,
                             args=(text,), daemon=True).start()

    def _api_keys_exist(self) -> bool:
        """
        Mirrors the original check: requires both gemini_api_key AND os_system
        so the rest of main.py (which reads os_system) keeps working.
        """
        if not API_FILE.exists():
            return False
        try:
            data = json.loads(API_FILE.read_text(encoding="utf-8"))
            return bool(data.get("gemini_api_key")) and bool(data.get("os_system"))
        except Exception:
            return False

    def _start_typing(self):
        if not self.typing_queue:
            self.is_typing = False
            if not self.speaking and not self.muted:
                self.set_state("LISTENING")
            return
        self.is_typing = True
        text = self.typing_queue.popleft()
        tl   = text.lower()

        if tl.startswith("you:"):
            sp   = text.index(":") + 1
            html = (f'<span style="color:rgba(110,165,255,205);font-weight:600;">{text[:sp]}</span>'
                    f'<span style="color:rgba(185,215,255,220);">{text[sp:]}</span>')
        elif tl.startswith("jarvis:") or tl.startswith("ai:"):
            sp   = text.index(":") + 1
            html = (f'<span style="color:rgba(0,200,255,220);font-weight:700;">{text[:sp]}</span>'
                    f'<span style="color:rgba(205,230,255,230);"> {text[sp:].strip()}</span>')
        elif "error" in tl or tl.startswith("err:"):
            html = f'<span style="color:rgba(255,75,95,215);">{text}</span>'
        elif tl.startswith("sys:"):
            html = f'<span style="color:rgba(65,95,155,175);font-style:italic;">{text}</span>'
        else:
            html = f'<span style="color:rgba(95,135,195,175);">{text}</span>'

        self.log_text.append(html)
        sb = self.log_text.verticalScrollBar()
        sb.setValue(sb.maximum())
        QTimer.singleShot(18, self._start_typing)

    # ── Setup overlay (OS + API key) ──────────────────────────────────
    @staticmethod
    def _detect_os() -> str:
        s = platform.system().lower()
        if s == "darwin":  return "mac"
        if s == "windows": return "windows"
        return "linux"

    def _show_setup_ui(self):
        detected = self._detect_os()
        self._selected_os = detected

        self.overlay = QFrame(self.bg)
        self.overlay.setGeometry(self.bg.rect())
        self.overlay.setStyleSheet("background: rgba(2,5,15,225);")

        card = QFrame(self.overlay)
        card.setFixedSize(480, 360)
        card.move(
            (self.overlay.width()  - 480) // 2,
            (self.overlay.height() - 360) // 2,
        )
        card.setStyleSheet("""
            QFrame {
                background: rgba(12,22,55,232);
                border: 1px solid rgba(80,120,210,95);
                border-radius: 20px;
            }
        """)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(32, 26, 32, 26)
        lay.setSpacing(12)

        t = QLabel("SYSTEM INITIALISATION")
        t.setFont(self._sans(12, bold=True))
        t.setStyleSheet(
            "color: rgba(100,160,255,225); letter-spacing: 3px; background: transparent;")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(t)

        s = QLabel("Enter your Gemini API key and select your OS.")
        s.setFont(self._sans(8))
        s.setStyleSheet("color: rgba(80,110,170,175); background: transparent;")
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(s)

        self.gemini_entry = QLineEdit()
        self.gemini_entry.setPlaceholderText("GEMINI API KEY")
        self.gemini_entry.setEchoMode(QLineEdit.EchoMode.Password)
        self.gemini_entry.setFont(self._mono(10))
        self.gemini_entry.setFixedHeight(40)
        self.gemini_entry.setStyleSheet("""
            QLineEdit {
                background: rgba(255,255,255,9);
                color: rgba(200,225,255,215);
                border: 1px solid rgba(70,110,200,75);
                border-radius: 20px;
                padding: 0 18px;
            }
            QLineEdit:focus { border: 1px solid rgba(100,160,255,175); }
        """)
        lay.addWidget(self.gemini_entry)

        # OS selector
        os_lbl = QLabel("SELECT OPERATING SYSTEM")
        os_lbl.setFont(self._mono(7, bold=True))
        os_lbl.setStyleSheet(
            "color: rgba(70,100,160,160); letter-spacing: 2px; background: transparent;")
        os_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(os_lbl)

        os_row = QHBoxLayout()
        os_row.setSpacing(8)
        self._os_btns: dict[str, QPushButton] = {}
        _os_options = [("windows", "⊞  WINDOWS"), ("mac", "  macOS"), ("linux", "🐧  LINUX")]
        _btn_base = """
            QPushButton {{
                background: {bg};
                color: {fg};
                border: 1px solid {bd};
                border-radius: 14px;
                font-size: 9px;
                letter-spacing: 1px;
                padding: 6px 10px;
            }}
        """
        for os_key, os_label in _os_options:
            btn = QPushButton(os_label)
            btn.setFont(self._mono(8, bold=True))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(32)
            btn.clicked.connect(lambda checked, k=os_key: self._select_os_btn(k))
            os_row.addWidget(btn)
            self._os_btns[os_key] = btn
        lay.addLayout(os_row)
        self._select_os_btn(detected)   # highlight detected OS

        btn = QPushButton("INITIALISE SYSTEMS")
        btn.setFixedHeight(40)
        btn.setFont(self._mono(9, bold=True))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: rgba(100,160,255,215);
                border: 1px solid rgba(80,130,255,135); border-radius: 20px; letter-spacing: 2px;
            }
            QPushButton:hover { background: rgba(80,130,255,55); color: white; }
            QPushButton:pressed { background: rgba(60,100,200,95); }
        """)
        btn.clicked.connect(self._save_api_keys)
        lay.addWidget(btn)

        self.overlay.show()
        self.overlay.raise_()

    def _select_os_btn(self, os_key: str):
        self._selected_os = os_key
        styles = {
            "windows": ("rgba(0,200,255,220)",  "rgba(0,50,80,240)",    "rgba(0,160,200,150)"),
            "mac":     ("rgba(255,210,50,220)",  "rgba(50,40,0,240)",    "rgba(200,160,30,150)"),
            "linux":   ("rgba(0,220,120,220)",   "rgba(0,40,20,240)",    "rgba(0,160,80,150)"),
        }
        dim = ("rgba(70,95,140,200)", "rgba(255,255,255,8)", "rgba(60,90,160,80)")
        for key, btn in self._os_btns.items():
            fg, bg, bd = styles[key] if key == os_key else dim
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {bg};
                    color: {fg};
                    border: 1px solid {bd};
                    border-radius: 14px;
                    font-size: 9px;
                    letter-spacing: 1px;
                    padding: 6px 10px;
                }}
            """)

    def _save_api_keys(self):
        gemini = self.gemini_entry.text().strip()
        if not gemini:
            self.gemini_entry.setStyleSheet(
                self.gemini_entry.styleSheet() +
                "border: 1px solid rgba(255,60,80,200);")
            return
        os_system = self._selected_os
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(API_FILE, "w", encoding="utf-8") as f:
            json.dump({"gemini_api_key": gemini, "os_system": os_system},
                      f, indent=4)
        self.overlay.deleteLater()
        self._api_key_ready = True
        self.set_state("LISTENING")
        self.write_log(
            f"SYS: Systems initialised. OS → {os_system.upper()}. JARVIS online.")

    def resizeEvent(self, e: QResizeEvent):
        super().resizeEvent(e)
        if hasattr(self, "overlay"):
            self.overlay.setGeometry(self.bg.rect())


# ═══════════════════════════════════════════════════════════════════════════════
#  STANDALONE ENTRY POINT  (python ui.py)
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    from PyQt6.QtGui import QPalette
    pal = app.palette()
    pal.setColor(QPalette.ColorRole.Window,        BG_DARK)
    pal.setColor(QPalette.ColorRole.WindowText,    TEXT_HI)
    pal.setColor(QPalette.ColorRole.Base,          BG_MID)
    pal.setColor(QPalette.ColorRole.AlternateBase, BG_DARK)
    pal.setColor(QPalette.ColorRole.Text,          TEXT_HI)
    pal.setColor(QPalette.ColorRole.Button,        BG_MID)
    pal.setColor(QPalette.ColorRole.ButtonText,    TEXT_HI)
    app.setPalette(pal)
    win = JarvisUI()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()