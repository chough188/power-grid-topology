/* CP-202606 — 引导式演示走查 (walkthrough.js)
 * 作用: 在『比赛验收证据』页提供一步引导, 串联 任务一 1.1→1.4 与 任务二 5.1→5.3.4,
 *       每步给出示例输入与「前往该页面」入口。纯叠加层, 不改动任何比赛页面实现。
 * 触发: ① competition.html 顶部「演示走查」按钮 ② 命令面板「演示走查」命令(带 sessionStorage 标记自动打开)
 */
(function (global) {
  "use strict";

  var STEPS = [
    { task: "任务一 · 1.1 设备拓扑悬空检测", params: "TMP00013138（10kV分段开关）一侧悬空；TMP00007913 单端悬空", page: "problem_list.html", note: "在『异常问题清单』按二级分类 1.1 过滤，查看悬空设备与修正 SQL。" },
    { task: "任务一 · 1.2 拓扑连通性异常诊断与断点定位", params: "断点定位：TMP00013138 → TMP00047197", page: "breakpoint.html", note: "在『断点定位』输入起点/终点，自动定位断点并给出补接方案。" },
    { task: "任务一 · 1.3 联络开关自动识别与可视化梳理", params: "LINE215 ↔ LINE216 经 LKS00021516 联络", page: "tie_switch.html", note: "查看联络开关台账与馈线配对关系。" },
    { task: "任务一 · 1.4 疑似联络开关智能识别与复核", params: "LKS00007403 / LKS00021507（分闸非检修）", page: "problem_list.html", note: "按二级分类 1.4 过滤，查看疑似联络开关复核建议。" },
    { task: "任务二 · 5.1 标准化美化", params: "LINE215 / LINE216 原始 SVG 重绘", page: "svg_beautify.html", note: "对比原始与标准化美化后图纸，含网格/图例/配色规范。" },
    { task: "任务二 · 5.2 交互式增删设备", params: "新增站房000300+3负荷开关 / 删除开关00024", page: "svg_edit.html", note: "动态增删设备，图形与模型同步校验。" },
    { task: "任务二 · 5.3 自动出图", params: "单线图 / 联络关系图 / 全站总图 / 电源追溯", page: "svg_beautify.html", note: "基于数据库拓扑关系自动生成接线图。" },
    { task: "任务二 · 5.3.4 电源追溯", params: "LINE074 配变0486 (TMP00034205) 主供/备供", page: "svg_beautify.html", note: "查看配变0486 的主供路径与经联络开关的备供路径。" }
  ];

  var WT_STYLE = "#wt{position:fixed;inset:0;z-index:9600;display:flex;align-items:center;justify-content:center;padding:20px}"
    + "#wt[hidden]{display:none}"
    + "#wt-backdrop{position:absolute;inset:0;background:rgba(15,23,42,.5)}"
    + "#wt-panel{position:relative;width:min(560px,94vw);background:var(--bg-elev);border:1px solid var(--border-strong);border-radius:var(--radius-lg);box-shadow:var(--shadow-lg);overflow:hidden}"
    + "#wt-head{display:flex;align-items:center;gap:10px;padding:14px 16px;border-bottom:1px solid var(--border)}"
    + "#wt-progress{font-size:11px;color:var(--fg-dim);white-space:nowrap}"
    + "#wt-title{font-size:14px;font-weight:700;flex:1}"
    + "#wt-close{border:none;background:transparent;font-size:22px;line-height:1;cursor:pointer;color:var(--fg-muted);padding:0 4px}"
    + "#wt-body{padding:18px 16px}"
    + "#wt-task{font-size:16px;font-weight:700;color:var(--accent);margin:0 0 12px}"
    + "#wt-params{font-size:13px;background:var(--bg-elev-2);border-radius:var(--radius);padding:10px 12px;margin-bottom:12px;line-height:1.5}"
    + "#wt-params b{color:var(--fg)}"
    + "#wt-note{font-size:12px;color:var(--fg-muted);line-height:1.6}"
    + "#wt-foot{display:flex;align-items:center;gap:8px;padding:12px 16px;border-top:1px solid var(--border)}"
    + "#wt-count{margin-left:auto;font-size:12px;color:var(--fg-dim)}";

  var cur = 0, built = false;
  var wtEl, wtTask, wtParams, wtNote, wtProgress, wtCount, wtPrev, wtNext, wtGoto, wtClose;

  function injectStyle() {
    if (document.getElementById("wt-style")) return;
    var s = document.createElement("style");
    s.id = "wt-style";
    s.textContent = WT_STYLE;
    document.head.appendChild(s);
  }

  function buildOverlay() {
    var html =
      '<div class="wt" id="wt" hidden>' +
      '  <div class="wt-backdrop" id="wt-backdrop"></div>' +
      '  <div class="wt-panel" role="dialog" aria-modal="true" aria-label="演示走查">' +
      '    <div class="wt-head"><span class="wt-progress" id="wt-progress"></span><span class="wt-title" id="wt-title">演示走查</span><button class="wt-close" id="wt-close" aria-label="关闭">×</button></div>' +
      '    <div class="wt-body">' +
      '      <div class="wt-task" id="wt-task"></div>' +
      '      <div class="wt-params" id="wt-params"></div>' +
      '      <div class="wt-note" id="wt-note"></div>' +
      '    </div>' +
      '    <div class="wt-foot">' +
      '      <button class="btn btn-ghost btn-sm" id="wt-prev">上一步</button>' +
      '      <span class="wt-count" id="wt-count"></span>' +
      '      <button class="btn btn-primary btn-sm" id="wt-next">下一步</button>' +
      '      <a class="btn btn-sm" id="wt-goto" target="_self">前往该页面 →</a>' +
      '    </div>' +
      '  </div>' +
      '</div>';
    document.body.insertAdjacentHTML("beforeend", html);
    wtEl = document.getElementById("wt");
    wtTask = document.getElementById("wt-task");
    wtParams = document.getElementById("wt-params");
    wtNote = document.getElementById("wt-note");
    wtProgress = document.getElementById("wt-progress");
    wtCount = document.getElementById("wt-count");
    wtPrev = document.getElementById("wt-prev");
    wtNext = document.getElementById("wt-next");
    wtGoto = document.getElementById("wt-goto");
    wtClose = document.getElementById("wt-close");

    wtClose.addEventListener("click", close);
    document.getElementById("wt-backdrop").addEventListener("click", close);
    wtPrev.addEventListener("click", function () { if (cur > 0) { cur--; renderStep(); } });
    wtNext.addEventListener("click", function () { if (cur >= STEPS.length - 1) { close(); } else { cur++; renderStep(); } });
    document.addEventListener("keydown", function (ev) {
      if (wtEl.hidden) return;
      if (ev.key === "Escape") { close(); }
      else if (ev.key === "ArrowRight") { if (cur < STEPS.length - 1) { cur++; renderStep(); } }
      else if (ev.key === "ArrowLeft") { if (cur > 0) { cur--; renderStep(); } }
    });
    built = true;
  }

  function renderStep() {
    var s = STEPS[cur];
    wtTask.textContent = s.task;
    wtParams.innerHTML = "<b>示例输入：</b> " + s.params;
    wtNote.textContent = s.note;
    wtProgress.textContent = "第 " + (cur + 1) + " / " + STEPS.length + " 步";
    wtCount.textContent = (cur + 1) + " / " + STEPS.length;
    wtGoto.setAttribute("href", s.page);
    wtPrev.disabled = cur === 0;
    wtPrev.style.opacity = cur === 0 ? "0.5" : "1";
    wtNext.textContent = cur === STEPS.length - 1 ? "完成" : "下一步";
  }

  function open() {
    if (!built) buildOverlay();
    cur = 0;
    renderStep();
    wtEl.hidden = false;
  }
  function close() { if (wtEl) wtEl.hidden = true; }

  function ensure() { injectStyle(); if (!built) buildOverlay(); }

  function init() {
    ensure();
    try {
      if (sessionStorage.getItem("v8-walkthrough") === "1") {
        sessionStorage.removeItem("v8-walkthrough");
        open();
      }
    } catch (e) {}
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();

  global.PowerWalk = { open: open, close: close };
})(typeof window !== "undefined" ? window : globalThis);
