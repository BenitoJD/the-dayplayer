"""First run: one screen that says what Circadia does, what it never does,
and asks for what it needs.

Shown once (marker in state.json), and reachable later from the menu as
"Welcome & Setup...". Opens as its own process, like the dashboard.

Run:  python3 -m dayplayer.onboarding
"""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QApplication, QCheckBox, QFrame,
                               QHBoxLayout, QLabel, QMainWindow,
                               QPushButton, QVBoxLayout, QWidget)

from . import autostart, config, maintenance
from .controller import open_accessibility_pane_once, open_input_monitoring_pane

BG, PANEL, BORDER = "#0a0a0c", "#101018", "#1e1e28"
INK, DIM = "#f5f5f7", "#8b93a7"
AMBER, GREEN, RED = "#f0b429", "#30d158", "#ff453a"
FONT = ("'SF Pro Display','SF Pro Text','Helvetica Neue','Segoe UI',"
        "'Arial',sans-serif")

QSS = f"""
QMainWindow, QWidget {{ background: {BG}; color: {INK}; font-family: {FONT}; }}
QLabel#h1 {{ font-size: 30px; font-weight: 300; }}
QLabel#tag {{ color: {DIM}; font-size: 14px; }}
QLabel#sect {{ font-size: 11px; letter-spacing: 2px; color: {DIM}; }}
QLabel#body {{ font-size: 14px; }}
QFrame#card {{ background: {PANEL}; border: 1px solid {BORDER};
  border-radius: 12px; }}
QPushButton {{ background: transparent; color: {DIM}; border: none;
  font-size: 13px; padding: 8px 12px; }}
QPushButton:hover {{ color: {INK}; }}
QPushButton#primary {{ background: {INK}; color: {BG}; font-weight: 600;
  border-radius: 999px; padding: 12px 26px; font-size: 14px; }}
QPushButton#primary:hover {{ background: #ffffff; }}
QPushButton#ghost {{ border: 1px solid {BORDER}; border-radius: 999px;
  padding: 10px 18px; color: {INK}; font-size: 13px; }}
QPushButton#ghost:hover {{ border-color: {DIM}; }}
QCheckBox {{ color: {DIM}; font-size: 13px; }}
"""


class Onboarding(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Circadia")
        self.resize(720, 660)
        self.setWindowIcon(QIcon(os.path.join(
            os.path.dirname(__file__), "..", "assets", "icon.png")))
        root = QWidget()
        self.setCentralWidget(root)
        col = QVBoxLayout(root)
        col.setContentsMargins(40, 34, 40, 30)
        col.setSpacing(16)

        head = QLabel("Circadia")
        head.setObjectName("h1")
        col.addWidget(head)
        tag = QLabel("Your workday is already a performance. This plays it "
                     "back.")
        tag.setObjectName("tag")
        col.addWidget(tag)
        col.addSpacing(6)

        col.addWidget(self._card(
            "WHAT IT RECORDS",
            "The timing of your input and nothing else.\n\n"
            "• how long you pause between keys, and how fast you type\n"
            "• how far your mouse travels, clicks, scrolling\n"
            "• which app is in front, by name\n\n"
            "That is enough to hear a day: bursts, stalls, flailing, flow.",
            AMBER))
        col.addWidget(self._card(
            "WHAT IT NEVER RECORDS",
            "• which keys you press (every letter is the same token)\n"
            "• words, passwords, window titles, URLs, file names\n"
            "• screen contents, clipboard, microphone, camera\n\n"
            "Everything stays in ~/.dayplayer on this computer. There is no "
            "server, no account, and nothing is ever uploaded.",
            GREEN))

        self.perm = QLabel("")
        self.perm.setObjectName("body")
        self.perm.setWordWrap(True)
        col.addWidget(self.perm)
        self.fix_btn = QPushButton("Open System Settings")
        self.fix_btn.setObjectName("ghost")
        self.fix_btn.clicked.connect(self._fix_permissions)
        row = QHBoxLayout()
        row.addWidget(self.fix_btn)
        row.addStretch(1)
        col.addLayout(row)

        self.login_cb = QCheckBox("Start Circadia when I log in, and record")
        self.login_cb.setChecked(autostart.is_enabled())
        col.addWidget(self.login_cb)

        col.addStretch(1)
        self.summary = QLabel(maintenance.summary_text())
        self.summary.setObjectName("sect")
        self.summary.setWordWrap(True)
        col.addWidget(self.summary)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        later = QPushButton("Not now")
        later.clicked.connect(self._later)
        self.start_btn = QPushButton("Start recording")
        self.start_btn.setObjectName("primary")
        self.start_btn.clicked.connect(self._start)
        buttons.addWidget(later)
        buttons.addWidget(self.start_btn)
        col.addLayout(buttons)

        self._refresh_permissions()

    def _card(self, title: str, body: str, accent: str) -> QFrame:
        card = QFrame(objectName="card")
        v = QVBoxLayout(card)
        v.setContentsMargins(18, 14, 18, 16)
        v.setSpacing(8)
        t = QLabel(title)
        t.setObjectName("sect")
        t.setStyleSheet(f"font-size:11px;letter-spacing:2px;color:{accent};")
        b = QLabel(body)
        b.setObjectName("body")
        b.setWordWrap(True)
        v.addWidget(t)
        v.addWidget(b)
        return card

    def _refresh_permissions(self):
        if sys.platform != "darwin":
            self.perm.setText("Ready. No permissions needed on this system.")
            self.fix_btn.hide()
            return
        from .recorder import permission_report
        rep = permission_report()
        acc, mon = rep["accessibility"], rep["input_monitoring"]
        if acc and mon is not False:
            self.perm.setText("Permissions granted. Circadia can hear your "
                              "keyboard and mouse timing.")
            self.perm.setStyleSheet(f"color:{GREEN};font-size:14px;")
            self.fix_btn.hide()
        else:
            missing = []
            if not acc:
                missing.append("Accessibility")
            if mon is False:
                missing.append("Input Monitoring")
            self.perm.setText(
                "macOS is not sharing input yet. Turn on "
                + " and ".join(missing)
                + " for Circadia. Until then it records mouse movement only.")
            self.perm.setStyleSheet(f"color:{AMBER};font-size:14px;")
            self.fix_btn.show()

    def _fix_permissions(self):
        from .recorder import permission_report
        rep = permission_report()
        if not rep["accessibility"]:
            open_accessibility_pane_once()
        else:
            open_input_monitoring_pane()

    def _start(self):
        from .recorder import spawn_recorder
        if self.login_cb.isChecked():
            autostart.enable()
        else:
            autostart.disable()
        spawn_recorder()
        maintenance.mark_onboarded()
        self.close()

    def _later(self):
        maintenance.mark_onboarded()      # do not nag on every launch
        self.close()


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    w = Onboarding()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
