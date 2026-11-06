"""院内で動く問診サーバー（標準ライブラリのみ・AIもインターネットも使わない）。"""

import json
import mimetypes
import os
import re
import socket
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from . import body, definitions, lang, store

MAX_BODY = 1 * 1024 * 1024  # 回答の送信は1MBまで
MAX_PAPER = 24 * 1024 * 1024  # 作る画面で受け取る帳票（base64）は24MBまで

# /karte は電子カルテの【問診】アイコンから患者IDつきで開く画面（中身は医師画面と同じ）
PAGES = {"/": "index.html", "/doctor": "doctor.html", "/karte": "doctor.html", "/reception": "reception.html"}

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
}


LOCAL_ADDRESSES = ("127.0.0.1", "::1", "::ffff:127.0.0.1")


def is_local(address):
    """サーバーを動かしているPC自身からの接続か。"""
    return address in LOCAL_ADDRESSES


def lan_addresses():
    """このPCの、ネットワーク上のアドレス（タブレットから開くときに使う）。"""
    try:
        found = [a for a in socket.gethostbyname_ex(socket.gethostname())[2] if not a.startswith("127.")]
    except OSError:
        found = []
    # ふだん外へ出ていくときに使うアドレス（Wi-Fi など）を先頭にする。仮想のアダプタのアドレスが先に出ると、打ち間違える。
    # UDP の connect は行き先を決めるだけで、何も送らない
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))
            main = s.getsockname()[0]
        if main and not main.startswith("127."):
            found = [main] + [a for a in found if a != main]
    except OSError:
        pass
    return found


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
            # 実機の確認用：タブレットの画面の状態（大きさ・拡大率）を data/debug.log に書く。本番（demo.enabled が false）では動かない
            "debug": bool(config.get("demo", {}).get("enabled")),
        }
        self._lock = threading.Lock()
        store.init_db(self.data_dir)
        self.reload()
        # 作る側（Claude API を使う）は、設定で有効にしたときだけ読み込む。
        # 院内の閉域網に置くサーバーでは false のまま（creator フォルダごと無くてもよい）
        self.creator = None
        if config.get("creator", {}).get("enabled"):
            from creator import service
            service.use_draft_dir(self.data_dir)
            self.creator = service

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

    def _client(self):
        return {"ip": self.client_address[0], "ua": self.headers.get("User-Agent", "")[:200]}

    def _read_json(self, limit=MAX_BODY):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > limit:
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
        if path == "/mock-karte":
            # デモ用の模擬カルテ（電子カルテのボタンから開いて、貼り付ける流れを見せる）。本番（demo.enabled が false）では出さない
            if not app.client_config["debug"]:
                return self._error(404, "ページがありません")
            return self._static("mock_karte.html")
        if path == "/admin" or path.startswith("/api/creator/"):
            if not app.creator:
                return self._error(404, "このサーバーでは「作る画面」は使えません（設定の creator.enabled が false）")
            if not is_local(self.client_address[0]):
                # 作る画面は Claude の APIキーを使うので、ほかの端末からは開かせない
                return self._error(403, "「作る画面」は、トルモンを動かしているPCからだけ開けます")
            if path == "/admin":
                return self._static("admin.html")
            if path == "/api/creator/info":
                return self._json(app.creator.info())
            if path == "/api/creator/last":
                return self._json(app.creator.last(qs.get("form_id")))
            if path == "/api/creator/paper":
                found = app.creator.paper(qs.get("form_id", ""))
                if not found:
                    return self._error(404, "この下書きの紙は取ってありません")
                return self._send(200, found[0], found[1])
            if path == "/api/creator/drafts":
                return self._json({"drafts": app.creator.drafts()})
            if path == "/api/creator/translation":
                return self._json(app.creator.translation(qs.get("form_id", ""), app.defs))
            if path == "/api/creator/trial":
                try:
                    return self._json(app.creator.trial())
                except app.creator.ServiceError as e:
                    return self._error(404, str(e))
            return self._error(404, "ページがありません")
        if path.startswith("/static/"):
            return self._static(path[len("/static/"):])
        if path == "/api/config":
            return self._json(app.client_config)
        if path == "/api/body":
            return self._json({"regions": body.REGIONS, "views": list(body.VIEWS)})
        if path == "/api/lang":
            return self._json(lang.client_data())
        if path == "/api/forms":
            forms = [{"id": d["id"], "title": d["title"], "version": d.get("version"), "count": len(d["questions"]),
                      "langs": list(d.get("_i18n") or {})}
                     for d in app.defs.values()]
            return self._json({"forms": forms, "errors": app.def_errors})
        if path.startswith("/api/forms/"):
            d = app.defs.get(path[len("/api/forms/"):])
            if not d:
                return self._error(404, "問診票がありません")
            return self._json({k: v for k, v in d.items() if k != "_file"})
        if path == "/api/answers":
            rows = store.list_registered(app.data_dir, day=qs.get("date"), pcode=qs.get("pcode"))
            return self._json({"records": rows})
        if path == "/api/pending":
            day = qs.get("date") or datetime.now().strftime("%Y-%m-%d")
            return self._json({"records": store.list_pending(app.data_dir, day)})
        if path == "/api/access":
            return self._json({"records": store.list_access(app.data_dir, day=qs.get("date")), "actions": store.ACTIONS})
        if path.startswith("/api/answers/"):
            rec = store.load_record(app.data_dir, path[len("/api/answers/"):])
            if not rec:
                return self._error(404, "記録がありません")
            store.log_access(app.data_dir, "view", rec["record_id"], self._client(), rec.get("pcode"))
            return self._json(rec)
        return self._error(404, "ページがありません")

    # ---- POST
    def do_POST(self):
        path = urlparse(self.path).path
        app = self.app
        creating = path.startswith("/api/creator/")
        if creating and not app.creator:
            return self._error(404, "このサーバーでは「作る画面」は使えません")
        if creating and not is_local(self.client_address[0]):
            return self._error(403, "「作る画面」は、トルモンを動かしているPCからだけ開けます")
        try:
            # 帳票（PDF・画像）を受け取る作る画面だけ、大きなデータを許す
            body = self._read_json(MAX_PAPER if creating else MAX_BODY) if path != "/api/reload" else {}
        except (ValueError, UnicodeDecodeError):
            return self._error(400, "送信データが読めません")

        if creating:
            try:
                if path == "/api/creator/read":
                    return self._json(app.creator.read(body))
                if path == "/api/creator/check":
                    return self._json(app.creator.check_yaml(body))
                if path == "/api/creator/draft":
                    return self._json(app.creator.save_draft(body))
                if path == "/api/creator/dummy":
                    return self._json(app.creator.dummy_test(body))
                if path == "/api/creator/trial":
                    return self._json(app.creator.set_trial(body))
                if path == "/api/creator/trial/karte":
                    return self._json(app.creator.trial_karte(body))
                if path == "/api/creator/translate":
                    return self._json(app.creator.make_translation(body, app.defs))
                if path == "/api/creator/translation/fix":
                    return self._json(app.creator.fix_translation(body, app.defs))
                if path == "/api/creator/translation/publish":
                    res = app.creator.publish_translation(body, app.defs, app.def_dirs[0])
                    app.reload()
                    return self._json(res)
                if path == "/api/creator/save":
                    res = app.creator.save(body, app.def_dirs[0])
                    if res.get("ok"):
                        app.reload()
                    return self._json(res)
            except app.creator.ServiceError as e:
                return self._error(400, str(e))
            return self._error(404, "ページがありません")

        if path == "/api/answers":
            # 患者さんの送信：患者IDなしの「受付待ち」で保存し、受付番号を返す
            d = app.defs.get(body.get("form_id"))
            if not d:
                return self._error(400, "問診票が見つかりません（受付でやり直してください）")
            if body.get("form_hash") and body["form_hash"] != d.get("_hash"):
                return self._error(409, "問診票が更新されました。受付でやり直してください")
            meta = {"started_at": body.get("started_at"), "seconds": body.get("seconds"), "lang": body.get("lang"),
                    "client": self._client()}
            try:
                rec = store.save_pending(app.data_dir, d, body.get("answers"), meta)
            except store.AnswerError as e:
                return self._error(400, str(e))
            return self._json({"ok": True, **rec})
        if path.startswith("/api/answers/") and path.endswith("/register"):
            # 受付の操作：受付番号の回答に患者IDを結ぶ
            record_id = path[len("/api/answers/"):-len("/register")]
            pcode = str(body.get("pcode", "")).strip()
            if not app.pcode_re.match(pcode):
                return self._error(400, "患者IDの形が正しくありません")
            try:
                rec = store.register(app.data_dir, record_id, pcode)
            except store.AnswerError as e:
                return self._error(400, str(e))
            store.log_access(app.data_dir, "register", record_id, self._client(), pcode)
            return self._json({"ok": True, **rec})
        if path.startswith("/api/answers/") and path.endswith("/copied"):
            # 医師・看護師の画面で「コピー」を押した記録
            record_id = path[len("/api/answers/"):-len("/copied")]
            if not store.load_record(app.data_dir, record_id):
                return self._error(404, "記録がありません")
            store.log_access(app.data_dir, "copy", record_id, self._client())
            return self._json({"ok": True})
        if path == "/api/debug":
            # 実機の確認用。画面の大きさ・拡大率だけを受け取る（回答は受け取らない）
            if not app.client_config["debug"]:
                return self._error(404, "ページがありません")
            line = {"at": datetime.now().isoformat(timespec="seconds"), **self._client(),
                    **{str(k)[:20]: str(v)[:200] for k, v in list(body.items())[:20]}}
            with open(os.path.join(app.data_dir, "debug.log"), "a", encoding="utf-8") as f:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
            return self._json({"ok": True})
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
    print(f"  受付待ち一覧　: http://{shown}:{port}/reception")
    print(f"  医師・看護師　: http://{shown}:{port}/karte?pcode=患者ID（電子カルテの【問診】から）")
    print(f"  問診一覧　　　: http://{shown}:{port}/doctor")
    if app.creator:
        print(f"  作る画面　　　: http://{shown}:{port}/admin（Claude で白紙の問診票を読み取る。このPCからだけ開ける）")
    if host == "0.0.0.0":
        print("  ── ほかの端末（タブレット）から開くとき ──")
        found = lan_addresses()
        if not found:
            print("  　（このPCのアドレスが分かりませんでした。ipconfig で確かめてください）")
        else:
            print(f"  　タブレットのブラウザに、これを打ちます →  http://{found[0]}:{port}/")
            for a in found[1:]:
                print(f"  　（上でつながらないときだけ試す：http://{a}:{port}/）")
    print(f"  問診票: {', '.join(d['title'] for d in app.defs.values()) or '（なし）'}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n停止しました")
    finally:
        httpd.server_close()
