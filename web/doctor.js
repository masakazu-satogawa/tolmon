// 医師画面。回答一覧→カルテ向けテキスト→コピー。AIは使わない。
"use strict";

const $ = (id) => document.getElementById(id);
const el = (tag, attrs = {}, ...children) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else e.setAttribute(k, v);
  }
  for (const c of children) e.append(c);
  return e;
};

const D = { selected: null, known: null };

function today() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

async function api(path) {
  const res = await fetch(path);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "通信できませんでした");
  return data;
}

// ---------------------------------------------------------------- 一覧
async function loadList() {
  const qs = new URLSearchParams();
  if ($("f-date").value) qs.set("date", $("f-date").value);
  const p = $("f-pcode").value.trim();
  if (p) qs.set("pcode", p);
  let rows;
  try {
    rows = (await api("/api/answers?" + qs)).records;
  } catch (e) {
    $("list-count").textContent = e.message;
    return;
  }
  const first = D.known === null;
  const known = D.known || new Set();
  const list = $("d-list");
  list.replaceChildren();
  for (const r of rows) {
    const isNew = !first && !known.has(r.record_id);
    const b = el("button", { class: "d-item" + (isNew ? " new" : ""), type: "button", "data-id": r.record_id,
      "aria-current": String(r.record_id === D.selected) },
      el("span", { class: "t" }, r.received_at.slice(11, 16)),
      el("span", { class: "p" }, r.pcode),
      el("span", { class: "f" }, r.form_title));
    b.addEventListener("click", () => openRecord(r.record_id));
    list.append(el("li", {}, b));
    known.add(r.record_id);
  }
  D.known = known;
  $("list-count").textContent = rows.length ? `${rows.length}件（新しい順）` : "この条件の問診はまだありません";
}

// ---------------------------------------------------------------- 詳細
async function openRecord(id) {
  D.selected = id;
  for (const b of document.querySelectorAll(".d-item")) b.setAttribute("aria-current", "false");
  let rec;
  try {
    rec = await api("/api/answers/" + encodeURIComponent(id));
  } catch (e) {
    $("d-detail").replaceChildren(el("p", { class: "warn" }, e.message));
    return;
  }
  const item = [...document.querySelectorAll(".d-item")].find((b) => b.dataset.id === id);
  if (item) { item.setAttribute("aria-current", "true"); item.classList.remove("new"); }

  const karte = el("textarea", { class: "d-karte", id: "karte-text", spellcheck: "false", "aria-label": "カルテ貼り付け用テキスト" });
  karte.value = rec.karte_text;
  const copyBtn = el("button", { class: "d-btn primary", type: "button" }, "カルテ貼り付け用にコピー");
  copyBtn.addEventListener("click", () => copyText(karte));

  const qa = el("ol");
  for (const s of rec.shown) {
    const empty = s.answer === "（未回答）";
    qa.append(el("li", {}, el("div", { class: "q" }, s.text), el("div", { class: "a" + (empty ? " empty" : "") }, s.answer)));
  }

  $("d-detail").replaceChildren(
    el("p", { class: "d-meta" },
      el("span", {}, "患者ID ", el("b", {}, rec.pcode)),
      el("span", {}, rec.form.title),
      el("span", {}, "送信 " + rec.received_at.replace("T", " ").slice(0, 16))),
    el("div", { class: "d-sec-head" }, el("h2", {}, "カルテ貼り付け用"), copyBtn),
    karte,
    el("details", { class: "d-qa" }, el("summary", {}, "患者さんに表示した設問と回答（原文）"), qa));
  fitHeight(karte);
}

// 中でスクロールしないよう、文章の長さに合わせて高さを伸ばす
function fitHeight(t) {
  t.style.height = "auto";
  t.style.height = t.scrollHeight + 4 + "px";
}
window.addEventListener("resize", () => { if ($("karte-text")) fitHeight($("karte-text")); });

// ---------------------------------------------------------------- コピー（院内の http でも動くよう3段構え）
async function copyText(textarea) {
  const text = textarea.value;
  // 1) 新しいコピー機能：HTTPS か localhost のときだけ使える
  if (window.isSecureContext && navigator.clipboard) {
    try {
      await navigator.clipboard.writeText(text);
      return toast("コピーしました。カルテに貼り付けてください");
    } catch (e) { /* 次の方法へ */ }
  }
  // 2) 古いコピー機能：院内の http でも動く
  textarea.focus();
  textarea.select();
  textarea.setSelectionRange(0, text.length);
  try {
    if (document.execCommand("copy")) return toast("コピーしました。カルテに貼り付けてください");
  } catch (e) { /* 次の方法へ */ }
  // 3) 最後の手段：全文を選んだ状態にして Ctrl+C を案内
  toast("全文を選択しました。Ctrl＋C でコピーしてください");
}

let toastTimer = null;
function toast(msg) {
  $("toast").textContent = msg;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $("toast").hidden = true; }, 2500);
}

// ---------------------------------------------------------------- 開始
$("f-date").value = today();
$("f-date").addEventListener("change", () => { D.known = null; loadList(); });
$("f-pcode").addEventListener("input", () => {
  const e = $("f-pcode");
  e.value = e.value.replace(/[０-９]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0xfee0)).replace(/\s/g, "");
  D.known = null;
  loadList();
});
$("btn-refresh").addEventListener("click", loadList);
loadList();
setInterval(loadList, 10000);  // 新しい問診が届いたら一覧に出す
