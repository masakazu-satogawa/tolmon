// 受付待ち一覧（職員用）。タブレット側で患者IDを登録できなかった回答を、ここから登録する。
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
function toHalf(s) { return s.replace(/[０-９]/g, function (c) { return String.fromCharCode(c.charCodeAt(0) - 0xfee0); }).replace(/\s/g, ""); }
function today() {
  var d = new Date();
  function p(n) { return (n < 10 ? "0" : "") + n; }
  return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate());
}
function api(path, opts) {
  return fetch(path, opts).catch(function () {
    throw new Error("トルモンのサーバーにつながりません");
  }).then(function (res) {
    return res.json().catch(function () { return {}; }).then(function (data) {
      if (!res.ok) throw new Error(data.error || "通信できませんでした");
      return data;
    });
  });
}

var R = { cfg: null, target: null };

function loadList() {
  var day = $("f-date").value || today();
  api("/api/pending?date=" + encodeURIComponent(day)).then(function (data) {
    var body = $("r-list");
    clear(body);
    data.records.forEach(function (r) {
      var inp = el("input", { "class": "r-input", inputmode: "numeric", autocomplete: "off", placeholder: "患者ID", "aria-label": "患者ID" });
      var btn = el("button", { "class": "d-btn primary", type: "button" }, "登録");
      btn.disabled = true;
      inp.addEventListener("input", function () {
        var fixed = toHalf(inp.value);
        if (fixed !== inp.value) inp.value = fixed;
        btn.disabled = !new RegExp(R.cfg.pcode_pattern).test(inp.value);
      });
      inp.addEventListener("keydown", function (ev) { if (ev.key === "Enter" && !btn.disabled) openConfirm(r, inp.value); });
      btn.addEventListener("click", function () { openConfirm(r, inp.value); });
      body.appendChild(el("tr", {},
        el("td", { "class": "r-num" }, String(r.number)),
        el("td", {}, r.created_at.slice(11, 16)),
        el("td", {}, r.form_title),
        el("td", {}, inp),
        el("td", {}, btn)));
    });
    $("list-count").textContent = data.records.length ? data.records.length + "件" : "受付待ちの回答はありません";
  }).catch(function (e) { $("list-count").textContent = e.message; });
}

function openConfirm(r, pcode) {
  R.target = { record: r, pcode: pcode };
  $("confirm-number").textContent = r.number;
  $("confirm-pcode").textContent = pcode;
  $("confirm-form").textContent = r.form_title + "（" + r.created_at.slice(11, 16) + " 送信）";
  $("confirm-msg").hidden = true;
  $("dlg-confirm").hidden = false;
}
$("btn-confirm-no").addEventListener("click", function () { $("dlg-confirm").hidden = true; });
$("btn-confirm-yes").addEventListener("click", function () {
  var t = R.target;
  api("/api/answers/" + encodeURIComponent(t.record.record_id) + "/register", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pcode: t.pcode })
  }).then(function () {
    $("dlg-confirm").hidden = true;
    toast("受付番号 " + t.record.number + " を患者ID " + t.pcode + " で登録しました");
    loadList();
  }).catch(function (e) {
    $("confirm-msg").textContent = e.message;
    $("confirm-msg").hidden = false;
  });
});

var toastTimer = null;
function toast(msg) {
  $("toast").textContent = msg;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(function () { $("toast").hidden = true; }, 3000);
}

$("f-date").value = today();
$("f-date").addEventListener("change", loadList);
$("btn-refresh").addEventListener("click", loadList);
api("/api/config").then(function (cfg) { R.cfg = cfg; loadList(); });
setInterval(loadList, 15000);
