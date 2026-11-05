// 作る画面。白紙の問診票を Claude に読ませて、問診の下書きを確認・修正・確定する。
// ここで扱うのは白紙の帳票と設問の定義だけ（患者さんの回答は扱わない）。
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
    if (c === null || c === undefined) continue;
    e.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return e;
}
function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

function api(path, body) {
  var opts = body === undefined ? undefined
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  return fetch(path, opts).catch(function () {
    // サーバーが止まっていると、ブラウザは英語の「Failed to fetch」しか出さない
    throw new Error("トルモンのサーバーにつながりません。サーバーが起動しているか確かめてから、もう一度押してください。");
  }).then(function (res) {
    return res.json().catch(function () { return {}; }).then(function (data) {
      if (!res.ok) throw new Error(data.error || "通信できませんでした");
      return data;
    });
  });
}

var A = {
  definition: null,   // いま表示している定義
  issues: [],         // Claude の見直し
  sources: {},        // 設問id → もとになった紙の文言
  added: {},          // 設問id → 紙にない選択肢（Claude が足したもの）の一覧
  formId: "",         // いま開いている下書きの問診ID
  paperUrl: null
};
var TYPE_NAMES = { text: "自由記入", single: "1つ選ぶ", multi: "いくつでも選ぶ", number: "数字", time: "時刻", body: "体の図" };

// ---------------------------------------------------------------- 手順（いま何をするところか）
var NEXT_TEXT = {
  2: "次にやること：右の設問を、左の紙と見比べてください。よければ「患者さんの画面で試す」へ。",
  3: "次にやること：開いた画面で、患者さんと同じように最後まで答えてみてください。",
  4: "次にやること：問題なければ「確定して公開」。受付の画面に診療科のボタンが出ます。",
  5: "公開しました。問診票を直したくなったら、この画面でやり直せます。"
};
function setStep(n) {
  A.step = n;
  var items = document.querySelectorAll("#steps li");
  for (var i = 0; i < items.length; i++) {
    var s = Number(items[i].getAttribute("data-step"));
    items[i].className = s < n ? "done" : s === n ? "now" : "";
  }
  $("next-text").textContent = NEXT_TEXT[n] || "";
  // いま押すボタンを目立たせる
  $("btn-try").className = "a-btn" + (n <= 3 ? " primary" : "");
  $("btn-save").className = "a-btn" + (n === 4 ? " primary" : "");
}
function nowText() {
  var d = new Date();
  return d.getHours() + ":" + (d.getMinutes() < 10 ? "0" : "") + d.getMinutes();
}

// ---------------------------------------------------------------- 入力
function updateReadButton() {
  $("btn-read").disabled = !($("file").files.length && /^[a-z][a-z0-9_]{1,30}$/.test($("form-id").value.trim()));
}
$("file").addEventListener("change", function () {
  var f = $("file").files[0];
  if (f) showPaper(f);
  updateReadButton();
});
$("form-id").addEventListener("input", updateReadButton);

function showPaper(file) {
  if (A.paperUrl) URL.revokeObjectURL(A.paperUrl);
  A.paperUrl = URL.createObjectURL(file);
  var box = $("paper");
  clear(box);
  if (/pdf$/i.test(file.type) || /\.pdf$/i.test(file.name)) {
    box.className = "a-paper-box";
    box.appendChild(el("iframe", { src: A.paperUrl + "#toolbar=0&view=FitH", title: "もとの帳票" }));
  } else {
    box.className = "a-paper-box scroll";
    box.appendChild(el("img", { src: A.paperUrl, alt: "もとの帳票" }));
  }
  $("work").hidden = false;
}

function readAsBase64(file) {
  return new Promise(function (resolve, reject) {
    var r = new FileReader();
    r.onload = function () { resolve(String(r.result).split(",")[1]); };
    r.onerror = function () { reject(new Error("ファイルを読み込めませんでした")); };
    r.readAsDataURL(file);
  });
}

// ---------------------------------------------------------------- 読み取り
$("btn-read").addEventListener("click", function () {
  var file = $("file").files[0];
  var msg = $("read-msg");
  var started = Date.now();
  $("btn-read").disabled = true;
  msg.hidden = false;
  msg.className = "a-msg";
  var timer = setInterval(function () {
    var s = Math.round((Date.now() - started) / 1000);
    msg.textContent = (s < 60 ? "Claude が帳票を読み取っています…" : "Claude が自分の読み取りを見直しています…") + "（" + s + "秒。1〜2分かかります）";
  }, 500);
  readAsBase64(file).then(function (b64) {
    return api("/api/creator/read", { name: file.name, form_id: $("form-id").value.trim(), data: b64 });
  }).then(function (r) {
    showResult(r);
    msg.textContent = "読み取りました（" + nowText() + "）。設問は " + r.definition.questions.length + " 問です。下の右側が、Claude が紙から作った設問です。";
  }).catch(function (e) {
    msg.className = "a-msg ng";
    msg.textContent = e.message;
  }).then(function () {
    clearInterval(timer);
    updateReadButton();
  });
});

// ---------------------------------------------------------------- 結果の表示
function showResult(r) {
  A.definition = r.definition;
  A.issues = r.issues || [];
  A.sources = r.sources || {};
  A.added = r.added || {};
  $("work").hidden = false;
  $("yaml").value = r.yaml;
  if (r.form_id) $("form-id").value = r.form_id;
  A.formId = r.form_id || "";
  updateReadButton();
  loadDrafts();
  renderProblems(r.problems || []);
  renderQuestions();
  renderIssues(r.summary || "", r.notes || []);
  renderSkipped(r.skipped || []);
  var u = r.usage || {};
  var parts = [];
  if (u.read) parts.push("読み取り " + u.read.seconds + "秒");
  if (u.check) parts.push("見直し " + u.check.seconds + "秒");
  if (u.read) parts.push("モデル " + u.read.model);
  $("usage").textContent = parts.join(" ／ ");
  $("save-msg").hidden = true;
  renderDummy(r.dummy || null);
  setStep(2);
}

function renderProblems(list) {
  $("problems").hidden = !list.length;
  $("problems").textContent = list.length ? "このままでは保存できません：\n" + list.join("\n") : "";
}

function describeCond(c) {
  if (c.all) return c.all.map(describeCond).join(" かつ ");
  if (c.any) return c.any.map(describeCond).join(" または ");
  var q = (A.definition.questions || []).filter(function (x) { return x.id === c.q; })[0];
  var name = q ? "「" + q.karte + "」" : "「" + c.q + "」";
  if ("eq" in c) return name + "で「" + c.eq + "」を選んだとき";
  if ("ne" in c) return name + "で「" + c.ne + "」を選んでいないとき";
  if ("lt" in c) return name + "が " + c.lt + " 未満のとき";
  if ("gte" in c) return name + "が " + c.gte + " 以上のとき";
  return "";
}

function renderQuestions() {
  var list = $("q-list");
  clear(list);
  var qs = (A.definition && A.definition.questions) || [];
  $("n-questions").textContent = qs.length;
  qs.forEach(function (q) {
    var mine = A.issues.filter(function (i) { return i.question_id === q.id; });
    var worst = mine.some(function (i) { return i.severity === "error"; }) ? " has-error"
      : mine.some(function (i) { return i.severity === "warning"; }) ? " has-warning" : "";
    var li = el("li", { "class": worst.trim() });
    li.appendChild(el("p", { "class": "q-text" }, q.text));
    var meta = el("p", { "class": "q-meta" },
      el("span", { "class": "chip type" }, TYPE_NAMES[q.type] || q.type),
      q.required ? el("span", { "class": "chip req" }, "必須") : null,
      el("span", { "class": "chip" }, q.tag || "その他"),
      el("span", { "class": "q-karte" }, "カルテ：", el("b", {}, q.karte + (q.unit ? "（" + q.unit + "）" : ""))),
      el("span", { "class": "q-karte" }, "id: " + q.id));
    li.appendChild(meta);
    if (q.options && q.options.length) {
      var ul = el("ul", { "class": "q-opts" });
      var addedHere = A.added[q.id] || [];
      var nAdded = 0;
      q.options.forEach(function (o) {
        var isAdded = addedHere.indexOf(o.label) >= 0;
        if (isAdded) nAdded++;
        ul.appendChild(el("li", isAdded ? { "class": "added" } : {}, o.label,
          o.karte && o.karte !== o.label ? el("span", { "class": "k" }, " → " + o.karte) : null,
          o.detail ? el("span", { "class": "d" }, "選ぶと記入欄（書かなくても進める）：" + o.detail) : null));
      });
      li.appendChild(ul);
      // 紙では書く欄だったものを、Claude が選ぶ形に変えた。中身は人が確かめる
      if (nAdded) li.appendChild(el("p", { "class": "q-added" },
        "点線の " + nAdded + " 個は紙にない選択肢です（紙の書く欄を、選ぶ形に変えました）。この内容でよいか確かめてください。"));
    }
    if (q.type === "number") li.appendChild(el("p", { "class": "q-hint" }, "画面の大きな数字ボタンで入力します（キーボードは出ません）。"));
    if (q.type === "text") li.appendChild(el("p", { "class": "q-hint" }, "書く欄です。「書かずに、診察のときに話します」ボタンも出ます（カルテには「記載がないので要聴取」）。"));
    if (q.type === "body" && window.TolmonBody) {
      // 患者さんがタップする図の見本（男性の図。性別の回答で女性の図に変わる）
      var figs = el("div", { "class": "q-figs" });
      TolmonBody.views.forEach(function (v) {
        if (q.views && q.views.indexOf(v.id) < 0) return;
        var box = el("div", {});
        TolmonBody.draw(v.id, box, {}, function () {}, "m");
        figs.appendChild(el("figure", {}, box, el("figcaption", {}, v.label)));
      });
      li.appendChild(figs);
      li.appendChild(el("p", { "class": "q-hint" }, "患者さんは図をタップして場所を選びます。2か所以上なら「いちばんつらいところ」を1つ選びます。"));
    }
    if (q.show_if) li.appendChild(el("p", { "class": "q-branch" }, "出る条件：" + describeCond(q.show_if)));
    if (q.hint) li.appendChild(el("p", { "class": "q-hint" }, "ヒント：" + q.hint));
    if (A.sources[q.id]) li.appendChild(el("p", { "class": "q-source" }, "紙の文言：" + A.sources[q.id]));
    mine.forEach(function (i) {
      li.appendChild(el("p", { "class": "q-issue " + i.severity }, "【見直し・" + i.kind + "】" + i.message));
    });
    list.appendChild(li);
  });
}

function renderIssues(summary, notes) {
  $("summary").textContent = summary ? "見直しの結果：" + summary : "見直しは行っていません";
  var list = $("issue-list");
  clear(list);
  var names = { error: "要修正", warning: "要確認", info: "気づき" };
  A.issues.forEach(function (i) {
    list.appendChild(el("li", { "class": i.severity },
      el("div", { "class": "head" }, "【" + names[i.severity] + "・" + i.kind + "】" + (i.question_id ? " " + i.question_id : "")),
      el("div", {}, i.message),
      i.suggestion ? el("div", { "class": "sug" }, "直し方：" + i.suggestion) : null));
  });
  if (!A.issues.length) list.appendChild(el("li", {}, "指摘はありません"));
  var n = $("n-issues");
  n.textContent = A.issues.length;
  n.className = "n" + (A.issues.some(function (i) { return i.severity === "error"; }) ? " err"
    : A.issues.some(function (i) { return i.severity === "warning"; }) ? " warn" : "");
  var nl = $("note-list");
  clear(nl);
  notes.forEach(function (t) { nl.appendChild(el("li", {}, t)); });
  if (!notes.length) nl.appendChild(el("li", {}, "ありません"));
}

function renderSkipped(skipped) {
  var list = $("skip-list");
  clear(list);
  skipped.forEach(function (s) {
    list.appendChild(el("li", {}, s.paper_text, el("div", { "class": "why" }, "理由：" + s.reason)));
  });
  if (!skipped.length) list.appendChild(el("li", {}, "ありません"));
  $("n-skipped").textContent = skipped.length;
}

// ---------------------------------------------------------------- ダミー患者（Claude が架空の患者を作り、通しで確かめる）
function renderDummy(d) {
  var box = $("dummy-summary"), list = $("dummy-list"), n = $("n-dummy");
  clear(box);
  clear(list);
  box.hidden = !d;
  n.hidden = !d;
  $("dummy-msg").textContent = "";
  if (!d) return;
  var s = d.summary;
  n.textContent = s.ok + "/" + s.patients;
  n.className = "n" + (s.errors ? " err" : "");
  box.className = "d-summary" + (s.errors ? " ng" : "");
  box.appendChild(el("p", { "class": "head" }, s.errors
    ? s.patients + "人のうち " + s.errors + "人の回答が受け取れませんでした（下の赤い枠）。"
    : s.patients + "人とも、最後まで答えてカルテ文になりました。"));
  if (s.branches) box.appendChild(el("p", {}, "出し分けのある設問 " + s.branches + " 問のうち、" + s.branches_both + " 問で「出る人」と「出ない人」の両方を確かめました。"));
  if (s.never_shown.length) box.appendChild(el("p", {}, "一度も出なかった設問：" + s.never_shown.join("／")));
  if (s.branches_always.length) box.appendChild(el("p", {}, "全員に出た（出ない場合を確かめていない）設問：" + s.branches_always.join("／")));
  var parts = [];
  if (d.tested_at) parts.push("確認した日時 " + d.tested_at.slice(5, 16));
  if (d.usage) parts.push(d.usage.seconds + "秒");
  parts.push("直したあとは、もう一度確認してください");
  box.appendChild(el("p", { "class": "small" }, parts.join(" ／ ")));
  d.patients.forEach(function (p) {
    var li = el("li", p.error ? { "class": "ng" } : {}, el("p", { "class": "d-persona" }, p.persona));
    if (p.error) li.appendChild(el("p", { "class": "d-error" }, "受け取れなかった理由：" + p.error));
    if (p.karte) li.appendChild(el("pre", { "class": "d-karte" }, p.karte));
    p.notes.forEach(function (t) { li.appendChild(el("p", { "class": "d-note" }, t)); });
    if (p.shown.length) {
      var dl = el("dl", {});
      p.shown.forEach(function (x) {
        dl.appendChild(el("dt", {}, x.text));
        dl.appendChild(el("dd", {}, x.answer));
      });
      li.appendChild(el("details", {}, el("summary", {}, "この人に出た設問と答え（" + p.shown.length + "問）"), dl));
    }
    list.appendChild(li);
  });
}
$("btn-dummy").addEventListener("click", function () {
  var m = $("dummy-msg"), btn = $("btn-dummy"), started = Date.now();
  btn.disabled = true;
  m.className = "a-inline";
  var timer = setInterval(function () {
    m.textContent = "Claude が架空の患者さんを作って答えています…（" + Math.round((Date.now() - started) / 1000) + "秒。1分ほどかかります）";
  }, 500);
  api("/api/creator/dummy", { form_id: A.formId, yaml: $("yaml").value, count: 5 }).then(function (d) {
    clearInterval(timer);
    renderDummy(d);
  }).catch(function (e) {
    clearInterval(timer);
    m.className = "a-inline ng";
    m.textContent = e.message;
  }).then(function () { btn.disabled = false; });
});

// ---------------------------------------------------------------- タブ
var tabs = document.querySelectorAll(".a-tabs button");
for (var i = 0; i < tabs.length; i++) {
  tabs[i].addEventListener("click", function () {
    var name = this.getAttribute("data-tab");
    for (var j = 0; j < tabs.length; j++) {
      var t = tabs[j].getAttribute("data-tab");
      tabs[j].setAttribute("aria-pressed", String(t === name));
      $("tab-" + t).hidden = t !== name;
    }
  });
}

// ---------------------------------------------------------------- 直す・確定する
function checkYaml() {
  return api("/api/creator/check", { yaml: $("yaml").value }).then(function (r) {
    renderProblems(r.problems);
    if (r.definition) {
      A.definition = r.definition;
      renderQuestions();
    }
    return r;
  });
}
$("btn-check").addEventListener("click", function () {
  var m = $("check-msg");
  checkYaml().then(function (r) {
    m.className = "a-inline " + (r.ok ? "ok" : "ng");
    m.textContent = r.ok ? "問題ありません。「設問」タブに反映しました" : "直すところがあります（上の赤い枠）";
    // 直した内容を下書きに残す（画面を開き直しても消えないように）
    if (r.ok && A.formId) return api("/api/creator/draft", { form_id: A.formId, yaml: $("yaml").value });
  }).catch(function (e) { m.className = "a-inline ng"; m.textContent = e.message; });
});

function save(overwrite) {
  var msg = $("save-msg");
  msg.hidden = false;
  api("/api/creator/save", { yaml: $("yaml").value, overwrite: !!overwrite }).then(function (r) {
    if (r.exists) {
      if (confirm("同じ問診ID（" + r.file + "）がすでにあります。上書きしますか？")) return save(true);
      msg.className = "a-msg ng";
      msg.textContent = "保存しませんでした";
      return;
    }
    msg.className = "a-msg";
    clear(msg);
    msg.appendChild(document.createTextNode("受付の画面に「" + r.title + "」のボタンが出ました。 "));
    msg.appendChild(el("a", { href: "/", target: "_blank" }, "受付の画面を開く"));
    setStep(5);
  }).catch(function (e) {
    msg.className = "a-msg ng";
    msg.textContent = e.message;
  });
}
// 公開する前に、患者さんの画面（タブレットと同じ画面）で最後まで試す。回答は保存されない
$("btn-try").addEventListener("click", function () {
  var msg = $("save-msg");
  // 押した瞬間にタブを開いておく（あとから開くと、ブラウザに止められることがある）
  var w = window.open("about:blank", "tolmon_trial");
  checkYaml().then(function (r) {
    if (!r.ok) throw new Error("直すところがあります（赤い枠）。直してから試してください。");
    return api("/api/creator/trial", { yaml: $("yaml").value });
  }).then(function () {
    if (w) w.location.href = "/?try=1"; else window.location.href = "/?try=1";
    msg.hidden = true;
    setStep(4);
  }).catch(function (e) {
    if (w) w.close();
    msg.hidden = false;
    msg.className = "a-msg ng";
    msg.textContent = e.message;
  });
});

$("btn-save").addEventListener("click", function () {
  checkYaml().then(function (r) { if (r.ok) save(false); else { $("save-msg").hidden = false; $("save-msg").className = "a-msg ng"; $("save-msg").textContent = "直すところがあります（上の赤い枠）"; } });
});

// ---------------------------------------------------------------- 読み取り済みの下書き（問診票ごとに残る）
function showDraft(d) {
  showResult(d);
  $("read-msg").hidden = false;
  $("read-msg").className = "a-msg";
  $("read-msg").textContent = "「" + d.definition.title + "」の下書き（" + (d.source_name || "") + "）を表示しています。紙と並べて見るには、同じファイルを選び直してください。読み取り直す必要はありません。";
}
function loadDrafts() {
  return api("/api/creator/drafts").then(function (res) {
    var list = $("draft-list");
    clear(list);
    $("drafts").hidden = !res.drafts.length;
    res.drafts.forEach(function (d) {
      var b = el("button", { type: "button", "aria-pressed": String(d.form_id === A.formId) },
        d.title + "（" + d.count + "問）", el("small", {}, d.form_id + " ／ " + d.source_name + " ／ " + d.saved_at.slice(5, 16)));
      b.addEventListener("click", function () {
        api("/api/creator/last?form_id=" + encodeURIComponent(d.form_id)).then(showDraft).catch(function (e) {
          $("read-msg").hidden = false;
          $("read-msg").className = "a-msg ng";
          $("read-msg").textContent = e.message;
        });
      });
      list.appendChild(b);
    });
  }).catch(function () {});
}

// ---------------------------------------------------------------- 開始
api("/api/creator/info").then(function (info) {
  $("rules").textContent = info.rules;
  $("a-env").textContent = info.has_key ? "読み取りに使うモデル：" + info.model : "APIキーがありません（.env に ANTHROPIC_API_KEY を書いてください）";
  if (!info.has_key) $("a-env").className = "a-env ng";
  return api("/api/creator/last");
}).then(function (last) {
  // 画面を開き直しても、いちばん新しい下書きを戻す（紙の表示だけは選び直しが必要）
  if (last && last.definition) showDraft(last);
  else loadDrafts();
}).catch(function (e) {
  $("a-env").className = "a-env ng";
  $("a-env").textContent = e.message;
});
setStep(1);
