"""トルモン起動用。  使い方:  python -X utf8 run.py"""

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
            with open(path, encoding="utf-8-sig") as f:
                return yamlmini.load(f.read()) or {}
    return {}


if __name__ == "__main__":
    serve(ROOT, load_config())
