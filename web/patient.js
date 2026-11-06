// 受付・患者画面。AIもインターネットも使わない（院内サーバーとだけ通信する）。
// 古いiPad（第7世代）やAndroidのChromeでも動くよう、新しすぎる書き方は使わない。
"use strict";

var $ = function (id) { return document.getElementById(id); };
function el(tag, attrs) {
  var e = document.createElement(tag);
  attrs = attrs || {};
  Object.keys(attrs).forEach(function (k) {
    if (k === "class") e.className = attrs[k];
    else e.setAttribute(k, attrs[k]);
  });
  for (var i = 2; i < arguments.length; i++) {
    var c = arguments[i];
    e.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return e;
}
function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
function toHalf(s) {
  return s.replace(/[０-９．]/g, function (c) { return c === "．" ? "." : String.fromCharCode(c.charCodeAt(0) - 0xfee0); });
}

var S = {
  cfg: null,
  forms: [],
  form: null,        // 選んだ問診定義
  answers: {},       // { qid: { value, details: { label: text } } }
  current: null,     // 表示中の設問id
  sub: null,         // "main" = 人体シェーマの「いちばんつらいところ」を選ぶ画面
  bodyView: {},      // { qid: 表示中の図（front/back/…） }
  bodyLabels: {},    // 部位id → 表示名（サーバーから）
  fromReview: false,
  startedAt: null,
  startedMs: null,   // 「はじめる」を押した時刻（回答にかかった時間を計る）
  pending: null,     // 送信後の { record_id, number }
  lastActive: Date.now(),
  idleShownAt: null,
  screen: null
};

// 端末の時計のまま「2026-11-02T17:34:06」の形にする（サーバーの時刻と同じ表記）
function localIso(d) {
  function p(n) { return (n < 10 ? "0" : "") + n; }
  return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + "T" + p(d.getHours()) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds());
}

// ---------------------------------------------------------------- 言語（日本語・English・繁體中文）
// 決まった言葉（ボタン・案内）と体の部位名は /api/lang から、設問と選択肢の訳は問診票ごとの _i18n から。
// 訳すのは画面に出す言葉だけ。サーバーに送る回答は日本語の選択肢名のままなので、カルテの文は日本語で出る。
var L = { data: null, code: "ja" };
function T(key, n) {
  var ui = L.data ? (L.data.ui[L.code] || L.data.ui.ja) : {};
  var text = ui[key] !== undefined ? ui[key] : key;
  return n === undefined ? text : text.replace("{n}", n);
}
function qTr(q) {
  var t = S.form && S.form._i18n && S.form._i18n[L.code];
  return (t && t.q[q.id]) || {};
}
function qText(q) { return qTr(q).text || q.text; }
function qHint(q) { return q.hint ? (qTr(q).hint || q.hint) : ""; }
function qUnit(q) { return q.unit ? (qTr(q).unit || q.unit) : ""; }
function oText(q, o) { var x = (qTr(q).o || {})[o.label]; return (x && x.t) || o.label; }
function oDetail(q, o) { var x = (qTr(q).o || {})[o.label]; return (x && x.d) || o.detail; }
function labelText(q, label) {
  var o = q.options.filter(function (x) { return x.label === label; })[0];
  return o ? oText(q, o) : label;
}
// 画面に出ている決まった言葉（data-t の付いた要素）を、いまの言語に入れ替える
function applyLang() {
  if (!L.data) return;
  document.documentElement.lang = L.data.html_lang[L.code] || "ja";
  var nodes = document.querySelectorAll("[data-t]");
  for (var i = 0; i < nodes.length; i++) nodes[i].textContent = T(nodes[i].getAttribute("data-t"));
  var btns = document.querySelectorAll("#lang-switch button");
  for (var j = 0; j < btns.length; j++) btns[j].setAttribute("aria-pressed", String(btns[j].getAttribute("data-lang") === L.code));
  if (S.form) $("welcome-count").textContent = T("welcome_count", visibleQuestions().length);
}
function setLang(code) {
  L.code = code;
  applyLang();
}
// この問診票に訳がある言語だけ、はじめの画面にボタンを出す（訳がなければ何も出さない）
function renderLangSwitch() {
  var box = $("lang-switch");
  clear(box);
  var have = (S.form && S.form._i18n) || {};
  var list = L.data ? L.data.langs.filter(function (x) { return x.id === "ja" || have[x.id]; }) : [];
  box.hidden = list.length < 2;
  if (list.length < 2) return;
  list.forEach(function (x) {
    var b = el("button", { type: "button", "data-lang": x.id, lang: L.data.html_lang[x.id] || "ja" }, x.name);
    b.addEventListener("click", function () { setLang(x.id); });
    box.appendChild(b);
  });
}
// 言葉の見た目の長さ（英数字は半分の幅として数える）。選択肢を何列に並べるかを決めるのに使う
function width(text) {
  var n = 0;
  for (var i = 0; i < text.length; i++) n += text.charCodeAt(i) > 0xff ? 1 : 0.5;
  return n;
}

function api(path, opts) {
  return fetch(path, opts).catch(function () {
    throw new Error(T("err_net"));
  }).then(function (res) {
    return res.json().catch(function () { return {}; }).then(function (data) {
      if (!res.ok) throw new Error(data.error || "通信できませんでした");
      return data;
    });
  });
}
function post(path, body) {
  return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

// ---------------------------------------------------------------- 画面の高さ（iPadのアドレスバーで100vhがずれる対策）
function fitViewport() {
  document.documentElement.style.setProperty("--vh", (window.innerHeight / 100) + "px");
}
window.addEventListener("resize", fitViewport);
window.addEventListener("orientationchange", fitViewport);
fitViewport();

// ---------------------------------------------------------------- 文字の大きさ（小・中・大）
function setFontSize(size) {
  var root = document.documentElement;
  root.className = root.className.replace(/\bfs-[sml]\b/g, "").trim() + " fs-" + size;
  var btns = document.querySelectorAll("[data-fs]");
  for (var i = 0; i < btns.length; i++) btns[i].setAttribute("aria-pressed", String(btns[i].getAttribute("data-fs") === size));
}
(function () {
  var btns = document.querySelectorAll("[data-fs]");
  for (var i = 0; i < btns.length; i++) {
    btns[i].addEventListener("click", function () { setFontSize(this.getAttribute("data-fs")); });
  }
  setFontSize("m");
})();

// ---------------------------------------------------------------- 画面切り替え
var SCREENS = ["reception", "welcome", "question", "review", "number", "register", "done", "trial"];
// お試し（作る画面の「患者さんの画面で試す」から開く）。公開前の問診票を、保存せずに最後まで試す
var TRIAL = /[?&]try=1(&|$)/.test(window.location.search);
var PATIENT_SCREENS = ["welcome", "question", "review"];
function show(name) {
  SCREENS.forEach(function (s) { $("s-" + s).hidden = s !== name; });
  var patient = PATIENT_SCREENS.indexOf(name) >= 0;
  $("topbar").hidden = !patient;
  document.body.className = patient ? "has-topbar" : "";
  S.screen = name;
  window.scrollTo(0, 0);
}
function patientMode() { return PATIENT_SCREENS.indexOf(S.screen) >= 0; }

// ---------------------------------------------------------------- 受付：診療科を選んで渡す
function initReception() {
  return api("/api/config").then(function (cfg) {
    S.cfg = cfg;
    return api("/api/lang");
  }).then(function (lang) {
    L.data = lang;
    return api("/api/body");
  }).then(function (b) {
    S.bodyLabels = b.regions;
    return api("/api/forms");
  }).then(function (data) {
    S.forms = data.forms;
    var list = $("form-list");
    clear(list);
    S.forms.forEach(function (f) {
      var b = el("button", { "class": "choice form-choice", type: "button" },
        el("span", {}, f.title, el("span", { "class": "small" }, f.count + "問" +
          ((f.langs || []).length ? "　" + ["日本語"].concat(f.langs.map(function (c) {
            return (L.data.langs.filter(function (x) { return x.id === c; })[0] || {}).name || c;
          })).join("・") : ""))));
      b.addEventListener("click", function () { startForm(f.id); });
      list.appendChild(b);
    });
    $("form-errors").hidden = !data.errors.length;
    $("form-errors").textContent = data.errors.length ? "読み込めなかった問診票があります：\n" + data.errors.join("\n") : "";
  });
}

function beginForm(form) {
  S.form = form;
  S.answers = {};
  S.startedAt = localIso(new Date());
  S.startedMs = null;
  renderLangSwitch();
  setLang("ja");
  setFontSize("m");
  touch();
  show("welcome");
}
function startForm(id) {
  api("/api/forms/" + encodeURIComponent(id)).then(beginForm).catch(function (e) { alert(e.message); });
}

// お試し：受付の画面は通らず、作る画面で確認中の問診票をそのまま始める
function startTrial() {
  $("trial-badge").hidden = false;
  return api("/api/config").then(function (cfg) {
    S.cfg = cfg;
    return api("/api/lang");
  }).then(function (lang) {
    L.data = lang;
    return api("/api/body");
  }).then(function (b) {
    S.bodyLabels = b.regions;
    return api("/api/creator/trial");
  }).then(beginForm);
}

// ---------------------------------------------------------------- 設問の表示条件（app/karte.py の check_condition と同じ考え方）
// 「答えていない」ときは聞く側に倒す（eq と gte だけは答えが必要）
function toNum(v) {
  var n = parseFloat(String(v).replace(",", "."));
  return isNaN(n) ? null : n;
}
function checkCondition(c, answers) {
  if (c.all) return c.all.every(function (x) { return checkCondition(x, answers); });
  if (c.any) return c.any.some(function (x) { return checkCondition(x, answers); });
  var ref = answers[c.q] || {};
  var v = ref.value;
  var answered = !(v === undefined || v === null || v === "" || (Array.isArray(v) && v.length === 0));
  function has(x) { return v === x || (Array.isArray(v) && v.indexOf(x) >= 0); }
  if ("eq" in c) return answered && has(c.eq);
  if ("ne" in c) return !answered || !has(c.ne);
  var n = answered ? toNum(v) : null;
  if ("lt" in c) return n === null || n < c.lt;
  if ("gte" in c) return n !== null && n >= c.gte;
  return true;
}
function isVisible(q) { return !q.show_if || checkCondition(q.show_if, S.answers); }
function visibleQuestions() { return S.form.questions.filter(isVisible); }
function findQ(id) { return S.form.questions.filter(function (x) { return x.id === id; })[0]; }
function indexOfId(qs, id) { for (var i = 0; i < qs.length; i++) if (qs[i].id === id) return i; return -1; }

function hasAnswer(q) {
  var a = S.answers[q.id];
  if (!a) return false;
  if (a.talk) return true;   // 書くかわりに「診察のときに話します」を選んだ
  var v = a.value;
  return !(v === undefined || v === null || v === "" || (Array.isArray(v) && v.length === 0));
}

// ---------------------------------------------------------------- 1問ずつ
$("btn-begin").addEventListener("click", function () {
  if (!S.startedMs) S.startedMs = Date.now();
  goTo(visibleQuestions()[0].id);
});

function goTo(qid) {
  S.current = qid;
  S.sub = null;
  renderQuestion();
  show("question");
}

function renderQuestion() {
  var qs = visibleQuestions();
  var q = findQ(S.current);
  var pos = indexOfId(qs, q.id) + 1;
  $("progress-text").textContent = pos + " / " + qs.length;
  $("progress-bar").style.width = ((pos - 1) / qs.length) * 100 + "%";
  $("q-text").textContent = qText(q);
  $("q-hint").hidden = !q.hint;
  $("q-hint").textContent = qHint(q);
  $("q-msg").hidden = true;
  var body = $("q-body");
  clear(body);
  var figure = q.type === "body" && S.sub !== "main";
  body.className = "q-body" + (figure ? " is-body" : "");
  // 体の図の設問は、スクロールなしで1画面に収める（style.css の .screen.fit）
  $("s-question").className = "screen" + (figure ? " fit" : "");
  var a = S.answers[q.id] || {};
  $("btn-back").textContent = S.fromReview ? T("to_review") : T("back");

  if (q.type === "body") {
    if (S.sub === "main") renderBodyMain(q, a, body);
    else renderBody(q, a, body);
    return;
  }
  if (q.type === "single" || q.type === "multi") {
    var multi = q.type === "multi";
    var chosen = multi ? (a.value || []) : (a.value ? [a.value] : []);
    // 選択肢が多いときは2列・3列に並べる（言葉が短いときだけ）
    var longest = 0;
    q.options.forEach(function (o) { longest = Math.max(longest, width(oText(q, o))); });
    if (q.options.length >= 13 && longest <= 7) body.className += " cols3";
    else if (q.options.length >= 6 && longest <= 20) body.className += " cols2" + (q.options.length >= 13 ? " dense" : "");
    q.options.forEach(function (o, idx) {
      var on = chosen.indexOf(o.label) >= 0;
      var btn = el("button", { "class": "choice" + (multi ? " multi" : ""), type: "button", "aria-pressed": String(on) },
        el("span", { "class": "mark" }, "✓"), el("span", {}, oText(q, o)));
      btn.addEventListener("click", function () { choose(q, o.label); });
      body.appendChild(btn);
      if (on && o.detail) {
        var id = "detail-" + q.id + "-" + idx;
        var ta = el("textarea", { id: id, rows: "2" });
        ta.value = (a.details || {})[o.label] || "";
        ta.addEventListener("input", function () {
          var cur = S.answers[q.id];
          cur.details = cur.details || {};
          cur.details[o.label] = ta.value;
        });
        body.appendChild(el("div", { "class": "detail" }, el("label", { "for": id }, oDetail(q, o)), ta,
          el("p", { "class": "detail-note" }, T("detail_note"))));
      }
    });
  } else if (q.type === "number") {
    renderNumber(q, a, body);
  } else if (q.type === "time") {
    var t = el("input", { "class": "q-input", type: "time", "aria-label": qText(q) });
    t.value = a.value || "";
    t.addEventListener("input", function () { setValue(q, t.value); });
    t.addEventListener("change", function () { setValue(q, t.value); });
    body.appendChild(t);
  } else {
    // 自由に書く欄。文字を打つのが難しい人のために、「診察のときに話します」で先へ進めるようにする
    var ta2 = el("textarea", { "aria-label": qText(q) });
    ta2.value = a.value || "";
    var talk = el("button", { "class": "choice talk", type: "button", "aria-pressed": String(!!a.talk) },
      el("span", { "class": "mark" }, "✓"), el("span", {}, T("talk_btn")));
    ta2.addEventListener("input", function () {
      setValue(q, ta2.value);
      talk.setAttribute("aria-pressed", "false");
    });
    talk.addEventListener("click", function () {
      if ((S.answers[q.id] || {}).talk) delete S.answers[q.id];
      else S.answers[q.id] = { talk: true };
      renderQuestion();
    });
    body.appendChild(ta2);
    body.appendChild(talk);
  }
  updateNext(q);
}

// ---------------------------------------------------------------- 数字（画面の大きな数字ボタン。端末のキーボードは出さない）
function numberText(q) {
  var a = S.answers[q.id];
  return a && a.value != null ? String(a.value) : "";
}
// 小数点を出すか。定義に decimal があればそれに従い、なければ単位で決める（体温・体重・身長）
function wantsDecimal(q) {
  return q.decimal !== undefined ? !!q.decimal : /℃|度|kg|ｋｇ|キロ|cm|ｃｍ|センチ/i.test(q.unit || "");
}
function renderNumber(q, a, body) {
  var cur = numberText(q);
  body.appendChild(el("div", { "class": "num-display" + (cur ? "" : " empty"), "aria-live": "polite" },
    el("span", { "class": "num-value" }, cur || "　"), el("span", { "class": "unit" }, qUnit(q))));
  var pad = el("div", { "class": "numpad" });
  ["1", "2", "3", "4", "5", "6", "7", "8", "9", wantsDecimal(q) ? "." : "", "0", "del"].forEach(function (k) {
    if (!k) { pad.appendChild(el("span", {})); return; }
    var b = el("button", { "class": "num-key" + (k === "del" ? " del" : ""), type: "button" }, k === "del" ? T("del") : k);
    b.addEventListener("click", function () { pressNumber(q, k); });
    pad.appendChild(b);
  });
  body.appendChild(pad);
}
function pressNumber(q, k) {
  var cur = numberText(q);
  if (k === "del") cur = cur.slice(0, -1);
  else if (k === ".") { if (cur && cur.indexOf(".") < 0 && wantsDecimal(q)) cur += "."; }
  else if (cur.length < 6) cur = (cur === "0" ? "" : cur) + k;
  setValue(q, cur);
  renderQuestion();
}
// パソコンのキーボードでも数字を入れられるようにする（職員が試すとき用）
document.addEventListener("keydown", function (ev) {
  if (S.screen !== "question" || !S.form) return;
  var q = findQ(S.current);
  if (!q || q.type !== "number") return;
  var k = /^[0-9]$/.test(ev.key) ? ev.key : ev.key === "." ? "." : ev.key === "Backspace" ? "del" : null;
  if (!k) return;
  ev.preventDefault();
  pressNumber(q, k);
});

// ---------------------------------------------------------------- 人体シェーマ
function bodyLabel(id) { return ((L.data && L.data.body[L.code]) || {})[id] || S.bodyLabels[id] || id; }

function renderBody(q, a, body) {
  var views = TolmonBody.views.filter(function (v) { return !q.views || q.views.indexOf(v.id) >= 0; });
  var current = S.bodyView[q.id] || views[0].id;
  var tabs = el("div", { "class": "body-tabs" });
  views.forEach(function (v) {
    var b = el("button", { "class": "body-tab", type: "button", "aria-pressed": String(v.id === current) }, T("view_" + v.id));
    b.addEventListener("click", function () { S.bodyView[q.id] = v.id; renderQuestion(); });
    tabs.appendChild(b);
  });
  var box = el("div", { "class": "body-box" });
  var selected = {};
  (a.value || []).forEach(function (id) { selected[id] = true; });
  TolmonBody.draw(current, box, selected, function (id) { toggleBody(q, id); }, bodySex(q));
  translateFigure(box);
  var picked = a.value || [];
  var list = el("p", { "class": "body-selected" + (picked.length ? "" : " empty") },
    picked.length ? T("body_picked") + picked.map(bodyLabel).join(T("sep")) : T("body_tap"));
  body.appendChild(tabs);
  body.appendChild(box);
  body.appendChild(list);
  updateNext(q);
}

// 図の中の文字（右側・左側・右手のひら など）を、いまの言語にする
var FIGURE_WORDS = { "右側": "fig_right", "左側": "fig_left", "頭の後ろ": "fig_head_back", "顔": "fig_face" };
function translateFigure(box) {
  if (L.code === "ja") return;
  var ids = {};
  Object.keys(S.bodyLabels).forEach(function (id) { ids[S.bodyLabels[id]] = id; });
  var texts = box.querySelectorAll("text");
  for (var i = 0; i < texts.length; i++) {
    var ja = texts[i].textContent;
    if (FIGURE_WORDS[ja]) texts[i].textContent = T(FIGURE_WORDS[ja]);
    else if (ids[ja]) texts[i].textContent = bodyLabel(ids[ja]);
  }
}

// 図の男女：性別の設問（既定は id "sex"）で「女性」と答えていれば女性の図。答えていなければ男性の図
function bodySex(q) {
  var a = S.answers[q.sex_q || "sex"];
  return a && a.value === (q.female || "女性") ? "f" : "m";
}

function toggleBody(q, id) {
  var a = S.answers[q.id] || { value: [] };
  var v = a.value || [];
  var i = v.indexOf(id);
  if (i >= 0) v.splice(i, 1); else v.push(id);
  if (a.main && v.indexOf(a.main) < 0) delete a.main;
  if (!v.length) delete S.answers[q.id];
  else { a.value = v; S.answers[q.id] = a; }
  renderQuestion();
}

// 2か所以上選んだときだけ：「いちばんつらいところ」を1つ選ぶ（紙の問診票の意図＝主訴を知る）
function renderBodyMain(q, a, body) {
  $("q-text").textContent = T("body_main_q");
  $("q-hint").hidden = false;
  $("q-hint").textContent = T("body_main_hint");
  (a.value || []).forEach(function (id) {
    var btn = el("button", { "class": "choice", type: "button", "aria-pressed": String(a.main === id) },
      el("span", { "class": "mark" }, "✓"), el("span", {}, bodyLabel(id)));
    btn.addEventListener("click", function () { a.main = id; renderQuestion(); });
    body.appendChild(btn);
  });
  $("btn-next").disabled = !a.main;
  $("btn-next").textContent = T("next");
  $("btn-back").textContent = T("to_figure");
}

function setValue(q, v) {
  if (v === "" || v === null) delete S.answers[q.id];
  else {
    var cur = S.answers[q.id] || {};
    cur.value = v;
    delete cur.talk;          // 書いたら「診察のときに話します」は取り消す
    S.answers[q.id] = cur;
  }
  updateNext(q);
}

function choose(q, label) {
  var a = S.answers[q.id] || { details: {} };
  if (q.type === "multi") {
    var cur = a.value || [];
    var on = cur.indexOf(label) >= 0;
    a.value = q.options.map(function (o) { return o.label; }).filter(function (l) {
      return l === label ? !on : cur.indexOf(l) >= 0;
    });
  } else {
    a.value = a.value === label ? null : label;
  }
  if (!a.value || (Array.isArray(a.value) && !a.value.length)) delete S.answers[q.id];
  else S.answers[q.id] = a;
  renderQuestion();
}

function updateNext(q) {
  var answered = hasAnswer(q);
  $("btn-next").disabled = !!q.required && !answered;
  $("btn-next").textContent = answered || q.required ? T("next") : T("skip");
}

function checkCurrent(q) {
  if (q.type === "number" && hasAnswer(q)) {
    // 「36.」のように小数点で終わっていたら、点を取る
    S.answers[q.id].value = String(S.answers[q.id].value).replace(/\.$/, "");
    var n = toNum(S.answers[q.id].value);
    if (n === null) return T("err_number");
    if (q.min !== undefined && n < q.min) return T("err_min", q.min);
    if (q.max !== undefined && n > q.max) return T("err_max", q.max);
  }
  return null;
}

$("btn-next").addEventListener("click", function () {
  var q = findQ(S.current);
  var err = checkCurrent(q);
  if (err) {
    $("q-msg").textContent = err;
    $("q-msg").hidden = false;
    return;
  }
  // 人体シェーマで2か所以上 → 先に「いちばんつらいところ」を選ぶ
  if (q.type === "body" && S.sub !== "main") {
    var picked = (S.answers[q.id] || {}).value || [];
    if (picked.length >= 2) {
      S.sub = "main";
      renderQuestion();
      return;
    }
  }
  S.sub = null;
  var qs = visibleQuestions();
  var i = indexOfId(qs, q.id);
  // 確認画面から直しに来たときは、新しく出てきた設問がなければ確認画面へ戻る
  if (S.fromReview) {
    var next = qs[i + 1];
    if (next && !hasAnswer(next) && next.show_if) return goTo(next.id);
    S.fromReview = false;
    return openReview();
  }
  if (i + 1 < qs.length) goTo(qs[i + 1].id);
  else openReview();
});

$("btn-back").addEventListener("click", function () {
  if (S.sub === "main") {
    S.sub = null;
    renderQuestion();
    return;
  }
  if (S.fromReview) {
    S.fromReview = false;
    return openReview();
  }
  var qs = visibleQuestions();
  var i = indexOfId(qs, S.current);
  if (i > 0) goTo(qs[i - 1].id);
  else show("welcome");
});

// ---------------------------------------------------------------- 確認・送信
function answerText(q) {
  if (!hasAnswer(q)) return null;
  var a = S.answers[q.id];
  if (a.talk) return T("talk");
  if (q.type === "body") {
    var many = a.value.length >= 2;
    return a.value.map(function (id) { return bodyLabel(id) + (many && id === a.main ? T("main_suffix") : ""); }).join(T("sep"));
  }
  if (q.type === "single" || q.type === "multi") {
    var labels = Array.isArray(a.value) ? a.value : [a.value];
    return labels.map(function (l) {
      var d = ((a.details || {})[l] || "").trim();
      return d ? labelText(q, l) + T("lp") + d + T("rp") : labelText(q, l);
    }).join(T("sep"));
  }
  if (q.type === "number") return (a.value + " " + qUnit(q)).trim();
  return a.value;
}

function openReview() {
  var list = $("review-list");
  clear(list);
  visibleQuestions().forEach(function (q) {
    var t = answerText(q);
    var fix = el("button", { "class": "btn", type: "button" }, T("fix"));
    fix.addEventListener("click", function () { S.fromReview = true; goTo(q.id); });
    list.appendChild(el("li", {},
      el("div", { "class": "grow" }, el("div", { "class": "rq" }, qText(q)), el("div", { "class": "ra" + (t ? "" : " empty") }, t || T("no_answer"))),
      fix));
  });
  $("submit-msg").hidden = true;
  show("review");
}

$("btn-review-back").addEventListener("click", function () {
  var qs = visibleQuestions();
  goTo(qs[qs.length - 1].id);
});

$("btn-submit").addEventListener("click", function () {
  var btn = $("btn-submit");
  btn.disabled = true;
  btn.textContent = T("sending");
  // 表示されていない設問の回答は送らない
  var answers = {};
  visibleQuestions().forEach(function (q) { if (hasAnswer(q)) answers[q.id] = S.answers[q.id]; });
  var sending = TRIAL
    // お試し：保存はしない。カルテにどう出るかだけ受け取って見せる
    ? post("/api/creator/trial/karte", { answers: answers }).then(function (res) {
      S.answers = {};
      $("trial-karte").textContent = res.karte;
      show("trial");
    })
    : post("/api/answers", { form_id: S.form.id, form_hash: S.form._hash, answers: answers, started_at: S.startedAt,
      seconds: S.startedMs ? Math.round((Date.now() - S.startedMs) / 1000) : null, lang: L.code === "ja" ? null : L.code })
    .then(function (res) {
      // 送った時点でサーバーに保存済み。タブレットには受付番号だけを出す（回答の中身は消す）
      S.pending = { record_id: res.record_id, number: res.number, title: S.form.title };
      S.answers = {};
      $("number").textContent = res.number;
      show("number");
    });
  sending
    .catch(function (e) {
      $("submit-msg").textContent = e.message + "\n" + T("call_staff");
      $("submit-msg").hidden = false;
    })
    .then(function () {
      btn.disabled = false;
      btn.textContent = T("submit");
    });
});

// ---------------------------------------------------------------- 職員：受付番号に患者IDを登録
$("btn-to-register").addEventListener("click", function () {
  $("reg-number").textContent = S.pending.number;
  $("reg-form").textContent = S.pending.title;
  $("pcode").value = "";
  updateRegister();
  show("register");
  $("pcode").focus();
});

function pcodeValid() { return new RegExp(S.cfg.pcode_pattern).test($("pcode").value.trim()); }
function updateRegister() {
  var v = $("pcode").value.trim();
  $("pcode-msg").hidden = !v || pcodeValid();
  $("pcode-msg").textContent = "患者IDは数字で入力してください";
  $("btn-reg-check").disabled = !pcodeValid();
}
$("pcode").addEventListener("input", function () {
  var e = $("pcode");
  var fixed = toHalf(e.value).replace(/\s/g, "");
  if (fixed !== e.value) e.value = fixed;
  updateRegister();
});
$("pcode").addEventListener("keydown", function (ev) { if (ev.key === "Enter" && !$("btn-reg-check").disabled) openConfirm(); });
$("btn-reg-check").addEventListener("click", openConfirm);
$("btn-reg-later").addEventListener("click", resetAll);  // 回答は「受付待ち」のまま残る（受付待ち一覧から登録できる）

function openConfirm() {
  $("confirm-number").textContent = S.pending.number;
  $("confirm-pcode").textContent = $("pcode").value.trim();
  $("confirm-form").textContent = S.pending.title;
  $("confirm-msg").hidden = true;
  $("dlg-confirm").hidden = false;
  $("pcode").blur();
}
$("btn-confirm-no").addEventListener("click", function () {
  $("dlg-confirm").hidden = true;
  $("pcode").focus();
  $("pcode").select();
});
$("btn-confirm-yes").addEventListener("click", function () {
  var pcode = $("pcode").value.trim();
  post("/api/answers/" + encodeURIComponent(S.pending.record_id) + "/register", { pcode: pcode })
    .then(function () {
      $("dlg-confirm").hidden = true;
      $("done-text").textContent = "受付番号 " + S.pending.number + " ＝ 患者ID " + pcode;
      show("done");
      setTimeout(resetAll, 2500);
    })
    .catch(function (e) {
      $("confirm-msg").textContent = e.message;
      $("confirm-msg").hidden = false;
    });
});

// ---------------------------------------------------------------- リセット（次の患者さんに前の回答を見せない）
function resetAll() {
  S.form = null;
  S.answers = {};
  S.current = null;
  S.fromReview = false;
  S.pending = null;
  S.idleShownAt = null;
  $("pcode").value = "";
  ["dlg-confirm", "dlg-idle", "dlg-abort"].forEach(function (d) { $(d).hidden = true; });
  setFontSize("m");
  setLang("ja");                                   // 次の患者さんは、また日本語から
  if (TRIAL) return startTrial().catch(trialFailed);   // お試しは受付の画面に戻らず、はじめからやり直す
  show("reception");
}

function trialFailed(e) { document.body.textContent = e.message; }
$("btn-trial-again").addEventListener("click", resetAll);
$("btn-trial-close").addEventListener("click", function () {
  window.close();                                // 作る画面から開いたタブなら閉じる
  window.location.href = "/admin";               // 閉じられなかったときは作る画面へ
});

$("btn-abort").addEventListener("click", function () { $("dlg-abort").hidden = false; });
$("btn-abort-no").addEventListener("click", function () { $("dlg-abort").hidden = true; touch(); });
$("btn-abort-yes").addEventListener("click", resetAll);

// ---------------------------------------------------------------- 無操作の見張り（答えている途中だけ）
function touch() {
  S.lastActive = Date.now();
  if (S.idleShownAt) {
    S.idleShownAt = null;
    $("dlg-idle").hidden = true;
  }
}
["pointerdown", "touchstart", "mousedown", "keydown", "input"].forEach(function (ev) {
  document.addEventListener(ev, function () { if (!S.idleShownAt) touch(); }, true);
});
$("btn-idle-continue").addEventListener("click", touch);

setInterval(function () {
  if (!S.cfg || !patientMode()) return;
  var now = Date.now();
  if (!S.idleShownAt && now - S.lastActive > S.cfg.idle_seconds * 1000) {
    S.idleShownAt = now;
    $("dlg-idle").hidden = false;
  }
  if (S.idleShownAt) {
    var left = Math.ceil(S.cfg.idle_grace_seconds - (now - S.idleShownAt) / 1000);
    $("idle-text").textContent = T("idle_text", Math.max(left, 0));
    if (left <= 0) resetAll();
  }
}, 1000);

// ---------------------------------------------------------------- 開始
if (TRIAL) {
  startTrial().then(function () {
    // 作る画面の「この設問を試す」から来たとき（?try=1&at=設問id）：その設問から始める
    var m = /[?&]at=([a-z][a-z0-9_]*)/.exec(window.location.search);
    if (m && findQ(m[1])) goTo(m[1]);
  }).catch(trialFailed);
} else {
  initReception().then(function () { show("reception"); }).catch(function (e) {
    document.body.textContent = "問診サーバーにつながりません：" + e.message;
  });
}
