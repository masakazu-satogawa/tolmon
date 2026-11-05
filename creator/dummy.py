"""架空の患者（ダミー患者）の回答を Claude に作らせて、できた問診を通しで確かめる。

  1. Claude：問診の定義を読み、分岐がひととおり通るように、架空の患者を何人か作って答えさせる
  2. アプリ：その回答を本番と同じ手順で検証し、カルテ文を作り、どの設問・選択肢が通ったかを数える（AIは使わない）

本物の患者さんの情報は使わない。Claude に送るのは設問の定義だけ。
"""

import json
from datetime import datetime

from app import body, karte, store

from . import claude_api

SYSTEM = """あなたは、病院のWeb問診（タブレットで答える問診）のテスト担当者です。
渡された問診の定義を読み、架空の患者さんを指定された人数だけ作り、その人になりきって問診に答えてください。
目的は、問診が正しく動くか（設問の出し分け、回答の受け取り、カルテ向けの文章）を、公開する前に確かめることです。

# 守ること
- すべて架空の人物にする。実在の人物・氏名・住所・電話番号は書かない（問診にも氏名の欄はない）。
- persona には、その人の設定を1〜2文で書く（例：「78歳の女性。昨日から熱とせき。文字を打つのは苦手」）。
- その人が実際に答えそうな内容にする。答えどうしが食い違わないようにする（体温が平熱なのに高熱の症状、など）。
- 診断名を決めつけない。患者さん本人が分かることだけを答える。

# テストとして確かめたいこと（全員を合わせて満たす）
- すべての分岐（show_if）が、少なくとも1回は出る側になるようにする。出ない側になる人もいるようにする。
- 選択肢がかたよらないようにする。「その他」「わからない」を選ぶ人も入れる。
- 年齢と性別をばらつかせる（高齢の男性・女性、若い女性、子どもや学生など、その問診に合う範囲で）。
- 記入欄（detail）は、書く人と書かない人の両方を入れる。高齢の人は書かないことが多い。
- 必須でない設問をいくつか飛ばす人を1人入れる。
- 自由に書く設問（text）があれば、書く人と、書かずに「診察のときに話します」（talk を true）を選ぶ人を入れる。

# 答え方（answers の1件が、1つの設問への答え）
- id：設問の id。定義にある id だけを使う。
- values：答え。
  - single：選んだ選択肢の label を1つ。label は定義の文字のまま。
  - multi ：選んだ選択肢の label をすべて。
  - number：数字を1つ、文字として（例："72"、"37.8"）。単位は付けない。
  - time  ：時刻を1つ（例："07:30"）。
  - text  ：書いた文章を1つ。talk が true のときは空の配列。
  - body  ：選んだ体の部位の id をすべて（下の「体の部位」にある id だけ）。
- details：選んだ選択肢に記入欄（detail）があり、そこに書いた場合だけ、その label と書いた内容。なければ空の配列。
- main：body で2か所以上選んだときだけ、いちばんつらい部位の id。それ以外は空文字。
- talk：text の設問で、書かずに「診察のときに話します」を選んだとき true。それ以外は false。
- 答えない設問は、answers に入れない。必須（required が true）の設問は必ず答える。

# 設問が出る条件（show_if）
その人のそれまでの答えで決まる。出ない設問には答えない。
- eq：その選択肢を選んだとき（multi なら、選んだ中に入っているとき）。答えていなければ出ない。
- ne：その選択肢を選んでいないとき。答えていなくても出る。
- lt：数字がそれより小さいとき。答えていなくても出る。
- gte：数字がそれ以上のとき。答えていなければ出ない。
- all：すべての条件を満たすとき。any：どれか1つでも満たすとき。
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "patients": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "persona": {"type": "string", "description": "架空の患者さんの設定（1〜2文）"},
                    "answers": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "values": {"type": "array", "items": {"type": "string"}},
                                "details": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {"label": {"type": "string"}, "text": {"type": "string"}},
                                        "required": ["label", "text"],
                                        "additionalProperties": False,
                                    },
                                },
                                "main": {"type": "string"},
                                "talk": {"type": "boolean"},
                            },
                            "required": ["id", "values", "details", "main", "talk"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["persona", "answers"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["patients"],
    "additionalProperties": False,
}

MAX_PATIENTS = 8


def brief(defn):
    """Claude に渡す、問診の定義の要点（患者さんに見える内容と、出る条件）。"""
    qs = []
    for q in defn["questions"]:
        d = {"id": q["id"], "type": q["type"], "text": q["text"]}
        for k in ("required", "unit", "min", "max", "hint", "show_if"):
            if k in q:
                d[k] = q[k]
        if q.get("options"):
            d["options"] = [{k: o[k] for k in ("label", "detail") if k in o} for o in q["options"]]
        qs.append(d)
    text = "# 問診の定義\n" + json.dumps({"title": defn.get("title", ""), "questions": qs}, ensure_ascii=False, indent=1)
    if any(q["type"] == "body" for q in defn["questions"]):
        text += "\n\n# 体の部位（body の設問で使える id と、その名前）\n" + "\n".join(f"{k}：{v}" for k, v in body.REGIONS.items())
    return text


def generate(defn, count=5, model=claude_api.DEFAULT_MODEL):
    """Claude に架空の患者を作らせる。戻り値は (患者の一覧, 使用量などの情報)。"""
    content = [{"type": "text", "text": brief(defn) + f"\n\n架空の患者さんを {count} 人作り、それぞれこの問診に答えてください。"}]
    data, info = claude_api.call(SYSTEM, content, SCHEMA, model=model, effort="medium")
    return data.get("patients", [])[:MAX_PATIENTS], info


def to_raw(defn, patient):
    """Claude の答え（一覧の形）を、患者画面が送ってくるのと同じ形にする。定義にない id は notes に入れる。"""
    by_id = {q["id"]: q for q in defn["questions"]}
    raw, notes = {}, []
    for a in patient.get("answers", []):
        q = by_id.get(a.get("id"))
        if not q:
            notes.append(f"定義にない設問「{a.get('id')}」に答えていました")
            continue
        values = [str(v) for v in a.get("values") or []]
        t = q["type"]
        if t == "body":
            ans = {"value": values}
            if a.get("main"):
                ans["main"] = a["main"]
        elif t == "multi":
            ans = {"value": values}
        else:
            ans = {"value": values[0] if values else None}
            if t == "text" and a.get("talk"):
                ans["talk"] = True
        details = {d["label"]: d["text"] for d in a.get("details") or [] if d.get("text")}
        if details and t in ("single", "multi"):
            ans["details"] = details
        raw[q["id"]] = ans
    return raw, notes


def _answered(a):
    return bool(a) and (a.get("talk") or a.get("value") not in (None, "", []))


def run(defn, patients, when=None):
    """ダミー患者の回答を、本番と同じ手順で検証する（AIは使わない）。

    1人ずつ：回答の検証 → カルテ文 → 表示した設問。全体：設問・選択肢・分岐がどれだけ通ったか。
    """
    when = when or datetime.now().strftime("%Y/%m/%d %H:%M")
    results, cleaned_all = [], []
    for p in patients:
        raw, notes = to_raw(defn, p)
        item = {"persona": p.get("persona", ""), "notes": notes, "error": "", "karte": "", "shown": []}
        try:
            cleaned = store.clean_answers(defn, raw)
        except store.AnswerError as e:
            item["error"] = str(e)         # 本番なら「送信できません」になる回答
            results.append(item)
            continue
        dropped = [q["text"] for q in defn["questions"] if _answered(raw.get(q["id"])) and q["id"] not in cleaned]
        if dropped:
            item["notes"].append("出ない設問に答えていたので、その答えは使いませんでした：" + "／".join(dropped))
        item["karte"] = karte.karte_text(defn, cleaned, when)
        item["shown"] = karte.shown_questions(defn, cleaned)
        results.append(item)
        cleaned_all.append(cleaned)

    # 通り具合：設問ごとに、何人に出て、何人が答えたか。選択肢ごとに、何人が選んだか
    coverage = []
    for q in defn["questions"]:
        shown = sum(1 for c in cleaned_all if karte.is_visible(q, c))
        row = {"id": q["id"], "text": q["text"], "branch": bool(q.get("show_if")), "shown": shown,
               "answered": sum(1 for c in cleaned_all if _answered(c.get(q["id"])))}
        if q.get("options"):
            picked = {o["label"]: 0 for o in q["options"]}
            for c in cleaned_all:
                v = (c.get(q["id"]) or {}).get("value")
                for label in (v if isinstance(v, list) else [v]):
                    if label in picked:
                        picked[label] += 1
            row["unused"] = [label for label, n in picked.items() if not n]
        coverage.append(row)
    branches = [r for r in coverage if r["branch"]]
    ok = len(cleaned_all)
    summary = {
        "patients": len(patients), "ok": ok, "errors": len(patients) - ok,
        "questions": len(coverage), "never_shown": [r["text"] for r in coverage if not r["shown"]],
        "branches": len(branches),
        "branches_both": sum(1 for r in branches if 0 < r["shown"] < ok),      # 出た人も、出なかった人もいる
        "branches_always": [r["text"] for r in branches if ok and r["shown"] == ok],
    }
    return {"patients": results, "coverage": coverage, "summary": summary}


def make(defn, count=5, model=claude_api.DEFAULT_MODEL):
    patients, info = generate(defn, max(1, min(int(count), MAX_PATIENTS)), model)
    result = run(defn, patients)
    result["usage"] = info
    return result
