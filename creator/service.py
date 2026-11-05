"""作る画面（/admin）からの依頼を受ける。サーバー（app/server.py）は、設定で有効なときだけここを読み込む。"""

import base64
import json
import os
import re
import threading
from datetime import datetime

from app import definitions, karte, store, yamlmini

from . import claude_api, reader

_FORM_ID = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
_last = {}                      # 直近の読み取り結果（画面を開き直しても消えないように覚えておく）
_trial = {}                     # 公開前に患者さんの画面で試す定義（覚えるだけ。保存しない）
_lock = threading.Lock()
_draft_file = None              # 直近の読み取り結果を置くファイル（use_draft_dir で決まる）


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
    with _lock:
        _last.clear()
        _last.update(result)
        _write_draft(result)
    return result


def use_draft_dir(path):
    """下書きの置き場所を決める。サーバーを起動し直しても、直前の読み取り結果を戻せるようにする。
    置くのは白紙の帳票から作った設問の下書きだけ（患者さんの回答は入らない）。"""
    global _draft_file
    _draft_file = os.path.join(path, "creator_last.json")
    try:
        with open(_draft_file, encoding="utf-8") as f:
            saved = json.load(f)
    except (OSError, ValueError):
        return
    if isinstance(saved, dict):
        with _lock:
            _last.clear()
            _last.update(saved)


def _write_draft(result):
    if not _draft_file:
        return
    try:
        os.makedirs(os.path.dirname(_draft_file), exist_ok=True)
        tmp = _draft_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
        os.replace(tmp, _draft_file)
    except OSError:
        pass                    # 覚えておけなくても、読み取り結果そのものは返す


def last():
    with _lock:
        return dict(_last)


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
