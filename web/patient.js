// 受付・患者画面。AIもインターネットも使わない（院内サーバーとだけ通信する）。
"use strict";

const $ = (id) => document.getElementById(id);
const el = (tag, attrs = {}, ...children) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  }
  for (const c of children) e.append(c);
  return e;
};

const S = {
  cfg: null,
  forms: [],
  form: null,        // 選んだ問診定義
  pcode: "",
  answers: {},       // { qid: { value, details: { label: text } } }
  current: null,     // 表示中の設問id
  fromReview: false,
  startedAt: null,
  lastActive: Date.now(),
  idleShownAt: null,
  thanksTimer: null,
};

// 端末の時計のまま「2026-11-02T17:34:06」の形にする（サーバーの送信時刻と同じ表記）
function localIso(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

async function api(path, opts) {
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "通信できませんでした");
  return data;
}

// ---------------------------------------------------------------- 画面切り替え
const SCREENS = ["reception", "welcome", "question", "review", "thanks"];
function show(name) {
  for (const s of SCREENS) $("s-" + s).hidden = s !== name;
  $("btn-abort").hidden = !["welcome", "question", "review"].includes(name);
  S.screen = name;
  window.scrollTo(0, 0);
}
const patientMode = () => ["welcome", "question", "review"].includes(S.screen);

// ---------------------------------------------------------------- 受付
async function initReception() {
  S.cfg = await api("/api/config");
  const data = await api("/api/forms");
  S.forms = data.forms;
  const list = $("form-list");
  list.replaceChildren();
  for (const f of S.forms) {
    const b = el("button", { class: "choice", type: "button", "aria-pressed": "false", "data-id": f.id },
      el("span", { class: "mark" }, "✓"),
      el("span", {}, f.title, el("span", { class: "small" }, `${f.count}問`)));
    b.addEventListener("click", () => selectForm(f.id));
    list.append(b);
  }
  if (S.forms.length === 1) selectForm(S.forms[0].id);
  $("form-errors").hidden = !data.errors.length;
  $("form-errors").textContent = data.errors.length ? "読み込めなかった問診票があります：\n" + data.errors.join("\n") : "";
}

function selectForm(id) {
  S.selectedFormId = id;
  for (const b of $("form-list").children) b.setAttribute("aria-pressed", String(b.dataset.id === id));
  updateStart();
}

function pcodeValid() {
  return new RegExp(S.cfg.pcode_pattern).test($("pcode").value.trim());
}

function updateStart() {
  const v = $("pcode").value.trim();
  const ok = pcodeValid();
  $("pcode-msg").hidden = !v || ok;
  $("pcode-msg").textContent = "患者IDは数字で入力してください";
  $("btn-start").disabled = !(S.selectedFormId && ok);
}

$("pcode").addEventListener("input", () => {
  // 全角数字は半角に直す
  const e = $("pcode");
  const fixed = e.value.replace(/[０-９]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0xfee0)).replace(/\s/g, "");
  if (fixed !== e.value) e.value = fixed;
  updateStart();
});
$("pcode").addEventListener("keydown", (ev) => { if (ev.key === "Enter" && !$("btn-start").disabled) openConfirm(); });
$("btn-start").addEventListener("click", openConfirm);

function openConfirm() {
  const f = S.forms.find((x) => x.id === S.selectedFormId);
  $("confirm-pcode").textContent = $("pcode").value.trim();
  $("confirm-form").textContent = f.title;
  $("dlg-confirm").hidden = false;
  $("pcode").blur();
}
$("btn-confirm-no").addEventListener("click", () => {
  $("dlg-confirm").hidden = true;
  $("pcode").focus();
  $("pcode").select();
});
$("btn-confirm-yes").addEventListener("click", async () => {
  $("dlg-confirm").hidden = true;
  try {
    S.form = await api("/api/forms/" + encodeURIComponent(S.selectedFormId));
  } catch (e) {
    alert(e.message);
    return;
  }
  S.pcode = $("pcode").value.trim();
  S.answers = {};
  S.startedAt = localIso(new Date());
  $("welcome-count").textContent = `質問はおよそ ${visibleQuestions().length} 問です。`;
  touch();
  show("welcome");
});

// ---------------------------------------------------------------- 設問の表示条件（サーバーと同じ考え方）
function isVisible(q, answers = S.answers) {
  const c = q.show_if;
  if (!c) return true;
  const ref = answers[c.q];
  if (!ref) return false;
  const v = ref.value;
  return v === c.eq || (Array.isArray(v) && v.includes(c.eq));
}
const visibleQuestions = () => S.form.questions.filter((q) => isVisible(q));

function hasAnswer(q) {
  const a = S.answers[q.id];
  if (!a) return false;
  const v = a.value;
  return !(v === undefined || v === null || v === "" || (Array.isArray(v) && v.length === 0));
}

// ---------------------------------------------------------------- 1問ずつ
$("btn-begin").addEventListener("click", () => {
  goTo(visibleQuestions()[0].id);
});

function goTo(qid) {
  S.current = qid;
  renderQuestion();
  show("question");
}

function renderQuestion() {
  const qs = visibleQuestions();
  const q = S.form.questions.find((x) => x.id === S.current);
  const pos = qs.findIndex((x) => x.id === q.id) + 1;
  $("progress-text").textContent = `${pos} / ${qs.length}`;
  $("progress-bar").style.width = `${((pos - 1) / qs.length) * 100}%`;
  $("q-text").textContent = q.text;
  $("q-hint").hidden = !q.hint;
  $("q-hint").textContent = q.hint || "";
  $("q-msg").hidden = true;
  const body = $("q-body");
  body.replaceChildren();
  const a = S.answers[q.id] || {};

  if (q.type === "single" || q.type === "multi") {
    const multi = q.type === "multi";
    const chosen = multi ? (a.value || []) : (a.value ? [a.value] : []);
    for (const o of q.options) {
      const on = chosen.includes(o.label);
      const btn = el("button", { class: "choice" + (multi ? " multi" : ""), type: "button", "aria-pressed": String(on) },
        el("span", { class: "mark" }, "✓"), el("span", {}, o.label));
      btn.addEventListener("click", () => choose(q, o.label));
      body.append(btn);
      if (on && o.detail) {
        const id = `detail-${q.id}-${q.options.indexOf(o)}`;
        const ta = el("textarea", { id, rows: "2" });
        ta.value = (a.details || {})[o.label] || "";
        ta.addEventListener("input", () => {
          const cur = S.answers[q.id];
          cur.details = cur.details || {};
          cur.details[o.label] = ta.value;
        });
        body.append(el("div", { class: "detail" }, el("label", { for: id }, o.detail), ta));
      }
    }
  } else if (q.type === "number") {
    const inp = el("input", { class: "q-input", inputmode: "decimal", autocomplete: "off", "aria-label": q.text });
    inp.value = a.value ?? "";
    inp.addEventListener("input", () => {
      inp.value = inp.value.replace(/[０-９．]/g, (c) => c === "．" ? "." : String.fromCharCode(c.charCodeAt(0) - 0xfee0));
      setValue(q, inp.value.trim());
    });
    body.append(el("div", { class: "number-row" }, inp, el("span", { class: "unit" }, q.unit || "")));
  } else if (q.type === "time") {
    const inp = el("input", { class: "q-input", type: "time", "aria-label": q.text });
    inp.value = a.value || "";
    inp.addEventListener("input", () => setValue(q, inp.value));
    body.append(inp);
  } else {
    const ta = el("textarea", { "aria-label": q.text });
    ta.value = a.value || "";
    ta.addEventListener("input", () => setValue(q, ta.value));
    body.append(ta);
  }
  updateNext(q);
  $("btn-back").textContent = S.fromReview ? "確認画面へ" : "もどる";
}

function setValue(q, v) {
  if (v === "" || v === null) delete S.answers[q.id];
  else S.answers[q.id] = { ...(S.answers[q.id] || {}), value: v };
  updateNext(q);
}

function choose(q, label) {
  const a = S.answers[q.id] || { details: {} };
  if (q.type === "multi") {
    const set = new Set(a.value || []);
    set.has(label) ? set.delete(label) : set.add(label);
    a.value = q.options.map((o) => o.label).filter((l) => set.has(l));
  } else {
    a.value = a.value === label ? null : label;
  }
  if (!a.value || (Array.isArray(a.value) && !a.value.length)) delete S.answers[q.id];
  else S.answers[q.id] = a;
  renderQuestion();
}

function updateNext(q) {
  const answered = hasAnswer(q);
  $("btn-next").disabled = !!q.required && !answered;
  $("btn-next").textContent = answered || q.required ? "次へ" : "答えずに次へ";
}

function checkCurrent(q) {
  if (q.type === "number" && hasAnswer(q)) {
    const n = Number(S.answers[q.id].value);
    if (Number.isNaN(n)) return "数字で入力してください";
    if (q.min !== undefined && n < q.min) return `${q.min} 以上の数字を入力してください`;
    if (q.max !== undefined && n > q.max) return `${q.max} 以下の数字を入力してください`;
  }
  return null;
}

$("btn-next").addEventListener("click", () => {
  const q = S.form.questions.find((x) => x.id === S.current);
  const err = checkCurrent(q);
  if (err) {
    $("q-msg").textContent = err;
    $("q-msg").hidden = false;
    return;
  }
  const qs = visibleQuestions();
  const i = qs.findIndex((x) => x.id === q.id);
  // 確認画面から直しに来たときは、新しく出てきた設問がなければ確認画面へ戻る
  if (S.fromReview) {
    const next = qs[i + 1];
    if (next && !hasAnswer(next) && next.show_if) return goTo(next.id);
    S.fromReview = false;
    return openReview();
  }
  if (i + 1 < qs.length) goTo(qs[i + 1].id);
  else openReview();
});

$("btn-back").addEventListener("click", () => {
  if (S.fromReview) {
    S.fromReview = false;
    return openReview();
  }
  const qs = visibleQuestions();
  const i = qs.findIndex((x) => x.id === S.current);
  if (i > 0) goTo(qs[i - 1].id);
  else show("welcome");
});

// ---------------------------------------------------------------- 確認・送信
function answerText(q) {
  const a = S.answers[q.id];
  if (!hasAnswer(q)) return null;
  if (q.type === "single" || q.type === "multi") {
    const labels = Array.isArray(a.value) ? a.value : [a.value];
    return labels.map((l) => {
      const d = ((a.details || {})[l] || "").trim();
      return d ? `${l}（${d}）` : l;
    }).join("、");
  }
  if (q.type === "number") return `${a.value} ${q.unit || ""}`.trim();
  return a.value;
}

function openReview() {
  const list = $("review-list");
  list.replaceChildren();
  for (const q of visibleQuestions()) {
    const t = answerText(q);
    const fix = el("button", { class: "btn", type: "button" }, "なおす");
    fix.addEventListener("click", () => { S.fromReview = true; goTo(q.id); });
    list.append(el("li", {},
      el("div", { class: "grow" }, el("div", { class: "rq" }, q.text), el("div", { class: "ra" + (t ? "" : " empty") }, t || "（答えていません）")),
      fix));
  }
  $("submit-msg").hidden = true;
  show("review");
}

$("btn-review-back").addEventListener("click", () => {
  const qs = visibleQuestions();
  goTo(qs[qs.length - 1].id);
});

$("btn-submit").addEventListener("click", async () => {
  const btn = $("btn-submit");
  btn.disabled = true;
  btn.textContent = "送っています…";
  // 表示されていない設問の回答は送らない
  const answers = {};
  for (const q of visibleQuestions()) if (hasAnswer(q)) answers[q.id] = S.answers[q.id];
  try {
    await api("/api/answers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ form_id: S.form.id, form_hash: S.form._hash, pcode: S.pcode, answers, started_at: S.startedAt }),
    });
    show("thanks");
    S.thanksTimer = setTimeout(resetAll, (S.cfg.thanks_seconds || 10) * 1000);
  } catch (e) {
    $("submit-msg").textContent = e.message + "\n係の者をお呼びください。";
    $("submit-msg").hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = "この内容で送る";
  }
});

// ---------------------------------------------------------------- リセット（次の患者さんに前の回答を見せない）
function resetAll() {
  clearTimeout(S.thanksTimer);
  S.form = null;
  S.pcode = "";
  S.answers = {};
  S.current = null;
  S.fromReview = false;
  S.idleShownAt = null;
  $("pcode").value = "";
  for (const d of ["dlg-confirm", "dlg-idle", "dlg-abort"]) $(d).hidden = true;
  updateStart();
  show("reception");
}
$("s-thanks").addEventListener("click", resetAll);

$("btn-abort").addEventListener("click", () => { $("dlg-abort").hidden = false; });
$("btn-abort-no").addEventListener("click", () => { $("dlg-abort").hidden = true; touch(); });
$("btn-abort-yes").addEventListener("click", resetAll);

// ---------------------------------------------------------------- 無操作の見張り
function touch() {
  S.lastActive = Date.now();
  if (S.idleShownAt) {
    S.idleShownAt = null;
    $("dlg-idle").hidden = true;
  }
}
for (const ev of ["pointerdown", "keydown", "input"]) document.addEventListener(ev, () => { if (!S.idleShownAt) touch(); }, true);
$("btn-idle-continue").addEventListener("click", touch);

setInterval(() => {
  if (!S.cfg || !patientMode()) return;
  const now = Date.now();
  if (!S.idleShownAt && now - S.lastActive > S.cfg.idle_seconds * 1000) {
    S.idleShownAt = now;
    $("dlg-idle").hidden = false;
  }
  if (S.idleShownAt) {
    const left = Math.ceil(S.cfg.idle_grace_seconds - (now - S.idleShownAt) / 1000);
    $("idle-count").textContent = Math.max(left, 0);
    if (left <= 0) resetAll();
  }
}, 1000);

// ---------------------------------------------------------------- 開始
initReception().then(() => show("reception")).catch((e) => {
  document.body.textContent = "問診サーバーにつながりません：" + e.message;
});
