/* CP-202606 — 离线 CSV 导出 (export_csv.js)
 * 作用: 一键导出《拓扑校验问题标准输出.xlsx》6 张标准表为 CSV（零依赖、离线、Blob 下载）。
 * 与 reports.html 的 xlsx 导出互补: xlsx 走 CDN 库, 本模块纯前端 Blob, 适合无网 / 比赛环境。
 * 严格复用 api_competition.js 的 STANDARD_HEADERS 与 getter, 不改动任何比赛数据契约。
 */
(function (global) {
  "use strict";

  function csvCell(v) {
    if (v === null || v === undefined) v = "";
    var s = String(v);
    if (/[",\n\r]/.test(s)) s = '"' + s.replace(/"/g, '""') + '"';
    return s;
  }

  function toCSV(headers, rows) {
    var lines = [headers.map(csvCell).join(",")];
    for (var i = 0; i < rows.length; i++) lines.push(rows[i].map(csvCell).join(","));
    // 前置 UTF-8 BOM, 保证 Excel 正确识别中文
    return "﻿" + lines.join("\r\n");
  }

  function safeName(name) {
    return (name || "sheet").replace(/[\\/:*?"<>|]/g, "_");
  }

  function download(name, content) {
    var blob = new Blob([content], { type: "text/csv;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(url); a.remove(); }, 2000);
  }

  // 严格对齐 api_competition.js 的 STANDARD_HEADERS + getter 返回字段
  function buildSheets() {
    return Promise.all([
      compApi.getProblems().then(function (l) {
        return { name: "拓扑校验问题清单", headers: compApi.STANDARD_HEADERS.problems, rows: l.map(function (p) {
          return [p.seq, compApi.l1Name(p.l1), compApi.l2Name(p.l2), p.devId, p.devName, p.feeder, p.station, p.desc, p.fix, p.sql];
        }) };
      }),
      compApi.getBreakpoints().then(function (l) {
        return { name: "拓扑连通性异常诊断与断点定位结果", headers: compApi.STANDARD_HEADERS.breakpoints, rows: l.map(function (b) {
          return [b.seq, b.startId, b.endId, b.breakType, b.thisSideId, b.thisSideName, b.otherSideId, b.otherSideName, b.fix, b.sql];
        }) };
      }),
      compApi.getTieSwitches().then(function (l) {
        return { name: "联络开关自动识别与可视化梳理任务结果", headers: compApi.STANDARD_HEADERS.tieSwitches, rows: l.map(function (t) {
          return [t.lineId, t.lineName, t.substation, t.swId, t.swName, t.hasTie, t.tieLineId, t.tieLineName, t.tieSub];
        }) };
      }),
      compApi.getLoops().then(function (l) {
        return { name: "非计划性合环拓扑识别任务结果", headers: compApi.STANDARD_HEADERS.loops, rows: l.map(function (x) {
          return [x.lineId, x.lineName, x.substation, x.loopLineId, x.loopLineName, x.loopSub, x.suspectSwId, x.suspectSwName, x.sql];
        }) };
      }),
      compApi.getQuality().then(function (l) {
        return { name: "模型修正质量评分任务结果", headers: compApi.STANDARD_HEADERS.quality, rows: l.map(function (q) {
          return [q.seq, q.station, q.stationId, q.feeder, q.feederId, q.before, q.after];
        }) };
      }),
      compApi.getTaxonomy().then(function (tax) {
        var rows = [];
        tax.forEach(function (t) { t.items.forEach(function (it) { rows.push([t.code + " " + t.name, it.code + " " + it.name]); }); });
        return { name: "问题类型下拉选项", headers: compApi.STANDARD_HEADERS.taxonomy, rows: rows };
      })
    ]);
  }

  // 一键导出 6 表: 分文件下载, 错开 300ms 避免浏览器拦截多下载
  function exportAll6() {
    return buildSheets().then(function (sheets) {
      sheets.forEach(function (s, i) {
        setTimeout(function () { download(safeName(s.name) + ".csv", toCSV(s.headers, s.rows)); }, i * 300);
      });
      return sheets.length;
    });
  }

  global.compCSV = {
    exportAll6: exportAll6,
    buildSheets: buildSheets,
    toCSV: toCSV
  };
})(typeof window !== "undefined" ? window : globalThis);
