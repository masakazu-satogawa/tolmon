"""トルモン起動用。

  python -X utf8 run.py          このPCの中だけで使う（ふだんはこちら）
  python -X utf8 run.py --lan    同じネットワークのタブレットからも開けるようにする（実機で試すとき）
"""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from app import yamlmini  # noqa: E402
from app.server import serve  # noqa: E402

if sys.version_info[:2] != (3, 13):
    print(f"[注意] Python 3.13 で動作確認しています（今は {sys.version.split()[0]}）")


def load_config():
    for name in ("config.yaml", "config.example.yaml"):
        path = os.path.join(ROOT, name)
        if os.path.exists(path):
            if name != "config.yaml":
                print("[注意] config.yaml がないので、見本の config.example.yaml で動かします"
                      "（デモ用の画面が有効です。本番では config.yaml を作ってください）")
            with open(path, encoding="utf-8-sig") as f:
                return yamlmini.load(f.read()) or {}
    return {}


if __name__ == "__main__":
    if any(a in ("-h", "--help") for a in sys.argv[1:]):
        print(__doc__)
        sys.exit(0)
    config = load_config()
    if "--lan" in sys.argv[1:]:
        # 設定ファイルは書きかえない。この起動のあいだだけ、ほかの端末からの接続を受ける
        config.setdefault("server", {})["host"] = "0.0.0.0"
    serve(ROOT, config)
