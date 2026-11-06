"""README 用の画面写真を撮る（開発用）。サーバーを起動してから実行する。

  python -X utf8 tools/screenshots.py

Edge を画面なしで動かして、docs/img/ に PNG を書き出す。先に demo_reset.bat で架空の患者さんを登録しておくこと。
画面の一部だけを切り出すのに Pillow、紙の問診票（PDF）を画像にするのに PyMuPDF を使う（どちらも、なければその分を飛ばす）。
この道具は README を作るためのもので、問診のアプリ本体は標準ライブラリだけで動く。
"""

import json
import os
import subprocess
import sys
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "http://localhost:8080"
EDGE = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]
FORM = "seikei"                     # 作る画面・患者画面の写真に使う問診票
PAPER = os.path.join(ROOT, "..", "整形外科.pdf")     # 紙の問診票（リポジトリの外。あれば画像にする）
SHOTS = [                           # ファイル名、画面の大きさ、URL、切り出す範囲（左, 上, 右, 下。None ならそのまま）
    ("admin_top.png", "1440,900", f"/admin?form={FORM}", (0, 0, 1440, 535)),
    ("admin_questions.png", "1440,2500", f"/admin?form={FORM}", (590, 545, 1418, 2338)),
    ("admin_dummy.png", "1440,1900", f"/admin?form={FORM}&tab=dummy", (590, 545, 1418, 1900)),
    ("reception.png", "1024,768", "/", None),
    ("patient_body.png", "1024,768", "/?try=1&at=site", None),
    ("patient_choice.png", "1024,768", "/?try=1&at=onset", None),
    ("patient_number.png", "1024,768", "/?try=1&at=temp_now", None),
    ("karte.png", "1024,768", "/karte?pcode=9000007", None),
    ("karte_alert.png", "1024,620", "/karte?pcode=9000004", None),          # 要確認の印が付く人（妊娠中）
    ("admin_lang.png", "1440,1700", f"/admin?form={FORM}&tab=lang", (590, 545, 1418, 1700)),
]


def main():
    edge = next((p for p in EDGE if os.path.exists(p)), None)
    if not edge:
        print("Edge が見つかりません")
        return 1
    # 患者画面の写真は「お試し」で撮る。先に、下書きをお試しに入れておく
    draft = json.load(urllib.request.urlopen(f"{BASE}/api/creator/last?form_id={FORM}", timeout=20))
    req = urllib.request.Request(f"{BASE}/api/creator/trial", data=json.dumps({"yaml": draft["yaml"]}).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=20).read()
    out = os.path.join(ROOT, "docs", "img")
    os.makedirs(out, exist_ok=True)
    for name, size, path, box in SHOTS:
        target = os.path.join(out, name)
        with tempfile.TemporaryDirectory() as profile:
            subprocess.run([edge, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={profile}",
                            f"--window-size={size}", "--virtual-time-budget=8000", f"--screenshot={target}", BASE + path],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90, check=False)
        if box and os.path.exists(target):
            try:
                from PIL import Image
                with Image.open(target) as im:
                    part = im.crop(box)
                part.save(target)
            except ImportError:
                print("   （Pillow がないので、切り出さずにそのまま）")
        print(("OK " if os.path.exists(target) else "NG ") + name)
    if os.path.exists(PAPER):
        try:
            import pymupdf
            from PIL import Image
            pix = pymupdf.open(PAPER)[0].get_pixmap(dpi=110)
            Image.frombytes("RGB", (pix.width, pix.height), pix.samples).save(os.path.join(out, "paper.jpg"), quality=82)
            print("OK paper.jpg")
        except ImportError:
            print("   （PyMuPDF か Pillow がないので、紙の画像は作りません）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
