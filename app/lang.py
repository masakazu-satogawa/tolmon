"""患者さんの画面を外国語で出すための、決まった言葉（ボタン・案内文・体の部位名）。

ここにあるのは、どの問診票でも同じ言葉だけ。設問と選択肢の訳は、問診票ごとに
definitions/i18n/<問診ID>.<言語>.yaml に置く（作る画面で Claude が訳し、人が確かめて公開する）。
患者さんが答えるときに AI は動かない。カルテに出る文は、どの言語で答えても日本語。
"""

from . import body

# 日本語のほかに出せる言語（画面のボタンに出す名前）
LANGS = {"en": "English", "zh-TW": "繁體中文"}
HTML_LANG = {"ja": "ja", "en": "en", "zh-TW": "zh-Hant-TW"}

# 画面の言葉。キー → (日本語, 英語, 繁体字中国語)
_UI = {
    "fs_label": ("文字の大きさ", "Text size", "字體大小"),
    "fs_s": ("小", "S", "小"),
    "fs_m": ("中", "M", "中"),
    "fs_l": ("大", "L", "大"),
    "welcome_1": ("これから、いくつか質問をします。", "We will ask you a few questions.", "接下來會請您回答幾個問題。"),
    "welcome_2": ("わかる範囲でお答えください。", "Please answer as far as you know.", "請就您知道的範圍回答即可。"),
    "welcome_count": ("質問はおよそ {n} 問です。", "There are about {n} questions.", "大約有 {n} 個問題。"),
    "welcome_font": ("文字が読みにくいときは、上の「大」を押してください。",
                     "If the text is hard to read, tap \"L\" at the top.", "如果字太小看不清楚，請按上方的「大」。"),
    "begin": ("はじめる", "Start", "開始"),
    "back": ("もどる", "Back", "上一步"),
    "next": ("次へ", "Next", "下一步"),
    "skip": ("答えずに次へ", "Skip", "不回答，下一步"),
    "to_review": ("確認画面へ", "Back to review", "回到確認畫面"),
    "to_figure": ("図にもどる", "Back to the picture", "回到圖片"),
    "detail_note": ("書かなくてもかまいません。診察のときにお話しください。",
                    "You may leave this blank and tell the doctor in person.", "可以不填寫，看診時再告訴醫師即可。"),
    "talk_btn": ("書かずに、診察のときに話します", "I will tell the doctor in person instead", "不填寫，看診時再說明"),
    "talk": ("診察のときに話します", "I will tell the doctor in person", "看診時再說明"),
    "del": ("1文字消す", "Delete", "刪除"),
    "body_picked": ("選んだところ：", "Selected: ", "已選擇："),
    "body_tap": ("図をタップして選んでください", "Tap the picture to choose", "請點選圖上的部位"),
    "body_main_q": ("いちばんつらいのは、どこですか？", "Which place bothers you the most?", "最不舒服的是哪個部位？"),
    "body_main_hint": ("選んだところの中から、1つ選んでください", "Please choose one of the places you selected", "請從已選的部位中選一個"),
    "main_suffix": ("（いちばんつらい）", " (worst)", "（最不舒服）"),
    "err_number": ("数字で入力してください", "Please enter a number", "請輸入數字"),
    "err_min": ("{n} 以上の数字を入力してください", "Please enter {n} or more", "請輸入 {n} 以上的數字"),
    "err_max": ("{n} 以下の数字を入力してください", "Please enter {n} or less", "請輸入 {n} 以下的數字"),
    "review_title": ("お答えの内容を確認してください", "Please check your answers", "請確認您的回答"),
    "fix": ("なおす", "Change", "修改"),
    "no_answer": ("（答えていません）", "(Not answered)", "（未回答）"),
    "submit": ("この内容で送る", "Send", "送出"),
    "sending": ("送っています…", "Sending…", "傳送中…"),
    "call_staff": ("係の者をお呼びください。", "Please call a staff member.", "請通知工作人員。"),
    "err_net": ("通信できませんでした。職員に声をかけてください。", "Could not connect. Please tell a staff member.", "無法連線，請通知工作人員。"),
    "thanks": ("ありがとうございました。", "Thank you.", "謝謝您。"),
    "number_label": ("受付番号", "Your number", "您的號碼"),
    "bring": ("この画面のまま、タブレットを\n受付にお持ちください。",
              "Please keep this screen open and\nbring the tablet to the reception desk.", "請保持這個畫面，\n將平板電腦交回櫃檯。"),
    "idle_title": ("問診を続けますか？", "Do you want to continue?", "要繼續填寫嗎？"),
    "idle_text": ("あと {n} 秒で、最初の画面にもどります。", "Returning to the first screen in {n} seconds.", "{n} 秒後將回到最初的畫面。"),
    "continue": ("続ける", "Continue", "繼續"),
    "sep": ("、", ", ", "、"),
    "lp": ("（", " (", "（"),
    "rp": ("）", ")", "）"),
    "view_front": ("正面", "Front", "正面"),
    "view_back": ("背面", "Back", "背面"),
    "view_head": ("頭", "Head", "頭部"),
    "view_hands": ("手", "Hands", "手"),
    "view_feet": ("足", "Feet", "腳"),
    "fig_right": ("右側", "Right side", "右側"),
    "fig_left": ("左側", "Left side", "左側"),
    "fig_head_back": ("頭の後ろ", "Back of the head", "後腦"),
    "fig_face": ("顔", "Face", "臉"),
}
_ORDER = ("ja", "en", "zh-TW")
UI = {lang: {k: v[i] for k, v in _UI.items()} for i, lang in enumerate(_ORDER)}

# 体の部位名。左右のあるものは {S}（文頭）・{s}（文中）に右・左が入る
_SIDES = {"en": {"r": ("Right", "right"), "l": ("Left", "left")},
          "zh-TW": {"r": ("右", "右"), "l": ("左", "左")}}
_BODY = {
    "head": ("Head", "頭"),
    "neck": ("Neck", "脖子"),
    "shoulder": ("{S} shoulder", "{S}肩"),
    "chest": ("Chest", "胸部"),
    "abdomen": ("Belly (abdomen)", "肚子（腹部）"),
    "upper_arm": ("{S} upper arm", "{S}上臂"),
    "forearm": ("{S} forearm", "{S}前臂"),
    "hand": ("{S} hand", "{S}手"),
    "hip": ("{S} hip joint", "{S}髖關節"),
    "thigh": ("{S} thigh", "{S}大腿"),
    "knee": ("{S} knee", "{S}膝蓋"),
    "shin": ("{S} shin", "{S}小腿（前側）"),
    "foot": ("{S} foot", "{S}腳"),
    "neck_back": ("Back of the neck", "後頸"),
    "upper_back": ("Upper back", "背部"),
    "lower_back": ("Lower back", "腰部"),
    "elbow": ("{S} elbow", "{S}手肘"),
    "buttock": ("{S} buttock", "{S}臀部"),
    "thigh_back": ("Back of the {s} thigh", "{S}大腿（後側）"),
    "knee_back": ("Back of the {s} knee", "{S}膝蓋（後側）"),
    "calf": ("{S} calf", "{S}小腿肚"),
    "heel": ("{S} heel", "{S}腳跟"),
    "forehead": ("Forehead", "額頭"),
    "eye": ("{S} eye", "{S}眼"),
    "nose": ("Nose", "鼻子"),
    "mouth": ("Mouth", "嘴巴"),
    "cheek": ("{S} cheek", "{S}臉頰"),
    "chin": ("Chin / jaw", "下巴"),
    "ear": ("{S} ear", "{S}耳"),
    "head_top": ("Top of the head", "頭頂"),
    "temple": ("{S} side of the head", "{S}側頭部"),
    "head_back": ("Back of the head ({s})", "{S}後腦"),
    "palm": ("{S} palm", "{S}手掌"),
    "hand_back": ("Back of the {s} hand", "{S}手背"),
    "wrist": ("{S} wrist", "{S}手腕"),
    "thumb": ("{S} thumb", "{S}手大拇指"),
    "index": ("{S} index finger", "{S}手食指"),
    "middle": ("{S} middle finger", "{S}手中指"),
    "ring": ("{S} ring finger", "{S}手無名指"),
    "little": ("{S} little finger", "{S}手小指"),
    "foot_top": ("Top of the {s} foot", "{S}腳背"),
    "sole": ("Sole of the {s} foot", "{S}腳底"),
    "ankle": ("{S} ankle", "{S}腳踝"),
    "big_toe": ("{S} big toe", "{S}腳大拇趾"),
    "toes": ("{S} toes (other than the big toe)", "{S}腳其他腳趾"),
}


def _split_side(region_id):
    if region_id[:2] in ("r_", "l_"):
        return region_id[0], region_id[2:]
    if region_id[-2:] in ("_r", "_l"):
        return region_id[-1], region_id[:-2]
    return "", region_id


def _body_names(lang):
    col = _ORDER.index(lang) - 1
    out = {}
    for rid in body.REGIONS:
        side, base = _split_side(rid)
        if base not in _BODY:           # 訳のない部位は、日本語の名前のまま出す
            continue
        upper, lower = _SIDES[lang].get(side, ("", ""))
        out[rid] = _BODY[base][col].replace("{S}", upper).replace("{s}", lower)
    return out


BODY = {lang: _body_names(lang) for lang in LANGS}


def body_label(region_id, lang=None):
    return BODY.get(lang, {}).get(region_id) or body.label(region_id)


def ui(lang):
    return UI.get(lang) or UI["ja"]


def client_data():
    """患者さんの画面に渡す分（言語の名前・画面の言葉・体の部位名）。"""
    return {"langs": [{"id": "ja", "name": "日本語"}] + [{"id": k, "name": v} for k, v in LANGS.items()],
            "html_lang": HTML_LANG, "ui": UI, "body": BODY}
