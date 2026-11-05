"""人体シェーマ（設問タイプ body）の部位一覧。ここが部位 id と表示名の正本。

図（線画とタップの区切り）は tools/make_body.py が web/body-data.js に書き出す。
部位を足したり名前を変えたりしたら、tools/make_body.py を直して実行し直すこと
（tests/test_body.py が、図とこの一覧のずれを見つける）。
「右・左」は患者さん本人から見た左右。
"""

REGIONS = {
    # 正面・背面で共通の部位
    "head": "頭",
    "neck": "首",
    "r_shoulder": "右肩", "l_shoulder": "左肩",
    "chest": "胸",
    "abdomen": "おなか",
    "r_upper_arm": "右上腕", "l_upper_arm": "左上腕",
    "r_forearm": "右前腕", "l_forearm": "左前腕",
    "r_hand": "右手", "l_hand": "左手",
    "r_hip": "右股関節", "l_hip": "左股関節",
    "r_thigh": "右太もも", "l_thigh": "左太もも",
    "r_knee": "右ひざ", "l_knee": "左ひざ",
    "r_shin": "右すね", "l_shin": "左すね",
    "r_foot": "右足", "l_foot": "左足",
    # 背面
    "neck_back": "首の後ろ",
    "upper_back": "背中",
    "lower_back": "腰",
    "r_elbow": "右ひじ", "l_elbow": "左ひじ",
    "r_buttock": "右おしり", "l_buttock": "左おしり",
    "r_thigh_back": "右太もも（裏）", "l_thigh_back": "左太もも（裏）",
    "r_knee_back": "右ひざ裏", "l_knee_back": "左ひざ裏",
    "r_calf": "右ふくらはぎ", "l_calf": "左ふくらはぎ",
    "r_heel": "右かかと", "l_heel": "左かかと",
    # 頭（顔・後ろ）
    "forehead": "額",
    "r_eye": "右目", "l_eye": "左目",
    "nose": "鼻",
    "mouth": "口",
    "r_cheek": "右ほほ", "l_cheek": "左ほほ",
    "chin": "あご",
    "r_ear": "右耳", "l_ear": "左耳",
    "head_top": "頭頂部",
    "r_temple": "右側頭部", "l_temple": "左側頭部",
    "head_back_r": "右後頭部", "head_back_l": "左後頭部",
    # 手
    "r_palm": "右手のひら", "l_palm": "左手のひら",
    "r_hand_back": "右手の甲", "l_hand_back": "左手の甲",
    "r_wrist": "右手首", "l_wrist": "左手首",
    "r_thumb": "右手の親指", "l_thumb": "左手の親指",
    "r_index": "右手の人さし指", "l_index": "左手の人さし指",
    "r_middle": "右手の中指", "l_middle": "左手の中指",
    "r_ring": "右手の薬指", "l_ring": "左手の薬指",
    "r_little": "右手の小指", "l_little": "左手の小指",
    # 足
    "r_foot_top": "右足の甲", "l_foot_top": "左足の甲",
    "r_sole": "右足の裏", "l_sole": "左足の裏",
    "r_ankle": "右足首", "l_ankle": "左足首",
    "r_big_toe": "右足の親指", "l_big_toe": "左足の親指",
    "r_toes": "右足の指（親指以外）", "l_toes": "左足の指（親指以外）",
}

VIEWS = ("front", "back", "head", "hands", "feet")


def label(region_id):
    return REGIONS.get(region_id, region_id)
