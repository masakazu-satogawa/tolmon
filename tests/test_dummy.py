"""ダミー患者の回答を検証する部分（Claude を呼ばない部分）のテスト。"""
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
from app import definitions  # noqa: E402
from creator import dummy  # noqa: E402

DEF = definitions.validate({"id": "t", "title": "テスト問診票", "questions": [
    {"id": "age", "type": "number", "text": "年齢", "karte": "年齢", "tag": "基本情報", "unit": "歳"},
    {"id": "sex", "type": "single", "text": "性別", "karte": "性別", "tag": "基本情報",
     "options": [{"label": "男性"}, {"label": "女性"}]},
    {"id": "site", "type": "body", "text": "場所", "karte": "症状部位", "tag": "主訴", "required": True},
    {"id": "drug", "type": "single", "text": "薬で具合が悪くなった", "karte": "薬剤副作用歴", "tag": "アレルギー",
     "options": [{"label": "ある", "karte": "あり", "detail": "薬の名前"}, {"label": "ない", "karte": "なし"}]},
    {"id": "preg", "type": "single", "text": "妊娠中ですか", "karte": "妊娠", "tag": "その他",
     "options": [{"label": "はい"}, {"label": "いいえ"}],
     "show_if": {"all": [{"q": "sex", "ne": "男性"}, {"q": "age", "lt": 50}]}},
    {"id": "memo", "type": "text", "text": "伝えたいこと", "karte": "その他", "tag": "その他"},
]})


def ans(qid, *values, details=(), main="", talk=False):
    return {"id": qid, "values": list(values), "details": [{"label": k, "text": v} for k, v in details],
            "main": main, "talk": talk}


PATIENTS = [
    {"persona": "70歳の男性。右ひざが痛い", "answers": [
        ans("age", "70"), ans("sex", "男性"), ans("site", "r_knee"), ans("drug", "ある"),
        ans("preg", "はい"),                       # 男性には出ない設問に答えている
        ans("memo", talk=True)]},
    {"persona": "30歳の女性。右ひざと左肩", "answers": [
        ans("age", "30"), ans("sex", "女性"), ans("site", "r_knee", "l_shoulder", main="l_shoulder"),
        ans("drug", "ある", details=[("ある", "ペニシリン")]), ans("preg", "いいえ"), ans("nothing", "x")]},
    {"persona": "場所を答えなかった人", "answers": [ans("age", "55"), ans("sex", "女性")]},
    {"persona": "選択肢にない答え", "answers": [ans("site", "head"), ans("sex", "その他")]},
]


class DummyTest(unittest.TestCase):
    def test_to_raw(self):
        raw, notes = dummy.to_raw(DEF, PATIENTS[1])
        self.assertEqual(raw["age"], {"value": "30"})
        self.assertEqual(raw["site"], {"value": ["r_knee", "l_shoulder"], "main": "l_shoulder"})
        self.assertEqual(raw["drug"], {"value": "ある", "details": {"ある": "ペニシリン"}})
        self.assertEqual(len(notes), 1)                      # 定義にない設問 nothing
        raw, _ = dummy.to_raw(DEF, PATIENTS[0])
        self.assertEqual(raw["memo"], {"value": None, "talk": True})

    def test_run(self):
        res = dummy.run(DEF, PATIENTS, when="2026/11/05 10:00")
        p1, p2, p3, p4 = res["patients"]
        self.assertIn("薬剤副作用歴：あり（記載がないので要聴取）", p1["karte"])
        self.assertIn("〔その他〕記載がないので要聴取", p1["karte"])     # 書く欄で「診察のときに話します」
        self.assertNotIn("妊娠", p1["karte"])
        self.assertTrue(any("妊娠中ですか" in n for n in p1["notes"]))    # 出ない設問に答えていた
        self.assertIn("左肩（いちばんつらい）", p2["karte"])
        self.assertIn("あり（ペニシリン）", p2["karte"])
        self.assertEqual(p3["karte"], "")
        self.assertIn("必ず答えてください", p3["error"])                  # 必須の「場所」が未回答
        self.assertIn("選択肢が正しくありません", p4["error"])
        s = res["summary"]
        self.assertEqual((s["patients"], s["ok"], s["errors"]), (4, 2, 2))
        self.assertEqual((s["branches"], s["branches_both"]), (1, 1))     # 妊娠：出た人も出なかった人もいる
        self.assertEqual(s["never_shown"], [])
        cov = {r["id"]: r for r in res["coverage"]}
        self.assertEqual((cov["preg"]["shown"], cov["preg"]["answered"]), (1, 1))
        self.assertEqual(cov["drug"]["unused"], ["ない"])
        self.assertEqual(cov["memo"]["answered"], 1)                      # 「診察のときに話します」も答えた数に入る

    def test_brief(self):
        text = dummy.brief(DEF)
        self.assertIn('"show_if"', text)
        self.assertIn("r_knee：右ひざ", text)                             # 体の図があるときだけ部位の一覧を付ける
        self.assertNotIn("karte", text)                                   # カルテ向けの文言は渡さない（患者さんに見える内容だけ）


if __name__ == "__main__":
    unittest.main()
