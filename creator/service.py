"""作る画面（/admin）からの依頼を受ける。サーバー（app/server.py）は、設定で有効なときだけここを読み込む。"""

import base64
import json
import os
import re
import threading
from datetime import datetime

from app import definitions, karte, store, yamlmini

from . import claude_api, dummy, reader

_FORM_ID = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
_drafts = {}                    # 読み取った下書き。問診ID → 結果（画面を開き直しても、起動し直しても消えない）
_trial = {}                     # 公開前に患者さんの画面で試す定義（覚えるだけ。保存しない）
_lock = threading.Lock()
_draft_dir = None               # 下書きを置くフォルダ（use_draft_dir で決まる）


class ServiceError(ValueError):
    pass


def read(body, model=claude_api.DEFAULT_MODEL):
    """帳票（base64）を読み取って下書きを返す。1〜2分かかる。"""
    form_id = str(body.get("form_id", "")).strip()
    if not _FORM_ID.match(form_id):
        raise ServiceError("問診IDは、半角の英小文字で始まる英数字と _ で入力してください（例：naika）")
    name = str(body.get("name", ""))
    media = reader.MEDIA.get(os.path.splitext(name)[1].lower())
    if not media:
        raise ServiceError("PDF・PNG・JPEG のファイルを選んでください")
    try:
        data = base64.b64decode(body.get("data", ""), validate=True)
    except ValueError as e:
        raise ServiceError("ファイルを読み込めませんでした") from e
    if not data:
        raise ServiceError("ファイルが空です")
    try:
        result = reader.make_draft(data, media, form_id, name, model=model, check=body.get("check", True))
    except claude_api.ClaudeError as e:
        raise ServiceError(str(e)) from e
    result["form_id"] = form_id
    result["source_name"] = name
    if _save_paper(form_id, data):
        result["paper"] = {"media": media}      # 読み取った紙も取っておく（下書きを開いたとき、横に並べて見られるように）
    result["saved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _lock:
        _drafts[form_id] = result
        _write_draft(result)
    return result


def use_draft_dir(path):
    """下書きの置き場所を決めて、置いてある下書きを読み込む（問診票ごとに1ファイル）。
    置くのは白紙の帳票から作った設問の下書きだけ（患者さんの回答は入らない）。"""
    global _draft_dir
    _draft_dir = os.path.join(path, "creator_drafts")
    found = {}
    names = sorted(os.listdir(_draft_dir)) if os.path.isdir(_draft_dir) else []
    files = [os.path.join(_draft_dir, n) for n in names if n.endswith(".json")]
    old = os.path.join(path, "creator_last.json")       # 以前の置き方（1件だけ）。あれば引き継ぐ
    for f in files + [old]:
        try:
            with open(f, encoding="utf-8") as fh:
                saved = json.load(fh)
        except (OSError, ValueError):
            continue                                    # 壊れた下書きは読まない（起動は止めない）
        if isinstance(saved, dict) and _FORM_ID.match(str(saved.get("form_id", ""))):
            if not saved.get("saved_at"):               # 日時のない古い下書きは、ファイルの日時を使う
                saved["saved_at"] = datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M:%S")
            found.setdefault(saved["form_id"], saved)
    with _lock:
        _drafts.clear()
        _drafts.update(found)
        if os.path.exists(old) and all(_write_draft(d) for d in found.values()):
            os.remove(old)


def _write_draft(result):
    if not _draft_dir:
        return True
    try:
        os.makedirs(_draft_dir, exist_ok=True)
        path = os.path.join(_draft_dir, result["form_id"] + ".json")
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
        os.replace(path + ".tmp", path)
        return True
    except OSError:
        return False            # 置けなくても、読み取り結果そのものは返す


def save_draft(body):
    """人が直した YAML を、下書きに残す（公開はしない）。"""
    form_id = str(body.get("form_id", ""))
    res = check_yaml(body)
    if not res["ok"]:
        raise ServiceError("直してから保存してください：\n" + "\n".join(res["problems"]))
    with _lock:
        d = _drafts.get(form_id)
        if d is None:
            raise ServiceError("この問診IDの下書きがありません")
        d["yaml"] = str(body["yaml"])
        d["definition"] = res["definition"]
        d["problems"] = []
        for key in ("added", "issues"):         # 足した選択肢の印・見直しの指摘を、直した内容に合わせて入れ替える
            if key in body:
                d[key] = body[key]
        d["edited_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _write_draft(d)
    return {"ok": True}


def _paper_path(form_id):
    return os.path.join(_draft_dir, form_id + ".paper") if _draft_dir and _FORM_ID.match(str(form_id)) else None


def _save_paper(form_id, data):
    path = _paper_path(form_id)
    if not path:
        return False
    try:
        os.makedirs(_draft_dir, exist_ok=True)
        with open(path + ".tmp", "wb") as f:
            f.write(data)
        os.replace(path + ".tmp", path)
        return True
    except OSError:
        return False


def paper(form_id):
    """下書きと一緒に取ってある紙（PDF・画像）。戻り値は (中身, 種類)。なければ None。"""
    with _lock:
        d = _drafts.get(str(form_id)) or {}
    path = _paper_path(form_id)
    if not d.get("paper") or not path or not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return f.read(), d["paper"]["media"]


def drafts():
    """読み取った下書きの一覧（新しい順）。"""
    with _lock:
        rows = [{"form_id": k, "title": (d.get("definition") or {}).get("title", ""),
                 "count": len((d.get("definition") or {}).get("questions", [])),
                 "source_name": d.get("source_name", ""), "saved_at": d.get("saved_at", "")}
                for k, d in _drafts.items()]
    return sorted(rows, key=lambda r: r["saved_at"], reverse=True)


def last(form_id=None):
    """下書きを1つ返す。問診IDがなければ、いちばん新しいもの。"""
    with _lock:
        if form_id:
            return dict(_drafts.get(form_id) or {})
        newest = max(_drafts.values(), key=lambda d: d.get("saved_at", ""), default={})
        return dict(newest)


def check_yaml(body):
    """人が直した YAML を確かめる（保存はしない）。"""
    text = str(body.get("yaml", ""))
    try:
        defn = yamlmini.load(text)
    except yamlmini.YamlError as e:
        return {"ok": False, "problems": [f"YAMLの書き方: {e}"], "definition": None}
    if not isinstance(defn, dict):
        return {"ok": False, "problems": ["YAMLの一番外側は「キー: 値」の形にしてください"], "definition": None}
    probs = reader.problems(defn)
    return {"ok": not probs, "problems": probs, "definition": defn}


def set_trial(body):
    """公開する前に、患者さんの画面で試すための定義を覚える（保存も公開もしない）。"""
    res = check_yaml(body)
    if not res["ok"]:
        raise ServiceError("直してから試してください：\n" + "\n".join(res["problems"]))
    with _lock:
        _trial.clear()
        _trial.update(res["definition"])
    return {"ok": True, "title": res["definition"].get("title", "")}


def trial():
    with _lock:
        if not _trial:
            raise ServiceError("お試しの問診票がありません。作る画面で「患者さんの画面で試す」を押してください")
        return dict(_trial)


def trial_karte(body):
    """お試しの回答が、カルテにどう出るかを返す。回答はどこにも保存しない。"""
    defn = trial()
    try:
        answers = store.clean_answers(defn, body.get("answers"))
    except store.AnswerError as e:
        raise ServiceError(str(e)) from e
    return {"karte": karte.karte_text(defn, answers, datetime.now().strftime("%Y/%m/%d %H:%M")),
            "shown": karte.shown_questions(defn, answers)}


def dummy_test(body):
    """架空の患者（ダミー）を Claude に作らせて、問診を通しで確かめる。1分ほどかかる。"""
    res = check_yaml(body)
    if not res["ok"]:
        raise ServiceError("直してから試してください：" + " ／ ".join(res["problems"]))
    try:
        result = dummy.make(res["definition"], body.get("count", 5))
    except claude_api.ClaudeError as e:
        raise ServiceError(str(e)) from e
    result["tested_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _lock:                                   # 下書きに残す（画面を開き直しても見られるように）
        d = _drafts.get(str(body.get("form_id", "")))
        if d is not None:
            d["dummy"] = result
            _write_draft(d)
    return result


def save(body, def_dir):
    """確定した YAML を definitions/ に保存する（問診サーバーが読む場所）。"""
    text = str(body.get("yaml", ""))
    res = check_yaml({"yaml": text})
    if not res["ok"]:
        raise ServiceError("直してから保存してください：\n" + "\n".join(res["problems"]))
    form_id = str(res["definition"].get("id", ""))
    if not _FORM_ID.match(form_id):
        raise ServiceError("id は半角の英小文字で始まる英数字と _ にしてください")
    path = os.path.join(def_dir, form_id + ".yaml")
    if os.path.exists(path) and not body.get("overwrite"):
        return {"ok": False, "exists": True, "file": os.path.basename(path)}
    os.makedirs(def_dir, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text if text.endswith("\n") else text + "\n")
    os.replace(tmp, path)
    return {"ok": True, "file": os.path.basename(path), "title": res["definition"].get("title", "")}


def info():
    """作る画面に出す情報（使うモデル、病院のルール）。"""
    try:
        claude_api.api_key()
        key = True
    except claude_api.ClaudeError:
        key = False
    return {"model": claude_api.DEFAULT_MODEL, "has_key": key, "rules": reader.hospital_rules(),
            "tags": list(definitions.TAGS)}
