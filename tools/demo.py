"""デモ・動作確認のための道具。本番の問診サーバーでは使わない（設定の demo.enabled が true のときだけ動く）。

  python -X utf8 tools/demo.py reset           回答を退避して空にする（受付番号が 1 からになる）
  python -X utf8 tools/demo.py seed            架空の患者さんの回答を登録する（samples/demo_patients.json）
  python -X utf8 tools/demo.py reset --seed    上の2つを続けて行う（デモの前に）
  python -X utf8 tools/demo.py export          （開発用）ダミー患者の確認結果から samples/demo_patients.json を作る

reset は回答を消さない。data/backup/日時/ へ移すだけなので、元に戻せる。
"""

import json
import os
import shutil
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import definitions, store, yamlmini  # noqa: E402

SAMPLE = os.path.join("samples", "demo_patients.json")
FIRST_PCODE = 9000001           # 架空の患者ID（実在の患者さんと重ならない番号にしている）


class DemoError(RuntimeError):
    pass


def load_config(root=ROOT):
    for name in ("config.yaml", "config.example.yaml"):
        path = os.path.join(root, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8-sig") as f:
                return yamlmini.load(f.read()) or {}
    return {}


def _paths(root, config):
    paths = config.get("paths", {})
    return (os.path.join(root, paths.get("data", "data")),
            [os.path.join(root, p) for p in paths.get("definitions", ["definitions"])])


def check_enabled(config):
    if not config.get("demo", {}).get("enabled"):
        raise DemoError("この道具は、設定の demo.enabled が true のときだけ使えます（本番では false のままにしてください）")


def count_records(data_dir):
    if not os.path.exists(store.db_path(data_dir)):
        return 0, 0
    rows = store._rows(data_dir, "SELECT COUNT(*) AS n, COALESCE(SUM(pcode IS NULL), 0) AS pending FROM records", ())
    return rows[0]["n"], rows[0]["pending"]


def reset(root, config, now=None):
    """回答（データベースと開示用TXT）を data/backup/日時/ へ移し、空のデータベースを作り直す。"""
    check_enabled(config)
    data_dir, _ = _paths(root, config)
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    backup = os.path.join(data_dir, "backup", stamp)
    targets = [n for n in ("tolmon.sqlite3", "tolmon.sqlite3-wal", "tolmon.sqlite3-shm", "answers")
               if os.path.exists(os.path.join(data_dir, n))]
    moved = []
    if targets:
        os.makedirs(backup)
        try:
            for n in targets:
                shutil.move(os.path.join(data_dir, n), os.path.join(backup, n))
                moved.append(n)
        except OSError as e:
            for n in moved:                      # 途中で止まったら、移した分を戻す
                shutil.move(os.path.join(backup, n), os.path.join(data_dir, n))
            raise DemoError(f"回答のファイルを移せませんでした。サーバーを止めてから、もう一度試してください（{e}）") from e
    store.init_db(data_dir)
    return backup if targets else None


def seed(root, config, sample_path=None):
    """架空の患者さんの回答を、本番と同じ手順（送信 → 患者IDの登録）で入れる。戻り値は結果の一覧。"""
    check_enabled(config)
    data_dir, def_dirs = _paths(root, config)
    path = sample_path or os.path.join(root, SAMPLE)
    if not os.path.exists(path):
        raise DemoError(f"架空の患者さんのデータがありません（{path}）")
    with open(path, encoding="utf-8-sig") as f:
        patients = json.load(f)["patients"]
    defs, _ = definitions.load_dir(*def_dirs)
    store.init_db(data_dir)
    out = []
    for p in patients:
        row = {"form_id": p["form_id"], "pcode": p.get("pcode"), "persona": p.get("persona", ""), "number": None, "error": ""}
        defn = defs.get(p["form_id"])
        if not defn:
            row["error"] = "この問診票が公開されていません"
        else:
            try:
                rec = store.save_pending(data_dir, defn, p["answers"], {"client": {"demo": True}})
                row["number"] = rec["number"]
                if p.get("pcode"):                # 患者IDがないものは「受付待ち」のまま残す
                    store.register(data_dir, rec["record_id"], str(p["pcode"]))
            except store.AnswerError as e:
                row["error"] = str(e)
        out.append(row)
    return out


def export(root, config, per_form=2):
    """（開発用）作る画面の「ダミー患者」の確認結果から、デモ用の架空の患者さんデータを作る。"""
    check_enabled(config)
    data_dir, def_dirs = _paths(root, config)
    defs, _ = definitions.load_dir(*def_dirs)
    draft_dir = os.path.join(data_dir, "creator_drafts")
    patients = []
    for name in sorted(os.listdir(draft_dir)) if os.path.isdir(draft_dir) else []:
        if not name.endswith(".json"):
            continue
        with open(os.path.join(draft_dir, name), encoding="utf-8") as f:
            draft = json.load(f)
        defn = defs.get(draft.get("form_id"))
        picked = 0
        for p in (draft.get("dummy") or {}).get("patients", []):
            if picked >= per_form or not defn or p.get("error") or not p.get("answers"):
                continue
            try:
                store.clean_answers(defn, p["answers"])      # 公開中の問診票で受け取れる回答だけを使う
            except store.AnswerError:
                continue
            patients.append({"form_id": defn["id"], "persona": p["persona"], "answers": p["answers"]})
            picked += 1
    for i, p in enumerate(patients):
        p["pcode"] = str(FIRST_PCODE + i)
    if len(patients) >= 2:
        patients[-1]["pcode"] = None                         # 最後の1人は「受付待ち」の見本にする
    body = {"note": "デモ・動作確認用の架空の患者さんです。Claude が作ったもので、実在の人物ではありません。",
            "patients": patients}
    path = os.path.join(root, SAMPLE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(body, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return path, patients


def main(argv):
    config = load_config()
    args = [a for a in argv if not a.startswith("--")]
    flags = [a for a in argv if a.startswith("--")]
    cmd = args[0] if args else ""
    if cmd not in ("reset", "seed", "export"):
        print(__doc__)
        return 1
    try:
        check_enabled(config)
        data_dir, _ = _paths(ROOT, config)
        if cmd == "export":
            path, patients = export(ROOT, config)
            print(f"{len(patients)} 人分を書き出しました：{path}")
            return 0
        if cmd == "reset":
            total, pending = count_records(data_dir)
            print(f"いまの回答：{total} 件（うち受付待ち {pending} 件）")
            print("回答を data/backup/ へ移して、空にします（消しません。受付番号は 1 からになります）。")
            if "--yes" not in flags and input("よければ reset と入力して Enter：").strip() != "reset":
                print("中止しました。何も変えていません。")
                return 1
            backup = reset(ROOT, config)
            print(f"空にしました。{'退避先：' + backup if backup else '（もともと回答はありませんでした）'}")
        if cmd == "seed" or "--seed" in flags:
            rows = seed(ROOT, config)
            for r in rows:
                state = r["error"] or (f"患者ID {r['pcode']}" if r["pcode"] else "受付待ち（患者IDなし）")
                print(f"  受付番号 {r['number'] if r['number'] else '-'}　{r['form_id']}　{state}　{r['persona'][:30]}")
            ok = sum(1 for r in rows if not r["error"])
            print(f"架空の患者さん {ok} 人の回答を登録しました。" + (f"（{len(rows) - ok} 人は登録できませんでした）" if ok < len(rows) else ""))
    except DemoError as e:
        print(f"できませんでした：{e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
