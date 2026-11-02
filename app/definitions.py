"""問診定義（definitions/*.yaml）の読み込みと検証。"""

import hashlib
import os

from . import yamlmini

TYPES = ("text", "single", "multi", "number", "time")
TAGS = ("主訴", "現病歴", "既往歴", "内服薬", "アレルギー", "生活歴", "その他")
CHOICE_TYPES = ("single", "multi")


class DefinitionError(ValueError):
    pass


def validate(d):
    """定義の中身を確認し、問題があれば理由をまとめて DefinitionError にする。"""
    errs = []
    if not isinstance(d, dict):
        raise DefinitionError("定義の一番外側は「キー: 値」の形にしてください")
    for k in ("id", "title", "questions"):
        if k not in d:
            errs.append(f"「{k}」がありません")
    qs = d.get("questions") or []
    if not isinstance(qs, list) or not qs:
        errs.append("questions に設問が1つもありません")
        qs = []
    seen = {}
    for n, q in enumerate(qs, start=1):
        where = f"{n}問目"
        if not isinstance(q, dict):
            errs.append(f"{where}: 設問の形になっていません")
            continue
        qid = q.get("id")
        where = f"{n}問目（{qid}）"
        if not qid or not isinstance(qid, str):
            errs.append(f"{where}: id がありません")
        elif qid in seen:
            errs.append(f"{where}: id が重複しています")
        t = q.get("type")
        if t not in TYPES:
            errs.append(f"{where}: type は {' / '.join(TYPES)} のどれかにしてください")
        if not q.get("text"):
            errs.append(f"{where}: text（患者向けの文言）がありません")
        if not q.get("karte"):
            errs.append(f"{where}: karte（カルテ向けの項目名）がありません")
        if q.get("tag", "その他") not in TAGS:
            errs.append(f"{where}: tag は {' / '.join(TAGS)} のどれかにしてください")
        opts = q.get("options")
        if t in CHOICE_TYPES:
            if not isinstance(opts, list) or not opts:
                errs.append(f"{where}: 選択肢（options）がありません")
            else:
                labels = []
                for o in opts:
                    if not isinstance(o, dict) or not o.get("label"):
                        errs.append(f"{where}: 選択肢に label がありません")
                        continue
                    labels.append(o["label"])
                if len(set(labels)) != len(labels):
                    errs.append(f"{where}: 同じ選択肢が重複しています")
        cond = q.get("show_if")
        if cond is not None:
            if not isinstance(cond, dict) or "q" not in cond or "eq" not in cond:
                errs.append(f"{where}: show_if は q と eq を書いてください")
            elif cond["q"] not in seen:
                errs.append(f"{where}: show_if の q「{cond['q']}」はこの設問より前にありません")
            else:
                ref = seen[cond["q"]]
                ref_labels = [o.get("label") for o in ref.get("options") or [] if isinstance(o, dict)]
                if ref_labels and cond["eq"] not in ref_labels:
                    errs.append(f"{where}: show_if の eq「{cond['eq']}」は {cond['q']} の選択肢にありません")
        if qid and isinstance(qid, str):
            seen[qid] = q
    if errs:
        raise DefinitionError("\n".join(errs))
    return d


def load_file(path):
    with open(path, encoding="utf-8-sig") as f:
        text = f.read()
    try:
        d = yamlmini.load(text)
    except yamlmini.YamlError as e:
        raise DefinitionError(f"{os.path.basename(path)}: {e}") from e
    try:
        validate(d)
    except DefinitionError as e:
        raise DefinitionError(f"{os.path.basename(path)}:\n{e}") from e
    d["_hash"] = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    d["_file"] = os.path.basename(path)
    return d


def load_dir(*dirs):
    """フォルダ内の定義をすべて読む。壊れた定義は読まずに errors に入れる（他の問診は止めない）。"""
    defs, errors = {}, []
    for folder in dirs:
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            if not name.endswith((".yaml", ".yml")):
                continue
            try:
                d = load_file(os.path.join(folder, name))
            except DefinitionError as e:
                errors.append(str(e))
                continue
            if d["id"] in defs:
                errors.append(f"{name}: id「{d['id']}」が他の定義と重複しています")
                continue
            defs[d["id"]] = d
    return defs, errors
