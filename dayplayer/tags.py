"""Day outcome tags — user-written labels like 'shipped', 'meeting day',
'good day'. Stored locally in ~/.dayplayer/tags.json. Correlations with
patterns are *descriptive*, never scores (see PRINCIPLES.md)."""
from __future__ import annotations

import json
import os
import time

from . import config, patterns

TAGS_FILE = os.path.join(config.DATA_DIR, "tags.json")


def _load() -> dict:
    try:
        with open(TAGS_FILE) as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data: dict):
    config.ensure_dirs()
    with open(TAGS_FILE, "w") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)


def set_tags(date: str, tags: list[str]):
    data = _load()
    if tags:
        data[date] = sorted(set(t.strip() for t in tags if t.strip()))
    else:
        data.pop(date, None)
    _save(data)


def get_tags(date: str) -> list[str]:
    return _load().get(date, [])


def all_tags() -> dict:
    return _load()


def correlations() -> list[dict]:
    """For each tag with >=2 tagged days: average Flow minutes and typing
    events on tagged days vs the rest. Descriptive only."""
    tagged = all_tags()
    if not tagged:
        return []

    # gather every recorded day's summary once
    import glob
    import re
    days = {}
    for path in glob.glob(os.path.join(config.LOG_DIR, "*.jsonl")):
        m = re.match(r"(\d{4}-\d{2}-\d{2})\.jsonl$", os.path.basename(path))
        if m and not m.group(1).startswith("2099-"):   # skip synthetic data
            s = patterns.day_summary(m.group(1))
            if not s.get("empty"):
                days[m.group(1)] = s

    out = []
    tags_seen = {t for ts in tagged.values() for t in ts}
    for tag in sorted(tags_seen):
        yes = [d for d, ts in tagged.items()
               if tag in ts and d in days]
        no = [d for d in days if d not in yes]
        if len(yes) < 2 or not no:
            continue
        flow = lambda ds: sum(days[d]["counts"][patterns.FLOW]
                              for d in ds) / len(ds)
        keys = lambda ds: sum(days[d]["total_key"] for d in ds) / len(ds)
        out.append({
            "tag": tag,
            "n": len(yes),
            "flow_yes": flow(yes), "flow_no": flow(no),
            "key_yes": keys(yes), "key_no": keys(no),
        })
    return out
