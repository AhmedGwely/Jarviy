"""
MARK XXXV — PyQt6 JARVIS UI
Apple Vision Pro / SF aesthetic — centered waveform, edge-fade pill, no cards.

Drop-in replacement. All public API preserved:
  JarvisUI(face_path, size=None)   ui.root.mainloop()
  ui.muted  ui.speaking  ui.on_text_command
  ui.set_state()  ui.write_log()  ui.start_speaking()
  ui.stop_speaking()  ui.wait_for_api_key()
"""

import os, json, time, math, random, threading, platform
import sys
from pathlib import Path
from collections import deque

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QLineEdit, QPushButton, QTextEdit, QFrame, QLabel, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, QRect
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont,
    QRadialGradient, QLinearGradient, QPaintEvent, QResizeEvent,
    QPainterPath, QFontMetrics, QFontDatabase,
)

# ── Paths ──────────────────────────────────────────────────────────────────────
def _base_dir():
    return Path(sys.executable).parent if getattr(sys, "frozen", False) \
           else Path(__file__).resolve().parent

BASE_DIR   = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"

SYSTEM_NAME = "J·A·R·V·I·S"
MODEL_BADGE = "MARK XXXV"

# ── Palette — Apple-inspired, desaturated depth ───────────────────────────────
_C = {
    "bg0":    QColor(5,    7,  18),
    "bg1":    QColor(8,   11,  26),
    "text":   QColor(230, 238, 255),
    "dim":    QColor(90,  115, 165),
    "accent": QColor(10,  180, 255),
    "red":    QColor(255,  58,  75),
    "orange": QColor(255, 148,  50),
    "yellow": QColor(255, 208,  48),
    "green":  QColor(50,  215, 130),
    "purple": QColor(175, 110, 255),
}

# Wave color palette per state  [primary, secondary, tertiary]
_STATE_WAVE = {
    "IDLE":         [(55,  110, 230), (40,   80, 190), (30,  55, 150)],
    "LISTENING":    [(10,  185, 255), (65,  145, 255), (110,  85, 255)],
    "SPEAKING":     [(255, 148,  55), (255,  90, 175), (155,  75, 255)],
    "THINKING":     [(155,  85, 255), (85,  115, 255), (210,  55, 255)],
    "PROCESSING":   [(75,  155, 255), (115,  75, 255), (10,  205, 185)],
    "MUTED":        [(185,  28,  48), (110,  18,  38), (65,   10,  28)],
    "INITIALISING": [(38,   75, 200), (28,   55, 160), (18,   38, 120)],
}

_STATE_ACCENT = {
    "IDLE":         _C["dim"],
    "LISTENING":    _C["accent"],
    "SPEAKING":     _C["orange"],
    "THINKING":     _C["purple"],
    "PROCESSING":   _C["accent"],
    "MUTED":        _C["red"],
    "INITIALISING": _C["dim"],
}

_STATE_LABEL = {
    "IDLE":         "STANDBY",
    "LISTENING":    "LISTENING",
    "SPEAKING":     "SPEAKING",
    "THINKING":     "THINKING",
    "PROCESSING":   "PROCESSING",
    "MUTED":        "MUTED",
    "INITIALISING": "INITIALISING",
}


# ══════════════════════════════════════════════════════════════════════════════
#  APPLE SIRI WAVEFORM
#  • Draws inside a centered "pill zone" — max 680 px wide, never full window
#  • Horizontal alpha mask fades wave to nothing at both edges (like real Siri)
#  • 5 layered sines with harmonic overtones
#  • At idle: barely-visible slow breath
#  • When speaking/listening: full organic bloom
# ══════════════════════════════════════════════════════════════════════════════
class SiriWave(QWidget):
    # Max wave width — wave never wider than this
    MAX_W = 700
    # Fade zone as fraction of wave width (each side)
    FADE  = 0.14

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.energy   = 0.0
        self.target_e = 0.0
        self._cols    = _STATE_WAVE["IDLE"]

        # Layer params: (phase_speed, freq_mul, amp_frac, line_width)
        self._layers = [
            [0.0220, 1.00, 0.00, 1.00, 3.4],   # [phase, spd, freq, af, lw]
            [0.0, 0.017, 1.58, 0.76, 2.5],
            [0.0, 0.028, 0.76, 0.56, 1.9],
            [0.0, 0.013, 2.15, 0.42, 1.3],
            [0.0, 0.034, 0.48, 0.29, 0.8],
        ]
        # Repack as dicts for clarity
        self._layers = [
            {"ph": i * 1.26, "spd": s, "freq": f, "af": af, "lw": lw}
            for i, (s, f, af, lw) in enumerate([
                (0.022, 1.00, 1.00, 3.4),
                (0.017, 1.58, 0.76, 2.5),
                (0.028, 0.76, 0.56, 1.9),
                (0.013, 2.15, 0.42, 1.3),
                (0.034, 0.48, 0.29, 0.8),
            ])
        ]

        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(16)

    def set_energy(self, v: float):
        self.target_e = max(0.0, min(1.0, v))

    def set_state(self, s: str):
        self._cols = _STATE_WAVE.get(s, _STATE_WAVE["IDLE"])

    def _tick(self):
        self.energy += (self.target_e - self.energy) * 0.055
        spd = 0.016 + self.energy * 0.055
        for L in self._layers:
            L["ph"] += L["spd"] * spd * 1.8
        self.update()

    def paintEvent(self, e: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        W, H = self.width(), self.height()
        en   = max(0.035, self.energy)

        # ── Wave zone: centered, capped at MAX_W ──────────────────────
        ww   = min(W, self.MAX_W)
        wx   = (W - ww) // 2      # left edge of wave zone
        cy   = H // 2

        p.fillRect(self.rect(), QColor(0, 0, 0, 0))

        # ── Ambient glow beneath the wave ─────────────────────────────
        for gi, (gcol, r_frac) in enumerate([
            (self._cols[0], 0.48),
            (self._cols[1], 0.30),
        ]):
            gc = QRadialGradient(W * 0.5, cy, ww * r_frac)
            c0 = QColor(*gcol)
            c0.setAlpha(int(28 * en * (1 - gi * 0.45)))
            gc.setColorAt(0, c0)
            gc.setColorAt(1, QColor(0, 0, 0, 0))
            p.setBrush(QBrush(gc))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(self.rect())

        SAMPLES = 380

        for li, L in enumerate(self._layers):
            col_i    = min(li, len(self._cols) - 1)
            base_col = QColor(*self._cols[col_i])

            idle_amp = H * 0.024 * max(0.3, 1.0 - li * 0.15)
            live_amp = H * 0.38  * en * L["af"]
            amp      = idle_amp + live_amp

            base_alpha = [225, 175, 135, 95, 58][li]
            alpha      = int(base_alpha * (0.42 + en * 0.58))
            lw         = L["lw"] * (0.65 + en * 0.55)

            path = QPainterPath()
            fade = self.FADE

            for i in range(SAMPLES + 1):
                t_  = i / SAMPLES
                x   = wx + t_ * ww

                # Organic tri-harmonic sine
                y = (cy
                     + amp * math.sin(L["freq"] * t_ * math.pi * 4.2 + L["ph"])
                     + amp * 0.34 * math.sin(L["freq"] * t_ * math.pi * 7.6 + L["ph"] * 1.38)
                     + amp * 0.13 * math.sin(L["freq"] * t_ * math.pi * 13.4 + L["ph"] * 0.72))

                # Edge alpha mask — smooth cosine fade
                if t_ < fade:
                    mask = 0.5 - 0.5 * math.cos(math.pi * t_ / fade)
                elif t_ > 1.0 - fade:
                    mask = 0.5 - 0.5 * math.cos(math.pi * (1.0 - t_) / fade)
                else:
                    mask = 1.0

                # Encode alpha in x by drawing segments — simpler: just adjust alpha per segment
                # We'll draw the full path then clip with a gradient mask
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)

            # Draw the path with base alpha
            qc = QColor(base_col)
            qc.setAlpha(alpha)
            p.setPen(QPen(qc, lw, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

            # White shimmer on primary wave
            if li == 0 and en > 0.10:
                wc = QColor(255, 255, 255, int(48 * en))
                p.setPen(QPen(wc, 0.7))
                p.drawPath(path)

        # ── Horizontal fade mask — two gradient rectangles ─────────────
        # Left fade
        fade_w = int(ww * self.FADE * 1.8)
        lf = QLinearGradient(wx, 0, wx + fade_w, 0)
        lf.setColorAt(0.0, QColor(5,  7, 18, 255))
        lf.setColorAt(1.0, QColor(5,  7, 18,   0))
        p.fillRect(QRect(wx, 0, fade_w, H), QBrush(lf))

        # Right fade
        rf = QLinearGradient(wx + ww - fade_w, 0, wx + ww, 0)
        rf.setColorAt(0.0, QColor(5,  7, 18,   0))
        rf.setColorAt(1.0, QColor(5,  7, 18, 255))
        p.fillRect(QRect(wx + ww - fade_w, 0, fade_w, H), QBrush(rf))

        # Mask everything outside wave zone
        if wx > 0:
            p.fillRect(QRect(0, 0, wx, H), QColor(5, 7, 18, 255))
            p.fillRect(QRect(wx + ww, 0, W - wx - ww, H), QColor(5, 7, 18, 255))

        p.end()


# ══════════════════════════════════════════════════════════════════════════════
#  DEEP SPACE BACKGROUND — very low fps, ambient only
# ══════════════════════════════════════════════════════════════════════════════
class DeepSpaceBG(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._fade   = 0.0
        self._scols  = _STATE_WAVE["IDLE"]
        t = QTimer(self); t.timeout.connect(self._step); t.start(50)  # 20 fps

    def set_state_colors(self, cols):
        self._scols = cols

    def _step(self):
        self._fade = min(1.0, self._fade + 0.018)
        self.update()

    def paintEvent(self, e: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        # Base gradient — very dark blue-black
        g = QLinearGradient(0, 0, 0, H)
        g.setColorAt(0.0,  QColor(4,   6,  16))
        g.setColorAt(0.45, QColor(6,   9,  22))
        g.setColorAt(1.0,  QColor(4,   6,  16))
        p.fillRect(self.rect(), QBrush(g))

        # Star field — deterministic, tiny dots only
        rng = random.Random(7)
        for _ in range(180):
            sx = rng.randint(0, W)
            sy = rng.randint(0, H)
            sa = rng.uniform(0.03, 0.22)
            sz = rng.uniform(0.4, 1.4)
            sc = QColor(210, 225, 255, int(sa * 255 * self._fade))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(sc))
            p.drawEllipse(QPointF(sx, sy), sz, sz)

        # State-reactive bottom bloom — very subtle
        c1 = QColor(*self._scols[0])
        c1.setAlpha(int(30 * self._fade))
        bg = QRadialGradient(W * 0.5, H * 0.88, W * 0.55)
        bg.setColorAt(0, c1); bg.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(bg)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(self.rect())

        # Vignette
        vig = QRadialGradient(W * 0.5, H * 0.5, max(W, H) * 0.68)
        vig.setColorAt(0, QColor(0, 0, 0, 0))
        vig.setColorAt(1, QColor(0, 0, 0, 145))
        p.setBrush(QBrush(vig)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(self.rect())

        p.end()


# ══════════════════════════════════════════════════════════════════════════════
#  STATUS DOT — Apple-style single blinking dot + label
# ══════════════════════════════════════════════════════════════════════════════
class StatusDot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedHeight(20)
        self._text  = "INITIALISING"
        self._color = _C["dim"]
        self._phase = 0.0
        self._alpha = 0.0
        t = QTimer(self); t.timeout.connect(self._tick); t.start(40)

    def set_status(self, text: str, color: QColor):
        self._text = text; self._color = color; self.update()

    def _tick(self):
        self._phase = (self._phase + 0.06) % (math.pi * 2)
        self._alpha = min(1.0, self._alpha + 0.035)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        cy = H // 2

        # SF-style tracking font
        font = QFont("Consolas", 8)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3.2)
        font.setWeight(QFont.Weight.Medium)
        p.setFont(font)
        fm  = QFontMetrics(font)
        dot_r   = 3.5
        spacing = 8
        tw  = fm.horizontalAdvance(self._text)
        total_w = dot_r * 2 + spacing + tw
        x0  = (W - total_w) / 2

        # Dot — breathes gently
        pulse = 0.82 + 0.18 * math.sin(self._phase)
        dc    = QColor(self._color)
        dc.setAlpha(int(220 * self._alpha * pulse))
        p.setBrush(QBrush(dc)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(x0 + dot_r, cy), dot_r * pulse, dot_r * pulse)

        # Label
        tc = QColor(self._color)
        tc.setAlpha(int(175 * self._alpha))
        p.setPen(tc)
        p.drawText(
            QRectF(x0 + dot_r * 2 + spacing, 0, tw + 4, H),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._text,
        )
        p.end()


# ══════════════════════════════════════════════════════════════════════════════
#  LOG TEXT — ghost overlay, minimal
# ══════════════════════════════════════════════════════════════════════════════
class GhostLog(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFont(QFont("Segoe UI", 9))
        self.setStyleSheet("""
            QTextEdit {
                background: transparent;
                color: rgba(140,175,230,170);
                border: none;
                padding: 0 2px;
            }
            QScrollBar:vertical  { width:  0px; }
            QScrollBar:horizontal{ height: 0px; }
        """)


# ══════════════════════════════════════════════════════════════════════════════
#  MIC BUTTON — frosted glass circle, Apple style
# ══════════════════════════════════════════════════════════════════════════════
class MicButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(60, 60)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        self.active    = False
        self.muted     = False
        self._hovered  = False
        self._ring_r   = 0.0
        self._ring_a   = 0.0
        self._ring_col = QColor(10, 185, 255)
        self._press_s  = 1.0   # scale on press

        t = QTimer(self); t.timeout.connect(self._tick); t.start(16)

    def set_active(self, active: bool, muted: bool = False):
        self.active    = active
        self.muted     = muted
        self._ring_col = _C["red"] if muted else (QColor(10, 185, 255) if active else QColor(160, 195, 255))

    def _tick(self):
        if self.active and not self.muted:
            self._ring_r = (self._ring_r + 0.022) % 1.0
            self._ring_a = 1.0 - self._ring_r
        else:
            self._ring_a = max(0.0, self._ring_a - 0.032)
        self.update()

    def enterEvent(self, e): self._hovered = True;  self.update()
    def leaveEvent(self, e): self._hovered = False; self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2
        R = 24.0

        p.fillRect(self.rect(), QColor(0, 0, 0, 0))

        # Rings
        if self._ring_a > 0.01:
            for i in range(2):
                f   = (self._ring_r + i * 0.5) % 1.0
                rr  = R + f * 20
                ra  = int((1.0 - f) * self._ring_a * 80)
                if ra > 2:
                    rc = QColor(self._ring_col); rc.setAlpha(ra)
                    p.setPen(QPen(rc, 1.1)); p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawEllipse(QPointF(cx, cy), rr, rr)

        # Frosted glass fill
        if self.muted:
            glass = QColor(200, 30, 55, 200 if self._hovered else 165)
        else:
            glass = QColor(255, 255, 255, 195 if self._hovered else 155)

        # Drop shadow
        sh = QRadialGradient(cx, cy + 4, R + 14)
        sh.setColorAt(0, QColor(0, 0, 0, 55)); sh.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(sh)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy + 4), R + 14, R + 14)

        p.setBrush(QBrush(glass)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), R, R)

        # Subtle rim highlight
        rim = QColor(255, 255, 255, 55)
        p.setPen(QPen(rim, 0.8)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), R - 0.4, R - 0.4)

        # Mic icon
        ic = QColor(255, 255, 255) if self.muted else QColor(12, 22, 52)
        p.setPen(Qt.PenStyle.NoPen)
        cap = QPainterPath()
        cap.addRoundedRect(QRectF(cx - 4, cy - 9.5, 8, 12), 4, 4)
        p.fillPath(cap, QBrush(ic))
        p.setPen(QPen(ic, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        arc = QPainterPath()
        arc.moveTo(cx - 6.5, cy + 2.5)
        arc.arcTo(QRectF(cx - 6.5, cy - 1.5, 13, 11), 180, -180)
        p.drawPath(arc)
        p.drawLine(int(cx), int(cy + 9), int(cx), int(cy + 13))
        p.drawLine(int(cx - 3.5), int(cy + 13), int(cx + 3.5), int(cy + 13))
        p.end()


# ══════════════════════════════════════════════════════════════════════════════
#  COMPAT SHIM
# ══════════════════════════════════════════════════════════════════════════════
class _RootShim:
    def __init__(self, app, win):
        self._app = app; self._win = win
    def mainloop(self):
        self._win.show(); sys.exit(self._app.exec())


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN WINDOW
# ══════════════════════════════════════════════════════════════════════════════
class JarvisUI(QMainWindow):

    def __init__(self, face_path=None, size=None):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")

        super().__init__()
        self.setWindowTitle("J.A.R.V.I.S")
        self.setMinimumSize(680, 440)
        self.resize(1080, 640)

        sc = QApplication.primaryScreen().geometry()
        self.move((sc.width() - self.width()) // 2, (sc.height() - self.height()) // 2)

        # ── Root canvas ────────────────────────────────────────────────
        self._bg = DeepSpaceBG()
        self.setCentralWidget(self._bg)

        # ── Top-left badge ─────────────────────────────────────────────
        self._badge = QLabel(MODEL_BADGE, self._bg)
        bf = QFont("Consolas", 7, QFont.Weight.Bold)
        bf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)
        self._badge.setFont(bf)
        self._badge.setStyleSheet("color: rgba(45,70,130,120); background: transparent;")
        self._badge.adjustSize()

        # ── Top-center name ────────────────────────────────────────────
        self._title = QLabel(SYSTEM_NAME, self._bg)
        tf = QFont("Consolas", 12, QFont.Weight.Bold)
        tf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 8)
        self._title.setFont(tf)
        self._title.setStyleSheet("color: rgba(110,155,240,150); background: transparent;")
        self._title.adjustSize()

        # ── Top-right clock ────────────────────────────────────────────
        self._clock = QLabel(time.strftime("%H:%M"), self._bg)
        cf = QFont("Consolas", 12, QFont.Weight.Bold)
        self._clock.setFont(cf)
        self._clock.setStyleSheet("color: rgba(75,120,205,155); background: transparent;")
        self._clock.adjustSize()
        ct = QTimer(self); ct.timeout.connect(self._tick_clock); ct.start(8000)

        # ── Ghost log ──────────────────────────────────────────────────
        self._log = GhostLog(self._bg)

        # ── Status dot ─────────────────────────────────────────────────
        self._status = StatusDot(self._bg)

        # ── Siri waveform ──────────────────────────────────────────────
        self._wave = SiriWave(self._bg)

        # ── Mic button ─────────────────────────────────────────────────
        self._mic = MicButton(self._bg)
        self._mic.clicked.connect(self._toggle_mute)

        # ── Input bar — pill style, centered ──────────────────────────
        self._input = QLineEdit(self._bg)
        self._input.setPlaceholderText("Ask JARVIS…")
        self._input.setFont(QFont("Segoe UI", 10))
        self._input.setFixedHeight(40)
        self._input.setStyleSheet("""
            QLineEdit {
                background: rgba(255,255,255,7);
                color: rgba(210,228,255,215);
                border: 1px solid rgba(70,110,200,30);
                border-radius: 20px;
                padding: 0 20px;
                selection-background-color: rgba(10,185,255,80);
            }
            QLineEdit:focus {
                background: rgba(255,255,255,11);
                border: 1px solid rgba(10,185,255,55);
            }
        """)
        self._input.returnPressed.connect(self._on_submit)

        self._send = QPushButton("↑", self._bg)
        self._send.setFixedSize(40, 40)
        self._send.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        self._send.setCursor(Qt.CursorShape.PointingHandCursor)
        self._send.setStyleSheet("""
            QPushButton {
                background: rgba(10,185,255,45);
                color: rgba(10,185,255,200);
                border: 1px solid rgba(10,185,255,35);
                border-radius: 20px;
            }
            QPushButton:hover  { background: rgba(10,185,255,100); color: white; }
            QPushButton:pressed{ background: rgba(10,150,220,150); }
        """)
        self._send.clicked.connect(self._on_submit)

        # ── Live pill ──────────────────────────────────────────────────
        self._live = QPushButton("● LIVE", self._bg)
        self._live.setFont(QFont("Consolas", 7))
        self._live.setFixedSize(62, 19)
        self._live.setCheckable(True)
        self._live.setCursor(Qt.CursorShape.PointingHandCursor)
        self._live.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: rgba(50,215,130,170);
                border: 1px solid rgba(30,155,80,70);
                border-radius: 9px; letter-spacing: 1px;
            }
            QPushButton:checked {
                color: rgba(255,58,75,190);
                border: 1px solid rgba(155,18,38,90);
            }
        """)
        self._live.clicked.connect(self._toggle_mute)

        # ── F4 hint ────────────────────────────────────────────────────
        self._f4 = QLabel("[F4]", self._bg)
        self._f4.setFont(QFont("Consolas", 6))
        self._f4.setStyleSheet("color: rgba(30,50,95,90); background: transparent;")
        self._f4.adjustSize()

        # ── State ──────────────────────────────────────────────────────
        self.speaking        = False
        self.muted           = False
        self._jarvis_state   = "INITIALISING"
        self.status_text     = "INITIALISING"
        self.typing_queue    = deque()
        self.is_typing       = False
        self.on_text_command = None

        self._api_key_ready  = self._api_keys_exist()
        if not self._api_key_ready:
            self._show_setup_ui()

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.root = _RootShim(self._app, self)
        self._layout()

    # ── Layout ────────────────────────────────────────────────────────

    def _layout(self):
        W, H = self._bg.width(), self._bg.height()
        if W < 20 or H < 20:
            return

        PAD   = 20
        TOP   = 48       # top bar height
        BOT   = 72       # bottom zone height

        # Top bar
        self._badge.move(PAD, (TOP - self._badge.height()) // 2)
        tw = self._title.sizeHint().width()
        self._title.move((W - tw) // 2, (TOP - self._title.height()) // 2)
        cw = self._clock.sizeHint().width()
        self._clock.move(W - cw - PAD, (TOP - self._clock.height()) // 2)

        # Bottom zone
        bot_y    = H - BOT
        # Input pill — centered, max 580px
        inp_w    = min(580, W - 140)
        inp_x    = (W - inp_w - 44) // 2
        input_y  = bot_y + (BOT - 40) // 2
        self._input.setGeometry(inp_x, input_y, inp_w, 40)
        self._send.setGeometry(inp_x + inp_w + 4, input_y, 40, 40)

        # Mic — centered above input
        mic_y = bot_y - self._mic.height() - 14
        self._mic.move((W - self._mic.width()) // 2, mic_y)

        # Status dot — just above mic
        stat_y = mic_y - 26
        self._status.setGeometry(0, stat_y, W, 20)

        # Live pill + F4 — bottom corners
        self._live.move(PAD, input_y + (40 - 19) // 2)
        self._f4.move(W - self._f4.sizeHint().width() - PAD,
                      input_y + (40 - self._f4.height()) // 2)

        # Waveform — middle zone
        wave_top = TOP + 4
        wave_bot = stat_y - 6
        wave_h   = max(60, wave_bot - wave_top)
        self._wave.setGeometry(0, wave_top, W, wave_h)

        # Log — top-center overlay on waveform, narrow
        log_w = min(600, W - 80)
        log_x = (W - log_w) // 2
        log_h = min(76, wave_h // 3)
        self._log.setGeometry(log_x, wave_top + 4, log_w, log_h)

    def resizeEvent(self, e: QResizeEvent):
        super().resizeEvent(e)
        self._bg.setGeometry(0, 0, self.width(), self.height())
        self._layout()
        if hasattr(self, "_overlay"):
            self._overlay.setGeometry(0, 0, self._bg.width(), self._bg.height())

    # ── Helpers ───────────────────────────────────────────────────────

    def _tick_clock(self):
        self._clock.setText(time.strftime("%H:%M"))
        self._clock.adjustSize()
        W = self._bg.width()
        self._clock.move(W - self._clock.sizeHint().width() - 20,
                         (48 - self._clock.height()) // 2)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_F4:
            self._toggle_mute()
        super().keyPressEvent(ev)

    def _apply_visuals(self, state: str):
        m = {
            "MUTED":      ("MUTED",      _C["red"],    0.04, False),
            "SPEAKING":   ("SPEAKING",   _C["orange"], 0.88, True),
            "THINKING":   ("THINKING",   _C["purple"], 0.52, False),
            "LISTENING":  ("LISTENING",  _C["accent"], 0.68, True),
            "PROCESSING": ("PROCESSING", _C["accent"], 0.46, True),
        }
        lbl, col, en, act = m.get(state, ("ONLINE", _C["accent"], 0.12, False))
        if self.muted:
            lbl, col, en, act = "MUTED", _C["red"], 0.04, False

        self._status.set_status(lbl, col)
        self._wave.set_energy(en)
        self._wave.set_state(state if not self.muted else "MUTED")
        self._bg.set_state_colors(
            _STATE_WAVE.get(state if not self.muted else "MUTED", _STATE_WAVE["IDLE"]))
        self._mic.set_active(act and not self.muted, self.muted)

    # ── Public API ────────────────────────────────────────────────────

    def set_state(self, state: str):
        self._jarvis_state = state
        sm = {
            "MUTED":      ("MUTED",      False),
            "SPEAKING":   ("SPEAKING",   True),
            "THINKING":   ("THINKING",   False),
            "LISTENING":  ("LISTENING",  False),
            "PROCESSING": ("PROCESSING", False),
        }
        self.status_text, self.speaking = sm.get(state, ("ONLINE", False))
        self._apply_visuals(state)

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
            self._pump()

    def wait_for_api_key(self):
        while not self._api_key_ready:
            time.sleep(0.1)

    # ── Private ───────────────────────────────────────────────────────

    def _toggle_mute(self):
        self.muted = not self.muted
        self._live.setChecked(self.muted)
        self._live.setText("● MUTED" if self.muted else "● LIVE")
        if self.muted:
            self.set_state("MUTED"); self.write_log("SYS: Microphone muted.")
        else:
            self.set_state("LISTENING"); self.write_log("SYS: Microphone active.")

    def _on_submit(self):
        text = self._input.text().strip()
        if not text: return
        self._input.clear()
        self.write_log(f"You: {text}")
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(text,), daemon=True).start()

    def _api_keys_exist(self) -> bool:
        if not API_FILE.exists(): return False
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8"))
            return bool(d.get("gemini_api_key")) and bool(d.get("os_system"))
        except Exception:
            return False

    def _pump(self):
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
            html = (f'<span style="color:rgba(95,155,255,185);font-weight:600">{text[:sp]}</span>'
                    f'<span style="color:rgba(175,210,255,195)">{text[sp:]}</span>')
        elif tl.startswith("jarvis:") or tl.startswith("ai:"):
            sp   = text.index(":") + 1
            html = (f'<span style="color:rgba(10,185,255,195);font-weight:700">{text[:sp]}</span>'
                    f'<span style="color:rgba(195,225,255,205)"> {text[sp:].strip()}</span>')
        elif "error" in tl or tl.startswith("err:"):
            html = f'<span style="color:rgba(255,58,75,200)">{text}</span>'
        elif tl.startswith("sys:"):
            html = f'<span style="color:rgba(50,80,145,155);font-style:italic">{text}</span>'
        else:
            html = f'<span style="color:rgba(85,125,190,155)">{text}</span>'

        self._log.append(html)
        self._log.verticalScrollBar().setValue(self._log.verticalScrollBar().maximum())
        QTimer.singleShot(14, self._pump)

    # ── Setup dialog ──────────────────────────────────────────────────

    @staticmethod
    def _detect_os():
        s = platform.system().lower()
        if s == "darwin":  return "mac"
        if s == "windows": return "windows"
        return "linux"

    def _show_setup_ui(self):
        detected = self._detect_os()
        self._selected_os = detected

        self._overlay = QFrame(self._bg)
        self._overlay.setGeometry(0, 0, self._bg.width(), self._bg.height())
        self._overlay.setStyleSheet("background: rgba(3,5,16,235);")

        card = QFrame(self._overlay)
        card.setFixedSize(440, 320)
        card.move((self._overlay.width() - 440) // 2,
                  (self._overlay.height() - 320) // 2)
        card.setStyleSheet("""
            QFrame {
                background: rgba(7,12,38,245);
                border: 1px solid rgba(10,185,255,45);
                border-radius: 22px;
            }
        """)

        from PyQt6.QtWidgets import QVBoxLayout, QHBoxLayout
        lay = QVBoxLayout(card)
        lay.setContentsMargins(32, 26, 32, 26)
        lay.setSpacing(13)

        t = QLabel("SYSTEM INITIALISATION")
        tf2 = QFont("Consolas", 10, QFont.Weight.Bold)
        tf2.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)
        t.setFont(tf2)
        t.setStyleSheet("color: rgba(10,185,255,215); background: transparent;")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(t)

        s = QLabel("Enter your Gemini API key and select OS")
        s.setFont(QFont("Segoe UI", 9))
        s.setStyleSheet("color: rgba(80,110,170,155); background: transparent;")
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(s)

        self._gem = QLineEdit()
        self._gem.setPlaceholderText("GEMINI API KEY")
        self._gem.setEchoMode(QLineEdit.EchoMode.Password)
        self._gem.setFont(QFont("Consolas", 10))
        self._gem.setFixedHeight(42)
        self._gem.setStyleSheet("""
            QLineEdit {
                background: rgba(255,255,255,6);
                color: rgba(210,230,255,215);
                border: 1px solid rgba(10,185,255,40);
                border-radius: 21px; padding: 0 18px;
            }
            QLineEdit:focus { border: 1px solid rgba(10,185,255,130); }
        """)
        lay.addWidget(self._gem)

        os_row = QHBoxLayout(); os_row.setSpacing(7)
        self._os_btns: dict = {}
        for k, lbl in [("windows","⊞ WINDOWS"), ("mac"," macOS"), ("linux","🐧 LINUX")]:
            b = QPushButton(lbl)
            b.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(28)
            b.clicked.connect(lambda chk, key=k: self._sel_os(key))
            os_row.addWidget(b)
            self._os_btns[k] = b
        lay.addLayout(os_row)
        self._sel_os(detected)

        go = QPushButton("INITIALISE SYSTEMS")
        go.setFixedHeight(42)
        go.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        go.setCursor(Qt.CursorShape.PointingHandCursor)
        go.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: rgba(10,185,255,210);
                border: 1px solid rgba(10,185,255,100);
                border-radius: 21px; letter-spacing: 2px;
            }
            QPushButton:hover  { background: rgba(10,185,255,45); color: white; }
            QPushButton:pressed{ background: rgba(10,150,220,80); }
        """)
        go.clicked.connect(self._save_keys)
        lay.addWidget(go)

        self._overlay.show()
        self._overlay.raise_()

    def _sel_os(self, key: str):
        self._selected_os = key
        styles = {
            "windows": ("rgba(10,185,255,215)", "rgba(0,35,65,240)",  "rgba(10,150,200,130)"),
            "mac":     ("rgba(255,210,48,215)", "rgba(42,32,0,240)",  "rgba(195,155,20,130)"),
            "linux":   ("rgba(50,215,130,215)", "rgba(0,32,16,240)",  "rgba(30,155,75,130)"),
        }
        dim = ("rgba(55,85,140,170)", "rgba(255,255,255,5)", "rgba(40,70,140,60)")
        for k, b in self._os_btns.items():
            fg, bg, bd = styles[k] if k == key else dim
            b.setStyleSheet(f"""
                QPushButton {{
                    background:{bg}; color:{fg};
                    border:1px solid {bd}; border-radius:14px;
                    font-size:9px; letter-spacing:1px; padding:3px 6px;
                }}
            """)

    def _save_keys(self):
        gemini = self._gem.text().strip()
        if not gemini:
            self._gem.setStyleSheet(self._gem.styleSheet() +
                                    "border:1px solid rgba(255,58,75,200);")
            return
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(API_FILE, "w", encoding="utf-8") as f:
            json.dump({"gemini_api_key": gemini, "os_system": self._selected_os}, f, indent=4)
        self._overlay.deleteLater()
        self._api_key_ready = True
        self.set_state("LISTENING")
        self.write_log(f"SYS: Systems initialised. OS → {self._selected_os.upper()}.")


# ══════════════════════════════════════════════════════════════════════════════
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = JarvisUI()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()