import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
from app import definitions, store  # noqa: E402

DEF = definitions.load_file(os.path.join(ROOT, "definitions", "sample_naika.yaml"))


class CleanTest(unittest.TestCase):
    def test_required(self):
        with self.assertRaises(store.AnswerError):
            store.clean_answers(DEF, {})

    def test_bad_option_and_range(self):
        with self.assertRaises(store.AnswerError):
            store.clean_answers(DEF, {"symptom": {"value": ["存在しない"]}})
        with self.assertRaises(store.AnswerError):
            store.clean_answers(DEF, {"symptom": {"value": ["熱がある"]}, "temp": {"value": "50"}})

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


class SaveTest(unittest.TestCase):
    def test_save_and_list(self):
        with tempfile.TemporaryDirectory() as d:
            raw = {"symptom": {"value": ["その他"], "details": {"その他": "めまい"}}, "smoke": {"value": "吸っている"},
                   "smoke_num": {"value": "5"}}
            r1 = store.save(d, DEF, "123", raw, {"started_at": "x"})
            r2 = store.save(d, DEF, "123", raw, {})
            self.assertNotEqual(r1["record_id"], r2["record_id"])  # 同じ秒でも上書きしない
            self.assertIn("〔主訴〕症状：その他（めまい）", r1["karte_text"])
            self.assertIn("喫煙本数：5本/日", r1["karte_text"])
            rows = store.list_records(d, pcode="123")
            self.assertEqual(len(rows), 2)
            rec = store.load_record(d, r1["record_id"])
            self.assertEqual(rec["definition_snapshot"]["id"], "sample_naika")
            self.assertIsNone(store.load_record(d, "../../etc"))
            with open(os.path.join(d, "answers", "index.csv"), "rb") as f:
                self.assertTrue(f.read(3) == b"\xef\xbb\xbf")
            json.dumps(rec, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
