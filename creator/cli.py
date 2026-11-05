"""コマンドから読み取りを試す。

  python -X utf8 -m creator.cli 帳票.pdf 問診ID [出力.yaml]

例: python -X utf8 -m creator.cli ../内科.pdf naika definitions/naika.yaml
"""

import json
import os
import sys

from . import claude_api, reader


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    path, form_id = argv[1], argv[2]
    media = reader.MEDIA.get(os.path.splitext(path)[1].lower())
    if not media:
        print("PDF・PNG・JPEG のどれかを指定してください")
        return 2
    with open(path, "rb") as f:
        data = f.read()
    try:
        r = reader.make_draft(data, media, form_id, os.path.basename(path))
    except claude_api.ClaudeError as e:
        print(f"失敗: {e}")
        return 1
    print(r["yaml"])
    print("=" * 60)
    print(f"設問 {len(r['definition']['questions'])} 個 / 見直し: {r['summary']}")
    for p in r["problems"]:
        print(f"[形式の問題] {p}")
    for i in r["issues"]:
        print(f"[{i['severity']}] {i['kind']} {i['question_id']}: {i['message']} → {i['suggestion']}")
    for s in r["skipped"]:
        print(f"[外した欄] {s['paper_text']} … {s['reason']}")
    for n in r["notes"]:
        print(f"[メモ] {n}")
    print(json.dumps(r["usage"], ensure_ascii=False))
    if len(argv) > 3:
        with open(argv[3], "w", encoding="utf-8", newline="\n") as f:
            f.write(r["yaml"])
        print(f"保存: {argv[3]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
