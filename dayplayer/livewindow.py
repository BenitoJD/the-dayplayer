"""Circadia Live — the real-time window: your attention as an instrument.

A big orb breathes in the color of your current state; the soundscape
morphs with it (see live.py). CALM MODE hides every number — just the
orb and the sound — a non-judgmental mirror (nothing to chase, nothing
to feel bad about).

Run:  python3 -m dayplayer.livewindow
"""
from __future__ import annotations

import math
import os
import sys

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QIcon, QPainter, QRadialGradient
from PySide6.QtWidgets import (QApplication, QCheckBox, QHBoxLayout,
                               QLabel, QMainWindow, QPushButton, QSlider,
                               QVBoxLayout, QWidget)

from . import patterns
from .live import LiveEngine

BG = "#070a12"
INK = "#e9edf6"
DIM = "#7c87a0"
BORDER = "#1d2a47"
GREEN = "#3ecf8e"

QSS = f"""
QMainWindow, QWidget {{ background: {BG}; color: {INK};
  font-family: 'Menlo','Cascadia Code','Consolas',monospace; }}
QLabel#dim {{ color: {DIM}; font-size: 11px; }}
QPushButton {{ background: #121a2e; color: {INK}; border: 1px solid
  {BORDER}; border-radius: 9px; padding: 8px 14px; font-size: 12px; }}
QPushButton:hover {{ border-color: #4fd8eb; }}
QPushButton#go {{ background: #3ecf8e; color: #04140c; font-weight: 700;
  border: none; padding: 11px 22px; font-size: 13px; }}
QPushButton#stop {{ background: rgba(239,108,87,.15); color: #ef6c57;
  border: 1px solid #5c2f28; font-weight: 700; padding: 11px 22px; }}
QSlider::groove:horizontal {{ height: 4px; background: {BORDER};
  border-radius: 2px; }}
QSlider::handle:horizontal {{ background: #4fd8eb; width: 14px; height: 14px;
  margin: -5px 0; border-radius: 7px; }}
QCheckBox {{ color: {DIM}; font-size: 12px; }}
"""


class Orb(QWidget):
    """Breathing state orb — color = pattern, mixed by live weights."""

    def __init__(self, engine: LiveEngine):
        super().__init__()
        self.engine = engine
        self.setMinimumHeight(260)
        self._t = 0.0

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        r = min(cx, cy) - 30
        self._t += 0.016
        # blend weights -> color
        col = [0, 0, 0]
        total_w = 0.0
        for key, w in self.engine.weights.items():
            hexc = patterns.PATTERN_META[key]["color"].lstrip("#")
            rgb = tuple(int(hexc[i:i+2], 16) for i in (0, 2, 4))
            for i in range(3):
                col[i] += rgb[i] * w
            total_w += w
        if total_w > 0:
            col = [c / total_w for c in col]
        breathe = 0.5 + 0.5 * math.sin(self._t * 0.9)
        rr = r * (0.86 + 0.10 * breathe)
        grad = QRadialGradient(cx, cy, rr)
        grad.setColorAt(0.0, QColor(int(col[0]), int(col[1]), int(col[2]), 235))
        grad.setColorAt(0.65, QColor(int(col[0] * 0.55), int(col[1] * 0.55),
                                     int(col[2] * 0.55), 160))
        grad.setColorAt(1.0, QColor(int(col[0] * 0.2), int(col[1] * 0.2),
                                    int(col[2] * 0.2), 0))
        p.setBrush(grad)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(cx - rr, cy - rr, rr * 2, rr * 2))


class LiveWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Circadia Live — hear your state")
        self.resize(460, 560)
        icon = os.path.join(os.path.dirname(__file__), "..", "assets",
                            "icon.png")
        self.setWindowIcon(QIcon(icon))
        self.engine = LiveEngine()

        root = QWidget()
        self.setCentralWidget(root)
        col = QVBoxLayout(root)
        col.setContentsMargins(20, 16, 20, 16)
        col.setSpacing(10)

        self.orb = Orb(self.engine)
        col.addWidget(self.orb, 1)

        self.state_lab = QLabel("○ idle")
        self.state_lab.setAlignment(Qt.AlignCenter)
        self.state_lab.setStyleSheet("font-size:22px;font-weight:700;")
        col.addWidget(self.state_lab)

        self.stats = QLabel("")
        self.stats.setObjectName("dim")
        self.stats.setAlignment(Qt.AlignCenter)
        col.addWidget(self.stats)

        row = QHBoxLayout()
        self.start_btn = QPushButton("◉ START SESSION")
        self.start_btn.setObjectName("go")
        self.start_btn.clicked.connect(self._toggle)
        row.addWidget(self.start_btn)
        col.addLayout(row)

        audio_row = QHBoxLayout()
        vol_lab = QLabel("vol")
        vol_lab.setObjectName("dim")
        self.vol = QSlider(Qt.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setValue(70)
        self.vol.valueChanged.connect(
            lambda v: setattr(self.engine, "gain", v / 100.0))
        self.calm = QCheckBox("calm mode (no numbers)")
        self.calm.toggled.connect(self._calm)
        audio_row.addWidget(vol_lab)
        audio_row.addWidget(self.vol, 1)
        audio_row.addWidget(self.calm)
        col.addLayout(audio_row)

        hint = QLabel("flow = warm pulse · flail = static · drift = wind · "
                      "quiet = low tone")
        hint.setObjectName("dim")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignCenter)
        col.addWidget(hint)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(200)

    def _toggle(self):
        if self.engine.running:
            self.engine.stop()
            self.start_btn.setText("◉ START SESSION")
            self.start_btn.setObjectName("go")
            self.state_lab.setText("○ idle")
            self.state_lab.setStyleSheet("font-size:22px;font-weight:700;")
        else:
            self.engine.start()
            if not self.engine.audio_on:
                self.stats.setText("(no audio device — analysis only)")
            self.start_btn.setText("■ STOP SESSION")
            self.start_btn.setObjectName("stop")
        self._tick()

    def _calm(self, on: bool):
        self.stats.setVisible(not on)

    def _tick(self):
        self.orb.update()
        meta = patterns.PATTERN_META[self.engine.state]
        self.state_lab.setText(meta["label"].upper())
        self.state_lab.setStyleSheet(
            f"font-size:22px;font-weight:700;color:{meta['color']};")
        if not self.calm.isChecked():
            self.stats.setText(
                f"{self.engine.cps:.1f} keys/s"
                + ("" if self.engine.audio_on else " · audio off"))

    def closeEvent(self, e):
        self.engine.stop()
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    w = LiveWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
