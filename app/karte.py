"""回答をカルテ貼り付け用の文章と、開示用の「設問と回答」に整える（AIは使わない）。"""

from . import body
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
        groups[tag].append(val if label == tag else f"{label}：{val}")
    lines = [f"【問診】{defn['title']}　{when}"]
    for tag in TAGS:
        if groups[tag]:
            lines.append(f"〔{tag}〕" + "／".join(groups[tag]))
    return "\n".join(lines)


def shown_questions(defn, answers):
    """患者に表示した設問とその回答（開示用スナップショット）。"""
    out = []
    for q in defn["questions"]:
        if not is_visible(q, answers):
            continue
        out.append({"id": q["id"], "text": q["text"], "answer": patient_value(q, answers.get(q["id"]))})
    return out
