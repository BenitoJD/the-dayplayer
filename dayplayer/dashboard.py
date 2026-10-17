"""Circadia — one window, one object: your day as a living ring.

Design rules (the Jobs kind):
  one hero object · one sentence, human words · one primary button
  everything else whispers or disappears

The ring: noon at top, now at the glowing dot. Quiet hours are negative
space; active minutes paint the circle in their pattern color. Live mode
makes the same ring breathe with your state.

Run:  python3 -m dayplayer.dashboard [--date ...] [--grab out.png]
"""
from __future__ import annotations

import math
import os
import sys
import time

from PySide6.QtCore import Qt, QTimer, Signal, QRectF
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPainterPath
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QPushButton,
                               QSizePolicy, QToolTip, QVBoxLayout, QWidget)

from . import config, patterns, pipeline, tags
from .controller import Controller, open_live_window
from .live import LiveEngine

# ------------------------------------------------------------------ theme
BG = "#0a0a0c"
INK = "#f5f5f7"
DIM = "#86868b"
HAIR = "#1c1c20"
GREEN = "#30d158"
UI_FONT = ("'SF Pro Display','SF Pro Text','Helvetica Neue',"
           "'Segoe UI','Arial',sans-serif")

QSS = f"""
QMainWindow, QWidget {{ background: {BG}; color: {INK};
  font-family: {UI_FONT}; }}
QLabel#sentence {{ font-size: 25px; font-weight: 300; color: {INK}; }}
QLabel#sub {{ color: {DIM}; font-size: 13px; font-weight: 400; }}
QLabel#nav {{ color: {DIM}; font-size: 13px; }}
QPushButton {{ background: transparent; color: {DIM}; border: none;
  font-size: 13px; padding: 8px 12px; }}
QPushButton:hover {{ color: {INK}; }}
QPushButton#primary {{ background: {INK}; color: {BG}; font-weight: 600;
  border-radius: 999px; padding: 12px 28px; font-size: 14px; }}
QPushButton#primary:hover {{ background: #ffffff; }}
QPushButton#round {{ border: 1px solid {HAIR}; border-radius: 999px;
  padding: 10px 22px; color: {INK}; font-size: 13px; }}
QPushButton#round:hover {{ border-color: {DIM}; }}
QPushButton#rec_on {{ color: {GREEN}; }}
QLineEdit {{ background: transparent; border: none; border-bottom: 1px
  solid {HAIR}; color: {INK}; font-size: 13px; padding: 4px 2px; }}
QFrame#line {{ color: {HAIR}; }}
"""


def _pat_color(key: str) -> QColor:
    return QColor(patterns.PATTERN_META[key]["color"])


# ------------------------------------------------------------------ ring
class DayRing(QWidget):
    """The hero: one day wrapped around a circle. Noon on top."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(380, 380)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.data, self.strip, self.start_ts = [], [], time.time()
        self.n_minutes = 1
        self.now_fraction = None          # glowing dot (today only)
        self.live_engine: LiveEngine | None = None
        self._t = 0.0
        self.setMouseTracking(True)

    def set_day(self, summary: dict, today: bool):
        self.data = summary.get("minutes", [])
        self.strip = summary.get("strip", [])
        self.start_ts = summary.get("start_ts", time.time())
        self.n_minutes = max(len(self.strip), 1)
        now_min = (time.time() - self.start_ts) / 60.0
        self.now_fraction = (now_min / self.n_minutes
                             if today and 0 <= now_min <= self.n_minutes
                             else None)
        self.update()

    # geometry helpers
    def _geo(self):
        s = min(self.width(), self.height())
        cx, cy = self.width() / 2, self.height() / 2
        r = s / 2 - 34
        return cx, cy, r

    def _minute_from_pos(self, x, y) -> int | None:
        cx, cy, r = self._geo()
        dx, dy = x - cx, y - cy
        if not (0.55 * r < math.hypot(dx, dy) < 1.25 * r):
            return None
        ang = math.degrees(math.atan2(dx, -dy))    # clockwise from top
        if ang < 0:
            ang += 360
        return int(ang / 360 * self.n_minutes)

    def mouseMoveEvent(self, e):
        i = self._minute_from_pos(e.position().x(), e.position().y())
        if i is None or not self.strip:
            QToolTip.hideText()
            return
        clock = time.strftime("%H:%M", time.localtime(
            self.start_ts + i * 60))
        pat = patterns.PATTERN_META[self.strip[i]]["label"]
        m = self.data[i] if i < len(self.data) else {}
        QToolTip.showText(e.globalPosition().toPoint(),
                          f"{clock} · {pat}"
                          + (f"\n{m.get('key_rate', 0)} keys" if m else ""),
                          self)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy, r = self._geo()
        self._t += 0.03

        # track
        pen = QPen(QColor("#17171b"), 13)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), 0, 360 * 16)

        # day segments (grouped consecutive same-pattern minutes)
        if self.strip:
            i = 0
            n = self.n_minutes
            while i < n:
                pat = self.strip[i]
                j = i
                while j < n and self.strip[j] == pat:
                    j += 1
                if pat != patterns.MIRE:            # quiet = negative space
                    a0 = (90 - (i / n) * 360) * 16
                    span = -((j - i) / n) * 360 * 16 - 16
                    pen = QPen(_pat_color(pat), 13)
                    pen.setCapStyle(Qt.FlatCap)
                    p.setPen(pen)
                    p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r),
                              int(a0), int(span))
                i = j

        # live breathing halo
        if self.live_engine is not None:
            eng = self.live_engine
            col = [0.0, 0.0, 0.0]
            for key, w in eng.weights.items():
                c = _pat_color(key)
                col[0] += c.red() * w
                col[1] += c.green() * w
                col[2] += c.blue() * w
            tot = sum(eng.weights.values()) or 1
            col = [min(255, int(c / tot)) for c in col]
            breathe = 0.5 + 0.5 * math.sin(self._t)
            halo_r = r * (1.06 + 0.05 * breathe)
            path = QPainterPath()
            path.addEllipse(QRectF(cx - halo_r, cy - halo_r,
                                   2 * halo_r, 2 * halo_r))
            pen = QPen(QColor(col[0], col[1], col[2],
                              int(90 + 60 * breathe)), 2)
            p.setPen(pen)
            p.drawPath(path)

        # the now dot
        if self.now_fraction is not None:
            ang = math.radians(self.now_fraction * 360)
            nx = cx + r * math.sin(ang)
            ny = cy - r * math.cos(ang)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(INK))
            p.drawEllipse(QRectF(nx - 4.5, ny - 4.5, 9, 9))


# -------------------------------------------------------------- sentence
def day_sentence(s: dict, live: bool, today: bool) -> list[str]:
    """One human sentence (two lines max) about a day."""
    if s.get("empty"):
        if today:
            return ["Your day hasn't spoken yet.",
                    "Press record — then just live it."]
        return ["Nothing recorded this day."]
    counts = s["counts"]
    flow_min = counts[patterns.FLOW]
    flail_min = counts[patterns.FLAIL]
    h, m = divmod(flow_min, 60)

    if today and live:
        head = "This is you, right now."
    elif flow_min >= 60:
        head = f"You found {h}h {m:02d}m of flow today."
    elif flow_min > 0:
        head = f"You found {m} minutes of flow today."
    elif flail_min > 10:
        head = "Today never settled."
    else:
        head = "A quiet day."

    tail = ""
    if s["longest_flow"] >= 8:
        # when did the best run happen?
        strip = s.get("strip", [])
        best = cur = best_start = 0
        for i, pat in enumerate(strip):
            cur = cur + 1 if pat == patterns.FLOW else 0
            if cur > best:
                best, best_start = cur, i - cur + 1
        when = time.strftime("%H:%M", time.localtime(
            s["start_ts"] + best_start * 60))
        hour = int(when[:2])
        part = ("before lunch" if hour < 12 else
                "in the afternoon" if hour < 17 else "in the evening")
        tail = f"Your deepest run was {best} minutes, {part}."
    elif flail_min > 15:
        tail = "The day kept slipping between things."
    return [head, tail]


# ---------------------------------------------------------------- window
class Dashboard(QMainWindow):
    _render_done_sig = Signal(dict)
    _week_done_sig = Signal(dict)

    def __init__(self, date: str | None = None):
        super().__init__()
        self.date = date
        self.ctl = Controller()
        self.setWindowTitle("Circadia")
        self.resize(760, 860)
        self.setWindowIcon(QIcon(os.path.join(
            os.path.dirname(__file__), "..", "assets", "icon.png")))
        self._rendering = False
        self._week_path = None
        self._selected_offset = 0                 # 0 = today
        self.live_engine = None
        self._render_done_sig.connect(self._on_render_done)
        self._week_done_sig.connect(self._on_week_done)
        self._build()
        self._refresh()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh)
        self.timer.start(4000)

    # -------------------------------------------------------------- build
    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        col = QVBoxLayout(root)
        col.setContentsMargins(36, 24, 36, 28)
        col.setSpacing(0)

        # top bar: rec control · date · live
        top = QHBoxLayout()
        self.rec_btn = QPushButton("○  record")
        self.rec_btn.clicked.connect(self._toggle_record)
        top.addWidget(self.rec_btn)
        top.addStretch(1)
        self.title = QLabel("Today")
        self.title.setObjectName("nav")
        top.addWidget(self.title)
        self.prev_btn = QPushButton("‹")
        self.prev_btn.setFixedWidth(30)
        self.prev_btn.clicked.connect(lambda: self._shift_day(1))
        self.next_btn = QPushButton("›")
        self.next_btn.setFixedWidth(30)
        self.next_btn.clicked.connect(lambda: self._shift_day(-1))
        top.addWidget(self.prev_btn)
        top.addWidget(self.next_btn)
        top.addStretch(1)
        self.live_btn = QPushButton("◉  listen live")
        self.live_btn.clicked.connect(self._toggle_live)
        top.addWidget(self.live_btn)
        col.addLayout(top)
        col.addSpacing(18)

        # hero ring
        self.ring = DayRing()
        col.addWidget(self.ring, 1)
        col.addSpacing(22)

        # sentence
        self.line1 = QLabel("")
        self.line1.setObjectName("sentence")
        self.line1.setAlignment(Qt.AlignCenter)
        self.line1.setWordWrap(True)
        self.line2 = QLabel("")
        self.line2.setObjectName("sub")
        self.line2.setAlignment(Qt.AlignCenter)
        self.line2.setWordWrap(True)
        col.addWidget(self.line1)
        col.addWidget(self.line2)
        col.addSpacing(26)

        # actions
        acts = QHBoxLayout()
        acts.setSpacing(10)
        acts.addStretch(1)
        self.play_btn = QPushButton("▸  Play My Day")
        self.play_btn.setObjectName("primary")
        self.play_btn.clicked.connect(self._render)
        acts.addWidget(self.play_btn)
        self.week_btn = QPushButton("Play My Week")
        self.week_btn.setObjectName("round")
        self.week_btn.clicked.connect(self._render_week)
        acts.addWidget(self.week_btn)
        acts.addStretch(1)
        col.addLayout(acts)

        # blind test (appears after render)
        self.blind = QWidget()
        bv = QVBoxLayout(self.blind)
        bv.setContentsMargins(0, 14, 0, 0)
        bv.setSpacing(10)
        q = QLabel("Two versions. One is you.")
        q.setObjectName("sub")
        q.setAlignment(Qt.AlignCenter)
        bv.addWidget(q)
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addStretch(1)
        self.ba = QPushButton("Play A")
        self.bb = QPushButton("Play B")
        for b in (self.ba, self.bb):
            b.setObjectName("round")
            row.addWidget(b)
        self.va = QPushButton("A is me")
        self.vb = QPushButton("B is me")
        for b in (self.va, self.vb):
            b.setObjectName("round")
            row.addWidget(b)
        row.addStretch(1)
        bv.addLayout(row)
        self.blind_result = QLabel("")
        self.blind_result.setObjectName("sub")
        self.blind_result.setAlignment(Qt.AlignCenter)
        bv.addWidget(self.blind_result)
        self.blind.hide()
        col.addWidget(self.blind)

        col.addStretch(1)

        # week dots + tags whisper at the bottom
        self.dots = QHBoxLayout()
        self.dots.setSpacing(10)
        self.dots.setAlignment(Qt.AlignCenter)
        col.addLayout(self.dots)
        col.addSpacing(14)
        tag_row = QHBoxLayout()
        tag_row.setAlignment(Qt.AlignCenter)
        tag_row.setSpacing(8)
        self.tag_input = QLineEdit()
        self.tag_input.setPlaceholderText("how was today?  shipped…")
        self.tag_input.setFixedWidth(200)
        self.tag_input.returnPressed.connect(self._add_tag)
        tag_row.addWidget(self.tag_input)
        self.tag_chips = QHBoxLayout()
        self.tag_chips.setSpacing(6)
        tag_row.addLayout(self.tag_chips)
        col.addLayout(tag_row)

        self.ba.clicked.connect(lambda: self._play_ab("a"))
        self.bb.clicked.connect(lambda: self._play_ab("b"))
        self.va.clicked.connect(lambda: self._vote("a"))
        self.vb.clicked.connect(lambda: self._vote("b"))

    # ------------------------------------------------------------ refresh
    def _day_offset(self) -> str:
        import datetime
        base = self.date or time.strftime("%Y-%m-%d")
        d = (datetime.date.fromisoformat(base)
             - datetime.timedelta(days=self._selected_offset))
        return d.isoformat()

    def _is_today(self) -> bool:
        return self._selected_offset == 0

    def _refresh(self):
        d = self._day_offset()
        s = patterns.day_summary(d)
        today = self._is_today()
        live = self._live()
        self.ring.set_day(s, today)

        # rec control
        self.rec_btn.setText("●  recording" if live else "○  record")
        self.rec_btn.setObjectName("rec_on" if live else "")
        self.rec_btn.style().unpolish(self.rec_btn)
        self.rec_btn.style().polish(self.rec_btn)

        # title
        if today:
            self.title.setText("Today")
        else:
            self.title.setText(time.strftime(
                "%A, %b %d", time.strptime(d, "%Y-%m-%d")))
        self.next_btn.setVisible(not today)

        # sentence
        if self.live_engine and self.live_engine.running:
            meta = patterns.PATTERN_META[self.live_engine.state]
            self.line1.setText(meta["label"].upper() + ".")
            self.line1.setStyleSheet(
                f"font-size:25px;font-weight:300;color:{meta['color']};")
            self.line2.setText("listening — you're hearing yourself work")
        else:
            l1, l2 = day_sentence(s, live, today)
            self.line1.setText(l1)
            self.line1.setStyleSheet("")
            self.line2.setText(l2)

        # week dots
        while self.dots.count():
            it = self.dots.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        import datetime
        base = datetime.date.fromisoformat(
            self.date or time.strftime("%Y-%m-%d"))
        for off in range(6, -1, -1):
            dd = (base - datetime.timedelta(days=off)).isoformat()
            ss = patterns.day_summary(dd)
            if ss.get("empty"):
                c = QColor("#26262c")
            else:
                c = _pat_color(max(ss["counts"],
                                   key=ss["counts"].get))
            b = QPushButton()
            b.setFixedSize(12, 12)
            b.setStyleSheet(f"background:{c.name()};border-radius:6px;"
                            f"border:none;")
            if off == self._selected_offset:
                b.setStyleSheet(f"background:{c.name()};border-radius:6px;"
                                f"border:2px solid {INK};")
            off_final = off
            b.clicked.connect(lambda _=False, o=off_final:
                              self._pick_day(o))
            self.dots.addWidget(b)

        self._refresh_tags(d)
        self.week_btn.setVisible(sum(
            1 for i in range(7)
            if not patterns.day_summary(
                (base - datetime.timedelta(days=i)).isoformat()
            ).get("empty")) >= 2)

    def _refresh_tags(self, d: str):
        while self.tag_chips.count():
            it = self.tag_chips.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for t in tags.get_tags(d):
            chip = QPushButton(f"{t} ✕")
            chip.setToolTip("remove tag")
            chip.clicked.connect(lambda _=False, tt=t:
                                 self._remove_tag(tt))
            self.tag_chips.addWidget(chip)

    def _add_tag(self):
        t = self.tag_input.text().strip()
        if t:
            tags.set_tags(self._day_offset(),
                          tags.get_tags(self._day_offset()) + [t])
            self.tag_input.clear()
            self._refresh_tags(self._day_offset())

    def _remove_tag(self, t: str):
        tags.set_tags(self._day_offset(),
                      [x for x in tags.get_tags(self._day_offset())
                       if x != t])
        self._refresh_tags(self._day_offset())

    # ------------------------------------------------------------ actions
    def _pick_day(self, offset: int):
        self._selected_offset = offset
        self.blind.hide()
        self._refresh()

    def _shift_day(self, delta: int):
        self._selected_offset = max(0, self._selected_offset + delta)
        self.blind.hide()
        self._refresh()

    def _live(self) -> bool:
        from . import features
        ev = features.load_events(self._day_offset())
        return bool(ev) and time.time() - ev[-1]["t"] < 90

    def _toggle_record(self):
        if self.ctl.recording:
            self.ctl.stop_recording()
        elif self._live():
            pass                                # someone else records
        else:
            self.ctl.start_recording()
        self._refresh()

    def _toggle_live(self):
        if self.live_engine and self.live_engine.running:
            self.live_engine.stop()
            self.live_engine = None
            self.ring.live_engine = None
            self.live_btn.setText("◉  listen live")
            self._refresh()
            return
        self.live_engine = LiveEngine()
        self.live_engine.start()
        self.ring.live_engine = self.live_engine
        self.live_btn.setText("■  stop")
        if not self.live_engine.audio_on:
            self.line2.setText("(no audio device found)")

    def _render(self):
        if self._rendering:
            return
        if not (self.ctl.recording or self._live()
                or self.ctl.has_any_data()):
            self.line2.setText("record something first — then play it back")
            return
        self._rendering = True
        self.play_btn.setText("composing…")
        self.ctl.render(self._render_done_sig.emit)

    def _on_render_done(self, result: dict):
        self._rendering = False
        self.play_btn.setText("▸  Play My Day")
        if result.get("error"):
            self.line2.setText(result.get("message", "render failed"))
            return
        self.ctl.accept_render(result)
        self.blind_result.setText("")
        self.blind.show()
        self._play_ab("a")                        # start immediately

    def _play_ab(self, which: str):
        self.ctl.play(which)
        self.blind_result.setText("")

    def _vote(self, which: str):
        self.ctl.stop_playback()
        res = self.ctl.vote(which)
        good = res.startswith("✔")
        self.blind_result.setText(res)
        self.blind_result.setStyleSheet(
            f"color:{'#30d158' if good else '#ff453a'};font-size:13px;")

    def _render_week(self):
        if getattr(self, "_week_rendering", False):
            return
        self._week_rendering = True
        self.week_btn.setText("composing…")

        def done(r):
            self._week_done_sig.emit(r)
        import threading

        def worker():
            try:
                r = pipeline.render_week()
            except Exception as e:
                r = {"error": "crash", "message": str(e)}
            done(r)
        threading.Thread(target=worker, daemon=True).start()

    def _on_week_done(self, result: dict):
        self._week_rendering = False
        self.week_btn.setText("Play My Week")
        if result.get("error"):
            self.line2.setText(result.get("message", ""))
            return
        self._week_path = os.path.join(config.RENDER_DIR, result["id"],
                                       "week.wav")
        self.ctl.player.play(self._week_path)
        self.line2.setText(f"playing your week — {len(result['dates'])} "
                           f"days, {len(result['dates']) * 42} seconds")

    def closeEvent(self, e):
        if self.live_engine:
            self.live_engine.stop()
        self.ctl.stop_playback()
        self.ctl.stop_recording()
        super().closeEvent(e)


def main():
    args = sys.argv[1:]
    date = args[args.index("--date") + 1] if "--date" in args else None
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    f = QFont()
    f.setWeight(QFont.Light)
    app.setFont(f)
    win = Dashboard(date)
    win.show()
    if "--grab" in args:
        out = args[args.index("--grab") + 1]
        if win.date:
            import json
            for sid in sorted(os.listdir(config.RENDER_DIR),
                              reverse=True):
                mp = os.path.join(config.RENDER_DIR, sid, "meta.json")
                if os.path.exists(mp):
                    with open(mp) as fh:
                        m = json.load(fh)
                    if m.get("date") == win.date:
                        win.ctl.session = sid
                        win.blind.show()
                        break
        QTimer.singleShot(1800, lambda: (
            win.grab().save(out), print(f"grabbed {out}"), app.quit()))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
