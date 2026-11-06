"""問診定義（definitions/*.yaml）の読み込みと検証。"""

import hashlib
import json
import os

from . import body, lang, yamlmini

TYPES = ("text", "single", "multi", "number", "time", "body")
TAGS = ("基本情報", "主訴", "現病歴", "既往歴", "内服薬", "アレルギー", "生活歴", "その他")
COND_OPS = ("eq", "ne", "lt", "gte")
CHOICE_TYPES = ("single", "multi")


class DefinitionError(ValueError):
    pass


def _check_cond(cond, seen):
    """show_if の書き方を確認する。参照先はこの設問より前にあること。"""
    for group in ("all", "any"):      # all = すべて満たすとき、any = どれか1つでも満たすとき
        if isinstance(cond, dict) and group in cond:
            if not isinstance(cond[group], list) or not cond[group]:
                return [f"show_if の {group} には条件を1つ以上並べてください"]
            out = []
            for c in cond[group]:
                out.extend(_check_cond(c, seen))
            return out
    ops = [k for k in COND_OPS if isinstance(cond, dict) and k in cond]
    if not isinstance(cond, dict) or "q" not in cond or len(ops) != 1:
        return ["show_if は q と、eq / ne / lt / gte のどれか1つを書いてください"]
    if cond["q"] not in seen:
        return [f"show_if の q「{cond['q']}」はこの設問より前にありません"]
    ref = seen[cond["q"]]
    op = ops[0]
    if op in ("eq", "ne"):
        labels = [o.get("label") for o in ref.get("options") or [] if isinstance(o, dict)]
        if labels and cond[op] not in labels:
            return [f"show_if の {op}「{cond[op]}」は {cond['q']} の選択肢にありません"]
    elif ref.get("type") != "number" or not isinstance(cond[op], (int, float)):
        return [f"show_if の {op} は数値の設問に対して数字で書いてください"]
    return []


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
                    if "alert" in o and not isinstance(o["alert"], bool):
                        errs.append(f"{where}: 選択肢の alert は true か false で書いてください")
                if len(set(labels)) != len(labels):
                    errs.append(f"{where}: 同じ選択肢が重複しています")
        if "alert" in q and (not isinstance(q["alert"], bool) or t not in CHOICE_TYPES):
            errs.append(f"{where}: alert は選ぶ設問（single / multi）に true か false で書いてください")
        if t == "body" and q.get("views") is not None:
            views = q["views"]
            if not isinstance(views, list) or not views or any(v not in body.VIEWS for v in views):
                errs.append(f"{where}: views は {' / '.join(body.VIEWS)} の中から並べてください")
        cond = q.get("show_if")
        if cond is not None:
            errs.extend(f"{where}: {e}" for e in _check_cond(cond, seen))
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


# ---------------------------------------------------------------- 外国語の画面（設問と選択肢の訳）

def i18n_key(d):
    """患者さんに見せる言葉（設問文・ヒント・単位・選択肢・記入欄の説明）だけから作る合言葉。
    訳を作ったあとで問診票の言葉が変わったら、古い訳を出さないために使う。"""
    seen = [d.get("title", "")]
    for q in d.get("questions", []):
        seen.append([q["id"], q.get("text", ""), q.get("hint", ""), q.get("unit", ""),
                     [[o["label"], o.get("detail", "")] for o in q.get("options") or []]])
    return hashlib.sha256(json.dumps(seen, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


def check_i18n(d, tr):
    """訳（definitions/i18n/*.yaml の中身）を問診票と突き合わせ、画面で使う形にして返す。
    欠けがあれば DefinitionError（訳が欠けた画面は出さない）。"""
    if not isinstance(tr, dict) or not isinstance(tr.get("questions"), list):
        raise DefinitionError("訳の形が正しくありません")
    if tr.get("key") != i18n_key(d):
        raise DefinitionError("問診票の言葉が変わったので、この訳は使えません（作る画面で訳を作り直してください）")
    by_id = {q.get("id"): q for q in tr["questions"] if isinstance(q, dict)}
    errs = []
    out = {"title": str(tr.get("title") or d["title"]), "q": {}}
    for q in d["questions"]:
        t = by_id.get(q["id"]) or {}
        item = {"text": str(t.get("text") or "")}
        if not item["text"]:
            errs.append(f"{q['id']}: 設問文の訳がありません")
        for k in ("hint", "unit"):
            if q.get(k):
                item[k] = str(t.get(k) or "")
                if not item[k] and k == "hint":
                    errs.append(f"{q['id']}: ヒントの訳がありません")
        if q.get("options"):
            opts = {o.get("label"): o for o in t.get("options") or [] if isinstance(o, dict)}
            item["o"] = {}
            for o in q["options"]:
                x = opts.get(o["label"]) or {}
                one = {"t": str(x.get("text") or "")}
                if not one["t"]:
                    errs.append(f"{q['id']}: 選択肢「{o['label']}」の訳がありません")
                if o.get("detail"):
                    one["d"] = str(x.get("detail") or "")
                    if not one["d"]:
                        errs.append(f"{q['id']}: 選択肢「{o['label']}」の記入欄の訳がありません")
                item["o"][o["label"]] = one
        out["q"][q["id"]] = item
    if errs:
        raise DefinitionError("\n".join(errs))
    return out


def load_i18n(folder, defs, errors):
    """<定義フォルダ>/i18n/<問診ID>.<言語>.yaml を読み、合うものだけ定義の _i18n に付ける。"""
    sub = os.path.join(folder, "i18n")
    if not os.path.isdir(sub):
        return
    for name in sorted(os.listdir(sub)):
        if not name.endswith(".yaml"):
            continue
        try:
            with open(os.path.join(sub, name), encoding="utf-8-sig") as f:
                tr = yamlmini.load(f.read())
            d = defs.get(tr.get("id")) if isinstance(tr, dict) else None
            if d is None or tr.get("lang") not in lang.LANGS:
                raise DefinitionError("もとの問診票がない、または言語の指定が正しくありません")
            d.setdefault("_i18n", {})[tr["lang"]] = check_i18n(d, tr)
        except (yamlmini.YamlError, DefinitionError) as e:
            errors.append(f"外国語の画面 {name} は出していません：{e}")


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
    for folder in dirs:
        load_i18n(folder, defs, errors)
    return defs, errors
