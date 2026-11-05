// 医師・看護師画面。AIは使わない。
//   /karte?pcode=患者ID … 電子カルテの【問診】アイコンから開く。その患者さんの当日の問診だけを表示
//   /doctor            … 職員用の一覧（日付・患者IDで絞り込み）
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
function today() {
  var d = new Date();
  function p(n) { return (n < 10 ? "0" : "") + n; }
  return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate());
}
function api(path) {
  return fetch(path).catch(function () {
    throw new Error("トルモンのサーバーにつながりません");
  }).then(function (res) {
    return res.json().catch(function () { return {}; }).then(function (data) {
      if (!res.ok) throw new Error(data.error || "通信できませんでした");
      return data;
    });
  });
}

var params = new URLSearchParams(location.search);
var D = {
  karteMode: location.pathname === "/karte",
  pcode: (params.get("pcode") || "").replace(/[^0-9A-Za-z]/g, ""),
  selected: null,
  known: null
};

// ---------------------------------------------------------------- 1件分の表示（カルテ向け文章＋コピー＋原文）
function recordView(rec, withHeader) {
  var karte = el("textarea", { "class": "d-karte", spellcheck: "false", "aria-label": "カルテ貼り付け用テキスト" });
  karte.value = rec.karte_text;
  var copyBtn = el("button", { "class": "d-btn primary", type: "button" }, "カルテ貼り付け用にコピー");
  copyBtn.addEventListener("click", function () { copyText(karte); });

  var qa = el("ol");
  rec.shown.forEach(function (s) {
    var empty = s.answer === "（未回答）";
    qa.appendChild(el("li", {}, el("div", { "class": "q" }, s.text), el("div", { "class": "a" + (empty ? " empty" : "") }, s.answer)));
  });

  var meta = el("p", { "class": "d-meta" });
  if (withHeader) meta.appendChild(el("span", {}, "患者ID ", el("b", {}, rec.pcode)));
  meta.appendChild(el("span", {}, rec.form_title));
  meta.appendChild(el("span", {}, "受付番号 " + rec.number));
  meta.appendChild(el("span", {}, "送信 " + rec.created_at.replace("T", " ").slice(0, 16)));

  var box = el("div", { "class": "k-record" },
    meta,
    el("div", { "class": "d-sec-head" }, el("h2", {}, "カルテ貼り付け用"), copyBtn),
    karte,
    el("details", { "class": "d-qa" }, el("summary", {}, "患者さんに表示した設問と回答（原文）"), qa));
  setTimeout(function () { fitHeight(karte); }, 0);
  return box;
}

// 中でスクロールしないよう、文章の長さに合わせて高さを伸ばす
function fitHeight(t) {
  t.style.height = "auto";
  t.style.height = (t.scrollHeight + 4) + "px";
}
window.addEventListener("resize", function () {
  var areas = document.querySelectorAll(".d-karte");
  for (var i = 0; i < areas.length; i++) fitHeight(areas[i]);
});

// ---------------------------------------------------------------- 患者IDつき（【問診】アイコンから）
function loadKarte() {
  var detail = $("d-detail");
  if (!D.pcode) {
    clear(detail);
    detail.appendChild(el("p", { "class": "warn" }, "患者IDが指定されていません（電子カルテの【問診】から開いてください）"));
    return;
  }
  var day = today();
  api("/api/answers?date=" + day + "&pcode=" + encodeURIComponent(D.pcode)).then(function (data) {
    var ids = data.records.map(function (r) { return r.record_id; });
    return Promise.all(ids.map(function (id) { return api("/api/answers/" + encodeURIComponent(id)); }));
  }).then(function (recs) {
    clear(detail);
    detail.appendChild(el("h2", { "class": "k-title" },
      el("span", {}, "患者ID ", el("b", { "class": "pc" }, D.pcode)),
      el("span", { "class": "day" }, "本日（" + day.replace(/-/g, "/") + "）の問診　" + recs.length + "件")));
    if (!recs.length) {
      detail.appendChild(el("p", { "class": "d-empty" }, "本日の問診はまだありません。受付待ちの場合は、受付で患者IDの登録が必要です。"));
      return;
    }
    recs.forEach(function (rec) { detail.appendChild(recordView(rec, false)); });
  }).catch(function (e) {
    clear(detail);
    detail.appendChild(el("p", { "class": "warn" }, e.message));
  });
}

// ---------------------------------------------------------------- 一覧（職員用）
function loadList() {
  var qs = [];
  if ($("f-date").value) qs.push("date=" + encodeURIComponent($("f-date").value));
  var p = $("f-pcode").value.trim();
  if (p) qs.push("pcode=" + encodeURIComponent(p));
  api("/api/answers?" + qs.join("&")).then(function (data) {
    var rows = data.records;
    var first = D.known === null;
    var known = D.known || {};
    var list = $("d-list");
    clear(list);
    rows.forEach(function (r) {
      var isNew = !first && !known[r.record_id];
      var b = el("button", { "class": "d-item" + (isNew ? " new" : ""), type: "button", "data-id": r.record_id,
        "aria-current": String(r.record_id === D.selected) },
        el("span", { "class": "t" }, r.created_at.slice(11, 16)),
        el("span", { "class": "p" }, r.pcode),
        el("span", { "class": "f" }, r.form_title + "　受付 " + r.number));
      b.addEventListener("click", function () { openRecord(r.record_id); });
      list.appendChild(el("li", {}, b));
      known[r.record_id] = true;
    });
    D.known = known;
    $("list-count").textContent = rows.length ? rows.length + "件（新しい順）" : "この条件の問診はまだありません";
  }).catch(function (e) { $("list-count").textContent = e.message; });
}

function openRecord(id) {
  D.selected = id;
  var items = document.querySelectorAll(".d-item");
  for (var i = 0; i < items.length; i++) {
    var on = items[i].getAttribute("data-id") === id;
    items[i].setAttribute("aria-current", String(on));
    if (on) items[i].classList.remove("new");
  }
  api("/api/answers/" + encodeURIComponent(id)).then(function (rec) {
    var detail = $("d-detail");
    clear(detail);
    detail.appendChild(recordView(rec, true));
  }).catch(function (e) {
    var detail = $("d-detail");
    clear(detail);
    detail.appendChild(el("p", { "class": "warn" }, e.message));
  });
}

// ---------------------------------------------------------------- コピー（院内の http でも動くよう3段構え）
function copyText(textarea) {
  var text = textarea.value;
  function done() { toast("コピーしました。カルテに貼り付けてください"); }
  function legacy() {
    textarea.focus();
    textarea.select();
    textarea.setSelectionRange(0, text.length);
    try {
      if (document.execCommand("copy")) return done();
    } catch (e) { /* 次の方法へ */ }
    toast("全文を選択しました。Ctrl＋C でコピーしてください");
  }
  // 1) 新しいコピー機能：HTTPS か localhost のときだけ使える
  if (window.isSecureContext && navigator.clipboard) {
    navigator.clipboard.writeText(text).then(done, legacy);
  } else {
    legacy();  // 2) 古いコピー機能：院内の http でも動く → 3) だめなら全文選択
  }
}

var toastTimer = null;
function toast(msg) {
  $("toast").textContent = msg;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(function () { $("toast").hidden = true; }, 2500);
}

// ---------------------------------------------------------------- 開始
if (D.karteMode) {
  document.body.className += " karte";
  document.title = "問診 " + D.pcode + " | トルモン";
  loadKarte();
  setInterval(loadKarte, 30000);
} else {
  $("f-date").value = today();
  $("f-date").addEventListener("change", function () { D.known = null; loadList(); });
  $("f-pcode").addEventListener("input", function () {
    var e = $("f-pcode");
    e.value = e.value.replace(/[０-９]/g, function (c) { return String.fromCharCode(c.charCodeAt(0) - 0xfee0); }).replace(/\s/g, "");
    D.known = null;
    loadList();
  });
  $("btn-refresh").addEventListener("click", loadList);
  loadList();
  setInterval(loadList, 10000);  // 新しい問診が届いたら一覧に出す
}
