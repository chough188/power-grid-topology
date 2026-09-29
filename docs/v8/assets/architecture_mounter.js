/* v8 — architecture.svg mounter
 *
 * 把 system architecture 全景图作为 dashboard 顶部 banner 注入.
 * 0 依赖, 纯 SVG 嵌入, 立即可用.
 *
 * 用法:
 *   1. 在 dashboard.html 末尾引入本文件
 *   2. <div id="arch-banner"></div> 出现在 dashboard 顶部,JS 会替换为 <object>
 *   3. 点击 banner 弹出可下载 .svg 链接, 答辩后可直接送 PNG (Chrome 右键另存)
 */

(function () {
  if (!document.getElementById) return;
  var slot = document.getElementById("arch-banner");
  if (!slot) return;

  // 1. 渲染 SVG 卡片
  slot.innerHTML =
    "<div class=\"card\" style=\"padding:12px;margin-bottom:12px\">" +
    "  <div style=\"display:flex;justify-content:space-between;align-items:center;margin-bottom:8px\">" +
    "    <strong style=\"font-size:13px\">" +
    "      <span class=\"sec-ico\"><svg viewBox='0 0 24 24' width='15' height='15' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round' aria-hidden='true'><rect x='3' y='3' width='7' height='7' rx='1'/><rect x='14' y='3' width='7' height='7' rx='1'/><rect x='3' y='14' width='7' height='7' rx='1'/><rect x='14' y='14' width='7' height='7' rx='1'/></svg></span> 系统架构全景 (5 层检测器 + 28 异常类型)" +
    "    </strong>" +
    "    <span class=\"badge\" id=\"arch-meta\">端到端闭环 · F1 96.4% · Recall 100%</span>" +
    "  </div>" +
    "  <div style=\"background:#0f172a;border-radius:6px;overflow:hidden\">" +
    "    <object id=\"arch-svg\" data=\"../assets/architecture.svg\" type=\"image/svg+xml\" " +
    "            style=\"width:100%;height:auto;display:block;max-height:520px\"></object>" +
    "  </div>" +
    "  <div style=\"display:flex;justify-content:flex-end;gap:8px;margin-top:8px\">" +
    "    <a class=\"btn btn-sm\" href=\"../assets/architecture.svg\" download=\"architecture.svg\">下载 SVG</a>" +
    "  </div>" +
    "</div>";
})();
