"""要確認の印・回答にかかった時間・閲覧の記録・外国語の画面。"""

import os
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
from app import body, definitions, karte, lang, server, store, yamlmini  # noqa: E402
from creator import translate  # noqa: E402

DEF_YAML = """
id: "t"
title: "テスト問診票"
questions:
  - id: "allergy"
    type: "single"
    text: "薬で具合が悪くなったことはありますか？"
    karte: "薬剤副作用歴"
    tag: "アレルギー"
    options:
      - label: "ある"
        karte: "あり"
        alert: true
        detail: "薬の名前を教えてください"
      - label: "ない"
        karte: "なし"
  - id: "foods"
    type: "multi"
    text: "アレルギーのある食べ物を選んでください。"
    karte: "食物アレルギー内容"
    tag: "アレルギー"
    alert: true
    options:
      - label: "卵"
      - label: "そば"
  - id: "temp"
    type: "number"
    text: "体温を教えてください。"
    karte: "体温"
    unit: "℃"
  - id: "where"
    type: "body"
    text: "症状のある場所を選んでください。"
    karte: "症状部位"
    tag: "主訴"
"""


def make_def():
    return definitions.validate(yamlmini.load(DEF_YAML))


def english(defn):
    """テスト用の訳（Claude は呼ばない）。もとの言葉の前に EN: を付けただけ。"""
    src = translate.source(defn)
    for q in src["questions"]:
        q["text"] = "EN:" + q["text"]
        q["unit"] = "deg" if q["unit"] else ""
        for o in q["options"]:
            o["text"] = "EN:" + o["label"]
            o["detail"] = "EN:" + o["detail"] if o["detail"] else ""
    src["title"] = "EN:" + src["title"]
    return translate.to_file(defn, "en", src)


class AlertTest(unittest.TestCase):
    def test_marked_answers_only(self):
        d = make_def()
        a = store.clean_answers(d, {"allergy": {"value": "ある"}, "foods": {"value": ["そば", "卵"]}})
        self.assertEqual(karte.alerts(d, a), ["薬剤副作用歴：あり（記載がないので要聴取）", "食物アレルギー内容：卵、そば"])
        a = store.clean_answers(d, {"allergy": {"value": "ない"}})
        self.assertEqual(karte.alerts(d, a), [])

    def test_alert_must_be_bool(self):
        bad = yamlmini.load(DEF_YAML.replace("alert: true\n        detail", 'alert: "はい"\n        detail'))
        with self.assertRaises(definitions.DefinitionError):
            definitions.validate(bad)

    def test_single_region_not_repeated(self):
        d = make_def()
        one = karte.karte_text(d, store.clean_answers(d, {"where": {"value": ["r_knee"]}}), "")
        self.assertIn("〔主訴〕右ひざ", one)
        self.assertNotIn("症状部位", one)
        two = karte.karte_text(d, store.clean_answers(d, {"where": {"value": ["r_knee", "lower_back"], "main": "lower_back"}}), "")
        self.assertIn("腰（いちばんつらい）／症状部位：右ひざ、腰", two)


class LangTest(unittest.TestCase):
    def test_every_word_and_body_part_has_all_languages(self):
        for code in lang.LANGS:
            self.assertEqual(set(lang.UI[code]), set(lang.UI["ja"]))
            self.assertTrue(all(lang.UI[code].values()))
            self.assertEqual(set(lang.BODY[code]), set(body.REGIONS))
            self.assertEqual(len(set(lang.BODY[code].values())), len(body.REGIONS))   # 同じ名前の部位がない
        self.assertEqual(lang.body_label("r_knee", "en"), "Right knee")
        self.assertEqual(lang.body_label("r_knee"), "右ひざ")

    def test_translation_file_roundtrip(self):
        d = make_def()
        tr = yamlmini.load(yamlmini.dump(english(d)))
        got = definitions.check_i18n(d, tr)
        self.assertEqual(got["q"]["allergy"]["o"]["ある"], {"t": "EN:ある", "d": "EN:薬の名前を教えてください"})
        self.assertEqual(got["q"]["temp"]["unit"], "deg")

    def test_stale_or_incomplete_translation_rejected(self):
        d = make_def()
        tr = english(d)
        tr["questions"][1]["options"][0]["text"] = ""
        with self.assertRaises(definitions.DefinitionError):
            definitions.check_i18n(d, tr)
        tr = english(d)
        d["questions"][0]["text"] = "言葉を変えた"               # 問診票の言葉が変わったら、古い訳は使わない
        with self.assertRaises(definitions.DefinitionError):
            definitions.check_i18n(d, tr)
        d2 = make_def()
        d2["questions"][0]["options"][0]["alert"] = False        # 印やカルテ向けの言葉を変えただけなら、訳はそのまま使える
        definitions.check_i18n(d2, english(make_def()))

    def test_load_dir_attaches_translation(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "i18n"))
            with open(os.path.join(tmp, "t.yaml"), "w", encoding="utf-8") as f:
                f.write(DEF_YAML)
            with open(os.path.join(tmp, "i18n", "t.en.yaml"), "w", encoding="utf-8") as f:
                f.write(yamlmini.dump(english(make_def())))
            with open(os.path.join(tmp, "i18n", "t.zh-TW.yaml"), "w", encoding="utf-8") as f:
                f.write(yamlmini.dump(dict(english(make_def()), lang="zh-TW", key="old")))
            defs, errors = definitions.load_dir(tmp)
            self.assertEqual(list(defs["t"]["_i18n"]), ["en"])
            self.assertEqual(len(errors), 1)                     # 古い訳は出さず、理由を知らせる
            self.assertIn("t.zh-TW.yaml", errors[0])

    def test_rows_and_fix(self):
        d = make_def()
        result = {"file": english(d), "rows": translate.rows(d, english(d))}
        result["rows"][2]["issue"] = {"severity": "warning", "message": "", "suggestion": ""}
        self.assertEqual([r["where"] for r in result["rows"][:5]], ["題名", "設問", "選択肢", "記入欄", "選択肢"])
        translate.fix(result, 2, "Yes")
        translate.fix(result, 3, "Name of the medicine")
        self.assertEqual(result["file"]["questions"][0]["options"][0], {"label": "ある", "text": "Yes", "detail": "Name of the medicine"})
        self.assertEqual(result["issues"], 0)
        definitions.check_i18n(d, result["file"])


class StoreExtrasTest(unittest.TestCase):
    def test_seconds_lang_alerts_and_access_log(self):
        d = make_def()
        d["_i18n"] = {"en": definitions.check_i18n(d, english(d))}
        with tempfile.TemporaryDirectory() as tmp:
            store.init_db(tmp)
            store.init_db(tmp)                                   # 2回呼んでも列を足し直さない
            raw = {"allergy": {"value": "ある", "details": {"ある": "penicillin"}}, "where": {"value": ["r_knee", "neck"], "main": "neck"}}
            rec = store.save_pending(tmp, d, raw, {"seconds": 192, "lang": "en"})
            store.save_pending(tmp, d, raw, {"seconds": "x", "lang": "fr"})      # おかしな値は捨てる
            got = store.load_record(tmp, rec["record_id"])
            self.assertEqual((got["seconds"], got["lang"]), (192, "en"))
            self.assertEqual(got["alerts"], ["薬剤副作用歴：あり（penicillin）"])
            self.assertIn("〔アレルギー〕薬剤副作用歴：あり（penicillin）", got["karte_text"])   # カルテの文は日本語のまま
            first = got["shown"][0]
            self.assertEqual((first["answer"], first["text_shown"], first["answer_shown"]),
                             ("ある（penicillin）", "EN:薬で具合が悪くなったことはありますか？", "EN:ある (penicillin)"))
            self.assertEqual(got["shown"][-1]["answer_shown"], "Right knee, Neck (worst)")
            other = store.load_record(tmp, rec["record_id"][:-1] + "2")
            self.assertEqual((other["seconds"], other["lang"]), (None, None))
            self.assertNotIn("text_shown", other["shown"][0])

            client = {"ip": "192.0.2.10", "ua": "test"}
            self.assertTrue(store.log_access(tmp, "view", rec["record_id"], client))
            self.assertFalse(store.log_access(tmp, "view", rec["record_id"], client))          # 開き直しは重ねて書かない
            self.assertTrue(store.log_access(tmp, "view", rec["record_id"], {"ip": "192.0.2.11"}))
            store.register(tmp, rec["record_id"], "9000001")
            self.assertTrue(store.log_access(tmp, "copy", rec["record_id"], client))
            rows = store.list_access(tmp)
            self.assertEqual([(r["action"], r["pcode"], r["ip"]) for r in rows],
                             [("copy", "9000001", "192.0.2.10"), ("view", None, "192.0.2.11"), ("view", None, "192.0.2.10")])
            with open(os.path.join(tmp, store.load_record(tmp, rec["record_id"])["txt_path"]), encoding="utf-8") as f:
                txt = f.read()
            self.assertIn("回答にかかった時間: 3分12秒", txt)
            self.assertIn("画面の言語: English", txt)
            self.assertIn("（画面の表示）EN:薬で具合が悪くなったことはありますか？", txt)


class LanTest(unittest.TestCase):
    def test_creator_is_only_for_this_pc(self):
        self.assertTrue(server.is_local("127.0.0.1"))
        self.assertTrue(server.is_local("::1"))
        self.assertFalse(server.is_local("192.0.2.10"))          # タブレットなど、ほかの端末
        self.assertTrue(all(not a.startswith("127.") for a in server.lan_addresses()))


if __name__ == "__main__":
    unittest.main()
