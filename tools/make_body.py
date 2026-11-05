"""人体シェーマの線画とタップの区切りを作り、web/body-data.js に書き出す（標準ライブラリのみ）。

  python -X utf8 tools/make_body.py          … web/body-data.js を作り直す

絵を直すとき・区切りを直すときは、このファイルを書き換えてから上のコマンドを実行する。
部位の id と表示名は app/body.py の REGIONS が正本（ここで使う id はすべて REGIONS にあること）。
「右・左」は患者さん本人から見た左右。
"""
import json
import math
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from app.body import REGIONS  # noqa: E402

OUT = os.path.join(ROOT, "web", "body-data.js")

INK = "#1d2422"
LINE = f'fill="none" stroke="{INK}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"'
THIN = LINE.replace("1.6", "1.2")
SKIN = f'fill="#ffffff" stroke="{INK}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"'
FINE = 'fill="none" stroke="#6b7773" stroke-width="1" stroke-linecap="round" stroke-linejoin="round"'
FILL = 'fill="#ffffff" stroke="none"'
DARK = f'fill="{INK}" stroke="none"'
HAIR = f'fill="#dfe4e1" stroke="{INK}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"'
STRAND = 'fill="none" stroke="#8a9590" stroke-width="0.9" stroke-linecap="round"'

USED = set()   # 図で使った部位 id（REGIONS との突き合わせ用）


# ====================================================================== 共通の部品
def mirror(d, w):
    """パスの x 座標を左右反転する（M/L/C の絶対座標だけを使うこと）。"""
    def rep(m):
        return f"{round(w - float(m.group(1)), 2)},{m.group(2)}"
    return re.sub(r"(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", rep, d)


def both(d, w, style):
    return f'<path d="{d}" {style}/><path d="{mirror(d, w)}" {style}/>'


def path(d, style=""):
    return f'<path d="{d}" {style}/>' if style else f'<path d="{d}"/>'


def ellipse(cx, cy, rx, ry, style="", rot=0):
    t = f' transform="rotate({rot} {cx} {cy})"' if rot else ""
    return f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" {style}{t}/>'


def poly(points):
    return '<polygon points="' + " ".join(f"{x},{y}" for x, y in points) + '"/>'


def mpoints(points, w):
    return [(w - x, y) for x, y in points]


def region(rid, shapes, clip=None):
    """タップできる区切り。clip を付けると、その輪郭の内側だけが反応する。"""
    if rid not in REGIONS:
        raise SystemExit(f"部位 id「{rid}」が app/body.py の REGIONS にありません")
    USED.add(rid)
    c = f' clip-path="url(#{clip})"' if clip else ""
    return f'<g class="part" data-id="{rid}"{c}>{shapes}</g>'


def text(x, y, s, cls):
    return f'<text x="{x}" y="{y}" class="label {cls}" text-anchor="middle">{s}</text>'


def placed(x, y, inner, flip_w=None):
    """図を (x, y) に置く。flip_w を渡すと左右反転する。"""
    t = f"translate({x + flip_w},{y}) scale(-1,1)" if flip_w else f"translate({x},{y})"
    return f'<g transform="{t}">{inner}</g>'


# ====================================================================== 全身
BW, BH = 220, 440

# 体の左半分の輪郭（画面の左側）。首の上から、腕→脇→胴→脚→股まで
HALF = {
    "m": ("M 110,66 L 98,66 "
          "C 98,74 97,81 94,85 "            # 首
          "C 84,91 70,93 60,96 "            # 僧帽筋〜肩
          "C 52,98 47,105 46,116 "          # 三角筋
          "C 45,130 44,140 43,150 "         # 上腕の外側
          "C 42,160 40,166 38,174 "         # ひじ
          "C 34,188 28,204 24,220 "         # 前腕の外側
          "C 22,226 19,231 16,236 "         # 手首〜親指のつけ根
          "C 12,240 10,246 13,248 "         # 親指
          "C 16,249 19,246 21,243 "
          "C 20,251 20,260 22,266 "         # 指
          "C 25,271 31,269 33,263 "
          "C 36,254 38,244 40,236 "         # 手の内側
          "C 41,230 42,226 43,222 "         # 手首の内側
          "C 48,206 54,190 58,176 "         # 前腕の内側
          "C 62,164 66,150 71,134 "         # 上腕の内側〜脇
          "C 73,150 72,168 72,184 "         # 胴の横
          "C 72,198 70,210 69,222 "         # 腰
          "C 68,240 70,262 74,282 "         # 太ももの外側
          "C 77,294 80,300 81,308 "         # ひざの外側
          "C 82,318 79,330 80,342 "         # ふくらはぎ
          "C 81,362 86,384 88,398 "         # 足首の外側
          "{foot}"
          "C 101,380 104,360 104,342 "      # ふくらはぎの内側
          "C 104,328 101,318 101,306 "      # ひざの内側
          "C 102,290 106,262 110,238"),     # 太ももの内側〜股
    # 女性：肩幅を狭く、ウエストを細く、腰を広く、腕を細く
    "f": ("M 110,66 L 100,66 "
          "C 100,74 99,81 96,85 "
          "C 88,90 76,93 67,96 "
          "C 59,98 55,105 54,115 "
          "C 53,129 52,140 51,150 "
          "C 50,160 48,166 46,174 "
          "C 42,188 35,204 31,220 "
          "C 29,226 26,231 23,236 "
          "C 19,240 17,246 20,248 "
          "C 23,249 26,246 28,243 "
          "C 27,251 27,260 29,266 "
          "C 32,271 37,269 39,263 "
          "C 41,254 43,244 45,236 "
          "C 46,230 47,226 48,222 "
          "C 52,206 57,190 61,176 "
          "C 65,164 69,150 73,134 "
          "C 75,148 79,164 79,178 "         # ウエスト
          "C 78,192 68,206 66,224 "         # 腰
          "C 65,242 68,264 73,284 "
          "C 76,295 80,300 81,308 "
          "C 82,318 80,330 81,342 "
          "C 82,362 86,384 88,398 "
          "{foot}"
          "C 101,380 103,360 103,342 "
          "C 103,328 101,318 101,306 "
          "C 102,290 106,262 110,239"),
}
FOOT_FRONT = "C 89,406 84,414 76,422 C 71,427 72,431 80,431 C 90,431 99,428 100,420 C 100,412 98,404 99,398 "
FOOT_BACK = "C 88,406 85,416 84,424 C 84,431 97,431 99,424 C 100,414 98,404 99,398 "
HEAD_HALF = "M 110,9 C 97,9 89,19 89,35 C 89,46 91,54 95,61 C 99,68 104,73 110,73"
EAR_HALF = "M 89,36 C 85,34 84,43 86,47 C 87,50 89,50 90,49"
FINGERS_LINE = {"m": "M 24.5,268 L 26,254 M 28,269.5 L 29.5,255 M 31,267.5 L 32.5,254",
                "f": "M 31.5,268 L 33,254 M 35,269.5 L 36,255 M 37.6,267.5 L 39,254"}

# 全身図の髪（小さい図）
B_HAIR = {
    ("m", False): "M 89,37 C 86,18 98,6 110,6 C 122,6 134,18 131,37 C 129,26 121,19 112,20 C 104,17 93,23 89,37 Z",
    ("m", True): "M 89,37 C 86,18 98,6 110,6 C 122,6 134,18 131,37 C 131,48 128,56 124,61 C 118,66 102,66 96,61 C 92,56 89,48 89,37 Z",
    ("f", False): ("M 110,5 C 94,5 84,17 85,38 C 84,52 86,64 89,74 L 95,71 C 92,60 90,48 91,37 "
                   "C 95,28 103,22 112,21 C 120,22 126,28 129,37 C 130,48 128,60 125,71 L 131,74 "
                   "C 134,64 136,52 135,38 C 136,17 126,5 110,5 Z"),
    ("f", True): "M 110,5 C 94,5 84,17 85,38 C 84,54 86,68 90,79 C 100,84 120,84 130,79 C 134,68 136,54 135,38 C 136,17 126,5 110,5 Z",
}
B_STRANDS = {
    ("m", False): "M 112,20 C 111,15 112,10 114,7 M 102,20 C 99,16 98,12 99,8 M 122,22 C 124,18 124,13 122,9",
    ("m", True): "M 110,8 C 109,26 109,46 110,64 M 100,10 C 96,26 96,46 100,62 M 120,10 C 124,26 124,46 120,62",
    ("f", False): "M 112,21 C 111,15 112,10 114,6 M 100,23 C 94,28 91,34 91,40 M 122,23 C 127,28 129,34 129,40 M 87,44 C 86,54 87,64 91,72 M 133,44 C 134,54 133,64 129,72",
    ("f", True): "M 110,7 C 109,30 109,56 110,82 M 99,9 C 94,30 94,58 98,80 M 121,9 C 126,30 126,58 122,80 M 90,22 C 87,42 88,62 92,77 M 130,22 C 133,42 132,62 128,77",
}


def body_art(back, sex):
    w = BW
    out = []
    half = HALF[sex].format(foot=FOOT_BACK if back else FOOT_FRONT)
    out.append(f'<path d="{half} L 110,66 Z" {FILL}/><path d="{mirror(half, w)} L 110,66 Z" {FILL}/>')
    out.append(both(half, w, LINE))
    out.append(both(FINGERS_LINE[sex], w, FINE))
    out.append(both(EAR_HALF, w, SKIN))
    out.append(ellipse(110, 41, 21, 32, FILL))
    out.append(both(HEAD_HALF, w, LINE))
    out.append(path(B_HAIR[(sex, back)], HAIR.replace("1.4", "1.2")))
    out.append(path(B_STRANDS[(sex, back)], STRAND.replace("0.9", "0.7")))
    f = sex == "f"
    if not back:
        out.append(both("M 99,38.5 C 101,37.3 104,37.3 106,38.3", w, FINE))                       # まゆ
        out.append(f'<circle cx="102.8" cy="43" r="1.5" {DARK}/><circle cx="117.2" cy="43" r="1.5" {DARK}/>')  # 目（点）
        out.append(path("M 108.3,52 C 109.3,53.3 110.7,53.3 111.7,52", FINE))                      # 鼻
        out.append(path("M 105,59.5 C 108,62.8 112,62.8 115,59.5", LINE.replace("1.6", "1.1")))    # 口
        if f:
            out.append(both("M 104,90 C 97,90 88,93 78,96", w, FINE))                             # 鎖骨
            out.append(both("M 80,128 C 79,142 92,149 105,141", w, FINE))                         # 胸
            out.append(f'<circle cx="110" cy="196" r="1.6" {FINE}/>')
            out.append(both("M 75,226 C 86,234 100,240 108,241", w, FINE))                        # 脚のつけ根
        else:
            out.append(both("M 104,90 C 96,90 84,93 72,96", w, FINE))
            out.append(both("M 74,134 C 82,146 98,148 108,142", w, FINE))
            out.append(f'<circle cx="110" cy="200" r="1.6" {FINE}/>')
            out.append(both("M 78,224 C 88,232 100,238 108,239", w, FINE))
        out.append(both("M 84,300 C 87,306 96,306 99,300", w, FINE))                              # ひざ
        out.append(both("M 76,424 L 78,429 M 82,426 L 83,430 M 88,426 L 88,430", w, FINE))        # 足の指
    else:
        out.append(path(f"M 110,{88 if f else 84} L 110,214", FINE))                               # 背骨
        out.append(both("M 86,110 C 88,122 95,130 102,130" if f else "M 84,110 C 86,124 94,132 102,132", w, FINE))  # 肩甲骨
        out.append(both("M 96,196 C 100,200 104,200 108,198", w, FINE))                           # 腰
        out.append(path("M 110,222 L 110,243", FINE))                                              # おしりの割れ目
        out.append(both("M 74,246 C 86,253 102,251 109,243" if f else "M 78,244 C 88,251 102,249 109,242", w, FINE))
        out.append(both("M 85,305 L 99,305", w, FINE))                                            # ひざ裏
        out.append(both("M 47,172 C 50,176 54,176 57,173" if f else "M 39,172 C 42,176 46,176 49,173", w, FINE))  # ひじ
    return "".join(out)


# 腕と胴のあいだ（すき間のまん中）の x 座標。高さごとに決めておく
ARM_GAP = {
    "m": {112: 71, 134: 71, 152: 69, 182: 64, 216: 58, 228: 56, 278: 53},
    "f": {112: 73, 134: 73, 152: 72, 182: 69, 216: 58, 228: 57, 278: 55},
}


def body_regions(back, sex):
    """全身図の区切り。大まかな多角形を、体の輪郭で切り抜いて使う。"""
    w = BW
    a = ARM_GAP[sex]
    cid = f"cb_{sex}{'b' if back else 'f'}"
    half = HALF[sex].format(foot=FOOT_BACK if back else FOOT_FRONT)
    defs = (f'<clipPath id="{cid}"><path d="{half} L 110,66 Z"/><path d="{mirror(half, w)} L 110,66 Z"/>'
            + ellipse(110, 41, 21.5, 32.5) + path(B_HAIR[(sex, back)]) + path(EAR_HALF) + path(mirror(EAR_HALF, w))
            + "</clipPath>")
    # 画面の左半分（x<110）の区切り。右半分は鏡写し
    side = {
        "shoulder": [(28, 80), (92, 80), (92, 90), (84, 90), (84, 112), (28, 112)],
        "upper_arm": [(18, 112), (a[112], 112), (a[134], 134), (a[152], 152), (18, 152)],
        "elbow": [(12, 152), (a[152], 152), (a[182], 182), (8, 182)],
        "forearm": [(6, 182), (a[182], 182), (a[216], 216), (2, 216)],
        "wrist": [(0, 216), (a[216], 216), (a[228], 228), (0, 228)],
        "hand": [(0, 228), (a[228], 228), (a[278], 278), (0, 278)],
        "hip": [(a[216], 212), (110, 212), (110, 246), (54, 246), (a[228], 228)],
        "thigh": [(54, 246), (110, 246), (110, 292), (58, 292)],
        "knee": [(58, 292), (110, 292), (110, 318), (58, 318)],
        "shin": [(58, 318), (110, 318), (110, 388), (58, 388)],
        "ankle": [(58, 388), (110, 388), (110, 404), (58, 404)],
        "foot": [(52, 404), (110, 404), (110, 440), (52, 440)],
    }
    chest = [(84, 90), (110, 90), (110, 150), (a[152], 150), (a[134], 134), (a[112], 112), (84, 112)]
    abdomen = [(a[152], 150), (110, 150), (110, 212), (a[216], 212), (a[182], 182)]
    neck = [(97, 62), (123, 62), (128, 90), (92, 90)]
    names = ({"hip": "buttock", "thigh": "thigh_back", "knee": "knee_back", "shin": "calf", "foot": "heel"} if back else {})
    out = []

    def full(points):
        return poly(points) + poly(mpoints(points, w))

    out.append(region("upper_back" if back else "chest", full(chest), cid))
    out.append(region("lower_back" if back else "abdomen", full(abdomen), cid))
    out.append(region("neck_back" if back else "neck", poly(neck), cid))
    # 頭：女性は髪が首の横まであるので、その分だけ下まで
    low = (84 if back else 76) if sex == "f" else (66 if back else 74)
    if back:
        out.append(region("head_back_l", poly([(78, 0), (110, 0), (110, low), (78, low)]), cid))
        out.append(region("head_back_r", poly([(110, 0), (142, 0), (142, low), (110, low)]), cid))
    elif sex == "f":
        out.append(region("head", poly([(78, 0), (142, 0), (142, 76), (124, 76), (118, 74), (102, 74), (96, 76), (78, 76)]), cid))
    else:
        out.append(region("head", poly([(82, 0), (138, 0), (138, 50), (126, 66), (118, 74), (102, 74), (94, 66), (82, 50)]), cid))
    # 画面の左側は、正面図では患者さんの右、背面図では患者さんの左
    left, right = ("l", "r") if back else ("r", "l")
    for name, pts in side.items():
        rid = names.get(name, name)
        out.append(region(f"{left}_{rid}", poly(pts), cid))
        out.append(region(f"{right}_{rid}", poly(mpoints(pts, w)), cid))
    hints = (text(26, 14, "左側", "hint") + text(194, 14, "右側", "hint")) if back else (text(26, 14, "右側", "hint") + text(194, 14, "左側", "hint"))
    return defs, "".join(out) + hints


def body_figure(back, sex):
    defs, regions = body_regions(back, sex)
    return {"w": BW, "h": BH, "html": f"<defs>{defs}</defs>" + body_art(back, sex) + regions}


# ====================================================================== 頭
HW, HH = 160, 200
SKULL_HALF = "M 80,14 C 55,14 41,34 41,64 C 41,82 44,97 50,111 C 57,127 68,138 80,138"
EAR2_HALF = "M 42,68 C 34,64 32,78 35,88 C 37,95 41,96 44,94"
NECK_HALF = "M 63,129 C 63,144 61,156 56,163 C 46,170 28,175 12,182"
NECK_SHAPE = ("M 63,122 C 63,144 61,156 56,163 C 46,170 28,175 12,182 L 12,200 L 148,200 L 148,182 "
              "C 132,175 114,170 104,163 C 99,156 97,144 97,122 Z")

H_HAIR = {
    ("m", False): "M 41,66 C 36,30 56,8 80,8 C 104,8 124,30 119,66 C 116,48 104,37 86,38 C 70,32 50,42 41,66 Z",
    ("m", True): ("M 41,66 C 36,30 56,8 80,8 C 104,8 124,30 119,66 C 119,84 116,98 110,110 "
                  "C 100,121 60,121 50,110 C 44,98 41,84 41,66 Z"),
    # 女性：あごの下まであるボブ。前は横に流した前髪
    ("f", False): ("M 80,5 C 50,5 31,30 33,66 C 31,100 35,130 43,154 L 57,149 C 49,126 45,98 45,70 "
                   "C 50,52 64,41 84,39 C 100,41 111,52 115,70 C 115,98 111,126 103,149 L 117,154 "
                   "C 125,130 129,100 127,66 C 129,30 110,5 80,5 Z"),
    ("f", True): ("M 80,5 C 50,5 31,30 33,66 C 31,102 35,134 43,158 C 60,165 100,165 117,158 "
                  "C 125,134 129,102 127,66 C 129,30 110,5 80,5 Z"),
}
H_STRANDS = {
    ("m", False): ("M 86,38 C 84,28 86,18 91,10 M 72,35 C 66,28 64,20 66,12 M 58,42 C 52,35 50,27 52,20 "
                   "M 48,54 C 44,48 43,40 45,33 M 100,39 C 104,30 104,22 101,13 M 111,48 C 115,40 115,31 112,23"),
    ("m", True): ("M 80,12 C 78,48 78,84 80,116 M 67,14 C 59,48 59,84 65,114 M 93,14 C 101,48 101,84 95,114 "
                  "M 55,24 C 47,52 48,86 55,108 M 105,24 C 113,52 112,86 105,108"),
    ("f", False): ("M 84,39 C 82,28 84,17 89,8 M 84,39 C 70,32 55,38 47,58 M 84,39 C 98,34 109,42 114,58 "
                   "M 70,36 C 62,30 58,22 60,13 M 100,38 C 106,30 108,22 105,13 "
                   "M 38,74 C 36,102 39,128 46,150 M 122,74 C 124,102 121,128 114,150 "
                   "M 50,112 C 51,126 53,138 56,148 M 110,112 C 109,126 107,138 104,148"),
    ("f", True): ("M 80,9 C 78,60 78,112 80,162 M 66,11 C 58,58 58,112 63,160 M 94,11 C 102,58 102,112 97,160 "
                  "M 53,20 C 44,62 45,116 51,158 M 107,20 C 116,62 115,116 109,158 "
                  "M 42,40 C 36,76 38,122 45,154 M 118,40 C 124,76 122,122 115,154"),
}


def head_art(back, sex):
    w = HW
    f = sex == "f"
    out = [both(NECK_HALF, w, LINE), both(EAR2_HALF, w, SKIN), ellipse(80, 76, 38.5, 61.5, FILL), both(SKULL_HALF, w, LINE)]
    out.append(path(H_HAIR[(sex, back)], HAIR))
    out.append(path(H_STRANDS[(sex, back)], STRAND))
    if back:
        if not f:
            out.append(path("M 80,142 L 80,186", FINE))                                            # 首のうしろ
    else:
        brow = "M 55,68 C 59,65 66,65 71,67" if f else "M 54,67 C 59,63.5 66,63.5 71,66"
        out.append(both(brow, w, FINE.replace('stroke-width="1"', 'stroke-width="1.1"' if f else 'stroke-width="1.4"')))
        out.append(f'<circle cx="63" cy="77" r="2.9" {DARK}/><circle cx="97" cy="77" r="2.9" {DARK}/>')  # 目（点）
        out.append(path("M 75,97 C 77.5,100.5 82.5,100.5 85,97" if f else "M 74,97 C 77,101 83,101 86,97", THIN))  # 鼻
        out.append(path("M 69,112 C 75,118 85,118 91,112" if f else "M 68,112 C 74,118 86,118 92,112", THIN))      # 口
    return "".join(out)


def head_regions(back, sex):
    w = HW
    k = f"{sex}{'b' if back else 'f'}"
    c_skull, c_hair, c_all = f"ch_s_{k}", f"ch_h_{k}", f"ch_a_{k}"
    skull = ellipse(80, 76, 39.5, 62.5)
    ears = path(EAR2_HALF) + path(mirror(EAR2_HALF, w))
    hair = path(H_HAIR[(sex, back)])
    defs = (f'<clipPath id="{c_skull}">{skull}</clipPath>'
            f'<clipPath id="{c_hair}">{skull}{hair}</clipPath>'
            f'<clipPath id="{c_all}">{skull}{hair}{ears}{path(NECK_SHAPE)}</clipPath>')
    out = []
    top = [(20, 0), (140, 0), (140, 40), (20, 40)]
    temple = [(20, 40), (46, 40), (46, 66), (20, 66)]
    ear = [(20, 66), (42, 66), (42, 100), (20, 100)]
    if back:
        # 頭の後ろ：画面の左が患者さんの左
        out.append(region("neck_back", poly([(26, 114), (134, 114), (136, 172), (24, 172)]), c_all))
        out.append(region("head_back_l", poly([(20, 40), (80, 40), (80, 114), (20, 114)]), c_all))
        out.append(region("head_back_r", poly([(80, 40), (140, 40), (140, 114), (80, 114)]), c_all))
        out.append(region("head_top", poly(top), c_all))
        out.append(region("l_temple", poly(temple), c_all))
        out.append(region("r_temple", poly(mpoints(temple, w)), c_all))
        out.append(region("l_ear", poly(ear), c_all))
        out.append(region("r_ear", poly(mpoints(ear, w)), c_all))
        hints = text(18, 12, "左側", "hint") + text(142, 12, "右側", "hint")
    else:
        # 顔：画面の左が患者さんの右
        cheek = [(38, 66), (47, 66), (47, 86), (70, 86), (70, 104), (63, 104), (63, 124), (38, 124)]
        eye = [(47, 62), (76, 62), (76, 86), (47, 86)]
        out.append(region("neck", poly([(28, 100), (132, 100), (134, 172), (26, 172)]), c_all))
        out.append(region("head_top", poly(top), c_hair))
        out.append(region("r_temple", poly(temple), c_hair))
        out.append(region("l_temple", poly(mpoints(temple, w)), c_hair))
        out.append(region("r_ear", poly(ear), c_all))
        out.append(region("l_ear", poly(mpoints(ear, w)), c_all))
        out.append(region("forehead", poly([(46, 40), (114, 40), (114, 62), (46, 62)]), c_skull))
        out.append(region("r_cheek", poly(cheek), c_skull))
        out.append(region("l_cheek", poly(mpoints(cheek, w)), c_skull))
        out.append(region("r_eye", poly(eye), c_skull))
        out.append(region("l_eye", poly(mpoints(eye, w)), c_skull))
        out.append(region("nose", poly([(76, 62), (84, 62), (84, 86), (90, 86), (90, 104), (70, 104), (70, 86), (76, 86)]), c_skull))
        out.append(region("mouth", poly([(63, 104), (97, 104), (97, 124), (63, 124)]), c_skull))
        out.append(region("chin", poly([(46, 124), (114, 124), (114, 142), (46, 142)]), c_skull))
        hints = text(18, 12, "右側", "hint") + text(142, 12, "左側", "hint")
    return defs, "".join(out) + hints


def head_figure(sex):
    d1, r1 = head_regions(False, sex)
    d2, r2 = head_regions(True, sex)
    html = (f"<defs>{d1}{d2}</defs>"
            + placed(0, 0, head_art(False, sex) + r1) + placed(170, 0, head_art(True, sex) + r2)
            + text(80, 214, "顔", "cap") + text(250, 214, "頭の後ろ", "cap"))
    return {"w": 330, "h": 220, "html": html}


# ====================================================================== 手
def base_points(cx, cy, w, angle):
    a = math.radians(angle)
    dx, dy = (w / 2) * math.cos(a), (w / 2) * math.sin(a)
    return (round(cx - dx, 2), round(cy - dy, 2)), (round(cx + dx, 2), round(cy + dy, 2))


def capsule(cx, cy, w, length, angle, style="", extra="", closed=False):
    r = w / 2
    d = f"M {-r},0 L {-r},{-(length - r)} A {r} {r} 0 0 1 {r},{-(length - r)} L {r},0" + (" Z" if closed else "")
    return f'<g transform="translate({cx},{cy}) rotate({angle})">{path(d, style)}{extra}</g>'


# 親指が左にある手（右手の甲／左手のひら）。指は 人さし指・中指・薬指・小指 の順
FINGER_IDS = ["index", "middle", "ring", "little"]
FINGERS = [(45, 86, 14, 50, -7), (60, 82, 14.5, 58, -1), (74, 85, 13.5, 52, 5), (87, 93, 12, 40, 13)]
THUMB = (33, 113, 16, 44, -42)


def hand_parts():
    pts = [base_points(cx, cy, w, a) for cx, cy, w, _, a in FINGERS]
    t_up, t_low = base_points(THUMB[0], THUMB[1], THUMB[2], THUMB[4])
    palm_poly = [pts[0][0]] + [p for pair in pts for p in pair] + [(88, 146), (84, 188), (38, 188), (35, 154), t_low, t_up]
    lower = f"M {t_low[0]},{t_low[1]} C 28,140 35,154 38,166 L 38,188 L 84,188 L 84,166 C 84,162 85,156 88,146 Z"
    return pts, t_up, t_low, palm_poly, lower


def hand_art(palm):
    pts, t_up, t_low, palm_poly, lower = hand_parts()
    first_l, last_r = pts[0][0], pts[-1][1]
    out = [f'<polygon points="{" ".join(f"{x},{y}" for x, y in palm_poly)}" {FILL}/>', path(lower, FILL)]
    out.append(path(f"M {first_l[0]},{first_l[1]} C 37,96 37,104 {t_up[0]},{t_up[1]}", LINE))
    out.append(path(f"M {t_low[0]},{t_low[1]} C 28,140 35,154 38,166 L 38,188", LINE))
    out.append(path(f"M {last_r[0]},{last_r[1]} C 94,110 92,130 88,146 C 85,156 84,162 84,166 L 84,188", LINE))
    for i in range(len(pts) - 1):   # 指のまたをつなぐ
        a, b = pts[i][1], pts[i + 1][0]
        out.append(path(f"M {a[0]},{a[1]} L {b[0]},{b[1]}", LINE))
    for cx, cy, w, length, angle in FINGERS + [THUMB]:
        r = w / 2
        if palm:   # 指の節のしわ
            extra = "".join(path(f"M {-r * .7},{-length * k} L {r * .7},{-length * k}", FINE) for k in (0.34, 0.62))
        else:      # 爪と節
            extra = (path(f"M {-r * .55},{-(length - r * 1.5)} L {-r * .55},{-(length - r * .7)} A {r * .55} {r * .55} 0 0 1 {r * .55},{-(length - r * .7)} L {r * .55},{-(length - r * 1.5)} Z", FINE)
                     + "".join(path(f"M {-r * .6},{-length * k} C {-r * .2},{-length * k - 1.5} {r * .2},{-length * k - 1.5} {r * .6},{-length * k}", FINE) for k in (0.32, 0.56)))
        out.append(capsule(cx, cy, w, length, angle, SKIN, extra))
    if palm:
        for d in ("M 42,108 C 55,99 76,100 91,110", "M 39,119 C 54,115 70,119 84,131",
                  "M 51,113 C 44,130 46,150 55,166", "M 40,170 C 54,173 70,173 83,170"):
            out.append(path(d, FINE))
    else:
        out.append(path("M 46,100 L 47,112 M 61,97 L 61,110 M 74,100 L 73,112 M 85,106 L 83,116", FINE))
    return "".join(out)


def hand_regions(side, palm):
    _, _, _, palm_poly, lower = hand_parts()
    out = [region(f"{side}_{'palm' if palm else 'hand_back'}", poly(palm_poly) + path(lower))]
    out.append(region(f"{side}_wrist", poly([(36, 164), (86, 164), (86, 190), (36, 190)])))
    for fid, (cx, cy, w, length, angle) in zip(FINGER_IDS + ["thumb"], FINGERS + [THUMB]):
        out.append(region(f"{side}_{fid}", capsule(cx, cy, w + 2, length + 1, angle, closed=True)))
    return "".join(out)


def hands_figure():
    def one(x, y, side, palm):
        thumb_left = (side == "r") != palm          # 右手の甲・左手のひら → 親指が画面の左
        return placed(x, y, hand_art(palm) + hand_regions(side, palm), None if thumb_left else 120)
    html = (one(0, 0, "l", False) + one(130, 0, "r", False) + one(0, 212, "l", True) + one(130, 212, "r", True)
            + text(60, 204, "左手の甲", "cap") + text(190, 204, "右手の甲", "cap")
            + text(60, 416, "左手のひら", "cap") + text(190, 416, "右手のひら", "cap"))
    return {"w": 250, "h": 422, "html": html}


# ====================================================================== 足
# 足の裏（親指が右＝右足の裏）。つま先が上
SOLE = ("M 22,72 C 16,92 18,122 24,147 C 27,168 31,192 45,195 C 59,197 65,181 65,161 C 65,141 60,127 64,107 "
        "C 68,92 75,82 73,66 C 71,55 61,50 50,50 C 38,50 26,57 22,72 Z")
SOLE_TOES = [(63, 36, 11, 15, 4), (46.5, 30, 7, 10.5, -4), (35.5, 34, 6.2, 9.5, -10), (26.5, 41, 5.6, 8.5, -16), (18.5, 50, 5, 7.5, -22)]
# 足の甲（前から見た図。親指が右＝右足）。すねが上、つま先が下
TOP_BODY = ("M 31,2 C 31,40 30,78 25,104 C 20,126 9,146 7,164 C 6,174 12,180 20,180 "
            "L 80,182 C 88,182 92,174 90,164 C 87,146 76,128 72,106 C 68,80 64,40 64,2")
TOP_TOES = [(76, 172, 13, 13), (57, 176, 8, 10), (43.5, 175, 7, 9.5), (31, 173, 6.5, 9), (19, 169, 6, 8.5)]


def sole_art():
    out = [ellipse(cx, cy, rx, ry, SKIN, rot) for cx, cy, rx, ry, rot in SOLE_TOES]
    out.append(path(SOLE, SKIN))
    out.append(path("M 26,84 C 38,76 56,74 70,82", FINE))            # 指のつけ根のふくらみ
    out.append(path("M 58,112 C 54,128 56,146 60,158", FINE))        # 土ふまず
    out.append(path("M 30,170 C 38,176 52,176 60,170", FINE))        # かかと
    return "".join(out)


def top_art():
    out = [path(TOP_BODY, FILL)]
    out.append(path("M 31,2 C 31,40 30,78 25,104 C 20,126 9,146 7,164", LINE))
    out.append(path("M 64,2 C 64,40 68,80 72,106 C 76,128 87,146 90,164", LINE))
    out.append(path("M 27,92 C 22,96 22,103 26,107", FINE) + path("M 69,92 C 74,96 74,103 71,108", FINE))   # くるぶし
    out.append(path("M 22,150 L 26,160 M 35,152 L 37,162 M 48,153 L 49,163 M 61,152 L 61,162", FINE))        # 指のすじ
    for cx, cy, rx, ry in TOP_TOES:
        out.append(ellipse(cx, cy, rx, ry, SKIN))
        out.append(path(f"M {cx - rx * .55},{cy + ry * .15} C {cx - rx * .5},{cy + ry * .75} {cx + rx * .5},{cy + ry * .75} {cx + rx * .55},{cy + ry * .15}", FINE))  # 爪
    return "".join(out)


def foot_regions(side, sole):
    out = []
    if sole:
        cid = "cf_sole"
        out.append(region(f"{side}_sole", poly([(0, 40), (92, 40), (92, 150), (0, 150)]), cid))
        out.append(region(f"{side}_heel", poly([(0, 150), (92, 150), (92, 200), (0, 200)]), cid))
        toes = SOLE_TOES
        big = ellipse(*[v + (1 if i >= 2 else 0) for i, v in enumerate(toes[0][:4])], rot=toes[0][4])
        rest = "".join(ellipse(cx, cy, rx + 1, ry + 1, rot=rot) for cx, cy, rx, ry, rot in toes[1:])
    else:
        cid = "cf_top"
        out.append(region(f"{side}_shin", poly([(0, 0), (98, 0), (98, 84), (0, 84)]), cid))
        out.append(region(f"{side}_ankle", poly([(0, 84), (98, 84), (98, 114), (0, 114)]), cid))
        out.append(region(f"{side}_foot_top", poly([(0, 114), (98, 114), (98, 190), (0, 190)]), cid))
        toes = TOP_TOES
        big = ellipse(toes[0][0], toes[0][1], toes[0][2] + 1, toes[0][3] + 1)
        rest = "".join(ellipse(cx, cy, rx + 1, ry + 1) for cx, cy, rx, ry in toes[1:])
    out.append(region(f"{side}_toes", rest))
    out.append(region(f"{side}_big_toe", big))
    return "".join(out)


def feet_figure():
    defs = f'<defs><clipPath id="cf_sole">{path(SOLE)}</clipPath><clipPath id="cf_top">{path(TOP_BODY + " Z")}</clipPath></defs>'

    def one(x, y, side, sole):
        w = 92 if sole else 98
        art = sole_art() if sole else top_art()
        # 絵は「親指が右＝右足」で描いてある。左足は左右反転
        return placed(x, y, art + foot_regions(side, sole), None if side == "r" else w)
    html = (defs + one(8, 0, "r", False) + one(124, 0, "l", False) + one(11, 222, "r", True) + one(127, 222, "l", True)
            + text(57, 212, "右足の甲", "cap") + text(173, 212, "左足の甲", "cap")
            + text(57, 436, "右足の裏", "cap") + text(173, 436, "左足の裏", "cap"))
    return {"w": 230, "h": 442, "html": html}


# ====================================================================== 書き出し
VIEWS = [("front", "正面"), ("back", "背面"), ("head", "頭"), ("hands", "手"), ("feet", "足")]


def build():
    """web/body-data.js の中身（文字列）を返す。"""
    USED.clear()
    figures = {}
    for sex in ("m", "f"):
        figures[f"front_{sex}"] = body_figure(False, sex)
        figures[f"back_{sex}"] = body_figure(True, sex)
        figures[f"head_{sex}"] = head_figure(sex)
    figures["hands"] = hands_figure()
    figures["feet"] = feet_figure()
    missing = set(REGIONS) - USED
    if missing:
        raise SystemExit(f"app/body.py にあるのに図にない部位: {sorted(missing)}")
    lines = ["// このファイルは tools/make_body.py が作ります。直接書き換えないでください。",
             "// 人体シェーマの線画とタップの区切り（部位 id は app/body.py の REGIONS）。",
             '"use strict";',
             "window.TolmonBodyData = {",
             "  views: " + json.dumps([{"id": i, "label": s} for i, s in VIEWS], ensure_ascii=False) + ",",
             "  figures: {"]
    for key, fig in figures.items():
        lines.append(f"    {key}: " + json.dumps(fig, ensure_ascii=False) + ",")
    lines += ["  }", "};", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    data = build()
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(data)
    print(f"{OUT} を書き出しました（部位 {len(USED)} 個・{len(data) // 1024} KB）")
