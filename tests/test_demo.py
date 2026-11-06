"""デモ用の道具（tools/demo.py）のテスト。回答は消さずに退避すること、本番では動かないこと。"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
from app import store  # noqa: E402
from tools import demo  # noqa: E402

CONFIG = {"demo": {"enabled": True}, "paths": {"data": "data", "definitions": ["definitions"]}}
ANSWERS = {"sex": {"value": "男性"}, "age": {"value": "70"}, "symptom": {"value": ["頭が痛い"]},
           "onset": {"value": "3日前から"}, "meds": {"value": "ない"}, "smoke": {"value": "吸わない"}}


class DemoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, "definitions"))
        shutil.copy(os.path.join(ROOT, "samples", "definitions", "sample_naika.yaml"), os.path.join(self.root, "definitions"))
        os.makedirs(os.path.join(self.root, "samples"))
        with open(os.path.join(self.root, "samples", "demo_patients.json"), "w", encoding="utf-8") as f:
            json.dump({"patients": [
                {"form_id": "sample_naika", "pcode": "9000001", "persona": "70歳の男性", "answers": ANSWERS},
                {"form_id": "sample_naika", "pcode": None, "persona": "受付待ちの人", "answers": ANSWERS},
                {"form_id": "nothing", "pcode": "9000003", "persona": "公開されていない問診票", "answers": {}},
                {"form_id": "sample_naika", "pcode": "9000004", "persona": "必須に答えていない", "answers": {}},
            ]}, f, ensure_ascii=False)
        self.data = os.path.join(self.root, "data")

    def tearDown(self):
        self.tmp.cleanup()

    def test_refused_unless_enabled(self):
        for config in ({}, {"demo": {"enabled": False}}):
            with self.subTest(config=config):
                with self.assertRaises(demo.DemoError):
                    demo.reset(self.root, config)
                with self.assertRaises(demo.DemoError):
                    demo.seed(self.root, config)
        self.assertFalse(os.path.exists(self.data))                  # 何も作っていない・触っていない

    def test_seed_and_reset(self):
        rows = demo.seed(self.root, CONFIG)
        self.assertEqual([(r["number"], bool(r["error"])) for r in rows], [(1, False), (2, False), (None, True), (None, True)])
        self.assertEqual(demo.count_records(self.data), (2, 1))      # 2件のうち1件は受付待ち
        day = datetime.now().strftime("%Y-%m-%d")
        self.assertEqual(len(store.list_registered(self.data, day, "9000001")), 1)
        self.assertEqual(len(store.list_pending(self.data, day)), 1)

        backup = demo.reset(self.root, CONFIG, now=datetime(2026, 11, 8, 9, 0, 0))
        self.assertEqual(demo.count_records(self.data), (0, 0))
        self.assertTrue(backup.endswith(os.path.join("backup", "20261108_090000")))
        self.assertTrue(os.path.exists(os.path.join(backup, "tolmon.sqlite3")))            # 消さずに退避している
        txts = [f for _, _, fs in os.walk(os.path.join(backup, "answers")) for f in fs]
        self.assertEqual(len(txts), 1)                               # 開示用TXTも一緒に退避
        self.assertFalse(os.path.exists(os.path.join(self.data, "answers")))

        rec = store.save_pending(self.data, {"id": "x", "title": "x", "questions": [
            {"id": "q", "type": "text", "text": "t", "karte": "k"}]}, {"q": {"value": "a"}}, {})
        self.assertEqual(rec["number"], 1)                           # 受付番号は1から
        self.assertIsNone(demo.reset(os.path.join(self.root, "empty"), CONFIG))             # 回答がなければ退避しない


if __name__ == "__main__":
    unittest.main()
