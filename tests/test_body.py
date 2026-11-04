import os
import re
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
from app import body, definitions, karte, store  # noqa: E402

DEF = definitions.load_file(os.path.join(ROOT, "definitions", "sample_seikei.yaml"))
BASE = {"symptom": {"value": ["痛い"]}}


class RegionSyncTest(unittest.TestCase):
    def test_js_ids_match_python(self):
        """web/body.js に出てくる部位 id が app/body.py の一覧と一致すること。"""
        with open(os.path.join(ROOT, "web", "body.js"), encoding="utf-8") as f:
            js = f.read()
        ids = set(re.findall(r'part\("([a-z_]+)"', js))
        # hand()/foot() で組み立てる id
        for side in ("r", "l"):
            ids.update(side + s for s in ("_palm", "_hand_back", "_wrist", "_thumb", "_index", "_middle", "_ring", "_little",
                                          "_sole", "_foot_top", "_toes", "_heel", "_ankle"))
        # pair() で組み立てる id は文字列リテラルで出てくる
        ids.update(re.findall(r'"([rl]_[a-z_]+)"', js))
        self.assertEqual(ids - set(body.REGIONS), set(), "JSにあってPythonにない id")
        self.assertEqual(set(body.REGIONS) - ids, set(), "PythonにあってJSにない id")


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
