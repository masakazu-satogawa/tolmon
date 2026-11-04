"""回答の検証と保存。

流れ（A案）：
  1. 患者さんが送信 → SQLite に「受付待ち」（患者IDなし）で保存し、その日の受付番号を返す
  2. 受付が受付番号に患者IDを登録 → 開示用の TXT を書き出す
患者IDが登録されなかった回答も消さずに残す。
"""

import json
import os
import re
import sqlite3
import threading
from datetime import datetime

from . import karte

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
  record_id     TEXT PRIMARY KEY,   -- 20261104-007（日付-受付番号）
  day           TEXT NOT NULL,      -- 2026-11-04
  number        INTEGER NOT NULL,   -- その日の受付番号（1から）
  form_id       TEXT NOT NULL,
  form_title    TEXT NOT NULL,
  form_version  TEXT,
  form_hash     TEXT,
  created_at    TEXT NOT NULL,      -- 送信した時刻
  started_at    TEXT,               -- 回答を始めた時刻（端末の時計）
  pcode         TEXT,               -- 患者ID（受付で登録するまで NULL）
  registered_at TEXT,
  txt_path      TEXT,               -- 開示用TXT（data からの相対パス）
  data          TEXT NOT NULL,      -- 回答・カルテ向け文章・表示した設問・定義のスナップショット（JSON）
  UNIQUE (day, number)
);
CREATE INDEX IF NOT EXISTS idx_records_pcode_day ON records (pcode, day);
"""

LIST_COLUMNS = "record_id, day, number, form_id, form_title, created_at, pcode, registered_at"


class AnswerError(ValueError):
    pass


# ---------------------------------------------------------------- データベース

def db_path(data_dir):
    return os.path.join(data_dir, "tolmon.sqlite3")


def _connect(data_dir):
    os.makedirs(data_dir, exist_ok=True)
    con = sqlite3.connect(db_path(data_dir), timeout=10)
    con.row_factory = sqlite3.Row
    return con


def init_db(data_dir):
    with _connect(data_dir) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(SCHEMA)
    con.close()


# ---------------------------------------------------------------- 回答の検証

def clean_answers(defn, raw):
    """送られてきた回答を定義と照らし合わせ、表示された設問の正しい値だけを残す。"""
    if not isinstance(raw, dict):
        raise AnswerError("回答の形が正しくありません")
    answers = {}
    for q in defn["questions"]:
        if not karte.is_visible(q, answers):
            continue
        a = raw.get(q["id"])
        if not isinstance(a, dict):
            a = {}
        v = a.get("value")
        details = a.get("details") if isinstance(a.get("details"), dict) else {}
        t = q["type"]
        labels = [o["label"] for o in q.get("options") or []]
        if t == "single":
            if v not in (None, "") and v not in labels:
                raise AnswerError(f"「{q['text']}」の選択肢が正しくありません")
            chosen = [v] if v else []
        elif t == "multi":
            v = v if isinstance(v, list) else []
            if any(x not in labels for x in v):
                raise AnswerError(f"「{q['text']}」の選択肢が正しくありません")
            v = [x for x in labels if x in v]  # 定義の順にそろえる
            chosen = v
        elif t == "number":
            if v not in (None, ""):
                num = karte._num(v)
                if num is None:
                    raise AnswerError(f"「{q['text']}」は数字で入力してください")
                if ("min" in q and num < q["min"]) or ("max" in q and num > q["max"]):
                    raise AnswerError(f"「{q['text']}」の数字が範囲外です")
                v = str(v)
            chosen = []
        else:  # text / time
            v = str(v)[:2000] if v not in (None, "") else None
            chosen = []
        if q.get("required") and (v in (None, "") or v == []):
            raise AnswerError(f"「{q['text']}」は必ず答えてください")
        kept = {o: str(details[o])[:1000] for o in chosen if details.get(o)}
        if v not in (None, "") and v != []:
            answers[q["id"]] = {"value": v, "details": kept} if kept else {"value": v}
    return answers


# ---------------------------------------------------------------- 保存（受付待ち）

def save_pending(data_dir, defn, raw_answers, meta):
    """回答を「受付待ち」で保存し、その日の受付番号を振る。"""
    answers = clean_answers(defn, raw_answers)
    now = datetime.now()
    when = now.strftime("%Y/%m/%d %H:%M")
    day = now.strftime("%Y-%m-%d")
    data = {
        "answers": answers,
        "karte_text": karte.karte_text(defn, answers, when),
        "shown": karte.shown_questions(defn, answers),
        "client": meta.get("client"),
        "form_file": defn.get("_file"),
        "definition_snapshot": {k: v for k, v in defn.items() if not k.startswith("_")},
    }
    with _lock:
        con = _connect(data_dir)
        try:
            with con:
                con.execute("BEGIN IMMEDIATE")
                number = con.execute("SELECT COALESCE(MAX(number), 0) + 1 FROM records WHERE day = ?", (day,)).fetchone()[0]
                record_id = f"{now.strftime('%Y%m%d')}-{number:03d}"
                con.execute(
                    "INSERT INTO records (record_id, day, number, form_id, form_title, form_version, form_hash,"
                    " created_at, started_at, data) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (record_id, day, number, defn["id"], defn["title"], str(defn.get("version", "")),
                     defn.get("_hash"), now.isoformat(timespec="seconds"), meta.get("started_at"),
                     json.dumps(data, ensure_ascii=False)))
        finally:
            con.close()
    return {"record_id": record_id, "number": number}


# ---------------------------------------------------------------- 患者IDの登録

def _atomic_write(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _disclosure_text(row, data):
    lines = [data["karte_text"], "", "=" * 40, "表示した設問と回答（開示用）", "=" * 40]
    for i, s in enumerate(data["shown"], start=1):
        lines.append(f"Q{i}. {s['text']}")
        lines.append(f"  → {s['answer']}")
    lines += [
        "",
        f"患者ID: {row['pcode']}",
        f"受付番号: {row['number']}（{row['day']}）",
        f"問診票: {row['form_title']}（id={row['form_id']} / 版={row['form_version']} / hash={row['form_hash']}）",
        f"開始: {row['started_at'] or ''}",
        f"送信: {row['created_at']}",
        f"患者ID登録: {row['registered_at']}",
        f"記録ID: {row['record_id']}",
    ]
    return "\n".join(lines) + "\n"


def register(data_dir, record_id, pcode):
    """受付番号の回答に患者IDを結び、開示用TXTを書き出す。"""
    with _lock:
        con = _connect(data_dir)
        try:
            row = con.execute("SELECT * FROM records WHERE record_id = ?", (record_id,)).fetchone()
            if row is None:
                raise AnswerError("この受付番号の回答が見つかりません")
            if row["pcode"]:
                raise AnswerError(f"受付番号 {row['number']} はすでに患者ID {row['pcode']} で登録済みです")
            now = datetime.now().isoformat(timespec="seconds")
            rel = os.path.join("answers", row["day"][:4], row["day"][5:7], f"{record_id}_{pcode}_{row['form_id']}.txt")
            path = os.path.join(data_dir, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            row = dict(row, pcode=pcode, registered_at=now)
            _atomic_write(path, _disclosure_text(row, json.loads(row["data"])))
            with con:
                con.execute("UPDATE records SET pcode = ?, registered_at = ?, txt_path = ? WHERE record_id = ? AND pcode IS NULL",
                            (pcode, now, rel.replace("\\", "/"), record_id))
        finally:
            con.close()
    return {"record_id": record_id, "number": row["number"], "pcode": pcode}


# ---------------------------------------------------------------- 読み出し

def _rows(data_dir, sql, args):
    con = _connect(data_dir)
    try:
        return [dict(r) for r in con.execute(sql, args).fetchall()]
    finally:
        con.close()


def list_registered(data_dir, day=None, pcode=None):
    sql = f"SELECT {LIST_COLUMNS} FROM records WHERE pcode IS NOT NULL"
    args = []
    if day:
        sql += " AND day = ?"
        args.append(day)
    if pcode:
        sql += " AND pcode = ?"
        args.append(pcode)
    return _rows(data_dir, sql + " ORDER BY created_at DESC", args)


def list_pending(data_dir, day):
    return _rows(data_dir, f"SELECT {LIST_COLUMNS} FROM records WHERE pcode IS NULL AND day = ? ORDER BY number", (day,))


_RID = re.compile(r"^\d{8}-\d{3,}$")


def load_record(data_dir, record_id):
    if not _RID.match(record_id):
        return None
    rows = _rows(data_dir, "SELECT * FROM records WHERE record_id = ?", (record_id,))
    if not rows:
        return None
    rec = rows[0]
    rec.update(json.loads(rec.pop("data")))
    return rec
