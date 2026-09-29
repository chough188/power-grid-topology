/* CP-202606 — 比赛数据契约守卫 (contract_guard.js)
 * 作用: 运行时零漂移校验。每次调用 compUI.exportXLSX / compUI.exportCSV 时,
 *       将导出的表头与 api_competition.js 的 STANDARD_HEADERS(6 张标准表) 做
 *       顺序敏感比对; 若任一 Sheet 表头与标准契约不符, 仅 console.warn + toast 告警,
 *       绝不阻断导出 (保证比赛环境可用性)。
 * 设计: 纯增强、只读 STANDARD_HEADERS、不修改任何比赛数据契约 / 渲染 class / 比赛内容。
 */
(function (global) {
  "use strict";

  function arraysEqual(a, b) {
    if (!a || !b || a.length !== b.length) return false;
    for (var i = 0; i < a.length; i++) if (String(a[i]) !== String(b[i])) return false;
    return true;
  }

  function standardHeaders() {
    return (global.compApi && global.compApi.STANDARD_HEADERS) || null;
  }

  // 校验单张表: headers 是否与 STANDARD_HEADERS 中任一表完全相等
  function validateSheet(sheet) {
    var ST = standardHeaders();
    if (!ST || !sheet || !sheet.headers) return true;
    var keys = Object.keys(ST);
    var ok = keys.some(function (k) { return arraysEqual(sheet.headers, ST[k]); });
    if (!ok) {
      var msg = "[contract-guard] 导出表头未对齐 STANDARD_HEADERS 任一标准表: " +
        (sheet.name || "?") + " → [" + sheet.headers.join(" | ") + "]";
      console.warn(msg);
      if (global.appShell && global.appShell.toast) {
        global.appShell.toast("⚠ 导出表头偏离标准契约: " + (sheet.name || "?"), "warn");
      }
    } else {
      console.info("[contract-guard] ✓ 表头对齐: " + (sheet.name || "?") + " (" + sheet.headers.length + " 列)");
    }
    return true; // 仅告警, 不阻断
  }

  function install() {
    if (!global.compUi && !global.compUI) return;
    var compUI = global.compUI || global.compUi;
    var origX = compUI.exportXLSX, origC = compUI.exportCSV;
    if (origX) {
      compUI.exportXLSX = function (filename, sheets) {
        (sheets || []).forEach(validateSheet);
        return origX.apply(compUI, arguments);
      };
    }
    if (origC) {
      compUI.exportCSV = function (filename, headers, rows) {
        validateSheet({ name: filename, headers: headers });
        return origC.apply(compUI, arguments);
      };
    }
    if (origX || origC) console.info("[contract-guard] 已挂载 STANDARD_HEADERS 零漂移守卫");
  }

  // 静态自检: 在控制台输出 6 张标准表契约与当前样本导出路径的一致性快照
  function selfCheck() {
    var ST = standardHeaders();
    if (!ST) return { ok: false, reason: "STANDARD_HEADERS 未加载" };
    var summary = Object.keys(ST).map(function (k) {
      return { sheet: k, columns: ST[k].length, headers: ST[k] };
    });
    console.info("[contract-guard] 契约快照:", summary);
    return { ok: true, sheets: summary };
  }

  if (global.compUI || global.compUi) install();
  else if (typeof document !== "undefined") document.addEventListener("DOMContentLoaded", function () { install(); });

  global.contractGuard = { validateSheet: validateSheet, install: install, selfCheck: selfCheck };
})(typeof window !== "undefined" ? window : globalThis);
