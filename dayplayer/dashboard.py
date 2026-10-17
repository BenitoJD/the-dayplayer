"""Circadia dashboard — futuristic native window (PySide6), both platforms.

Tabs:
  TODAY — timeline, patterns, stats, tags, render + blind A/B vote
  WEEK  — the audible diary: day-by-day grid, week render, tag correlations

Run:  python3 -m dayplayer.dashboard [--date YYYY-MM-DD] [--grab out.png]
"""
from __future__ import annotations

import os
import sys
import time

from PySide6.QtCore import Qt, QTimer, Signal, QRectF
from PySide6.QtGui import (QColor, QFont, QIcon, QPainter,
                           QPainterPath, QLinearGradient)
from PySide6.QtWidgets import (QApplication, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit,
                               QMainWindow, QPushButton, QScrollArea,
                               QSizePolicy, QTabWidget, QToolTip,
                               QVBoxLayout, QWidget)

from . import config, patterns, pipeline, tags
from .controller import Controller, open_dashboard_window, open_live_window

# ------------------------------------------------------------------ theme
BG = "#070a12"
PANEL = "#0e1424"
PANEL2 = "#121a2e"
BORDER = "#1d2a47"
INK = "#e9edf6"
DIM = "#7c87a0"
AMBER = "#f0b429"
CYAN = "#4fd8eb"
RED = "#ef6c57"
BLUE = "#5b8def"
GREEN = "#3ecf8e"

QSS = f"""
QMainWindow, QWidget {{ background: {BG}; color: {INK};
  font-family: 'Menlo', 'Cascadia Code', 'Consolas', monospace; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 12px;
  background: {PANEL}; }}
QTabBar::tab {{ background: {PANEL2}; color: {DIM}; border: 1px solid
  {BORDER}; padding: 7px 22px; margin-right: 4px;
  border-top-left-radius: 9px; border-top-right-radius: 9px;
  font-size: 11px; letter-spacing: 2px; }}
QTabBar::tab:selected {{ color: {CYAN}; border-bottom: 2px solid {CYAN}; }}
QFrame#card {{ background: {PANEL}; border: 1px solid {BORDER};
  border-radius: 12px; }}
QFrame#subtle {{ background: {PANEL2}; border: 1px solid {BORDER};
  border-radius: 10px; }}
QLabel#h1 {{ font-size: 21px; font-weight: 700; letter-spacing: 3px; }}
QLabel#dim  {{ color: {DIM}; font-size: 11px; }}
QLabel#big  {{ font-size: 21px; font-weight: 700; color: {CYAN}; }}
QLabel#bigA {{ font-size: 21px; font-weight: 700; color: {AMBER}; }}
QPushButton {{ background: {PANEL2}; color: {INK}; border: 1px solid {BORDER};
  border-radius: 9px; padding: 8px 14px; font-size: 12px; }}
QPushButton:hover {{ border-color: {CYAN}; }}
QPushButton#primary {{ background: {AMBER}; color: #1a1405; font-weight: 700;
  border: none; padding: 11px 20px; font-size: 13px; }}
QPushButton#primary:hover {{ background: #ffc94a; }}
QPushButton#primary:disabled {{ background: #4a4020; color: #8a7a45; }}
QPushButton#live {{ background: rgba(62,207,142,.12); color: {GREEN};
  border: 1px solid #2a6b52; font-weight: 700; }}
QPushButton#live:hover {{ background: rgba(62,207,142,.22); }}
QPushButton#vote {{ border: 1px solid {CYAN}; color: {CYAN}; }}
QPushButton#vote:hover {{ background: rgba(79,216,235,.12); }}
QLineEdit {{ background: {PANEL2}; border: 1px solid {BORDER};
  border-radius: 8px; padding: 6px 10px; color: {INK}; font-size: 12px; }}
QScrollArea {{ border: none; background: transparent; }}
"""


# ------------------------------------------------------------- components
class StatCard(QFrame):
    def __init__(self, title: str, value="—", accent=CYAN):
        super().__init__(objectName="card")
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        self.value = QLabel(str(value))
        self.value.setObjectName("bigA" if accent == AMBER else "big")
        lab = QLabel(title.upper())
        lab.setObjectName("dim")
        v.addWidget(self.value)
        v.addWidget(lab)


class Timeline(QFrame):
    MARGIN_L, MARGIN_R, MARGIN_B = 6, 6, 26

    def __init__(self):
        super().__init__(objectName="card")
        self.setMinimumHeight(140)
        self.data, self.strip, self.start_ts = [], [], time.time()
        self.setMouseTracking(True)

    def set_day(self, summary: dict):
        self.data = summary.get("minutes", [])
        self.strip = summary.get("strip", [])
        self.start_ts = summary.get("start_ts", time.time())
        self.update()

    def _minute_at(self, x: int) -> int | None:
        if not self.data:
            return None
        w = self.width() - self.MARGIN_L - self.MARGIN_R
        i = int((x - self.MARGIN_L) / max(w, 1) * len(self.data))
        return i if 0 <= i < len(self.data) else None

    def mouseMoveEvent(self, e):
        i = self._minute_at(e.position().x())
        if i is None or not self.data:
            return
        m = self.data[i]
        clock = time.strftime("%H:%M", time.localtime(
            self.start_ts + m["minute"] * 60))
        pat = patterns.PATTERN_META[m.get("pattern", patterns.MIRE)]["label"]
        QToolTip.showText(e.globalPosition().toPoint(),
                          f"{clock}\n{m['key_rate']} keys · "
                          f"{int(m['mouse_dist'])}px mouse\n"
                          f"{m['switches']:.0f} switches · {pat}", self)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width() - self.MARGIN_L - self.MARGIN_R
        h = self.height() - self.MARGIN_B
        if not self.data:
            p.setPen(QColor(DIM))
            p.drawText(self.rect(), Qt.AlignCenter,
                       "no data yet — start the recorder")
            return
        max_key = max((m["key_rate"] for m in self.data), default=1) or 1
        max_mouse = max((m["mouse_dist"] for m in self.data), default=1) or 1
        bw = max(w / len(self.data) - 0.6, 0.8)
        for i, m in enumerate(self.data):
            x = self.MARGIN_L + i * w / len(self.data)
            pat = m.get("pattern", patterns.MIRE)
            if pat == patterns.MIRE:
                p.fillRect(QRectF(x, h - 4, bw, 4),
                           QColor(patterns.PATTERN_META[pat]["color"]))
                continue
            hk = m["key_rate"] / max_key * (h - 14)
            hm = m["mouse_dist"] / max_mouse * (h * 0.35)
            p.fillRect(QRectF(x, h - 4 - hm, bw, hm), QColor(35, 52, 95))
            p.fillRect(QRectF(x, h - 4 - hk, bw, max(hk, 2)),
                       QColor(patterns.PATTERN_META[pat]["color"]))
        p.setPen(QColor(DIM))
        f = QFont(p.font())
        f.setPointSize(8)
        p.setFont(f)
        step = max(len(self.data) // 8, 1)
        for i in range(0, len(self.data), step):
            x = self.MARGIN_L + i * w / len(self.data)
            t = time.strftime("%H:%M", time.localtime(
                self.start_ts + i * 60))
            p.drawText(QRectF(x - 30, h + 6, 60, 16), Qt.AlignCenter, t)


class MiniTimeline(QWidget):
    """Tiny strip version for week cards."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(26)
        self.strip = []

    def set_strip(self, strip: list):
        self.strip = strip or []
        self.update()

    def paintEvent(self, _):
        if not self.strip:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n = len(self.strip)
        bw = max(self.width() / n - 0.5, 1.0)
        for i, pat in enumerate(self.strip):
            c = patterns.PATTERN_META[pat]["color"]
            h = 6 if pat == patterns.MIRE else 14 + 10 * (i % 3) / 2
            p.fillRect(QRectF(i * bw, self.height() - h, bw, h), QColor(c))


class Waveform(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(44)
        self.peaks = []
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def load(self, path: str):
        import wave as wav
        import numpy as np
        try:
            with wav.open(path) as w:
                n = min(w.getnframes(), 44100 * 120)
                x = np.frombuffer(w.readframes(n), dtype=np.int16)
                x = x[::2].astype(float) / 32768.0
            step = max(len(x) // 240, 1)
            self.peaks = np.abs(x[: len(x) // step * step]
                                .reshape(-1, step)).max(axis=1).tolist()
        except Exception:
            self.peaks = []
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(PANEL2))
        if not self.peaks:
            p.setPen(QColor(DIM))
            p.drawText(self.rect(), Qt.AlignCenter, "render to see waveform")
            return
        h, w, n = self.height(), self.width(), len(self.peaks)
        path = QPainterPath()
        for i, v in enumerate(self.peaks):
            x = i / n * w
            path.moveTo(x, h / 2)
            path.lineTo(x, h / 2 - v * h * 0.46)
        p.setPen(QColor(CYAN))
        p.drawPath(path)


class PlayerCard(QFrame):
    voted = Signal(str)

    def __init__(self, label: str, ctl: Controller):
        super().__init__(objectName="card")
        self.label, self.ctl = label, ctl
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        top = QHBoxLayout()
        name = QLabel(label)
        name.setStyleSheet(f"font-size:15px;font-weight:700;color:{CYAN};")
        self.play_btn = QPushButton("▶ play")
        self.play_btn.setFixedWidth(84)
        self.play_btn.clicked.connect(self.toggle)
        top.addWidget(name)
        top.addStretch(1)
        top.addWidget(self.play_btn)
        self.wave = Waveform()
        self.vote_btn = QPushButton(f"{label} is me")
        self.vote_btn.setObjectName("vote")
        self.vote_btn.clicked.connect(lambda: self.voted.emit(label.lower()))
        v.addLayout(top)
        v.addWidget(self.wave)
        v.addWidget(self.vote_btn)

    def toggle(self):
        if self.play_btn.text().startswith("▶"):
            self.ctl.play(self.label.lower())
            self.play_btn.setText("■ stop")
        else:
            self.ctl.stop_playback()
            self.play_btn.setText("▶ play")

    def load_session(self, blind_path: str):
        self.wave.load(blind_path)


class TagRow(QFrame):
    """Chips + add box for outcome tags."""

    def __init__(self, date: str):
        super().__init__(objectName="card")
        self.date = date
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 10, 14, 10)
        head = QHBoxLayout()
        lab = QLabel("HOW DID TODAY GO?  (tags)")
        lab.setObjectName("dim")
        v.addWidget(lab)
        self.chips = QHBoxLayout()
        self.chips.setSpacing(6)
        self.input = QLineEdit()
        self.input.setPlaceholderText("shipped · meeting day · exhausted…")
        self.input.returnPressed.connect(self._add)
        add = QPushButton("add")
        add.clicked.connect(self._add)
        row = QHBoxLayout()
        row.addWidget(self.input, 1)
        row.addWidget(add)
        v.addLayout(row)
        v.addLayout(self.chips)
        self.refresh()

    def _add(self):
        t = self.input.text().strip()
        if t:
            tags.set_tags(self.date, tags.get_tags(self.date) + [t])
            self.input.clear()
            self.refresh()

    def _remove(self, t: str):
        tags.set_tags(self.date,
                      [x for x in tags.get_tags(self.date) if x != t])
        self.refresh()

    def refresh(self):
        while self.chips.count():
            item = self.chips.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for t in tags.get_tags(self.date):
            chip = QPushButton(f"✕ {t}")
            chip.setToolTip("remove")
            chip.clicked.connect(lambda _=False, tt=t: self._remove(tt))
            self.chips.addWidget(chip)
        self.chips.addStretch(1)


class WeekDayCard(QFrame):
    def __init__(self):
        super().__init__(objectName="card")
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(4)
        self.day = QLabel("")
        self.day.setObjectName("dim")
        row = QHBoxLayout()
        self.flow = QLabel("—")
        self.flow.setStyleSheet(f"font-size:17px;font-weight:700;"
                                f"color:{AMBER};")
        self.meta = QLabel("")
        self.meta.setObjectName("dim")
        row.addWidget(self.flow)
        row.addStretch(1)
        row.addWidget(self.meta, 0, Qt.AlignTop)
        self.strip = MiniTimeline()
        v.addWidget(self.day)
        v.addLayout(row)
        v.addWidget(self.strip)

    def set_day(self, date: str, s: dict):
        self.day.setText(time.strftime("%a %b %d",
                        time.strptime(date, "%Y-%m-%d")))
        fl = s["counts"][patterns.FLOW]
        self.flow.setText(f"{fl}m flow")
        self.meta.setText(f"{s['total_key']:,} keys")
        self.strip.set_strip(s.get("strip", []))


# ---------------------------------------------------------------- window
class Dashboard(QMainWindow):
    _render_done_sig = Signal(dict)
    _week_done_sig = Signal(dict)

    def __init__(self, date: str | None = None):
        super().__init__()
        self.date = date
        self.ctl = Controller()
        self.setWindowTitle("Circadia — your day, played back")
        self.resize(1020, 860)
        icon_path = os.path.join(os.path.dirname(__file__), "..",
                                 "assets", "icon.png")
        self.setWindowIcon(QIcon(icon_path))
        self._rendering = False
        self._render_done_sig.connect(self._on_render_done)
        self._week_done_sig.connect(self._on_week_done)

        self._build()
        self._refresh()
        self._refresh_week()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh)
        self.timer.start(5000)

    # -------------------------------------------------------------- build
    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 14, 18, 12)
        outer.setSpacing(10)

        # header
        head = QHBoxLayout()
        title = QLabel("CIRCADIA")
        title.setObjectName("h1")
        sub = QLabel("your day, played back")
        sub.setObjectName("dim")
        self.status = QLabel("○ not recording")
        self.status.setStyleSheet(
            f"color:{DIM};font-size:12px;padding:4px 10px;"
            f"border:1px solid {BORDER};border-radius:999px;")
        live_btn = QPushButton("◉ GO LIVE")
        live_btn.setObjectName("live")
        live_btn.clicked.connect(lambda: open_live_window())
        self.record_btn = QPushButton("start recording")
        self.record_btn.clicked.connect(self._toggle_record)
        head.addWidget(title)
        head.addSpacing(8)
        head.addWidget(sub)
        head.addStretch(1)
        head.addWidget(self.status)
        head.addWidget(self.record_btn)
        head.addWidget(live_btn)
        outer.addLayout(head)

        # tabs
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)
        self.tabs.addTab(self._build_today(), "TODAY")
        self.tabs.addTab(self._build_week(), "WEEK")

    def _build_today(self) -> QWidget:
        wrap = QWidget()
        col = QVBoxLayout(wrap)
        col.setContentsMargins(12, 12, 12, 12)
        col.setSpacing(10)

        cards = QHBoxLayout()
        cards.setSpacing(10)
        self.card_key = StatCard("typing events")
        self.card_active = StatCard("active minutes")
        self.card_flow = StatCard("longest flow streak", accent=AMBER)
        self.card_flail = StatCard("flail minutes", accent=AMBER)
        self.card_sw = StatCard("app switches")
        self.card_mouse = StatCard("mouse travelled")
        for c in (self.card_key, self.card_active, self.card_flow,
                  self.card_flail, self.card_sw, self.card_mouse):
            cards.addWidget(c)
        col.addLayout(cards)

        tl_wrap = QVBoxLayout()
        tl_head = QLabel("TODAY'S TIMELINE")
        tl_head.setObjectName("dim")
        self.timeline = Timeline()
        tl_wrap.addWidget(tl_head)
        tl_wrap.addWidget(self.timeline)
        col.addLayout(tl_wrap)

        mid = QHBoxLayout()
        mid.setSpacing(10)
        pat_wrap = QFrame(objectName="card")
        pv = QVBoxLayout(pat_wrap)
        pv.setContentsMargins(14, 12, 14, 12)
        pv.setSpacing(4)
        pv.addWidget(QLabel("PATTERNS"))
        self.pat_rows = {}
        for key, meta in patterns.PATTERN_META.items():
            row = QHBoxLayout()
            name = QLabel(meta["label"].upper())
            name.setFixedWidth(52)
            name.setStyleSheet(f"color:{meta['color']};font-weight:700;")
            bar = QFrame()
            bar.setFixedHeight(8)
            bar.setStyleSheet(f"background:{meta['color']};"
                              f"border-radius:4px;")
            val = QLabel("0 min")
            val.setObjectName("dim")
            row.addWidget(name)
            row.addWidget(bar, 1)
            row.addWidget(val)
            self.pat_rows[key] = (bar, val)
            pv.addLayout(row)
            d = QLabel(meta["desc"])
            d.setObjectName("dim")
            pv.addWidget(d)
        mid.addWidget(pat_wrap, 3)

        app_wrap = QFrame(objectName="card")
        av = QVBoxLayout(app_wrap)
        av.setContentsMargins(14, 12, 14, 12)
        av.setSpacing(6)
        av.addWidget(QLabel("TOP APPS"))
        self.app_rows = []
        for _ in range(6):
            row = QHBoxLayout()
            name = QLabel("—")
            name.setFixedWidth(120)
            bar = QFrame()
            bar.setFixedHeight(8)
            bar.setStyleSheet(f"background:{CYAN};border-radius:4px;")
            val = QLabel("")
            val.setObjectName("dim")
            row.addWidget(name)
            row.addWidget(bar, 1)
            row.addWidget(val)
            av.addLayout(row)
            self.app_rows.append((name, bar, val))
        mid.addWidget(app_wrap, 2)
        col.addLayout(mid)

        rw = QFrame(objectName="card")
        rv = QVBoxLayout(rw)
        rv.setContentsMargins(14, 12, 14, 12)
        rrow = QHBoxLayout()
        self.render_btn = QPushButton("▶  RENDER MY DAY")
        self.render_btn.setObjectName("primary")
        self.render_btn.clicked.connect(self._render)
        hint = QLabel("two versions — one is you, one is your day shuffled. "
                      "listen blind, vote.")
        hint.setObjectName("dim")
        rrow.addWidget(self.render_btn)
        rrow.addSpacing(12)
        rrow.addWidget(hint)
        rrow.addStretch(1)
        self.reveal = QLabel("")
        self.reveal.setStyleSheet(f"color:{CYAN};font-weight:700;")
        rrow.addWidget(self.reveal)
        rv.addLayout(rrow)
        players = QHBoxLayout()
        self.pa = PlayerCard("A", self.ctl)
        self.pb = PlayerCard("B", self.ctl)
        self.pa.voted.connect(self._vote)
        self.pb.voted.connect(self._vote)
        players.addWidget(self.pa)
        players.addWidget(self.pb)
        rv.addLayout(players)
        col.addWidget(rw)

        self.tagrow = TagRow(self.date or time.strftime("%Y-%m-%d"))
        col.addWidget(self.tagrow)

        col.addStretch(1)
        return wrap

    def _build_week(self) -> QWidget:
        wrap = QWidget()
        col = QVBoxLayout(wrap)
        col.setContentsMargins(12, 12, 12, 12)
        col.setSpacing(10)

        head = QHBoxLayout()
        self.week_btn = QPushButton("▶  RENDER MY WEEK")
        self.week_btn.setObjectName("primary")
        self.week_btn.clicked.connect(self._render_week)
        whint = QLabel("seven days, each ~42s — the audible diary")
        whint.setObjectName("dim")
        self.week_info = QLabel("")
        self.week_info.setStyleSheet(f"color:{CYAN};font-weight:700;")
        head.addWidget(self.week_btn)
        head.addSpacing(12)
        head.addWidget(whint)
        head.addStretch(1)
        head.addWidget(self.week_info)
        col.addLayout(head)

        self.week_wave = Waveform()
        self.week_play = QPushButton("▶ play week")
        self.week_play.clicked.connect(self._play_week)
        p = QHBoxLayout()
        p.addWidget(self.week_wave, 1)
        p.addWidget(self.week_play)
        col.addLayout(p)

        grid = QGridLayout()
        grid.setSpacing(8)
        self.day_cards = []
        for i in range(7):
            c = WeekDayCard()
            self.day_cards.append(c)
            grid.addWidget(c, i // 4, i % 4)
        col.addLayout(grid)

        corr = QFrame(objectName="card")
        cv = QVBoxLayout(corr)
        cv.setContentsMargins(14, 10, 14, 10)
        cv.addWidget(QLabel("WHAT YOUR TAGS SAY (needs ≥2 tagged days)"))
        self.corr_label = QLabel("tag a few days first — e.g. 'shipped', "
                                 "'meeting day', 'good day'")
        self.corr_label.setObjectName("dim")
        self.corr_label.setWordWrap(True)
        cv.addWidget(self.corr_label)
        col.addWidget(corr)

        col.addStretch(1)
        return wrap

    # ------------------------------------------------------------ today
    def _live(self) -> bool:
        from . import features
        ev = features.load_events(self.date)
        return bool(ev) and time.time() - ev[-1]["t"] < 90

    def _refresh(self):
        s = patterns.day_summary(self.date)
        self.tagrow.date = self.date or time.strftime("%Y-%m-%d")
        live = self._live()
        self.status.setText("● recording" if live else "○ not recording")
        self.status.setStyleSheet(
            f"color:{'#3ecf8e' if live else DIM};font-size:12px;"
            f"padding:4px 10px;border:1px solid "
            f"{'#2a6b52' if live else BORDER};border-radius:999px;")
        self.record_btn.setText("stop recording" if self.ctl.recording
                                else "start recording")
        if s.get("empty"):
            return
        self.timeline.set_day(s)
        self.card_key.value.setText(f"{s['total_key']:,}")
        self._set(self.card_active, f"{s['active_minutes']} min")
        self._set(self.card_flow, f"{s['longest_flow']} min")
        self._set(self.card_flail, f"{s['counts'][patterns.FLAIL]} min")
        self._set(self.card_sw, f"{int(s['switches']):,}")
        km = s["mouse_km"]
        self._set(self.card_mouse, f"{km:.1f} km" if km >= 1
                  else f"{km*1000:.0f} m")
        total = s["n_minutes"]
        for key, (bar, val) in self.pat_rows.items():
            share = s["counts"][key] / max(total, 1)
            bar.setMaximumWidth(int(share * 220) + 2)
            val.setText(f"{s['counts'][key]} min")
        top = s["top_apps"]
        mx = top[0][1] if top else 1
        for i, (name, bar, val) in enumerate(self.app_rows):
            if i < len(top):
                app, n = top[i]
                name.setText(app[:14])
                bar.setMaximumWidth(max(int(n / mx * 160), 2))
                val.setText(f"{n}")
            else:
                name.setText("—")
                bar.setMaximumWidth(2)
                val.setText("")

    def _set(self, card: StatCard, text: str):
        card.value.setText(text)

    def _toggle_record(self):
        if self.ctl.recording:
            self.ctl.stop_recording()
        elif self._live():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "Circadia",
                "Already recording — the menu bar / tray app is watching.\n"
                "(stop it from its own menu to avoid double logs)")
        else:
            self.ctl.start_recording()
        self._refresh()

    def _render(self):
        if self._rendering:
            return
        if not (self.ctl.recording or self._live()
                or self.ctl.has_any_data()):
            self.reveal.setText("nothing to render — record first")
            self.reveal.setStyleSheet(f"color:{RED};font-weight:700;")
            return
        self._rendering = True
        self.render_btn.setText("rendering… (~30s)")
        self.reveal.setText("")
        self.ctl.render(self._render_done_sig.emit)

    def _on_render_done(self, result: dict):
        self._rendering = False
        self.render_btn.setText("▶  RENDER MY DAY")
        if result.get("error"):
            self.reveal.setText(result.get("message", "render failed"))
            self.reveal.setStyleSheet(f"color:{RED};font-weight:700;")
            return
        self.ctl.accept_render(result)
        self.pa.load_session(self.ctl._blind_path("a") or "")
        self.pb.load_session(self.ctl._blind_path("b") or "")
        self.reveal.setText("rendered — listen to A and B, then vote")
        self.reveal.setStyleSheet(f"color:{CYAN};font-weight:700;")

    def _vote(self, which: str):
        self.ctl.stop_playback()
        res = self.ctl.vote(which)
        self.reveal.setText(res)
        good = res.startswith("✔")
        self.reveal.setStyleSheet(
            f"color:{'#3ecf8e' if good else RED};font-weight:700;")

    # ------------------------------------------------------------- week
    def _refresh_week(self):
        import datetime
        self._week_summaries = []
        today = self.date or time.strftime("%Y-%m-%d")
        end = datetime.date.fromisoformat(today)
        for i in range(6, -1, -1):
            d = (end - datetime.timedelta(days=i)).isoformat()
            s = patterns.day_summary(d)
            self._week_summaries.append((d, s))
        for card, (d, s) in zip(self.day_cards, self._week_summaries):
            if s.get("empty"):
                card.day.setText(time.strftime(
                    "%a %b %d", time.strptime(d, "%Y-%m-%d")))
                card.flow.setText("—")
                card.meta.setText("no data")
                card.strip.set_strip([])
            else:
                card.set_day(d, s)
        corrs = tags.correlations()
        if corrs:
            lines = []
            for c in corrs:
                d_flow = c["flow_yes"] - c["flow_no"]
                arrow = "↑" if d_flow > 0 else "↓"
                lines.append(
                    f"“{c['tag']}” ({c['n']} days): "
                    f"{c['flow_yes']:.0f}m flow vs {c['flow_no']:.0f}m "
                    f"usual ({arrow}{abs(d_flow):.0f}m) · "
                    f"{c['key_yes']:,.0f} keys vs {c['key_no']:,.0f}")
            self.corr_label.setText("\n".join(lines))
            self.corr_label.setStyleSheet(f"color:{INK};")
        else:
            tagged = sum(1 for _, s in self._week_summaries
                         if not s.get("empty"))
            self.corr_label.setText(
                f"{tagged} day(s) recorded this week — tag days "
                f"(e.g. 'shipped', 'meeting day') and correlations "
                f"appear once you have ≥2 of a tag")

    def _render_week(self):
        if getattr(self, "_week_rendering", False):
            return
        self._week_rendering = True
        self.week_btn.setText("rendering…")
        self.week_info.setText("")

        def done(r):
            self._week_done_sig.emit(r)
        import threading

        def worker():
            try:
                r = pipeline.render_week(self.date)
            except Exception as e:
                r = {"error": "crash", "message": str(e)}
            done(r)
        threading.Thread(target=worker, daemon=True).start()

    def _on_week_done(self, result: dict):
        self._week_rendering = False
        self.week_btn.setText("▶  RENDER MY WEEK")
        if result.get("error"):
            self.week_info.setText(result.get("message", ""))
            self.week_info.setStyleSheet(f"color:{RED};")
            return
        self._week_path = os.path.join(config.RENDER_DIR, result["id"],
                                       "week.wav")
        self.week_wave.load(self._week_path)
        self.week_info.setText(
            f"{len(result['dates'])} days · "
            f"{int(len(result['dates']) * 42)}s album")

    def _play_week(self):
        if getattr(self, "_week_path", None):
            if self.week_play.text().startswith("▶"):
                self.ctl.player.play(self._week_path)
                self.week_play.setText("■ stop")
            else:
                self.ctl.stop_playback()
                self.week_play.setText("▶ play week")


def main():
    args = sys.argv[1:]
    date = args[args.index("--date") + 1] if "--date" in args else None
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    win = Dashboard(date)
    win.show()
    if "--grab" in args:                          # UI test mode
        out = args[args.index("--grab") + 1]
        if win.date:
            import json
            for sid in sorted(os.listdir(config.RENDER_DIR), reverse=True):
                mp = os.path.join(config.RENDER_DIR, sid, "meta.json")
                if os.path.exists(mp):
                    with open(mp) as fh:
                        m = json.load(fh)
                    if m.get("date") == win.date:
                        win.ctl.session = sid
                        win.pa.load_session(win.ctl._blind_path("a") or "")
                        win.pb.load_session(win.ctl._blind_path("b") or "")
                        break
        QTimer.singleShot(1800, lambda: (
            win.tabs.setCurrentIndex(0),
            win.grab().save(out),
            print(f"grabbed {out}"),
            QTimer.singleShot(400, lambda: (
                win.tabs.setCurrentIndex(1), win.grab().save(
                    out.replace(".png", "-week.png")),
                print("grabbed week tab"),
                app.quit()))))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
