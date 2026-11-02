import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.yamlmini import YamlError, dump, load  # noqa: E402


class LoadTest(unittest.TestCase):
    def test_basic(self):
        text = """
# コメント
id: "naika"
title: 内科 初診
version: 1
active: true
memo: null
questions:
  - id: "q1"
    type: text
    text: "今日はどうされましたか？"
  - id: q2
    options:
      - label: "ある"
        detail: "薬の名前：（例）ロキソニン"
      - label: ない
"""
        d = load(text)
        self.assertEqual(d["id"], "naika")
        self.assertEqual(d["title"], "内科 初診")
        self.assertEqual(d["version"], 1)
        self.assertIs(d["active"], True)
        self.assertIsNone(d["memo"])
        self.assertEqual(len(d["questions"]), 2)
        self.assertEqual(d["questions"][1]["options"][0]["detail"], "薬の名前：（例）ロキソニン")
        self.assertEqual(d["questions"][1]["options"][1]["label"], "ない")

    def test_colon_hash_in_quotes(self):
        d = load('a: "時刻 12: 30 # これは文字"  # ここはコメント\nb: \'it\'\'s\'\n')
        self.assertEqual(d["a"], "時刻 12: 30 # これは文字")
        self.assertEqual(d["b"], "it's")

    def test_flow_list_and_empty(self):
        d = load('unit: [℃, "本/日", 3]\nempty: []\n')
        self.assertEqual(d["unit"], ["℃", "本/日", 3])
        self.assertEqual(d["empty"], [])

    def test_seq_same_indent_under_key(self):
        d = load("items:\n- a\n- b\nnext: 1\n")
        self.assertEqual(d, {"items": ["a", "b"], "next": 1})

    def test_bom_and_crlf(self):
        d = load('\ufeffa: "あ"\r\nb: 2\r\n')
        self.assertEqual(d, {"a": "あ", "b": 2})

    def test_errors(self):
        bad = [
            "a: |\n  multi\n",       # ブロック
            "a: &x 1\n",             # アンカー
            "a: {b: 1}\n",           # フロー辞書
            "a: 1\n\tb: 2\n",        # タブ
            "a: 1\na: 2\n",          # 重複キー
            'a: "閉じてない\n',       # クオート
            "a:\n    b: 1\n  c: 2\n",  # インデント崩れ
            "これはキーではない\nb: 1\n",
        ]
        for t in bad:
            with self.subTest(t=t):
                with self.assertRaises(YamlError):
                    load(t)


class RoundTripTest(unittest.TestCase):
    def test_roundtrip(self):
        data = {
            "id": "naika",
            "version": 2,
            "ratio": 0.5,
            "flag": False,
            "none": None,
            "questions": [
                {"id": "q1", "text": "「はい」: と答えた方 # 注意", "options": [{"label": "ある", "detail": "内容"}, {"label": "ない"}]},
                {"id": "q2", "show_if": {"q": "q1", "eq": "ある"}, "tags": []},
            ],
            "日本語キー": ["a", "b\nc", 'quote "x"'],
        }
        self.assertEqual(load(dump(data)), data)


if __name__ == "__main__":
    unittest.main()
