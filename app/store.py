"""回答の検証と保存（TXT＋JSON＋CSV索引）。上書きせず、途中で壊れない書き方をする。"""

import csv
import json
import os
import re
import threading
from datetime import datetime

from . import karte

INDEX_HEADER = ["record_id", "received_at", "pcode", "form_id", "form_title", "form_version", "form_hash", "txt_path"]
_lock = threading.Lock()


class AnswerError(ValueError):
    pass


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
                try:
                    num = float(str(v).replace(",", "."))
                except ValueError:
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


def _atomic_write(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def save(data_dir, defn, pcode, raw_answers, meta):
    answers = clean_answers(defn, raw_answers)
    now = datetime.now()
    when = now.strftime("%Y/%m/%d %H:%M")
    folder = os.path.join(data_dir, "answers", now.strftime("%Y"), now.strftime("%m"))
    os.makedirs(folder, exist_ok=True)

    text_karte = karte.karte_text(defn, answers, when)
    shown = karte.shown_questions(defn, answers)
    snapshot = {k: v for k, v in defn.items() if not k.startswith("_")}

    with _lock:
        base = f"{now.strftime('%Y%m%d-%H%M%S')}_{pcode}_{defn['id']}"
        n = 1
        record_id = base
        while os.path.exists(os.path.join(folder, record_id + ".json")):
            n += 1
            record_id = f"{base}-{n}"
        txt_path = os.path.join(folder, record_id + ".txt")
        json_path = os.path.join(folder, record_id + ".json")

        lines = [
            text_karte,
            "",
            "=" * 40,
            "表示した設問と回答（開示用）",
            "=" * 40,
        ]
        for i, s in enumerate(shown, start=1):
            lines.append(f"Q{i}. {s['text']}")
            lines.append(f"  → {s['answer']}")
        lines += [
            "",
            f"患者ID: {pcode}",
            f"問診票: {defn['title']}（id={defn['id']} / 版={defn.get('version', '')} / hash={defn.get('_hash', '')}）",
            f"開始: {meta.get('started_at', '')}",
            f"送信: {now.isoformat(timespec='seconds')}",
            f"記録ID: {record_id}",
        ]
        _atomic_write(txt_path, "\n".join(lines) + "\n")

        record = {
            "record_id": record_id,
            "pcode": pcode,
            "received_at": now.isoformat(timespec="seconds"),
            "started_at": meta.get("started_at"),
            "client": meta.get("client"),
            "form": {"id": defn["id"], "title": defn["title"], "version": defn.get("version"),
                     "hash": defn.get("_hash"), "file": defn.get("_file")},
            "answers": answers,
            "karte_text": text_karte,
            "shown": shown,
            "definition_snapshot": snapshot,
        }
        _atomic_write(json_path, json.dumps(record, ensure_ascii=False, indent=2))

        index = os.path.join(data_dir, "answers", "index.csv")
        new = not os.path.exists(index)
        with open(index, "a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(INDEX_HEADER)
            w.writerow([record_id, record["received_at"], pcode, defn["id"], defn["title"],
                        defn.get("version", ""), defn.get("_hash", ""),
                        os.path.relpath(txt_path, data_dir).replace("\\", "/")])
    return record


def list_records(data_dir, date=None, pcode=None):
    index = os.path.join(data_dir, "answers", "index.csv")
    if not os.path.exists(index):
        return []
    with _lock, open(index, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if date:
        rows = [r for r in rows if r["received_at"].startswith(date)]
    if pcode:
        rows = [r for r in rows if r["pcode"] == pcode]
    rows.reverse()  # 新しい順
    return rows


_RID = re.compile(r"^\d{8}-\d{6}_[0-9A-Za-z]+_[0-9A-Za-z_\-]+$")


def load_record(data_dir, record_id):
    if not _RID.match(record_id):
        return None
    path = os.path.join(data_dir, "answers", record_id[:4], record_id[4:6], record_id + ".json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)
