"""作る側のうち、Claude を呼ばない部分（変換・検証・保存）のテスト。"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
from app import definitions, yamlmini  # noqa: E402
from creator import reader, service  # noqa: E402


def q(qid, qtype="text", **kw):
    base = {"id": qid, "type": qtype, "text": "質問", "karte": "項目", "tag": "その他", "required": False,
            "hint": "", "unit": "", "options": [], "show_if": [], "source": "紙の文言"}
    base.update(kw)
    return base


DRAFT = {"title": "テスト問診票", "skipped": [], "notes": [], "questions": [
    q("sex", "single", tag="基本情報", options=[{"label": "男性", "karte": "男性", "detail": ""}, {"label": "女性", "karte": "女性", "detail": ""}]),
    q("age", "number", tag="基本情報", unit="歳"),
    q("allergy", "single", required=True, options=[{"label": "ある", "karte": "あり", "detail": "薬の名前"}, {"label": "ない", "karte": "なし", "detail": ""}]),
    q("pregnancy", "single", options=[{"label": "妊娠中", "karte": "妊娠中", "detail": ""}],
      show_if=[{"q": "sex", "op": "ne", "value": "男性"}, {"q": "age", "op": "lt", "value": "50"}]),
    q("site", "body", unit="使わない"),
    q("memo", "text", hint="例：なし", show_if=[{"q": "allergy", "op": "eq", "value": "ある"}]),
]}


class ConvertTest(unittest.TestCase):
    def test_to_definition(self):
        d = reader.to_definition(DRAFT, "test_form")
        self.assertEqual(reader.problems(d), [])
        byid = {x["id"]: x for x in d["questions"]}
        self.assertEqual(d["id"], "test_form")
        self.assertEqual(byid["age"]["unit"], "歳")
        self.assertNotIn("unit", byid["site"])                      # 数字以外に単位は付けない
        self.assertNotIn("options", byid["site"])
        self.assertTrue(byid["allergy"]["required"])
        self.assertEqual(byid["allergy"]["options"][0], {"label": "ある", "karte": "あり", "detail": "薬の名前"})
        self.assertEqual(byid["sex"]["options"][0], {"label": "男性"})   # label と同じ karte は省く
        self.assertEqual(byid["pregnancy"]["show_if"], {"all": [{"q": "sex", "ne": "男性"}, {"q": "age", "lt": 50}]})
        self.assertEqual(byid["memo"]["show_if"], {"q": "allergy", "eq": "ある"})

    def test_yaml_roundtrip(self):
        d = reader.to_definition(DRAFT, "test_form")
        text = reader.to_yaml(d, "テスト.pdf")
        self.assertEqual(yamlmini.load(text), d)
        definitions.validate(yamlmini.load(text))

    def test_problems_found(self):
        bad = {"title": "x", "skipped": [], "notes": [], "questions": [
            q("Q-1"), q("b", show_if=[{"q": "nothing", "op": "eq", "value": "a"}])]}
        probs = reader.problems(reader.to_definition(bad, "x1"))
        self.assertTrue(any("Q-1" in p for p in probs))
        self.assertTrue(any("nothing" in p for p in probs))


class ServiceTest(unittest.TestCase):
    def test_check_and_save(self):
        text = reader.to_yaml(reader.to_definition(DRAFT, "test_form"))
        self.assertTrue(service.check_yaml({"yaml": text})["ok"])
        self.assertFalse(service.check_yaml({"yaml": "a: |\n  x"})["ok"])
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(service.save({"yaml": text}, d)["ok"])
            self.assertTrue(service.save({"yaml": text}, d)["exists"])           # 黙って上書きしない
            self.assertTrue(service.save({"yaml": text, "overwrite": True}, d)["ok"])
            self.assertEqual(definitions.load_file(os.path.join(d, "test_form.yaml"))["title"], "テスト問診票")
            with self.assertRaises(service.ServiceError):
                service.save({"yaml": text.replace('"ある"', '"あ"', 1)}, d)

    def test_read_rejects_bad_input(self):
        for body in ({"form_id": "Bad ID", "name": "a.pdf", "data": "AAAA"},
                     {"form_id": "ok_id", "name": "a.txt", "data": "AAAA"},
                     {"form_id": "ok_id", "name": "a.pdf", "data": ""}):
            with self.subTest(body=body):
                with self.assertRaises(service.ServiceError):
                    service.read(body)


if __name__ == "__main__":
    unittest.main()
