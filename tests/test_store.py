import os
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
from app import definitions, karte, store, yamlmini  # noqa: E402

DEF = definitions.load_file(os.path.join(ROOT, "definitions", "sample_naika.yaml"))
REQ = {"symptom": {"value": ["熱がある"]}}  # 必須の設問


class CleanTest(unittest.TestCase):
    def test_required(self):
        with self.assertRaises(store.AnswerError):
            store.clean_answers(DEF, {})

    def test_bad_option_and_range(self):
        with self.assertRaises(store.AnswerError):
            store.clean_answers(DEF, {"symptom": {"value": ["存在しない"]}})
        with self.assertRaises(store.AnswerError):
            store.clean_answers(DEF, dict(REQ, temp={"value": "50"}))

    def test_hidden_answer_dropped(self):
        a = store.clean_answers(DEF, {
            "symptom": {"value": ["頭が痛い", "熱がある"]},
            "smoke": {"value": "吸わない"},
            "smoke_num": {"value": "20"},           # 「吸わない」なので表示されない設問
            "meds": {"value": "ない", "details": {"ある": "これは捨てる"}},
        })
        self.assertNotIn("smoke_num", a)
        self.assertEqual(a["symptom"]["value"], ["熱がある", "頭が痛い"])  # 定義の順
        self.assertNotIn("details", a["meds"])

    def test_pregnancy_by_sex_and_age(self):
        preg = {"pregnant": {"value": "どちらでもない"}}
        cases = [
            ({}, True),                                                   # 答えていなければ聞く
            ({"sex": {"value": "男性"}}, False),
            ({"sex": {"value": "女性"}, "age": {"value": "49"}}, True),
            ({"sex": {"value": "女性"}, "age": {"value": "50"}}, False),
            ({"age": {"value": "72"}}, False),
        ]
        for extra, shown in cases:
            with self.subTest(extra=extra):
                a = store.clean_answers(DEF, dict(REQ, **extra, **preg))
                self.assertEqual("pregnant" in a, shown)


class ConditionCheckTest(unittest.TestCase):
    def test_any_condition(self):
        # any：どれか1つでも満たせば出す（答えていなければ出さない）
        cond = {"any": [{"q": "onset", "eq": "今日から"}, {"q": "onset", "eq": "昨日から"}]}
        self.assertTrue(karte.check_condition(cond, {"onset": {"value": "昨日から"}}))
        self.assertFalse(karte.check_condition(cond, {"onset": {"value": "1年以上前から"}}))
        self.assertFalse(karte.check_condition(cond, {}))
        d = {"id": "x", "title": "x", "questions": [
            {"id": "onset", "type": "single", "text": "t", "karte": "k", "options": [{"label": "今日から"}, {"label": "昨日から"}]},
            {"id": "q", "type": "text", "text": "t", "karte": "k", "show_if": cond}]}
        definitions.validate(d)
        self.assertEqual(yamlmini.load(yamlmini.dump(d)), d)

    def test_bad_conditions_rejected(self):
        base = {"id": "x", "title": "x", "questions": [
            {"id": "age", "type": "number", "text": "年齢", "karte": "年齢"},
            {"id": "q", "type": "text", "text": "t", "karte": "k"}]}
        for cond in ({"q": "age", "lt": "50"}, {"q": "nope", "eq": "a"}, {"q": "age"}, {"all": []}, {"any": []}):
            with self.subTest(cond=cond):
                d = {**base, "questions": [base["questions"][0], dict(base["questions"][1], show_if=cond)]}
                with self.assertRaises(definitions.DefinitionError):
                    definitions.validate(d)


class SaveTest(unittest.TestCase):
    def test_pending_register_and_list(self):
        with tempfile.TemporaryDirectory() as d:
            store.init_db(d)
            raw = {"symptom": {"value": ["その他"], "details": {"その他": "めまい"}}, "smoke": {"value": "吸っている"},
                   "smoke_num": {"value": "5"}}
            r1 = store.save_pending(d, DEF, raw, {"started_at": "x"})
            r2 = store.save_pending(d, DEF, raw, {})
            self.assertEqual((r1["number"], r2["number"]), (1, 2))   # その日の受付番号
            self.assertEqual(len(store.list_pending(d, r1["record_id"][:4] + "-" + r1["record_id"][4:6] + "-" + r1["record_id"][6:8])), 2)

            store.register(d, r1["record_id"], "123")
            with self.assertRaises(store.AnswerError):
                store.register(d, r1["record_id"], "999")               # 二重登録しない
            rows = store.list_registered(d, pcode="123")
            self.assertEqual([r["number"] for r in rows], [1])

            rec = store.load_record(d, r1["record_id"])
            self.assertIn("〔主訴〕症状：その他（めまい）", rec["karte_text"])
            self.assertIn("喫煙本数：5本/日", rec["karte_text"])
            self.assertEqual(rec["definition_snapshot"]["id"], "sample_naika")
            with open(os.path.join(d, rec["txt_path"]), encoding="utf-8") as f:
                txt = f.read()
            self.assertIn("患者ID: 123", txt)
            self.assertIn("受付番号: 1", txt)
            self.assertIsNone(store.load_record(d, "../../etc"))
            # 登録されなかった回答も消えずに残る
            self.assertIsNone(store.load_record(d, r2["record_id"])["pcode"])


class KarteTextTest(unittest.TestCase):
    def test_basic_info_line(self):
        a = store.clean_answers(DEF, dict(REQ, sex={"value": "女性"}, age={"value": "34"}))
        text = karte.karte_text(DEF, a, "2026/11/04 10:00")
        self.assertIn("〔基本情報〕性別：女性／年齢：34歳", text)


if __name__ == "__main__":
    unittest.main()
