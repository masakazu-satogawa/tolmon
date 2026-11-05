// 人体シェーマを描いて、タップを受け取る（設問タイプ body）。
// 絵と区切りのデータは body-data.js（tools/make_body.py が作る）。部位の表示名はサーバーの /api/body から。
"use strict";

window.TolmonBody = (function () {
  var D = window.TolmonBodyData;

  // 図の名前。全身と頭は男性・女性で絵が違う（front_m / front_f）。手と足は共通
  function figure(viewId, sex) {
    return D.figures[viewId + "_" + (sex === "f" ? "f" : "m")] || D.figures[viewId];
  }

  // box（div）の中に図を描く。selected: {部位id: true}、onTap(部位id)、sex: "m" | "f"
  function draw(viewId, box, selected, onTap, sex) {
    var f = figure(viewId, sex);
    if (!f) return;
    box.innerHTML = '<svg class="body-svg" viewBox="0 0 ' + f.w + " " + f.h + '" xmlns="http://www.w3.org/2000/svg">' + f.html + "</svg>";
    var svg = box.firstChild;
    var parts = svg.querySelectorAll(".part");
    for (var i = 0; i < parts.length; i++) {
      if (selected[parts[i].getAttribute("data-id")]) parts[i].setAttribute("class", "part on");
    }
    svg.addEventListener("click", function (ev) {
      var t = ev.target;
      while (t && t !== svg) {
        var id = t.getAttribute && t.getAttribute("data-id");
        if (id) { onTap(id); return; }
        t = t.parentNode;
      }
    });
  }

  return { views: D.views, draw: draw };
})();
