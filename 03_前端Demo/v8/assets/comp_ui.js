/* CP-202606 比赛前端 — 共享 UI 助手 (comp_ui.js)
 * 依赖: theme.css token / shell.js(appShell) / 可选 echarts / 可选 SheetJS(XLSX)
 * 提供: 导出(CSV/XLSX) / 图表自适应 / KPI / 分类配色 / SVG 自动出图渲染器
 */
(function (global) {
  "use strict";
  var shell = global.appShell || {};

  /* ---------- 导出 ---------- */
  function download(filename, content, mime) {
    var blob = new Blob([content], { type: mime || "text/plain;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url; a.download = filename; document.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(url); a.remove(); }, 2000);
  }
  function rowsToCSV(headers, rows) {
    var esc = function (v) { v = (v === undefined || v === null) ? "" : String(v); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
    var lines = [headers.map(esc).join(",")];
    rows.forEach(function (r) { lines.push(headers.map(function (h, i) { return esc(r[i] !== undefined ? r[i] : (r[h] !== undefined ? r[h] : "")); }).join(",")); });
    return "﻿" + lines.join("\n"); // BOM 保证 Excel 中文不乱码
  }
  function exportCSV(filename, headers, rows) {
    download(filename, rowsToCSV(headers, rows), "text/csv;charset=utf-8");
  }
  // sheets: [{ name, headers, rows }]
  function exportXLSX(filename, sheets) {
    if (typeof global.XLSX === "undefined") {
      if (shell.toast) shell.toast("未加载 SheetJS, 已降级导出 CSV", "warn");
      sheets.forEach(function (s, i) { exportCSV((filename.replace(/\.xlsx?$/, "") + "_" + (i + 1) + "_" + s.name + ".csv"), s.headers, s.rows); });
      return;
    }
    var wb = global.XLSX.utils.book_new();
    sheets.forEach(function (s) {
      var aoa = [s.headers].concat(s.rows.map(function (r) { return s.headers.map(function (h, i) { return r[i] !== undefined ? r[i] : (r[h] !== undefined ? r[h] : ""); }); }));
      var ws = global.XLSX.utils.aoa_to_sheet(aoa);
      global.XLSX.utils.book_append_sheet(wb, ws, s.name.slice(0, 28));
    });
    global.XLSX.writeFile(wb, filename);
  }

  /* ---------- 图表自适应 ---------- */
  function makeChart(el, optionFn) {
    if (typeof global.echarts === "undefined" || !el) return null;
    var inst = global.echarts.init(el);
    function draw() { inst.setOption(optionFn(shell.chartTheme ? shell.chartTheme() : {}), true); }
    draw();
    window.addEventListener("themechange", draw);
    if (shell.addResizeHandler) shell.addResizeHandler(function () { inst.resize(); });
    return inst;
  }

  /* ---------- 分类配色 (一级分类 → token) ---------- */
  function catColor(l1) {
    return { "1": "var(--accent)", "2": "var(--warn)", "3": "var(--info)", "4": "var(--dev-tie)" }[l1] || "var(--fg-dim)";
  }

  /* ---------- KPI 卡片 ---------- */
  function kpi(opts) {
    var mod = opts.mod ? " " + opts.mod : "";
    return '<div class="kpi' + mod + '">' +
      (opts.icon ? '<div style="color:var(--fg-dim)">' + shell.icon(opts.icon) + '</div>' : "") +
      '<div class="kpi-label">' + opts.label + '</div>' +
      '<div class="kpi-value">' + opts.value + '</div>' +
      (opts.sub ? '<div class="kpi-sub">' + opts.sub + '</div>' : "") +
      '</div>';
  }

  /* ============================================================
   * SVG 自动出图渲染器 (任务二 5.3)
   * 全部走 theme.css token; 返回 SVG 字符串, 由页面注入 .svg-canvas
   * ========================================================== */
  function glyphGroup(type) {
    // 以 (0,0) 为中心, 半径 r=16
    switch (type) {
      case "bus": return '<g class="g-bus"><rect x="-26" y="-10" width="52" height="20" rx="3"/></g>';
      case "source": return '<g class="g-source"><circle r="16"/><circle r="8" fill="var(--svg-bg)"/></g>';
      case "switch": return '<g class="g-switch"><circle r="14"/></g>';
      case "tie": return '<g class="g-tie"><circle r="14"/></g>';
      case "loop": return '<g class="g-loop"><circle r="14"/></g>';
      case "transformer": return '<g class="g-transformer"><rect x="-14" y="-14" width="28" height="28" rx="4"/><circle cx="0" cy="0" r="6" fill="var(--svg-bg)"/></g>';
      case "load": return '<g class="g-load"><rect x="-12" y="-12" width="24" height="24" rx="3"/></g>';
      case "station": return '<g class="g-station"><rect x="-30" y="-20" width="60" height="40" rx="6"/></g>';
      default: return '<g class="g-switch"><circle r="14"/></g>';
    }
  }

  // 径向分层布局 (以电源点/母线为根)
  function layoutRadial(graph) {
    var adj = {}; graph.nodes.forEach(function (n) { adj[n.id] = []; });
    graph.edges.forEach(function (e) { (adj[e.from] = adj[e.from] || []).push(e.to); (adj[e.to] = adj[e.to] || []).push(e.from); });
    var depth = {}, order = [];
    var src = graph.nodes.find(function (n) { return n.feederSource; }) || graph.nodes[0];
    var q = [src.id]; depth[src.id] = 0;
    while (q.length) {
      var cur = q.shift(); order.push(cur);
      (adj[cur] || []).forEach(function (nb) { if (depth[nb] === undefined) { depth[nb] = depth[cur] + 1; q.push(nb); } });
    }
    var levels = {}; order.forEach(function (id, i) { var d = depth[id] !== undefined ? depth[id] : 0; (levels[d] = levels[d] || []).push(id); });
    var colW = 140, rowH = 90;
    var maxCol = 0, maxRows = 1;
    Object.keys(levels).forEach(function (c) { maxCol = Math.max(maxCol, +c); maxRows = Math.max(maxRows, levels[c].length); });
    var pos = {};
    Object.keys(levels).forEach(function (c) {
      var arr = levels[c]; var totalH = (arr.length - 1) * rowH;
      arr.forEach(function (id, i) { pos[id] = { x: 70 + (+c) * colW, y: (maxRows * rowH) / 2 - totalH / 2 + i * rowH + 50 }; });
    });
    return { pos: pos, levels: levels, src: src.id, colW: colW, rowH: rowH, w: 70 + maxCol * colW + 120, h: maxRows * rowH + 100 };
  }

  function nodeClass(n) { if (n.tie) return "g-tie"; if (n.loop) return "g-loop"; return "g-" + (n.type || "switch"); }

  function renderSingleLine(graph) {
    var L = layoutRadial(graph);
    var parts = ['<svg class="svg-stage" viewBox="0 0 ' + L.w + ' ' + L.h + '" width="' + L.w + '" height="' + L.h + '" xmlns="http://www.w3.org/2000/svg">'];
    // wires
    graph.edges.forEach(function (e) {
      var a = L.pos[e.from], b = L.pos[e.to]; if (!a || !b) return;
      var fromN = graph.nodes.find(function (n) { return n.id === e.from; });
      var toN = graph.nodes.find(function (n) { return n.id === e.to; });
      var cls = (fromN && fromN.tie) || (toN && toN.tie) ? "wire-tie" : ((fromN && fromN.loop) || (toN && toN.loop) ? "wire-loop" : "wire");
      if (cls === "wire" || cls === "wire-loop") cls += " power-flow";
      parts.push('<path class="' + cls + '" d="M' + a.x + ',' + a.y + ' L' + b.x + ',' + b.y + '"/>');
    });
    // nodes
    graph.nodes.forEach(function (n) {
      var p = L.pos[n.id]; if (!p) return;
      parts.push('<g class="' + nodeClass(n) + '" transform="translate(' + p.x + ',' + p.y + ')">' + glyphGroup(n.type) + '</g>');
      parts.push('<text class="glyph-label" x="' + p.x + '" y="' + (p.y + 30) + '" text-anchor="middle">' + (n.name || n.id) + '</text>');
    });
    parts.push('</svg>');
    return parts.join("");
  }

  // 电源追溯路径图(5.3.4): 高亮主供路径 + 备供路径(经联络开关接入对侧电源)
  function renderPowerTrace(graph, targetId) {
    var L = layoutRadial(graph);
    var adj = {}; graph.edges.forEach(function (e) { (adj[e.from] = adj[e.from] || []).push(e.to); (adj[e.to] = adj[e.to] || []).push(e.from); });
    // 从目标设备 BFS 记录 prev, 便于回溯到任一电源点(主供/备供)
    var prev = {}, q = [targetId]; prev[targetId] = null;
    while (q.length) { var c = q.shift(); (adj[c] || []).forEach(function (nb) { if (prev[nb] === undefined) { prev[nb] = c; q.push(nb); } }); }
    function pathOf(src) {
      var set = {}, edges = {}, cur = src;
      while (cur !== null && cur !== undefined) {
        set[cur] = true;
        if (prev[cur] !== null && prev[cur] !== undefined) { edges[prev[cur] + ">" + cur] = true; edges[cur + ">" + prev[cur]] = true; }
        cur = prev[cur];
      }
      return { set: set, edges: edges };
    }
    var sources = graph.nodes.filter(function (n) { return n.feederSource; }).map(function (n) { return n.id; });
    var primary = sources.length ? pathOf(sources[0]) : { set: {}, edges: {} };
    var backup = sources.length > 1 ? pathOf(sources[1]) : { set: {}, edges: {} };
    var parts = ['<svg class="svg-stage" viewBox="0 0 ' + L.w + ' ' + L.h + '" width="' + L.w + '" height="' + L.h + '" xmlns="http://www.w3.org/2000/svg">'];
    graph.edges.forEach(function (e) {
      var a = L.pos[e.from], b = L.pos[e.to]; if (!a || !b) return;
      var k1 = e.from + ">" + e.to, k2 = e.to + ">" + e.from;
      var isP = primary.edges[k1] || primary.edges[k2];
      var isB = backup.edges[k1] || backup.edges[k2];
      var cls = isP ? "trace-path" : (isB ? "trace-backup" : "wire");
      if (isP || isB) cls += " power-flow";
      parts.push('<path class="' + cls + '" d="M' + a.x + ',' + a.y + ' L' + b.x + ',' + b.y + '"/>');
    });
    graph.nodes.forEach(function (n) {
      var p = L.pos[n.id]; if (!p) return;
      var onP = primary.set[n.id], onB = backup.set[n.id];
      var hl = onP ? " node-hl" : (onB ? " node-hl trace-node-backup" : "");
      parts.push('<g class="' + nodeClass(n) + hl + '" transform="translate(' + p.x + ',' + p.y + ')">' + glyphGroup(n.type) + '</g>');
      var tag = n.id === targetId ? " ◀目标" : (n.feederSource && sources[0] === n.id ? " ★主供" : (n.feederSource && sources[1] === n.id ? " ★备供" : ""));
      parts.push('<text class="glyph-label" x="' + p.x + '" y="' + (p.y + 30) + '" text-anchor="middle">' + (n.name || n.id) + tag + '</text>');
    });
    return parts.join("");
  }

  // 馈线联络关系图 (以馈线为节点, 联络开关为连线)
  function renderTieRelation(graphs) {
    var feeders = Object.keys(graphs);
    var w = 60 + feeders.length * 180, h = 240;
    var pos = {};
    feeders.forEach(function (f, i) { pos[f] = { x: 120 + i * 180, y: h / 2 }; });
    // 构建联络连线(基于样例 data 的 tie pairs)
    var ties = [["LINE215", "LINE216"], ["10kVLINE111", "LINE215"], ["LINE216", "LINE215"]];
    var parts = ['<svg class="svg-stage" viewBox="0 0 ' + w + ' ' + h + '" width="' + w + '" height="' + h + '" xmlns="http://www.w3.org/2000/svg">'];
    ties.forEach(function (t) {
      var a = pos[t[0]], b = pos[t[1]]; if (!a || !b) return;
      parts.push('<path class="wire-tie" d="M' + a.x + ',' + a.y + ' C' + (a.x + 60) + ',' + (a.y - 50) + ' ' + (b.x - 60) + ',' + (b.y - 50) + ' ' + b.x + ',' + b.y + '"/>');
      var mx = (a.x + b.x) / 2, my = (a.y - 50);
      parts.push('<g class="g-tie" transform="translate(' + mx + ',' + my + ')">' + glyphGroup("tie") + '</g>');
    });
    feeders.forEach(function (f) {
      var p = pos[f];
      parts.push('<g transform="translate(' + p.x + ',' + p.y + ')"><rect x="-70" y="-22" width="140" height="44" rx="8" fill="var(--bg-elev-2)" stroke="var(--border-strong)"/></g>');
      parts.push('<text class="glyph-label" x="' + p.x + '" y="' + p.y + '" text-anchor="middle" font-weight="600">' + graphs[f].name + '</text>');
    });
    parts.push('</svg>');
    return parts.join("");
  }

  // 全站间馈线联络总图 (5.3.3): 多变电站分组 + 跨站联络可视化
  function renderStationTie(graphs, opts) {
    opts = opts || {};
    var ties = opts.ties || [];
    var scope = opts.scope || null;
    // 按变电站分组
    var groups = {};
    Object.keys(graphs).forEach(function (f) {
      var g = graphs[f]; if (scope && g.substation !== scope) return;
      (groups[g.substation] = groups[g.substation] || []).push(f);
    });
    var subs = Object.keys(groups);
    var colW = 320, feedH = 80;
    var maxFeeds = subs.reduce(function (m, s) { return Math.max(m, groups[s].length); }, 1);
    var W = 90 + subs.length * colW + 110;
    var H = 120 + maxFeeds * feedH + 60;
    var parts = ['<svg class="svg-stage" viewBox="0 0 ' + W + ' ' + H + '" width="' + W + '" height="' + H + '" xmlns="http://www.w3.org/2000/svg">'];
    var pos = {}; // feederId -> {x,y}
    subs.forEach(function (s, si) {
      var subX = 90 + si * colW, busY = 60;
      parts.push('<g transform="translate(' + subX + ',' + busY + ')"><rect x="-90" y="-22" width="180" height="44" rx="8" fill="var(--dev-station)" opacity="0.18" stroke="var(--dev-station)"/></g>');
      parts.push('<text class="glyph-label" x="' + subX + '" y="' + (busY + 5) + '" text-anchor="middle" font-weight="700">' + s + '</text>');
      groups[s].forEach(function (f, j) {
        var fx = subX + 150, fy = 130 + j * feedH;
        pos[f] = { x: fx, y: fy };
        parts.push('<path class="wire" d="M' + subX + ',' + (busY + 22) + ' L' + subX + ',' + fy + ' L' + (fx - 75) + ',' + fy + '"/>');
        parts.push('<g transform="translate(' + fx + ',' + fy + ')"><rect x="-75" y="-18" width="150" height="36" rx="6" fill="var(--bg-elev-2)" stroke="var(--border-strong)"/></g>');
        parts.push('<text class="glyph-label" x="' + fx + '" y="' + (fy + 4) + '" text-anchor="middle">' + graphs[f].name + '</text>');
      });
    });
    // 联络弧线(同站=虚线联络; 跨站=实线加粗 + 标签)
    ties.forEach(function (t) {
      if (!pos[t.from] || !pos[t.to]) return;
      var a = pos[t.from], b = pos[t.to];
      var ax = a.x + 75, ay = a.y, bx = b.x - 75, by = b.y;
      var mx = (ax + bx) / 2, my = Math.min(ay, by) - 50;
      parts.push('<path class="' + (t.cross ? "wire-tie cross" : "wire-tie") + '" d="M' + ax + ',' + ay + ' Q' + mx + ',' + my + ' ' + bx + ',' + by + '"/>');
      parts.push('<g class="g-tie" transform="translate(' + mx + ',' + my + ')">' + glyphGroup("tie") + '</g>');
      if (t.cross) parts.push('<text class="glyph-label" x="' + mx + '" y="' + (my - 18) + '" text-anchor="middle" font-weight="600" fill="var(--dev-tie)">跨站联络</text>');
    });
    parts.push('</svg>');
    return parts.join("");
  }

  global.compUI = {
    exportCSV: exportCSV,
    exportXLSX: exportXLSX,
    makeChart: makeChart,
    catColor: catColor,
    kpi: kpi,
    renderSingleLine: renderSingleLine,
    renderPowerTrace: renderPowerTrace,
    renderTieRelation: renderTieRelation,
    renderStationTie: renderStationTie,
    glyphGroup: glyphGroup,
  };
})(typeof window !== "undefined" ? window : globalThis);
