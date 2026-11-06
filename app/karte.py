"""回答をカルテ貼り付け用の文章と、開示用の「設問と回答」に整える（AIは使わない）。"""

from . import body, lang
from .definitions import TAGS

MAIN_SUFFIX = "（いちばんつらい）"
# 患者さんに文字を書かせない：書く欄は「診察のときに話します」で先へ進める。カルテには聞くべきことが分かるよう残す
TALK_PATIENT = "診察のときに話します"
TALK_KARTE = "記載がないので要聴取"


def _num(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def check_condition(cond, answers):
    """show_if の1条件。考え方：「答えていない」ときは聞く側に倒す（eq と gte だけは答えが必要）。
      eq: 選んだ（含む）  ne: 選んでいない  lt: 数値が未満  gte: 数値が以上
    web/patient.js の checkCondition と同じ動きにすること。
    """
    if "all" in cond:
        return all(check_condition(c, answers) for c in cond["all"])
    if "any" in cond:
        return any(check_condition(c, answers) for c in cond["any"])
    ref = answers.get(cond["q"]) or {}
    v = ref.get("value")
    answered = v not in (None, "", [])
    if "eq" in cond:
        return answered and (v == cond["eq"] or (isinstance(v, list) and cond["eq"] in v))
    if "ne" in cond:
        return not answered or not (v == cond["ne"] or (isinstance(v, list) and cond["ne"] in v))
    n = _num(v) if answered else None
    if "lt" in cond:
        return n is None or n < cond["lt"]
    if "gte" in cond:
        return n is not None and n >= cond["gte"]
    return True


def is_visible(q, answers):
    cond = q.get("show_if")
    return True if not cond else check_condition(cond, answers)


def _option(q, label):
    for o in q.get("options") or []:
        if o["label"] == label:
            return o
    return None


def karte_value(q, a):
    """1問分の回答をカルテ向けの短い表現にする。未回答なら None。"""
    if not a:
        return None
    v = a.get("value")
    details = a.get("details") or {}
    t = q["type"]
    if t in ("single", "multi"):
        labels = v if isinstance(v, list) else ([v] if v else [])
        if not labels:
            return None
        parts = []
        for label in labels:
            o = _option(q, label) or {}
            s = o.get("karte") or label
            d = (details.get(label) or "").strip()
            if not d and o.get("detail"):
                d = TALK_KARTE          # 記入欄のある選択肢を選んだが、書いていない → 医師が聞く
            parts.append(f"{s}（{d}）" if d else s)
        return "、".join(parts)
    if t == "body":
        return "、".join(body.label(x) for x in v) if isinstance(v, list) and v else None
    if v is None or str(v).strip() == "":
        return TALK_KARTE if a.get("talk") else None
    if t == "number":
        return f"{v}{q.get('unit', '')}"
    return str(v).strip()


def alerts(defn, answers):
    """要確認の印。定義で alert: true にした選択肢（設問に付けたときは、その設問の全部の選択肢）を
    選んだ回答を、「項目名：値」で返す。どの答えに印を付けるかは病院が決める。アプリは判断しない。"""
    out = []
    for q in defn["questions"]:
        if q["type"] not in ("single", "multi") or not is_visible(q, answers):
            continue
        a = answers.get(q["id"]) or {}
        v = a.get("value")
        details = a.get("details") or {}
        parts = []
        for label in (v if isinstance(v, list) else ([v] if v else [])):
            o = _option(q, label) or {}
            if not (o.get("alert") or (q.get("alert") and o.get("alert") is not False)):
                continue
            d = (details.get(label) or "").strip() or (TALK_KARTE if o.get("detail") else "")
            s = o.get("karte") or label
            parts.append(f"{s}（{d}）" if d else s)
        if parts:
            out.append(f"{q['karte']}：" + "、".join(parts))
    return out


def body_main(q, a):
    """人体シェーマで「いちばんつらいところ」があればその部位名（1か所だけならその部位）。"""
    if not a or q["type"] != "body":
        return None
    v = a.get("value") or []
    main = a.get("main")
    if main in v:
        return body.label(main)
    return body.label(v[0]) if len(v) == 1 else None


def patient_value(q, a):
    """1問分の回答を、患者が選んだ言葉のまま表す（開示・確認用）。"""
    if not a:
        return "（未回答）"
    v = a.get("value")
    details = a.get("details") or {}
    if q["type"] == "body":
        if not v:
            return "（未回答）"
        main = a.get("main") if len(v) >= 2 else None
        return "、".join(body.label(x) + (MAIN_SUFFIX if x == main else "") for x in v)
    if q["type"] in ("single", "multi"):
        labels = v if isinstance(v, list) else ([v] if v else [])
        if not labels:
            return "（未回答）"
        out = []
        for label in labels:
            d = (details.get(label) or "").strip()
            out.append(f"{label}（{d}）" if d else label)
        return "、".join(out)
    if v is None or str(v).strip() == "":
        return TALK_PATIENT if a.get("talk") else "（未回答）"
    if q["type"] == "number":
        return f"{v} {q.get('unit', '')}".strip()
    return str(v)


def karte_text(defn, answers, when):
    """カルテ貼り付け用。タグごとに1行、「項目：値」を「／」でつなぐ。"""
    groups = {t: [] for t in TAGS}
    for q in defn["questions"]:
        if not is_visible(q, answers):
            continue
        val = karte_value(q, answers.get(q["id"]))
        if val is None:
            continue
        tag = q.get("tag", "その他")
        label = q["karte"]
        if q["type"] == "body":
            # いちばんつらい部位は主訴として先頭に。部位の一覧は設問のタグの行に残す
            main = body_main(q, answers.get(q["id"]))
            if main:
                many = len(answers[q["id"]].get("value") or []) >= 2
                groups["主訴"].insert(0, main + (MAIN_SUFFIX if many else ""))
                if not many:
                    continue                    # 1か所だけなら主訴に出ているので、同じ部位をもう一度は書かない
        groups[tag].append(val if label == tag else f"{label}：{val}")
    lines = [f"【問診】{defn['title']}　{when}"]
    for tag in TAGS:
        if groups[tag]:
            lines.append(f"〔{tag}〕" + "／".join(groups[tag]))
    return "\n".join(lines)


def shown_value(q, a, tr, words, code):
    """外国語の画面で、患者さんに見えていた言葉のままの回答。"""
    if not a:
        return words["no_answer"]
    v = a.get("value")
    details = a.get("details") or {}

    def with_detail(s, d):
        d = (d or "").strip()
        return f"{s}{words['lp']}{d}{words['rp']}" if d else s

    if q["type"] == "body":
        if not v:
            return words["no_answer"]
        main = a.get("main") if len(v) >= 2 else None
        return words["sep"].join(lang.body_label(x, code) + (words["main_suffix"] if x == main else "") for x in v)
    if q["type"] in ("single", "multi"):
        labels = v if isinstance(v, list) else ([v] if v else [])
        if not labels:
            return words["no_answer"]
        opts = tr.get("o") or {}
        return words["sep"].join(with_detail((opts.get(x) or {}).get("t") or x, details.get(x)) for x in labels)
    if v is None or str(v).strip() == "":
        return words["talk"] if a.get("talk") else words["no_answer"]
    if q["type"] == "number":
        return f"{v} {tr.get('unit') or q.get('unit', '')}".strip()
    return str(v)


def shown_questions(defn, answers, code=None):
    """患者に表示した設問とその回答（開示用スナップショット）。
    外国語の画面で答えたときは、見えていた言葉（text_shown / answer_shown）も残す。"""
    tr_all = (defn.get("_i18n") or {}).get(code) if code else None
    out = []
    for q in defn["questions"]:
        if not is_visible(q, answers):
            continue
        a = answers.get(q["id"])
        row = {"id": q["id"], "text": q["text"], "answer": patient_value(q, a)}
        if tr_all:
            tr = tr_all["q"].get(q["id"]) or {}
            row["text_shown"] = tr.get("text") or q["text"]
            row["answer_shown"] = shown_value(q, a, tr, lang.ui(code), code)
        out.append(row)
    return out
