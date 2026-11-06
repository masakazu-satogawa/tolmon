"""公開した問診票を、外国語の画面にする（英語・繁体字中国語）。

  1. 訳す　：Claude が、患者さんに見せる言葉（設問・ヒント・単位・選択肢・記入欄の説明）だけを訳す
  2. 戻す　：別の呼び出しの Claude が、もとの日本語を見ずに、訳だけを日本語に戻す
  3. 比べる：もとの日本語・訳・戻した日本語を Claude が比べて、意味がずれた所を挙げる
人は、もとの日本語と戻した日本語（どちらも日本語）を見比べ、確かめてから公開する。

Claude に送るのは設問の言葉だけ。患者さんの回答は送らない。
カルテ向けの言葉（karte）は訳さない。どの言語で答えても、カルテに出る文は日本語になる。
"""

import json

from app import definitions
from app.lang import LANGS

from . import claude_api

RULES = {
    "en": "アメリカ英語。英語が母語でない人にも分かる、やさしい英語（plain English）にする。",
    "zh-TW": "台湾で使われている繁体字中国語（正體字）。簡体字や、中国大陸だけの言い回しは使わない。患者さんには「您」を使う。",
}
NAMES = {"en": "英語", "zh-TW": "繁体字中国語（台湾）"}

TRANSLATE_SYSTEM = """あなたは、日本の病院の問診票を{name}に訳す医療翻訳者です。
患者さんがタブレットで読む言葉（題名・設問・ヒント・単位・選択肢・記入欄の説明）を訳します。

# 守ること
- 意味を足さない、引かない、変えない。日本語が聞いていることだけを聞く。
- 患者さんが読む言葉なので、やさしく、ていねいで、短い言い方にする。専門用語は一般の人の言葉にする。
- 同じ日本語は、どこでも同じ訳にする（「わからない」「その他」「ある」「ない」など）。
- 選択肢は、ボタンに入る短さにする。
- 日本特有のもの（学年、部活、マイナ保険証 など）は、日本の制度のまま、その言語の人に通じる言い方にする。
- 単位（unit）は、その言語でふつうに書く形にする。℃ や kg のような記号はそのまま。
- 病名を推定する言葉、重さを判断する言葉を足さない。
- options の label は、もとの日本語を一字も変えずにそのまま返す（照合に使う）。訳は text に入れる。
- もとが空文字の項目（hint・unit・detail）は、空文字のまま返す。
- すべての設問・すべての選択肢を、もとと同じ順で返す。

# この言語の決まり
{rule}
"""

BACK_SYSTEM = """あなたは翻訳者です。渡された{name}の問診票の言葉を、日本語に訳し戻してください。
もとの日本語は見せません。別の人が、もとの日本語と見比べて、訳の意味が合っているかを確かめるために使います。

- 書いてあるとおりに直訳する。意味を足さない、引かない。
- あいまいな所、不自然な所があっても、きれいに整えず、そのまま日本語にする（直さない）。
- 構造と順番は変えない。id と n は、そのまま返す。空文字は空文字のまま返す。
"""

COMPARE_SYSTEM = """あなたは、問診票の翻訳の検査担当者です。
1行ごとに、もとの日本語（ja）、{name}の訳（tr）、その訳を別の翻訳者が日本語に戻したもの（back）が並んでいます。
患者さんが訳を読んだとき、もとの日本語と違う意味に受け取るおそれがある行だけを報告してください。

# 重さ（severity）
- error  ：意味が違う。聞いている内容が抜けている、足されている。
- warning：あいまいで別の受け取り方ができる。その言語として不自然で、患者さんが迷う。

# 報告しないもの
- 言い方の好みの違い。戻した日本語が硬い、というだけのもの。
- 日本の制度の言葉を、その言語の人に通じるように言いかえたもの（意味が合っていれば問題にしない）。

row には行の番号を入れる。message と summary は、病院の職員が読むので、かならず日本語で書く。
suggestion には、直した訳だけを{name}で書く（説明や、いくつもの案は書かない）。問題がなければ issues は空の配列にする。
"""

_ITEM = {"type": "object",
         "properties": {"id": {"type": "string"}, "text": {"type": "string"}, "hint": {"type": "string"},
                        "unit": {"type": "string"}},
         "additionalProperties": False}


def _schema(option_key, option_type):
    option = {"type": "object",
              "properties": {option_key: {"type": option_type}, "text": {"type": "string"}, "detail": {"type": "string"}},
              "required": [option_key, "text", "detail"], "additionalProperties": False}
    q = dict(_ITEM, properties=dict(_ITEM["properties"], options={"type": "array", "items": option}),
             required=["id", "text", "hint", "unit", "options"])
    return {"type": "object",
            "properties": {"title": {"type": "string"}, "questions": {"type": "array", "items": q}},
            "required": ["title", "questions"], "additionalProperties": False}


TRANSLATE_SCHEMA = _schema("label", "string")
BACK_SCHEMA = _schema("n", "integer")
COMPARE_SCHEMA = {
    "type": "object",
    "properties": {
        "issues": {"type": "array", "items": {
            "type": "object",
            "properties": {"row": {"type": "integer"}, "severity": {"type": "string", "enum": ["error", "warning"]},
                           "message": {"type": "string"}, "suggestion": {"type": "string"}},
            "required": ["row", "severity", "message", "suggestion"], "additionalProperties": False}},
        "summary": {"type": "string", "description": "全体の一言（例：意味のずれはありません）"},
    },
    "required": ["issues", "summary"], "additionalProperties": False,
}


def source(defn):
    """訳してもらう言葉だけを取り出す（カルテ向けの言葉・出る条件は渡さない）。"""
    return {"title": defn["title"],
            "questions": [{"id": q["id"], "text": q["text"], "hint": q.get("hint", ""), "unit": q.get("unit", ""),
                           "options": [{"label": o["label"], "detail": o.get("detail", "")} for o in q.get("options") or []]}
                          for q in defn["questions"]]}


def to_file(defn, code, translated):
    """Claude の訳を、definitions/i18n/<問診ID>.<言語>.yaml に書く形にする。もとにない項目は捨てる。"""
    by_id = {q.get("id"): q for q in translated.get("questions", [])}
    qs = []
    for q in defn["questions"]:
        t = by_id.get(q["id"]) or {}
        item = {"id": q["id"], "text": str(t.get("text") or "")}
        for k in ("hint", "unit"):
            if q.get(k):
                item[k] = str(t.get(k) or "")
        if q.get("options"):
            got = {o.get("label"): o for o in t.get("options") or []}
            item["options"] = []
            for o in q["options"]:
                x = got.get(o["label"]) or {}
                one = {"label": o["label"], "text": str(x.get("text") or "")}
                if o.get("detail"):
                    one["detail"] = str(x.get("detail") or "")
                item["options"].append(one)
        qs.append(item)
    return {"id": defn["id"], "lang": code, "key": definitions.i18n_key(defn),
            "title": str(translated.get("title") or ""), "questions": qs}


def rows(defn, tr_file, back=None):
    """人が見比べる表の行。1行＝1つの言葉（題名／設問／ヒント／単位／選択肢／記入欄の説明）。"""
    back = back or {}
    back_q = {q.get("id"): q for q in back.get("questions", [])}
    tr_q = {q["id"]: q for q in tr_file["questions"]}
    # at は、その言葉が訳のどこにあるか（設問の番号、項目名、選択肢の番号）。人が訳を直すときに使う
    out = [{"qid": "", "where": "題名", "ja": defn["title"], "tr": tr_file["title"], "back": back.get("title", ""),
            "at": [-1, "title", -1]}]
    for i, q in enumerate(defn["questions"]):
        t, b = tr_q[q["id"]], back_q.get(q["id"]) or {}
        out.append({"qid": q["id"], "where": "設問", "ja": q["text"], "tr": t["text"], "back": b.get("text", ""),
                    "at": [i, "text", -1]})
        for k, name in (("hint", "ヒント"), ("unit", "単位")):
            if q.get(k):
                out.append({"qid": q["id"], "where": name, "ja": q[k], "tr": t.get(k, ""), "back": b.get(k, ""),
                            "at": [i, k, -1]})
        b_opts = {o.get("n"): o for o in b.get("options") or []}
        for n, o in enumerate(q.get("options") or []):
            x, bo = t["options"][n], b_opts.get(n) or {}
            out.append({"qid": q["id"], "where": "選択肢", "ja": o["label"], "tr": x["text"], "back": bo.get("text", ""),
                        "at": [i, "text", n]})
            if o.get("detail"):
                out.append({"qid": q["id"], "where": "記入欄", "ja": o["detail"], "tr": x.get("detail", ""),
                            "back": bo.get("detail", ""), "at": [i, "detail", n]})
    for i, r in enumerate(out):
        r["row"] = i
    return out


def fix(result, row, text):
    """人が訳を1か所直す。直した行は、戻し訳と指摘を消して「人が直した」印を付ける。"""
    r = result["rows"][row]
    qi, key, n = r["at"]
    target = result["file"] if qi < 0 else result["file"]["questions"][qi]
    if n >= 0:
        target = target["options"][n]
    target[key] = text
    r["tr"] = text
    r["back"] = ""
    r.pop("issue", None)
    r["fixed"] = True
    result["issues"] = sum(1 for x in result["rows"] if x.get("issue"))


def _blind(tr_file):
    """戻してもらう側に渡す形。もとの日本語（label）は入れず、選択肢は順番の番号（n）だけにする。"""
    return {"title": tr_file["title"],
            "questions": [{"id": q["id"], "text": q["text"], "hint": q.get("hint", ""), "unit": q.get("unit", ""),
                           "options": [{"n": n, "text": o["text"], "detail": o.get("detail", "")}
                                       for n, o in enumerate(q.get("options") or [])]}
                          for q in tr_file["questions"]]}


def make(defn, code, model=claude_api.DEFAULT_MODEL):
    """1つの言語について、訳す → 戻す → 比べる。画面に返す dict を作る。"""
    name = NAMES[code]
    as_text = lambda obj: [{"type": "text", "text": json.dumps(obj, ensure_ascii=False, indent=1)}]  # noqa: E731

    translated, t_info = claude_api.call(TRANSLATE_SYSTEM.format(name=name, rule=RULES[code]), as_text(source(defn)),
                                         TRANSLATE_SCHEMA, model=model, effort="medium", max_tokens=32000)
    tr_file = to_file(defn, code, translated)
    definitions.check_i18n(defn, tr_file)                      # 欠けがあれば、ここで止める

    back, b_info = claude_api.call(BACK_SYSTEM.format(name=name), as_text(_blind(tr_file)),
                                   BACK_SCHEMA, model=model, effort="low", max_tokens=32000)
    table = rows(defn, tr_file, back)

    report, c_info = claude_api.call(COMPARE_SYSTEM.format(name=name),
                                     as_text([{k: r[k] for k in ("row", "ja", "tr", "back")} for r in table]),
                                     COMPARE_SCHEMA, model=model, effort="medium")
    for issue in report.get("issues", []):
        if isinstance(issue.get("row"), int) and 0 <= issue["row"] < len(table):
            table[issue["row"]]["issue"] = {k: issue[k] for k in ("severity", "message", "suggestion")}
    return {"lang": code, "name": LANGS[code], "file": tr_file, "rows": table,
            "summary": report.get("summary", ""),
            "issues": sum(1 for r in table if r.get("issue")),
            "usage": {"translate": t_info, "back": b_info, "compare": c_info,
                      "seconds": round(t_info["seconds"] + b_info["seconds"] + c_info["seconds"], 1)}}
