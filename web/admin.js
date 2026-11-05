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
  return fetch(path, opts).then(function (res) {
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
  paperUrl: null
};
var TYPE_NAMES = { text: "自由記入", single: "1つ選ぶ", multi: "いくつでも選ぶ", number: "数字", time: "時刻", body: "体の図" };

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
    msg.textContent = "読み取りました。右の内容を紙と見比べて、違うところを直してください。";
    showResult(r);
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
  $("work").hidden = false;
  $("yaml").value = r.yaml;
  if (r.form_id && !$("form-id").value) $("form-id").value = r.form_id;
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
}

function renderProblems(list) {
  $("problems").hidden = !list.length;
  $("problems").textContent = list.length ? "このままでは保存できません：\n" + list.join("\n") : "";
}

function describeCond(c) {
  if (c.all) return c.all.map(describeCond).join(" かつ ");
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
      q.options.forEach(function (o) {
        ul.appendChild(el("li", {}, o.label,
          o.karte && o.karte !== o.label ? el("span", { "class": "k" }, " → " + o.karte) : null,
          o.detail ? el("span", { "class": "d" }, "選ぶと記入欄：" + o.detail) : null));
      });
      li.appendChild(ul);
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
    msg.appendChild(document.createTextNode("「" + r.title + "」を確定して公開しました（" + r.file + "）。 "));
    msg.appendChild(el("a", { href: "/", target: "_blank" }, "タブレットの画面で試す"));
  }).catch(function (e) {
    msg.className = "a-msg ng";
    msg.textContent = e.message;
  });
}
$("btn-save").addEventListener("click", function () {
  checkYaml().then(function (r) { if (r.ok) save(false); else { $("save-msg").hidden = false; $("save-msg").className = "a-msg ng"; $("save-msg").textContent = "直すところがあります（上の赤い枠）"; } });
});

// ---------------------------------------------------------------- 開始
api("/api/creator/info").then(function (info) {
  $("rules").textContent = info.rules;
  $("a-env").textContent = info.has_key ? "読み取りに使うモデル：" + info.model : "APIキーがありません（.env に ANTHROPIC_API_KEY を書いてください）";
  if (!info.has_key) $("a-env").className = "a-env ng";
  return api("/api/creator/last");
}).then(function (last) {
  // 画面を開き直しても、直前の読み取り結果を戻す（紙の表示だけは選び直しが必要）
  if (last && last.definition) {
    showResult(last);
    $("read-msg").hidden = false;
    $("read-msg").textContent = "直前に読み取った結果（" + (last.source_name || "") + "）を表示しています。紙と並べて見るには、同じファイルを選び直してください。";
  }
}).catch(function (e) {
  $("a-env").className = "a-env ng";
  $("a-env").textContent = e.message;
});
