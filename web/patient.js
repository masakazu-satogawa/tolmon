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
  fromReview: false,
  startedAt: null,
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

function api(path, opts) {
  return fetch(path, opts).then(function (res) {
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
var SCREENS = ["reception", "welcome", "question", "review", "number", "register", "done"];
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
    return api("/api/forms");
  }).then(function (data) {
    S.forms = data.forms;
    var list = $("form-list");
    clear(list);
    S.forms.forEach(function (f) {
      var b = el("button", { "class": "choice form-choice", type: "button" },
        el("span", {}, f.title, el("span", { "class": "small" }, f.count + "問")));
      b.addEventListener("click", function () { startForm(f.id); });
      list.appendChild(b);
    });
    $("form-errors").hidden = !data.errors.length;
    $("form-errors").textContent = data.errors.length ? "読み込めなかった問診票があります：\n" + data.errors.join("\n") : "";
  });
}

function startForm(id) {
  api("/api/forms/" + encodeURIComponent(id)).then(function (form) {
    S.form = form;
    S.answers = {};
    S.startedAt = localIso(new Date());
    $("welcome-count").textContent = "質問はおよそ " + visibleQuestions().length + " 問です。";
    setFontSize("m");
    touch();
    show("welcome");
  }).catch(function (e) { alert(e.message); });
}

// ---------------------------------------------------------------- 設問の表示条件（app/karte.py の check_condition と同じ考え方）
// 「答えていない」ときは聞く側に倒す（eq と gte だけは答えが必要）
function toNum(v) {
  var n = parseFloat(String(v).replace(",", "."));
  return isNaN(n) ? null : n;
}
function checkCondition(c, answers) {
  if (c.all) return c.all.every(function (x) { return checkCondition(x, answers); });
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
  var v = a.value;
  return !(v === undefined || v === null || v === "" || (Array.isArray(v) && v.length === 0));
}

// ---------------------------------------------------------------- 1問ずつ
$("btn-begin").addEventListener("click", function () { goTo(visibleQuestions()[0].id); });

function goTo(qid) {
  S.current = qid;
  renderQuestion();
  show("question");
}

function renderQuestion() {
  var qs = visibleQuestions();
  var q = findQ(S.current);
  var pos = indexOfId(qs, q.id) + 1;
  $("progress-text").textContent = pos + " / " + qs.length;
  $("progress-bar").style.width = ((pos - 1) / qs.length) * 100 + "%";
  $("q-text").textContent = q.text;
  $("q-hint").hidden = !q.hint;
  $("q-hint").textContent = q.hint || "";
  $("q-msg").hidden = true;
  var body = $("q-body");
  clear(body);
  var a = S.answers[q.id] || {};

  if (q.type === "single" || q.type === "multi") {
    var multi = q.type === "multi";
    var chosen = multi ? (a.value || []) : (a.value ? [a.value] : []);
    q.options.forEach(function (o, idx) {
      var on = chosen.indexOf(o.label) >= 0;
      var btn = el("button", { "class": "choice" + (multi ? " multi" : ""), type: "button", "aria-pressed": String(on) },
        el("span", { "class": "mark" }, "✓"), el("span", {}, o.label));
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
        body.appendChild(el("div", { "class": "detail" }, el("label", { "for": id }, o.detail), ta));
      }
    });
  } else if (q.type === "number") {
    var inp = el("input", { "class": "q-input", inputmode: "decimal", autocomplete: "off", "aria-label": q.text });
    inp.value = a.value != null ? a.value : "";
    inp.addEventListener("input", function () {
      var fixed = toHalf(inp.value);
      if (fixed !== inp.value) inp.value = fixed;
      setValue(q, inp.value.trim());
    });
    body.appendChild(el("div", { "class": "number-row" }, inp, el("span", { "class": "unit" }, q.unit || "")));
  } else if (q.type === "time") {
    var t = el("input", { "class": "q-input", type: "time", "aria-label": q.text });
    t.value = a.value || "";
    t.addEventListener("input", function () { setValue(q, t.value); });
    t.addEventListener("change", function () { setValue(q, t.value); });
    body.appendChild(t);
  } else {
    var ta2 = el("textarea", { "aria-label": q.text });
    ta2.value = a.value || "";
    ta2.addEventListener("input", function () { setValue(q, ta2.value); });
    body.appendChild(ta2);
  }
  updateNext(q);
  $("btn-back").textContent = S.fromReview ? "確認画面へ" : "もどる";
}

function setValue(q, v) {
  if (v === "" || v === null) delete S.answers[q.id];
  else {
    var cur = S.answers[q.id] || {};
    cur.value = v;
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
  $("btn-next").textContent = answered || q.required ? "次へ" : "答えずに次へ";
}

function checkCurrent(q) {
  if (q.type === "number" && hasAnswer(q)) {
    var n = toNum(S.answers[q.id].value);
    if (n === null) return "数字で入力してください";
    if (q.min !== undefined && n < q.min) return q.min + " 以上の数字を入力してください";
    if (q.max !== undefined && n > q.max) return q.max + " 以下の数字を入力してください";
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
  if (q.type === "single" || q.type === "multi") {
    var labels = Array.isArray(a.value) ? a.value : [a.value];
    return labels.map(function (l) {
      var d = ((a.details || {})[l] || "").trim();
      return d ? l + "（" + d + "）" : l;
    }).join("、");
  }
  if (q.type === "number") return (a.value + " " + (q.unit || "")).trim();
  return a.value;
}

function openReview() {
  var list = $("review-list");
  clear(list);
  visibleQuestions().forEach(function (q) {
    var t = answerText(q);
    var fix = el("button", { "class": "btn", type: "button" }, "なおす");
    fix.addEventListener("click", function () { S.fromReview = true; goTo(q.id); });
    list.appendChild(el("li", {},
      el("div", { "class": "grow" }, el("div", { "class": "rq" }, q.text), el("div", { "class": "ra" + (t ? "" : " empty") }, t || "（答えていません）")),
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
  btn.textContent = "送っています…";
  // 表示されていない設問の回答は送らない
  var answers = {};
  visibleQuestions().forEach(function (q) { if (hasAnswer(q)) answers[q.id] = S.answers[q.id]; });
  post("/api/answers", { form_id: S.form.id, form_hash: S.form._hash, answers: answers, started_at: S.startedAt })
    .then(function (res) {
      // 送った時点でサーバーに保存済み。タブレットには受付番号だけを出す（回答の中身は消す）
      S.pending = { record_id: res.record_id, number: res.number, title: S.form.title };
      S.answers = {};
      $("number").textContent = res.number;
      show("number");
    })
    .catch(function (e) {
      $("submit-msg").textContent = e.message + "\n係の者をお呼びください。";
      $("submit-msg").hidden = false;
    })
    .then(function () {
      btn.disabled = false;
      btn.textContent = "この内容で送る";
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
  show("reception");
}

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
    $("idle-count").textContent = Math.max(left, 0);
    if (left <= 0) resetAll();
  }
}, 1000);

// ---------------------------------------------------------------- 開始
initReception().then(function () { show("reception"); }).catch(function (e) {
  document.body.textContent = "問診サーバーにつながりません：" + e.message;
});
