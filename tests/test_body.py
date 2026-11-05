import os
import re
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
from app import body, definitions, karte, store  # noqa: E402

DEF = definitions.load_file(os.path.join(ROOT, "definitions", "sample_seikei.yaml"))
BASE = {"symptom": {"value": ["痛い"]}}


class BodyDataTest(unittest.TestCase):
    def test_data_file_is_up_to_date(self):
        """web/body-data.js が tools/make_body.py の出力と同じであること（作り直し忘れを見つける）。"""
        from tools import make_body
        with open(os.path.join(ROOT, "web", "body-data.js"), encoding="utf-8") as f:
            self.assertEqual(f.read(), make_body.build(), "python -X utf8 tools/make_body.py を実行してください")

    def test_region_ids_match(self):
        """図の中の部位 id が app/body.py の一覧と過不足なく一致すること。"""
        with open(os.path.join(ROOT, "web", "body-data.js"), encoding="utf-8") as f:
            ids = set(re.findall(r'data-id=\\"([a-z_]+)\\"', f.read()))
        self.assertEqual(ids, set(body.REGIONS))


class BodyAnswerTest(unittest.TestCase):
    def test_single_site_is_main(self):
        a = store.clean_answers(DEF, dict(BASE, site={"value": ["r_foot"]}))
        self.assertEqual(a["site"], {"value": ["r_foot"], "main": "r_foot"})
        text = karte.karte_text(DEF, a, "2026/11/04 10:00")
        self.assertIn("〔主訴〕右足／症状：疼痛", text)
        self.assertIn("〔現病歴〕症状のある部位：右足", text)

    def test_many_sites_with_main(self):
        a = store.clean_answers(DEF, dict(BASE, site={"value": ["l_shoulder", "r_foot", "l_shoulder"], "main": "r_foot"}))
        self.assertEqual(a["site"]["value"], ["l_shoulder", "r_foot"])   # 重複は除く
        self.assertEqual(a["site"]["main"], "r_foot")
        text = karte.karte_text(DEF, a, "2026/11/04 10:00")
        self.assertIn("〔主訴〕右足（いちばんつらい）／症状：疼痛", text)
        self.assertIn("〔現病歴〕症状のある部位：左肩、右足", text)
        shown = karte.shown_questions(DEF, a)
        site = [s for s in shown if s["id"] == "site"][0]
        self.assertEqual(site["answer"], "左肩、右足（いちばんつらい）")

    def test_many_sites_without_main(self):
        a = store.clean_answers(DEF, dict(BASE, site={"value": ["l_shoulder", "r_foot"], "main": "nope"}))
        self.assertNotIn("main", a["site"])
        self.assertNotIn("いちばんつらい", karte.karte_text(DEF, a, "x"))

    def test_bad_region_and_required(self):
        with self.assertRaises(store.AnswerError):
            store.clean_answers(DEF, dict(BASE, site={"value": ["r_foot", "tail"]}))
        with self.assertRaises(store.AnswerError):
            store.clean_answers(DEF, BASE)

    def test_views_validation(self):
        bad = {"id": "x", "title": "x", "questions": [{"id": "s", "type": "body", "text": "t", "karte": "k", "views": ["front", "nose"]}]}
        with self.assertRaises(definitions.DefinitionError):
            definitions.validate(bad)


if __name__ == "__main__":
    unittest.main()
