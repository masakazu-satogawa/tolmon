"""院内で動く問診サーバー（標準ライブラリのみ・AIもインターネットも使わない）。"""

import json
import mimetypes
import os
import re
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from . import definitions, store

MAX_BODY = 1 * 1024 * 1024  # 回答の送信は1MBまで

PAGES = {"/": "index.html", "/doctor": "doctor.html"}

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
}


class App:
    """設定と問診定義を持つ。定義は「再読み込み」で差し替えられる（文言変更・科追加用）。"""

    def __init__(self, root, config):
        self.root = root
        self.config = config
        self.web_dir = os.path.join(root, "web")
        paths = config.get("paths", {})
        self.def_dirs = [os.path.join(root, p) for p in paths.get("definitions", ["definitions"])]
        self.data_dir = os.path.join(root, paths.get("data", "data"))
        patient = config.get("patient", {})
        self.pcode_re = re.compile(patient.get("pcode_pattern", r"^[0-9]{1,10}$"))
        self.client_config = {
            "idle_seconds": patient.get("idle_seconds", 180),
            "idle_grace_seconds": patient.get("idle_grace_seconds", 20),
            "thanks_seconds": patient.get("thanks_seconds", 10),
            "pcode_pattern": self.pcode_re.pattern,
        }
        self._lock = threading.Lock()
        self.reload()

    def reload(self):
        defs, errors = definitions.load_dir(*self.def_dirs)
        with self._lock:
            self.defs, self.def_errors = defs, errors
        for e in errors:
            print(f"[定義エラー] {e}")
        return defs, errors


class Handler(BaseHTTPRequestHandler):
    app: App = None
    server_version = "Tolmon"
    sys_version = ""

    # ---- 共通
    def log_message(self, fmt, *args):
        print(f"[{datetime.now():%H:%M:%S}] {self.address_string()} {fmt % args}")

    def _send(self, status, body, ctype):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status=200):
        self._send(status, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def _error(self, status, message):
        self._json({"ok": False, "error": message}, status)

    def _static(self, rel):
        base = os.path.realpath(self.app.web_dir)
        path = os.path.realpath(os.path.join(base, rel))
        if not path.startswith(base + os.sep) or not os.path.isfile(path):
            return self._error(404, "ページがありません")
        # Windowsのレジストリ設定に左右されないよう、よく使う型は固定する
        ext = os.path.splitext(path)[1].lower()
        ctype = CONTENT_TYPES.get(ext) or mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            self._send(200, f.read(), ctype)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            raise ValueError("送信データの大きさが正しくありません")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    # ---- GET
    def do_GET(self):
        url = urlparse(self.path)
        path = unquote(url.path)
        qs = {k: v[0] for k, v in parse_qs(url.query).items()}
        app = self.app

        if path in PAGES:
            return self._static(PAGES[path])
        if path.startswith("/static/"):
            return self._static(path[len("/static/"):])
        if path == "/api/config":
            return self._json(app.client_config)
        if path == "/api/forms":
            forms = [{"id": d["id"], "title": d["title"], "version": d.get("version"), "count": len(d["questions"])}
                     for d in app.defs.values()]
            return self._json({"forms": forms, "errors": app.def_errors})
        if path.startswith("/api/forms/"):
            d = app.defs.get(path[len("/api/forms/"):])
            if not d:
                return self._error(404, "問診票がありません")
            return self._json({k: v for k, v in d.items() if k != "_file"})
        if path == "/api/answers":
            rows = store.list_records(app.data_dir, date=qs.get("date"), pcode=qs.get("pcode"))
            return self._json({"records": rows})
        if path.startswith("/api/answers/"):
            rec = store.load_record(app.data_dir, path[len("/api/answers/"):])
            if not rec:
                return self._error(404, "記録がありません")
            return self._json(rec)
        return self._error(404, "ページがありません")

    # ---- POST
    def do_POST(self):
        path = urlparse(self.path).path
        app = self.app
        try:
            body = self._read_json() if path != "/api/reload" else {}
        except (ValueError, UnicodeDecodeError):
            return self._error(400, "送信データが読めません")

        if path == "/api/answers":
            d = app.defs.get(body.get("form_id"))
            if not d:
                return self._error(400, "問診票が見つかりません（受付でやり直してください）")
            pcode = str(body.get("pcode", "")).strip()
            if not app.pcode_re.match(pcode):
                return self._error(400, "患者IDの形が正しくありません")
            if body.get("form_hash") and body["form_hash"] != d.get("_hash"):
                return self._error(409, "問診票が更新されました。受付でやり直してください")
            meta = {"started_at": body.get("started_at"),
                    "client": {"ip": self.client_address[0], "ua": self.headers.get("User-Agent", "")[:200]}}
            try:
                rec = store.save(app.data_dir, d, pcode, body.get("answers"), meta)
            except store.AnswerError as e:
                return self._error(400, str(e))
            return self._json({"ok": True, "record_id": rec["record_id"]})
        if path == "/api/reload":
            defs, errors = app.reload()
            return self._json({"ok": not errors, "forms": list(defs), "errors": errors})
        return self._error(404, "ページがありません")


def serve(root, config):
    app = App(root, config)
    Handler.app = app
    srv = config.get("server", {})
    host, port = srv.get("host", "127.0.0.1"), int(srv.get("port", 8080))
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    shown = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
    print("トルモン 起動しました（止めるときは Ctrl+C）")
    print(f"  受付・患者画面: http://{shown}:{port}/")
    print(f"  医師画面　　　: http://{shown}:{port}/doctor")
    print(f"  問診票: {', '.join(d['title'] for d in app.defs.values()) or '（なし）'}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n停止しました")
    finally:
        httpd.server_close()
