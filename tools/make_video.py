"""デモ動画の下書きを作る（開発用）。サーバーを起動してから実行する。

  python -X utf8 tools/make_video.py 出力先.mp4

Edge を画面なしで動かし、台本の時間割どおりに画面を操作しながら、画面を1秒に10枚ずつ写して動画にする。
声は入らない。話す言葉は、字幕として下に出す（あとで、この動画を流しながら声を入れて録画し直す）。
先に demo_reset.bat で架空の患者さんを登録し、外国語の訳を公開しておくこと。
OpenCV（動画の書き出し）と Pillow（字幕）を使う。問診のアプリ本体は標準ライブラリだけで動く。
"""

import base64
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "http://localhost:8080"
PORT = 9333
SIZE = (1280, 720)              # ブラウザの画面の大きさ
BAND = 110                      # その下に足す、字幕の帯の高さ（画面のボタンに字幕が重ならないように、画面の外に出す）
FPS = 10
EDGE = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]
FONTS = [r"C:\Windows\Fonts\meiryob.ttc", r"C:\Windows\Fonts\YuGothB.ttc", r"C:\Windows\Fonts\msgothic.ttc"]
FORM = "seikei"
KARTE_PCODE = "9000004"         # 要確認の印が出る、架空の患者さん


# ---------------------------------------------------------------- ブラウザを外から動かす（Chrome DevTools Protocol）
class Browser:
    """Edge に WebSocket でつないで操作する。外部ライブラリを使わない、最小限の実装。"""

    def __init__(self, ws_url):
        host, rest = ws_url[len("ws://"):].split("/", 1)
        name, port = host.split(":")
        self.sock = socket.create_connection((name, int(port)), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET /{rest} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                           f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.sock.recv(4096)
        if b" 101 " not in buf.split(b"\r\n", 1)[0]:
            raise RuntimeError("ブラウザにつなげませんでした")
        self.rest = buf.split(b"\r\n\r\n", 1)[1]
        self.next_id = 0

    def _read(self, n):
        while len(self.rest) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise RuntimeError("ブラウザとの接続が切れました")
            self.rest += chunk
        out, self.rest = self.rest[:n], self.rest[n:]
        return out

    def _send(self, payload, opcode=1):
        mask = os.urandom(4)
        head = bytes([0x80 | opcode])
        n = len(payload)
        if n < 126:
            head += bytes([0x80 | n])
        elif n < 65536:
            head += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            head += bytes([0x80 | 127]) + struct.pack(">Q", n)
        self.sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def _recv(self):
        data = b""
        while True:
            b1, b2 = self._read(2)
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(n)
            opcode = b1 & 0x0F
            if opcode == 9:                         # ping には pong を返す
                self._send(payload, opcode=10)
                continue
            if opcode in (0, 1, 2):
                data += payload
                if b1 & 0x80:
                    return data

    def call(self, method, **params):
        self.next_id += 1
        self._send(json.dumps({"id": self.next_id, "method": method, "params": params}).encode())
        while True:
            msg = json.loads(self._recv().decode("utf-8"))
            if msg.get("id") == self.next_id:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def js(self, expression):
        r = self.call("Runtime.evaluate", expression=expression, awaitPromise=True, returnByValue=True)
        if r.get("exceptionDetails"):
            raise RuntimeError("画面の中でエラー: " + json.dumps(r["exceptionDetails"], ensure_ascii=False)[:400])
        return r.get("result", {}).get("value")


# 押した所が分かるように、丸い印を出す。動画を作るときだけ画面に入れる（アプリには入っていない）
HELPERS = r"""
window.__ring = function (x, y, keep) {
  var d = document.createElement('div');
  d.style.cssText = 'position:fixed;left:' + (x - 24) + 'px;top:' + (y - 24) + 'px;width:48px;height:48px;border-radius:50%;'
    + 'background:rgba(255,140,0,.35);border:4px solid #ff8c00;z-index:2147483647;pointer-events:none;transition:transform .4s,opacity .4s';
  document.documentElement.appendChild(d);
  setTimeout(function () { d.style.transform = 'scale(1.7)'; d.style.opacity = '0'; }, keep || 450);
  setTimeout(function () { d.remove(); }, (keep || 450) + 450);
};
// 要素のまん中の位置（画面の左上から）。入れ子の画面（iframe）の中の要素にも対応する
window.__center = function (el) {
  var r = el.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
  var f = el.ownerDocument.defaultView.frameElement;
  if (f) { var fr = f.getBoundingClientRect(); x += fr.left; y += fr.top; }
  return [Math.round(x), Math.round(y)];
};
"""


class Recorder:
    """画面を写して動画に書く。字幕と、場面の名前を重ねる。"""

    def __init__(self, browser, path):
        import cv2
        from PIL import ImageFont
        self.cv2, self.b = cv2, browser
        self.writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), FPS, (SIZE[0], SIZE[1] + BAND))
        font = next(f for f in FONTS if os.path.exists(f))
        self.font = ImageFont.truetype(font, 28)
        self.small = ImageFont.truetype(font, 18)
        self.caption, self.label = "", ""
        self.last = None
        self.started = time.time()
        self.frames = 0

    def now(self):
        return time.time() - self.started

    def _wrap(self, text, width=38):
        lines, line = [], ""
        for ch in text:
            line += ch
            if len(line) >= width and ch not in "「（":
                lines.append(line)
                line = ""
        if line:
            lines.append(line)
        # 行のはじめに句読点が来ないよう、前の行に送る
        for i in range(1, len(lines)):
            while lines[i] and lines[i][0] in "、。」）":
                lines[i - 1] += lines[i][0]
                lines[i] = lines[i][1:]
        return [x for x in lines if x][:2]

    def _draw(self, frame):
        import numpy as np
        from PIL import Image, ImageDraw
        w, h = SIZE
        out = Image.new("RGB", (w, h + BAND), (24, 32, 30))
        out.paste(Image.fromarray(self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB)), (0, 0))
        d = ImageDraw.Draw(out)
        if self.label:                              # いまどの画面か（帯の左上）
            tw = d.textlength(self.label, font=self.small)
            d.rounded_rectangle([14, h + 8, 14 + tw + 28, h + 38], radius=15, fill=(15, 107, 92))
            d.text((28, h + 11), self.label, font=self.small, fill=(255, 255, 255))
        if self.caption:                            # 話す言葉（帯のまん中。2行まで）
            lines = self._wrap(self.caption)
            top = h + (46 if len(lines) == 1 else 34) + (0 if self.label else -8)
            for i, line in enumerate(lines):
                tw = d.textlength(line, font=self.font)
                d.text(((w - tw) / 2, top + 36 * i), line, font=self.font, fill=(255, 255, 255))
        return self.cv2.cvtColor(np.asarray(out), self.cv2.COLOR_RGB2BGR)

    def shoot(self):
        """いまの画面を1枚写し、動画の時間が実際の時間に追いつくまで、同じ絵を書く。"""
        import numpy as np
        try:
            data = base64.b64decode(self.b.call("Page.captureScreenshot", format="jpeg", quality=88)["data"])
            raw = self.cv2.imdecode(np.frombuffer(data, np.uint8), self.cv2.IMREAD_COLOR)
            if (raw.shape[1], raw.shape[0]) != SIZE:
                raw = self.cv2.resize(raw, SIZE)
            self.last = raw
        except RuntimeError:
            # ページを切り替えている最中は写せない。直前の絵をそのまま使う
            time.sleep(0.05)
            if self.last is None:
                return
        frame = self._draw(self.last)
        if self.frames / FPS > self.now():
            time.sleep(0.03)                        # 動画のほうが先に進んでいるときは、書かずに少し待つ
            return
        while self.frames / FPS <= self.now():
            self.writer.write(frame)
            self.frames += 1

    def hold(self, seconds):
        end = self.now() + seconds
        while self.now() < end:
            self.shoot()

    def until(self, t):
        while self.now() < t:
            self.shoot()

    def close(self):
        self.writer.release()


class Demo:
    """台本の1行ごとの操作で使う道具。"""

    def __init__(self, browser, rec):
        self.b, self.r = browser, rec

    def go(self, path, wait=1.6):
        self.b.call("Page.navigate", url=BASE + path)
        end = time.time() + 15
        while time.time() < end:
            self.r.shoot()
            try:
                if self.b.js("document.readyState + '|' + location.pathname").startswith("complete|" + path.split("?")[0]):
                    break
            except RuntimeError:
                pass                                # 切り替えの途中
        self.r.hold(wait)

    def run(self, js):
        return self.b.js(js)

    def tap(self, finder, wait=0.5, click=True):
        """finder：要素を返す JavaScript の式。丸い印を出してから、本当のマウス操作で押す。"""
        pos = self.b.js(f"(function(){{var el={finder}; if(!el) return null; el.scrollIntoView({{block:'nearest'}}); return __center(el);}})()")
        if not pos:
            raise RuntimeError("押す場所が見つかりません: " + finder)
        x, y = pos
        self.b.js(f"__ring({x},{y},{450 if click else 1400})")
        self.r.hold(0.45)
        if click:
            for kind in ("mousePressed", "mouseReleased"):
                self.b.call("Input.dispatchMouseEvent", type=kind, x=x, y=y, button="left", clickCount=1)
        self.r.hold(wait)

    def scroll(self, js_top, seconds=1.2):
        self.b.js(f"window.scrollTo({{top: {js_top}, behavior: 'smooth'}})")
        self.r.hold(seconds)


# ---------------------------------------------------------------- 台本（場面の名前、話す言葉、秒数、その間の操作）
def q(sel):
    return f"document.querySelector({json.dumps(sel)})"


def by_text(sel, text):
    return (f"[].filter.call(document.querySelectorAll({json.dumps(sel)}),"
            f"function(e){{return e.textContent.indexOf({json.dumps(text)})>=0}})[0]")


def top_of(sel, offset=-12):
    return f"({q(sel)}.getBoundingClientRect().top + window.pageYOffset + ({offset}))"


def in_frame(sel):
    return f"document.getElementById('m-frame').contentDocument.querySelector({json.dumps(sel)})"


def paper_image():
    """作る画面の左の紙。画面なしのブラウザは PDF を表示できないので、同じ紙を画像にしたものを出す。"""
    path = os.path.join(ROOT, "docs", "img", "paper.jpg")
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    return ("(function(){var box=document.getElementById('paper'); box.className='a-paper-box scroll';"
            f"box.innerHTML='<img alt=\"もとの帳票\" src=\"data:image/jpeg;base64,{data}\">';}})()")


# 途中の設問は、動画では飛ばす（全部で16問あるため）。飛ばした設問には、架空の答えを入れておく
FILL = """(function(){
  var set = {sex:'女性', myna_consent:'はい', temp_max_when:'わからない', symptoms:['痛い','腫れている'], onset:'1週間くらい前から',
             cause:['転んだ'], past_illness:['高血圧'], current_treatment:'ない', drug_reaction:'ない'};
  Object.keys(set).forEach(function(id){ var qq=findQ(id); if(!qq) return;
    var ok = function(l){ return qq.options.some(function(o){return o.label===l}); };
    var v = set[id];
    if (Array.isArray(v)) { v = v.filter(ok); if (v.length) S.answers[id] = {value: v}; }
    else if (ok(v)) S.answers[id] = {value: v}; });
  ['temp_now','temp_max'].forEach(function(id){ if(findQ(id)) S.answers[id] = {value:'36.5'}; });
})()"""


def beats(d):
    """(場面の名前, 話す言葉, 秒数, その間にする操作) の並び。秒数の合計が、動画の長さになる。"""
    A, P, K, S = "作る画面（情報システム担当）", "患者さんの画面（タブレット）", "医師・看護師（電子カルテから開く）", ""

    def open_admin():
        d.go(f"/admin?form={FORM}", wait=1.0)
        d.run(paper_image())
        d.scroll(top_of("#work"), 1.0)

    def show_read():
        d.scroll("0", 1.0)
        d.tap(q("#btn-read"), click=False, wait=1.6)

    def open_draft():
        d.tap(by_text("#draft-list button", "整形"), wait=0.8)
        d.run(paper_image())
        d.scroll(top_of("#work"), 1.0)

    def show_added():
        d.scroll(top_of("#q-list li.added, #q-list .q-added", -260), 1.6)

    def show_figure():
        d.scroll(top_of("#q-list .q-figs", -200), 1.6)

    def tab(name, then=None):
        def f():
            d.scroll(top_of(".a-tabs", -90), 0.8)
            d.tap(q(f'.a-tabs button[data-tab="{name}"]'), wait=0.8)
            if then:
                d.scroll(top_of(then, -150), 1.4)
        return f

    def reception():
        d.go("/", wait=2.2)
        d.tap(by_text("#form-list button", "整形"), wait=1.0)

    def languages():
        d.tap(q('#lang-switch button[data-lang="en"]'), wait=1.6)
        d.tap(q('#lang-switch button[data-lang="ja"]'), wait=0.5)

    def numbers():
        d.tap(q("#btn-begin"), wait=0.8)
        for key in ("7", "2"):
            d.tap(by_text(".num-key", key), wait=0.25)
        d.tap(q("#btn-next"), wait=0.6)

    def figure():
        d.run(FILL)
        d.run("goTo('site')")
        d.r.hold(1.0)
        d.tap(q('.body-svg .part[data-id="r_knee"]'), wait=2.8)

    def send():
        d.run("openReview()")
        d.r.hold(1.6)
        d.tap(q("#btn-submit"), wait=1.5)

    def open_karte():
        d.go(f"/mock-karte?pcode={KARTE_PCODE}", wait=2.6)
        d.tap(q("#btn-monshin"), wait=2.0)

    def copy_paste():
        d.tap(in_frame(".d-btn.primary"), wait=1.4)
        d.tap(q("#soap-s"), wait=0.5)
        # 貼り付け（Ctrl＋V）のかわりに、コピーした文をそのまま入れる
        d.run("(function(){var t=document.getElementById('soap-s');"
              "t.value=document.getElementById('m-frame').contentDocument.querySelector('.d-karte').value;})()")

    return [
        (A, "武蔵ヶ丘病院で情報システムを担当している、里川です。", 6.0, open_admin),
        (A, "病院の受付と患者さんと医師が毎日使う、紙の問診票。", 5.5, None),
        (A, "トルモンは、この紙を読み取るだけで、同じ設問のWeb問診に変えます。", 7.0, None),
        (A, "紙のPDFを選んで「読み取る」を押すと、Claude が1分半ほどで設問を作ります。", 7.5, show_read),
        (A, "今日は、読み取り済みのものを開きます。", 4.5, open_draft),
        (A, "左が紙、右が Claude の作った設問です。", 4.5, None),
        (A, "紙では「書く欄」だった所は、選ぶ形に変わっています。", 5.5, show_added),
        (A, "高齢の患者さんは、タブレットで文字を打てないからです。", 5.5, None),
        (A, "点線は Claude が足した選択肢で、人が確かめます。", 5.5, show_figure),
        (A, "Claude は自分の読み取りを、紙と突き合わせて見直します。", 6.0, tab("issues")),
        (A, "架空の患者さんを5人作って、最後まで通るかも確かめます。", 6.0, tab("dummy", "#dummy-list")),
        (A, "英語と中国語の訳は、別の Claude が日本語に戻して、ずれを探します。", 7.0, tab("lang", ".l-table")),
        (A, "公開を決めるのは、人です。", 3.0, None),
        (P, "ここからは患者さんの画面です。受付が診療科を選んで、タブレットを渡します。", 7.5, reception),
        (P, "言葉も選べます。", 3.6, languages),
        (P, "数字は大きなボタンで。", 4.2, numbers),
        (P, "痛い所は、体の図を押すだけ。キーボードは出ません。", 6.0, figure),
        (P, "送ると、受付番号だけが出ます。", 5.2, send),
        (P, "この間、AIは動いていません。", 3.2, None),
        (K, "医師は、電子カルテの患者画面で【問診】を押します。", 7.0, open_karte),
        (K, "アレルギーや妊娠中といった、病院が決めた答えは、いちばん上に出ます。", 6.5, None),
        (K, "何語で答えても、文は日本語です。コピーして、カルテに貼り付けます。", 7.0, copy_paste),
        (K, "診断はしません。判断は医師がします。", 4.0, None),
        (S, "Claude を使うのは、問診票を作るときだけです。", 5.0, lambda: d.go("/static/demo_slides.html?slide=flow", wait=0.3)),
        (S, "患者さんの回答は、AIにも、病院の外にも出ません。", 5.0, None),
        (S, "だから、インターネットにつながらない院内のネットワークで、そのまま使えます。", 7.0, None),
        (S, "私の専門は、パソコンやネットワークの運用と保守です。開発は専門ではありません。", 7.5, lambda: d.go("/static/demo_slides.html?slide=end", wait=0.3)),
        (S, "それでも Claude Code と話しながら、ここまで作れました。", 5.5, None),
        (S, "現場を知る人が、自分で道具を作れる。", 4.0, None),
        (S, "読み取りはAI、確定は人、判断は医師。トルモンです。", 5.5, None),
    ]


def main(argv):
    out = os.path.abspath(argv[0]) if argv else os.path.join(ROOT, "tolmon_demo_draft.mp4")
    edge = next((p for p in EDGE if os.path.exists(p)), None)
    if not edge:
        print("Edge が見つかりません")
        return 1
    profile = tempfile.mkdtemp(prefix="tolmon_video_")
    tmp_video = os.path.join(profile, "video.mp4")        # 日本語の入らない場所に書いてから、移す
    proc = subprocess.Popen([edge, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--remote-debugging-port={PORT}",
                             "--remote-allow-origins=*", f"--user-data-dir={profile}", f"--window-size={SIZE[0]},{SIZE[1]}",
                             "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        target = None
        for _ in range(60):
            try:
                pages = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=2))
                target = next(p for p in pages if p.get("type") == "page")
                break
            except (OSError, StopIteration):
                time.sleep(0.25)
        if not target:
            print("ブラウザを起動できませんでした")
            return 1
        b = Browser(target["webSocketDebuggerUrl"])
        b.call("Page.enable")
        b.call("Emulation.setDeviceMetricsOverride", width=SIZE[0], height=SIZE[1], deviceScaleFactor=1, mobile=False)
        b.call("Page.addScriptToEvaluateOnNewDocument", source=HELPERS)
        try:
            b.call("Browser.grantPermissions", permissions=["clipboardReadWrite", "clipboardSanitizedWrite"], origin=BASE)
        except RuntimeError:
            pass                                    # 許可できなくても、コピーは別の方法で動く
        rec = Recorder(b, tmp_video)
        demo = Demo(b, rec)
        plan = beats(demo)
        total = sum(x[2] for x in plan)
        print(f"場面は {len(plan)} こ、長さは {int(total // 60)}分{total % 60:.0f}秒 の予定です")
        rec.started = time.time()
        clock, late = 0.0, 0.0
        for label, caption, seconds, action in plan:
            rec.label, rec.caption = label, caption
            if action:
                action()
            clock += seconds
            late = max(late, rec.now() - clock)
            rec.until(clock)
        rec.hold(0.6)
        rec.close()
        os.makedirs(os.path.dirname(out), exist_ok=True)
        if os.path.exists(out):
            os.remove(out)
        os.replace(tmp_video, out)
        length = rec.frames / FPS
        print(f"できました：{out}")
        print(f"長さ {int(length // 60)}分{length % 60:.0f}秒" + (f"（操作が言葉より長引いた場面があります。最大 {late:.1f} 秒）" if late > 0.3 else ""))
        return 0
    finally:
        proc.terminate()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
