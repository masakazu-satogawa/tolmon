// 患者さんの画面の全部の設問を、言語・文字の大きさごとに開いて、「もどる・次へ」が画面からはみ出さないかを測る（開発用）。
// 使い方：このファイルを web/ に一時的にコピーし、患者さんの画面を開いたブラウザの開発者ツールで
//   var s = document.createElement("script"); s.src = "/static/fit_scan.js"; document.body.appendChild(s);
//   await __scan()
// を実行する。画面の大きさを変えながら、くり返し測る。終わったら web/ のコピーは消す。
window.__scan = async function () {
  var bad = [], count = 0, worst = 0;
  var forms = (await api("/api/forms")).forms;
  for (var i = 0; i < forms.length; i++) {
    var form = await api("/api/forms/" + forms[i].id);
    beginForm(form);
    var langs = ["ja"].concat(Object.keys(form._i18n || {}));
    for (var li = 0; li < langs.length; li++) {
      setLang(langs[li]);
      var sizes = ["s", "m", "l"];
      for (var s = 0; s < sizes.length; s++) {
        setFontSize(sizes[s]);
        // はじめの画面
        show("welcome");
        var w = document.documentElement.scrollHeight - window.innerHeight;
        count++;
        if (w > 0) bad.push(form.id + "/" + langs[li] + "/" + sizes[s] + "/welcome:" + w);
        for (var k = 0; k < form.questions.length; k++) {
          var q = form.questions[k];
          S.answers = {};
          S.sub = null;
          goTo(q.id);
          var over = document.documentElement.scrollHeight - window.innerHeight;
          var hover = document.documentElement.scrollWidth - window.innerWidth;
          var nav = document.querySelector("#s-question .nav").getBoundingClientRect();
          over = Math.max(over, Math.round(nav.bottom - window.innerHeight));
          count++;
          worst = Math.max(worst, over);
          if (over > 0 || hover > 0) {
            bad.push(form.id + "/" + langs[li] + "/" + sizes[s] + "/" + (k + 1) + "." + q.id + "(" + q.type + "," + (q.options ? q.options.length : 0) + "):" + over + (hover > 0 ? " 横" + hover : ""));
          }
          // 記入欄（選ぶと出る欄）を開いた状態でも測る
          var withDetail = (q.options || []).filter(function (o) { return o.detail; });
          if (withDetail.length) {
            choose(q, withDetail[0].label);      // 記入欄を1つ開く（2つ以上開いたときは、スクロールになってよい）
            var nav2 = document.querySelector("#s-question .nav").getBoundingClientRect();
            var over2 = Math.max(document.documentElement.scrollHeight - window.innerHeight, Math.round(nav2.bottom - window.innerHeight));
            count++;
            worst = Math.max(worst, over2);
            if (over2 > 0) bad.push(form.id + "/" + langs[li] + "/" + sizes[s] + "/" + (k + 1) + "." + q.id + "＋記入欄:" + over2);
          }
        }
        // 送ったあとの受付番号の画面
        document.getElementById("number").textContent = "128";
        show("number");
        var n = document.documentElement.scrollHeight - window.innerHeight;
        count++;
        if (n > 0) bad.push(form.id + "/" + langs[li] + "/" + sizes[s] + "/number:" + n);
      }
    }
  }
  setFontSize("m");
  setLang("ja");
  return { size: window.innerWidth + "x" + window.innerHeight, screens: count, bad: bad.length, worst: worst, list: bad };
};
"ready";
