// 人体シェーマの図形（設問タイプ body）。部位の id は app/body.py の REGIONS と一致させる。
// 「右・左」は患者さん本人から見た左右。正面図では患者さんの右が画面の左に来る（紙の問診票と同じ）。
"use strict";

window.TolmonBody = (function () {
  var NS = "http://www.w3.org/2000/svg";

  function node(tag, attrs) {
    var e = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    return e;
  }

  // 図形の指定：{t:"rect"|"ellipse"|"path", ...}
  function mirror(s, W) {
    var m = {};
    Object.keys(s).forEach(function (k) { m[k] = s[k]; });
    if (s.t === "rect") m.x = W - s.x - s.w;
    else if (s.t === "ellipse") m.cx = W - s.cx;
    else if (s.t === "path") m.d = s.md;   // path は鏡写しを md に書いておく
    return m;
  }
  function part(id, s) { var p = {}; Object.keys(s).forEach(function (k) { p[k] = s[k]; }); p.id = id; return p; }
  // 右半身の形を、正面図では左半身へ鏡写し、背面図では右半身を鏡写しにする
  function pair(spec, rId, lId, flipped, W) {
    var a = part(rId, flipped ? mirror(spec, W) : spec);
    var b = part(lId, flipped ? spec : mirror(spec, W));
    return [a, b];
  }
  function text(x, y, s, cls) { return { t: "text", x: x, y: y, s: s, cls: cls || "" }; }

  // ---------------------------------------------------------------- 全身（正面・背面）
  var BW = 220, BH = 385;
  var R = {   // 患者さんの右半身（正面図＝画面の左側）
    shoulder: { t: "ellipse", cx: 70, cy: 86, rx: 18, ry: 11 },
    upper_arm: { t: "rect", x: 50, y: 96, w: 20, h: 52, rx: 8 },
    forearm: { t: "rect", x: 46, y: 150, w: 18, h: 52, rx: 8 },
    elbow: { t: "ellipse", cx: 59, cy: 149, rx: 11, ry: 9 },
    hand: { t: "ellipse", cx: 55, cy: 218, rx: 11, ry: 16 },
    buttock: { t: "ellipse", cx: 97, cy: 170, rx: 13, ry: 12 },
    thigh: { t: "rect", x: 85, y: 180, w: 24, h: 72, rx: 8 },
    knee: { t: "ellipse", cx: 97, cy: 262, rx: 13, ry: 12 },
    shin: { t: "rect", x: 87, y: 276, w: 20, h: 68, rx: 8 },
    foot: { t: "ellipse", cx: 97, cy: 356, rx: 14, ry: 16 }
  };

  function bodyView(back) {
    var W = BW, f = back;
    var parts = [];
    if (back) {
      parts.push(part("head_back_l", { t: "path", d: "M110,11 A27,27 0 0 0 110,65 Z" }));
      parts.push(part("head_back_r", { t: "path", d: "M110,11 A27,27 0 0 1 110,65 Z" }));
      parts.push(part("neck_back", { t: "rect", x: 100, y: 64, w: 20, h: 16 }));
      parts.push(part("upper_back", { t: "rect", x: 82, y: 78, w: 56, h: 52, rx: 8 }));
      parts.push(part("lower_back", { t: "rect", x: 84, y: 130, w: 52, h: 30, rx: 6 }));
      parts = parts.concat(pair(R.buttock, "r_buttock", "l_buttock", f, W));
    } else {
      parts.push(part("chest", { t: "rect", x: 82, y: 78, w: 56, h: 52, rx: 8 }));
      parts.push(part("abdomen", { t: "rect", x: 84, y: 130, w: 52, h: 48, rx: 6 }));
      parts.push(part("head", { t: "ellipse", cx: 110, cy: 38, rx: 27, ry: 27 }));
      parts.push(part("neck", { t: "rect", x: 100, y: 64, w: 20, h: 16 }));
    }
    parts = parts.concat(pair(R.shoulder, "r_shoulder", "l_shoulder", f, W));
    parts = parts.concat(pair(R.upper_arm, "r_upper_arm", "l_upper_arm", f, W));
    parts = parts.concat(pair(R.forearm, "r_forearm", "l_forearm", f, W));
    if (back) parts = parts.concat(pair(R.elbow, "r_elbow", "l_elbow", f, W));
    parts = parts.concat(pair(R.hand, "r_hand", "l_hand", f, W));
    parts = parts.concat(pair(R.thigh, back ? "r_thigh_back" : "r_thigh", back ? "l_thigh_back" : "l_thigh", f, W));
    parts = parts.concat(pair(R.knee, "r_knee", "l_knee", f, W));
    parts = parts.concat(pair(R.shin, back ? "r_calf" : "r_shin", back ? "l_calf" : "l_shin", f, W));
    parts = parts.concat(pair(R.foot, back ? "r_heel" : "r_foot", back ? "l_heel" : "l_foot", f, W));
    var hints = back
      ? [text(28, 20, "左側", "hint"), text(192, 20, "右側", "hint"), text(110, 380, "うしろ", "cap")]
      : [text(28, 20, "右側", "hint"), text(192, 20, "左側", "hint"), text(110, 380, "まえ", "cap")];
    return { w: W, h: BH, parts: parts, texts: hints };
  }

  // ---------------------------------------------------------------- 頭（顔・頭の後ろ）
  function headView() {
    var parts = [
      // 顔（患者さんの右が画面の左）
      part("forehead", { t: "rect", x: 38, y: 36, w: 74, h: 28, rx: 14 }),
      part("r_eye", { t: "ellipse", cx: 57, cy: 78, rx: 11, ry: 7 }),
      part("l_eye", { t: "ellipse", cx: 93, cy: 78, rx: 11, ry: 7 }),
      part("nose", { t: "ellipse", cx: 75, cy: 96, rx: 8, ry: 12 }),
      part("r_cheek", { t: "ellipse", cx: 48, cy: 102, rx: 11, ry: 11 }),
      part("l_cheek", { t: "ellipse", cx: 102, cy: 102, rx: 11, ry: 11 }),
      part("mouth", { t: "ellipse", cx: 75, cy: 119, rx: 14, ry: 6 }),
      part("chin", { t: "ellipse", cx: 75, cy: 135, rx: 16, ry: 8 }),
      part("r_ear", { t: "ellipse", cx: 19, cy: 88, rx: 6, ry: 12 }),
      part("l_ear", { t: "ellipse", cx: 131, cy: 88, rx: 6, ry: 12 }),
      // 頭の後ろ（患者さんの右が画面の右）
      part("head_top", { t: "ellipse", cx: 225, cy: 44, rx: 36, ry: 13 }),
      part("head_back_l", { t: "path", d: "M225,60 Q180,60 178,100 Q182,130 225,138 Z" }),
      part("head_back_r", { t: "path", d: "M225,60 Q270,60 272,100 Q268,130 225,138 Z" }),
      part("l_temple", { t: "ellipse", cx: 171, cy: 92, rx: 7, ry: 20 }),
      part("r_temple", { t: "ellipse", cx: 279, cy: 92, rx: 7, ry: 20 })
    ];
    var outlines = [
      { t: "ellipse", cx: 75, cy: 86, rx: 56, ry: 58 },
      { t: "ellipse", cx: 225, cy: 86, rx: 56, ry: 58 }
    ];
    var texts = [
      text(75, 162, "顔", "cap"), text(225, 162, "頭の後ろ", "cap"),
      text(20, 20, "右側", "hint"), text(130, 20, "左側", "hint"),
      text(170, 20, "左側", "hint"), text(280, 20, "右側", "hint")
    ];
    return { w: 300, h: 170, parts: parts, outlines: outlines, texts: texts };
  }

  // ---------------------------------------------------------------- 手（甲・ひら）
  var FINGERS = ["thumb", "index", "middle", "ring", "little"];
  // 指の順（画面の左から）。親指が画面のどちらに来るかは、右手か左手か・甲かひらかで決まる
  // 親指を左に置いたときの、各指の位置と長さ（親指は外側の下寄り、ほかの指は上に並ぶ）
  var FINGER_X = [-30, -14, -1, 12, 25];
  var FINGER_H = [26, 40, 46, 42, 32];
  var FINGER_Y = [-6, -34, -40, -36, -26];
  function hand(cx, cy, side, palm) {
    var thumbLeft = (side === "r") !== palm;   // 右手の甲・左手のひら → 親指が画面の左
    var parts = [part(side + (palm ? "_palm" : "_hand_back"), { t: "ellipse", cx: cx, cy: cy + 22, rx: 24, ry: 30 })];
    FINGERS.forEach(function (f, j) {
      var x = cx + (thumbLeft ? FINGER_X[j] : -FINGER_X[j]);
      parts.push(part(side + "_" + f, { t: "rect", x: x - 5, y: cy + FINGER_Y[j], w: 10, h: FINGER_H[j], rx: 5 }));
    });
    parts.push(part(side + "_wrist", { t: "rect", x: cx - 16, y: cy + 52, w: 32, h: 14, rx: 6 }));
    return parts;
  }
  function handsView() {
    var parts = hand(60, 60, "r", false).concat(hand(180, 60, "l", false), hand(60, 215, "r", true), hand(180, 215, "l", true));
    var texts = [text(60, 142, "右手の甲", "cap"), text(180, 142, "左手の甲", "cap"), text(60, 297, "右手のひら", "cap"), text(180, 297, "左手のひら", "cap")];
    return { w: 240, h: 305, parts: parts, texts: texts };
  }

  // ---------------------------------------------------------------- 足（甲・裏）
  function foot(cx, cy, side, sole) {
    var parts = [part(side + (sole ? "_sole" : "_foot_top"), { t: "ellipse", cx: cx, cy: cy + 26, rx: 21, ry: 42 })];
    parts.push(part(side + "_toes", { t: "rect", x: cx - 22, y: cy - 30, w: 44, h: 18, rx: 9 }));
    if (sole) parts.push(part(side + "_heel", { t: "ellipse", cx: cx, cy: cy + 54, rx: 14, ry: 12 }));
    else parts.push(part(side + "_ankle", { t: "rect", x: cx - 13, y: cy + 64, w: 26, h: 12, rx: 6 }));
    return parts;
  }
  function feetView() {
    var parts = foot(60, 60, "r", false).concat(foot(180, 60, "l", false), foot(60, 215, "r", true), foot(180, 215, "l", true));
    var texts = [text(60, 148, "右足の甲", "cap"), text(180, 148, "左足の甲", "cap"), text(60, 303, "右足の裏", "cap"), text(180, 303, "左足の裏", "cap")];
    return { w: 240, h: 310, parts: parts, texts: texts };
  }

  var VIEWS = [
    { id: "front", label: "正面", build: function () { return bodyView(false); } },
    { id: "back", label: "背面", build: function () { return bodyView(true); } },
    { id: "head", label: "頭", build: headView },
    { id: "hands", label: "手", build: handsView },
    { id: "feet", label: "足", build: feetView }
  ];

  function shape(s) {
    if (s.t === "rect") return node("rect", { x: s.x, y: s.y, width: s.w, height: s.h, rx: s.rx || 0 });
    if (s.t === "ellipse") return node("ellipse", { cx: s.cx, cy: s.cy, rx: s.rx, ry: s.ry });
    return node("path", { d: s.d });
  }

  // svg に図を描く。selected: {部位id: true}、labels: {部位id: 表示名}、onTap(id)
  function draw(viewId, svg, selected, labels, onTap) {
    var view = null;
    VIEWS.forEach(function (v) { if (v.id === viewId) view = v.build(); });
    if (!view) return;
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    svg.setAttribute("viewBox", "0 0 " + view.w + " " + view.h);
    (view.outlines || []).forEach(function (o) {
      var e = shape(o);
      e.setAttribute("class", "outline");
      svg.appendChild(e);
    });
    view.parts.forEach(function (p) {
      var e = shape(p);
      e.setAttribute("class", "part" + (selected[p.id] ? " on" : ""));
      e.setAttribute("data-id", p.id);
      var t = node("title");
      t.textContent = labels[p.id] || p.id;
      e.appendChild(t);
      e.addEventListener("click", function () { onTap(p.id); });
      svg.appendChild(e);
    });
    (view.texts || []).forEach(function (t) {
      var e = node("text", { x: t.x, y: t.y, "class": "label " + t.cls, "text-anchor": "middle" });
      e.textContent = t.s;
      svg.appendChild(e);
    });
  }

  // すべての部位 id（テスト・確認用）
  function allIds() {
    var ids = {};
    VIEWS.forEach(function (v) { v.build().parts.forEach(function (p) { ids[p.id] = true; }); });
    return Object.keys(ids);
  }

  return { views: VIEWS, draw: draw, allIds: allIds };
})();
