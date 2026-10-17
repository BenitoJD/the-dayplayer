"""Local web UI + API for The Dayplayer.  http://127.0.0.1:7331

Endpoints:
  GET  /                    dashboard
  GET  /api/status          recorder liveness + today stats
  GET  /api/features        per-minute features for the timeline
  POST /api/render          render real+shuffled, returns blind A/B pair
  POST /api/vote            cast a vote, get the answer
  GET  /audio/<id>/<f>.wav  rendered audio
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config, features, pipeline

PORT = 7331
WEB_DIR = os.path.join(os.path.dirname(__file__), "web")
SAFE = re.compile(r"^[\w.-]+$")

_render_lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):                          # quiet
        pass

    # ------------------------------------------------------------ helpers
    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, ctype):
        try:
            with open(path, "rb") as fh:
                body = fh.read()
        except FileNotFoundError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # -------------------------------------------------------------- GET
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self._file(os.path.join(WEB_DIR, "index.html"),
                              "text/html; charset=utf-8")
        if self.path == "/api/status":
            return self._json(self.status())
        if self.path.startswith("/api/features"):
            date = None
            if "date=" in self.path:
                date = self.path.split("date=")[1].split("&")[0]
            data = features.extract(date)
            return self._json(data)
        m = re.match(r"^/audio/([\w.-]+)/([\w.-]+\.wav)$", self.path)
        if m:
            sid, fname = m.groups()
            if not SAFE.match(sid) or not SAFE.match(fname):
                return self.send_error(400)
            # blind names: a.wav/b.wav map to real/shuffled server-side,
            # so the browser never learns which is which
            meta = pipeline.load_session(sid)
            if meta is None:
                return self.send_error(404)
            mapping = {"a.wav": ("real.wav" if meta["real_label"] == "a"
                                 else "shuffled.wav"),
                       "b.wav": ("shuffled.wav" if meta["real_label"] == "a"
                                 else "real.wav")}
            if fname not in mapping:
                return self.send_error(404)
            p = os.path.join(config.RENDER_DIR, sid, mapping[fname])
            if not os.path.abspath(p).startswith(os.path.abspath(config.RENDER_DIR)):
                return self.send_error(400)
            return self._file(p, "audio/wav")
        self.send_error(404)

    # ------------------------------------------------------------- POST
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "bad_json"}, 400)

        if self.path == "/api/render":
            if not _render_lock.acquire(blocking=False):
                return self._json({"error": "busy",
                                   "message": "Render already running."})
            try:
                result = pipeline.render_day(payload.get("date"))
                if isinstance(result, dict):
                    result.pop("real_label", None)   # keep the test blind
                return self._json(result)
            finally:
                _render_lock.release()

        if self.path == "/api/vote":
            sid = str(payload.get("id", ""))
            choice = str(payload.get("choice", ""))
            if not SAFE.match(sid) or choice not in ("a", "b"):
                return self._json({"error": "bad_request"}, 400)
            meta = pipeline.load_session(sid)
            if not meta:
                return self._json({"error": "not_found"}, 404)
            correct = choice == meta["real_label"]
            return self._json({
                "correct": correct,
                "real_label": meta["real_label"],
                "message": ("Correct, that was your real day."
                            if correct else
                            "Wrong, the real one was the other player."),
            })
        self.send_error(404)

    # ------------------------------------------------------------- status
    @staticmethod
    def status():
        events = features.load_events()
        input_ev = [e for e in events if e.get("type") in features.INPUT_TYPES
                    or e.get("type") == "win"]
        now = time.time()
        fresh = any(now - e["t"] < 90 for e in input_ev[-50:]) if input_ev else False
        apps = sorted({e["app"] for e in input_ev if e.get("app")})
        return {
            "date": time.strftime("%Y-%m-%d"),
            "recording_live": fresh,
            "events_today": len(input_ev),
            "last_event_age": round(now - input_ev[-1]["t"], 1) if input_ev else None,
            "apps": apps[:12],
            "log_file": config.log_path(),
        }


def main():
    config.ensure_dirs()
    url = f"http://127.0.0.1:{PORT}"
    print(f"Dayplayer UI → {url}   (Ctrl-C to stop)")
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
