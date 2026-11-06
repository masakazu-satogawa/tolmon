"""白紙の問診票（PDF・画像）を Claude に読ませて、問診定義の下書きを作る。

  1. 読み取り：紙 → 設問・選択肢・分岐・患者向け文言・カルテ向け文言（JSON）
  2. 見直し　：できた定義を、Claude がもう一度紙と突き合わせて、ずれを報告する
  3. 変換　　：JSON → 決めた書き方の YAML（人が直して確定する）

Claude に送るのは白紙の問診票と、そこから作った設問の構造だけ。
"""

import base64
import os
import re

from app import definitions, yamlmini
from app.definitions import TAGS, TYPES

from . import claude_api

HERE = os.path.dirname(os.path.abspath(__file__))
MEDIA = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def hospital_rules():
    with open(os.path.join(HERE, "hospital_rules.md"), encoding="utf-8-sig") as f:
        return f.read()


# ====================================================================== 1. 読み取り
READ_SYSTEM = """あなたは、病院の紙の問診票を、タブレットで答えるWeb問診の定義に置き換える担当者です。
添付されるのは、記入前（白紙）の問診票です。

# 目的
紙と同じ内容を、紙より楽に答えられる形にすること。答える人の多くは高齢の患者さんです。
紙にない設問を足してはいけません。診断・病名の推定・受診の判断など、医学的な判断は一切しません。

# 読み取りの手順
1. 紙の上から順に、すべての記入欄を拾う。見落としがないよう、欄ごとに確認する。
2. 「この病院のルール」に照らして、設問にしない欄を外す。外した欄は skipped に、紙の文言と理由を書く。
3. 残った欄を設問にする。紙の1つの欄が1つの設問になるのが基本。

# いちばん大事な決まり：患者さんに文字を書かせない
患者さんはタブレットで答えます。画面のキーボードで文字を打つのは、高齢の方にはとても難しく、時間がかかります。
紙では書く欄（空欄「（　　）」）になっていても、できるかぎり「選ぶ」か「数字」で答えられる形にします。
- 紙の空欄は、その設問でよくある答えを選択肢にして、single か multi にする。
  変えるのは答え方だけ。設問を増やさない。聞いている内容を変えない。
- 紙にない選択肢を足したときは、その選択肢の added を true にする（あとで人が確認する）。紙にある選択肢は false。
- 足してよいのは、患者さんが自分で分かる事実（いつ・どこで・何をしていて・どのくらい）だけ。
  病名の推定、重さの判断、受診の要否につながる選択肢は作らない。
- 選択肢は、ふつうは12個まで。答えが決められない人のために、最後に「わからない」か「その他」を置く。
- 「この病院のルール」に決まった選択肢があるときは、その言い方をそのまま使う。
- 同じ設問の中に、チェック欄と書く欄の両方がある場合は、1つの設問にまとめる（紙の選択肢＋足した選択肢）。
- 数字で答えられるもの（年齢・体温・本数・回数・年数）は number にする。画面には大きな数字ボタンが出る。
- text のまま残してよいのは、病名・薬の名前・手術の内容のように、選択肢にしきれないものだけ。
  text の設問と、選択肢の detail（記入欄）には、画面に「診察のときに話します」が出るので、書かなくても先へ進める。

# 設問タイプ（type）
- single : 1つだけ選ぶ（はい・いいえ、ある・ない、〜・〜・〜 から1つ、など）。
- multi  : いくつでも選べる（□が並んでいる、あてはまるものすべて、など）。
- number : 数字で答える。unit に単位（℃、歳、本、回 など）。
- body   : 体の図に印をつけて場所を示す欄。選択肢は付けない。
- time   : 時刻（何時何分）。ほかの形にできないときだけ。
- text   : 自由に書く欄。上の決まりのとおり、選択肢にしきれないときだけ。

# 紙によくある形の置き換え方
- 「ある（　　　）・ない」のように、選んだときだけ書く欄があるもの：
  その選択肢の detail に、何を書いてほしいかを患者さん向けの言葉で入れる。別の設問にはしない。
  （detail の記入は任意。書かなかったときは、カルテに「記載がないので要聴取」と出る）
- 選択肢の中に「その他（　　）」があるもの：「その他」の選択肢の detail を使う。
- 1つの欄に複数の記入がまとまっているもの（例：たばこ 1日（　）本・（　）年）：
  まず状況を選ぶ single の設問を作り、選んだ内容に応じて出る number の設問に分ける（show_if を使う）。
  分けてよいのは、紙に書かれている内容の範囲だけ。
- 病名といつ頃、のように同じ形が何行も並ぶ表：まず「ある・ない」の single にし、「ある」の detail に書き方の例を入れる。
- 表の形のアンケート（各行に質問、右に選択肢）：1行を1つの single の設問にする。

# 要確認の印（alert）
- 医師・看護師の画面のいちばん上に目立たせたい答えには、選択肢の alert を true にする。それ以外は false。
- どの答えに印を付けるかは「この病院のルール」に書いてある。ルールにない答えには付けない。
  印は「見落とさないため」のもので、病気や重さの判断ではない。

# 分岐（show_if）
- 紙に書かれている条件、または「この病院のルール」にある条件だけを使う。
- 参照する設問は、必ずその設問より前にあること。q には設問の id、value には選択肢の label をそのまま入れる。
- op は eq（それを選んだとき）、ne（それを選んでいないとき）、lt（数値が未満）、gte（数値が以上）。
  いくつでも選べる設問（multi）を参照したとき、eq は「選んだ中にそれが入っているとき」になる。
- 条件がなければ空の配列にする。複数入れたときは show_if_mode で決まる：
  all は「すべて満たすとき」、any は「どれか1つでも満たすとき」。条件が1つ以下なら all にしておく。

# 文言
- text（患者さん向け）：やさしい言葉、ていねいな言い方、短い1文。紙の意味を変えない。
  むずかしい言葉は言いかえる（例：「既往歴」→「これまでにかかった大きな病気」）。
- karte（カルテ向け）：医療者が読む短い項目名（例：「薬剤副作用歴」「発症時期」）。
- options の label は患者さん向け、karte はカルテ向けの短い言い方（例：label「ある」→ karte「あり」）。
  label とカルテ向けが同じでよいときは、karte に同じ文字を入れる。
- hint：書き方の例など、あると答えやすいときだけ。不要なら空文字。

# そのほかの決まり
- id：半角の英小文字・数字・アンダースコアだけ。内容が分かる短い名前にする（例：onset, allergy_drug）。重複させない。
- tag：カルテでのまとまり。基本情報／主訴／現病歴／既往歴／内服薬／アレルギー／生活歴／その他 から選ぶ。
- required：その問診の中心になる設問（いちばん聞きたい症状など）だけ true。ほかは false。
- source：その設問のもとになった紙の文言を、そのまま書き写す。
- 使わない項目は、文字なら空文字、配列なら空の配列にする。
- 読み取りに自信がない所、解釈が分かれる所、紙の印刷がかすれて読めない所は、推測で埋めたままにせず notes に書く。

# この病院のルール
{rules}
"""

READ_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "問診票の名前（例：内科 初診問診票）"},
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "type": {"type": "string", "enum": list(TYPES)},
                    "text": {"type": "string", "description": "患者さん向けの設問文"},
                    "karte": {"type": "string", "description": "カルテ向けの項目名"},
                    "tag": {"type": "string", "enum": list(TAGS)},
                    "required": {"type": "boolean"},
                    "hint": {"type": "string"},
                    "unit": {"type": "string"},
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "karte": {"type": "string"},
                                "detail": {"type": "string", "description": "選んだときだけ出す記入欄の説明。不要なら空文字"},
                                "added": {"type": "boolean", "description": "紙にない選択肢を足したとき true。紙にある選択肢は false"},
                                "alert": {"type": "boolean", "description": "病院のルールで「要確認の印」を付ける答えなら true。ほかは false"},
                            },
                            "required": ["label", "karte", "detail", "added", "alert"],
                            "additionalProperties": False,
                        },
                    },
                    "show_if": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "q": {"type": "string"},
                                "op": {"type": "string", "enum": ["eq", "ne", "lt", "gte"]},
                                "value": {"type": "string"},
                            },
                            "required": ["q", "op", "value"],
                            "additionalProperties": False,
                        },
                    },
                    "show_if_mode": {"type": "string", "enum": ["all", "any"],
                                     "description": "show_if に複数の条件があるとき。all=すべて満たす、any=どれか1つでも満たす"},
                    "source": {"type": "string", "description": "もとになった紙の文言"},
                },
                "required": ["id", "type", "text", "karte", "tag", "required", "hint", "unit", "options", "show_if", "show_if_mode", "source"],
                "additionalProperties": False,
            },
        },
        "skipped": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"paper_text": {"type": "string"}, "reason": {"type": "string"}},
                "required": ["paper_text", "reason"],
                "additionalProperties": False,
            },
        },
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "questions", "skipped", "notes"],
    "additionalProperties": False,
}


def paper_block(data, media_type):
    """紙（PDFまたは画像）を、Claude に渡す形にする。"""
    b64 = base64.standard_b64encode(data).decode("ascii")
    kind = "document" if media_type == "application/pdf" else "image"
    return {"type": kind, "source": {"type": "base64", "media_type": media_type, "data": b64}}


def read_paper(data, media_type, model=claude_api.DEFAULT_MODEL):
    system = READ_SYSTEM.format(rules=hospital_rules())
    content = [paper_block(data, media_type),
               {"type": "text", "text": "この白紙の問診票を読み取り、Web問診の定義にしてください。"}]
    return claude_api.call(system, content, READ_SCHEMA, model=model, effort="high")


# ====================================================================== 2. 見直し
CHECK_SYSTEM = """あなたは、問診票の検査担当者です。
添付の紙（白紙の問診票）と、そこから作られたWeb問診の定義を、1欄ずつ突き合わせて、ずれを報告します。
定義を作った人とは別の目で、厳しく確認してください。問題がなければ issues は空の配列にします。

# 確認すること
- 抜け　　：紙にある記入欄が、定義にも skipped にもない。
- 余計　　：紙にない設問が定義にある（「この病院のルール」で決められた設問は除く）。
- 選択肢　：選択肢の抜け・余計・誤字。紙の選択肢と1つずつ比べる。
- 足した選択肢：added が true の選択肢は、患者さんに文字を書かせないために、紙の空欄を選ぶ形に変えたもの。
  紙にないこと自体は指摘しない。次の場合だけ指摘する。
  ・病名の推定、重さの判断、受診の要否につながる選択肢がある
  ・紙が聞いている内容からはずれている、設問の意味が変わっている
  ・「この病院のルール」に決まった選択肢があるのに、言い方が違う
  ・よくある答えが抜けている、似た選択肢が重なっている、数が多すぎる
  ・紙にある選択肢なのに added が true、または紙にないのに false になっている
- 書かせない：選ぶ形や数字にできるのに、text（自由に書く欄）のままになっている設問がある。
- タイプ　：1つだけ選ぶ欄が multi になっている、数字の欄が text になっている、など。
- 記入欄　：「ある（　　）」のような記入欄が detail として入っているか。
- 分岐　　：show_if の条件が紙（またはルール）と合っているか。参照先の id と label が正しいか。
  このアプリでは、eq は「それを選んだとき」。いくつでも選べる設問（multi）を参照した eq は
  「選んだ中にそれが入っているとき」と判定されるので、multi に eq を使うこと自体は問題にしない。
  参照先の設問に答えていないとき、eq と gte の条件は満たさない（出ない）、ne と lt の条件は満たす（出る）。
- 文言　　：患者さん向けの文が、紙の意味を変えていないか。むずかしすぎないか。
- ルール　：「この病院のルール」に反していないか（聞かない欄を聞いている、残す欄を外している、など）。
- 要確認の印：alert が true の選択肢が、「この病院のルール」の決まりと合っているか（付け忘れ、付けすぎ）。

# 重さ（severity）
- error   ：このままでは使えない（抜け、選択肢の誤り、分岐の誤り、ルール違反）。
- warning ：人の確認が要る（解釈が分かれる、文言の言いかえが大きい）。
- info    ：気づいた点（直さなくても使える）。

suggestion には、どう直せばよいかを具体的に書きます。question_id には該当する設問の id を入れ、
特定の設問でない場合（抜けなど）は空文字にします。

# この病院のルール
{rules}
"""

CHECK_SCHEMA = {
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question_id": {"type": "string"},
                    "severity": {"type": "string", "enum": ["error", "warning", "info"]},
                    "kind": {"type": "string", "enum": ["抜け", "余計", "選択肢", "足した選択肢", "書かせない", "タイプ", "記入欄", "分岐", "文言", "ルール", "その他"]},
                    "message": {"type": "string"},
                    "suggestion": {"type": "string"},
                },
                "required": ["question_id", "severity", "kind", "message", "suggestion"],
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string", "description": "全体の一言（例：大きな問題なし、選択肢に2か所の誤り）"},
    },
    "required": ["issues", "summary"],
    "additionalProperties": False,
}


def check_paper(data, media_type, draft, model=claude_api.DEFAULT_MODEL):
    """draft（読み取り結果の dict）を、もう一度紙と突き合わせる。"""
    import json
    system = CHECK_SYSTEM.format(rules=hospital_rules())
    content = [paper_block(data, media_type),
               {"type": "text", "text": "この紙から作った定義は次のとおりです。紙と突き合わせて、ずれを報告してください。\n\n"
                                        + json.dumps(draft, ensure_ascii=False, indent=1)}]
    return claude_api.call(system, content, CHECK_SCHEMA, model=model, effort="high")


# ====================================================================== 3. 変換
_ID = re.compile(r"^[a-z][a-z0-9_]*$")


def _number(s):
    try:
        f = float(str(s).replace(",", "."))
    except ValueError:
        return s
    return int(f) if f == int(f) else f


def to_definition(draft, form_id, version=1):
    """読み取り結果（JSON）を、問診定義（definitions/*.yaml と同じ形の dict）にする。"""
    qs = []
    for q in draft.get("questions", []):
        d = {"id": q["id"], "type": q["type"], "text": q["text"], "karte": q["karte"], "tag": q["tag"]}
        if q.get("required"):
            d["required"] = True
        if q.get("hint"):
            d["hint"] = q["hint"]
        if q["type"] == "number" and q.get("unit"):
            d["unit"] = q["unit"]
        if q["type"] in ("single", "multi"):
            opts = []
            for o in q.get("options", []):
                od = {"label": o["label"]}
                if o.get("karte") and o["karte"] != o["label"]:
                    od["karte"] = o["karte"]
                if o.get("detail"):
                    od["detail"] = o["detail"]
                if o.get("alert"):
                    od["alert"] = True
                opts.append(od)
            d["options"] = opts
        conds = [{"q": c["q"], c["op"]: (_number(c["value"]) if c["op"] in ("lt", "gte") else c["value"])}
                 for c in q.get("show_if", [])]
        if len(conds) == 1:
            d["show_if"] = conds[0]
        elif conds:
            d["show_if"] = {("any" if q.get("show_if_mode") == "any" else "all"): conds}
        qs.append(d)
    return {"id": form_id, "title": draft.get("title") or form_id, "version": version, "questions": qs}


def to_yaml(defn, source_name=""):
    head = ["# トルモンの問診定義。白紙の問診票から Claude が下書きを作り、人が確認して確定したもの。",
            "# 書き方は CLAUDE.md「4. 問診定義」を参照。"]
    if source_name:
        head.insert(1, f"# もとの帳票: {source_name}")
    return "\n".join(head) + "\n" + yamlmini.dump(defn)


def problems(defn):
    """定義がアプリで使える形かを確かめ、だめな点を文字列の一覧で返す（空なら問題なし）。"""
    out = [f"設問の id「{q['id']}」は半角の英小文字・数字・_ だけにしてください"
           for q in defn.get("questions", []) if not _ID.match(str(q.get("id", "")))]
    try:
        definitions.validate(defn)
    except definitions.DefinitionError as e:
        out.extend(str(e).split("\n"))
    return out


# ====================================================================== まとめて実行
def make_draft(data, media_type, form_id, source_name="", model=claude_api.DEFAULT_MODEL, check=True):
    """読み取り → 見直し → YAML。画面に返す dict を作る。"""
    draft, read_info = read_paper(data, media_type, model)
    defn = to_definition(draft, form_id)
    result = {
        "definition": defn,
        "yaml": to_yaml(defn, source_name),
        "problems": problems(defn),
        "skipped": draft.get("skipped", []),
        "notes": draft.get("notes", []),
        "sources": {q["id"]: q.get("source", "") for q in draft.get("questions", [])},
        # 紙にない選択肢（Claude が足したもの）。設問id → 選択肢の一覧。作る画面で印を付けて、人が確かめる
        "added": {q["id"]: [o["label"] for o in q.get("options", []) if o.get("added")]
                  for q in draft.get("questions", []) if any(o.get("added") for o in q.get("options", []))},
        "issues": [], "summary": "",
        "usage": {"read": read_info},
    }
    if check:
        report, check_info = check_paper(data, media_type, draft, model)
        result["issues"] = report.get("issues", [])
        result["summary"] = report.get("summary", "")
        result["usage"]["check"] = check_info
    return result
