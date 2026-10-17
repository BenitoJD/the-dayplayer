"""Central paths and constants.

PRIVACY: all raw logs live under ~/.dayplayer, OUTSIDE any git repo.
Only rendered audio and anonymous aggregates are ever meant to leave
this machine, and only when the user explicitly shares them.
"""
import os
import time

# Where private data lives (never inside the repo)
DATA_DIR = os.path.expanduser("~/.dayplayer")
LOG_DIR = os.path.join(DATA_DIR, "logs")
RENDER_DIR = os.path.join(DATA_DIR, "renders")

# Render settings
TARGET_DURATION = 180.0        # seconds, the "~3 minute piece"
SAMPLE_RATE = 44100

# Recorder settings
MOUSE_MOVE_MIN_PX = 12         # throttle: only log moves >= this distance
WINDOW_POLL_SECONDS = 4.0      # foreground-app poll interval

# Activity model
MINUTE = 60.0
IDLE_EVENTS_PER_MIN = 6        # below this, a minute is considered "idle"
HIGH_SWITCHES_PER_MIN = 3.0    # above this, a minute is a "flail" minute


def ensure_dirs():
    for d in (LOG_DIR, RENDER_DIR):
        os.makedirs(d, exist_ok=True)


def log_path(date=None):
    """Log file for a date (YYYY-MM-DD); defaults to today."""
    date = date or time.strftime("%Y-%m-%d")
    return os.path.join(LOG_DIR, f"{date}.jsonl")


def today_log_path():
    return log_path()
