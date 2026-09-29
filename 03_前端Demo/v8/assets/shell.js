/* PowerGrid AI Operations — v8/v9 页面 shell + 导航 (shell.js)
 * 调用 appShell.renderShell({page, title, breadcrumb}) 注入布局
 * 提供 appShell.cssVar() / appShell.chartTheme() / appShell.icon() 供页面与图表使用
 * v9 增强: 自动注入 theme-v9.css / comp-v9.css, 通过 data-v9 属性激活 Industrial Tech Console 美学
 */
(function (global) {
  var C = global.CONFIG;
  var A = global.api;

  // v9 皮肤 CSS 早注入 (wave-1): 在 shell.js 加载时(头部解析期)即注入 theme-v9/comp-v9 并激活 data-v9,
  // 消除 renderShell 内 injectV9 的"二次注入往返"。红线安全: 仅注入皮肤 CSS + 设 data-v9 属性,
  // 不改任何 class 名 / 渲染逻辑 / 比赛内容 / 契约。renderShell 内 injectV9 因此变为安全 no-op。
  (function injectV9Early() {
    var html = document.documentElement;
    if (html.getAttribute("data-v9") === "loaded") return; // 防重复
    var base = (function () {
      var scripts = document.querySelectorAll("script[src]");
      for (var i = scripts.length - 1; i >= 0; i--) {
        var src = scripts[i].getAttribute("src") || "";
        if (src.indexOf("shell.js") >= 0) return src.replace(/shell\.js.*$/, "");
      }
      return "./assets/";
    })();
    function loadCSS(href) {
      if (document.querySelector('link[href$="' + href.split("/").pop() + '"]')) return;
      var link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = base + href;
      document.head.appendChild(link);
    }
    loadCSS("theme-v9.css");
    loadCSS("comp-v9.css");
    html.setAttribute("data-v9", "loaded");
  })();

  // 读取当前主题下的 CSS 变量计算值 (供 canvas 类图表使用, canvas 无法解析 var())
  function cssVar(name) {
    try {
      return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    } catch (e) { return ""; }
  }

  // 面包屑版本前缀规范化: 旧 "v5 / xxx" -> 当前 CONFIG.VERSION
  function normalizeBreadcrumb(bc) {
    if (!bc) return bc;
    var v = (C && C.VERSION) || "v8.0.0";
    return bc.replace(/^v5\s*\/\s*/, v + " / ");
  }

  // 生成 ECharts 可用的主题色 (已解析为 rgb/hex, 随明暗主题变化)
  function chartTheme() {
    return {
      fg: cssVar("--fg"),
      muted: cssVar("--fg-muted"),
      dim: cssVar("--fg-dim"),
      accent: cssVar("--accent"),
      success: cssVar("--success"),
      warn: cssVar("--warn"),
      err: cssVar("--err"),
      info: cssVar("--info"),
      grid: cssVar("--border"),
      axis: cssVar("--fg-dim"),
      tooltipBg: cssVar("--bg-elev"),
      tooltipBorder: cssVar("--border-strong"),
      tooltipText: cssVar("--fg"),
    };
  }

  // 统一线性图标 (Lucide 风格, stroke=currentColor 随主题上色, 支持暗色)
  var ICONS = {
    dashboard: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/>',
    trends: '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    reports: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="16 2 16 8 22 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="16" y2="17"/>',
    topology: '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>',
    highlights: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
    anomalies: '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    corrections: '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
    feedback: '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>',
    mobile: '<rect x="5" y="2" width="14" height="20" rx="2"/><line x1="12" y1="18" x2="12" y2="18"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
    back: '<line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>',
    bolt: '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    menu: '<line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>',
    sun: '<circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>',
    moon: '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>',
    dot: '<circle cx="12" cy="12" r="3"/>',
    // 以下为页面内常用动作/语义图标 (Lucide 风格, stroke=currentColor)
    scan: '<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><line x1="3" y1="12" x2="21" y2="12"/>',
    play: '<polygon points="6 4 20 12 6 20 6 4"/>',
    download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
    list: '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>',
    refresh: '<polyline points="23 4 23 10 18 10"/><polyline points="1 20 1 14 6 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>',
    mapPin: '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>',
    clipboard: '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1"/>',
    camera: '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/>',
    checkCircle: '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>',
    alertOctagon: '<polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>',
    database: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>',
    flag: '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/>',
    xCircle: '<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>',
    bar: '<line x1="6" y1="20" x2="6" y2="14"/><line x1="12" y1="20" x2="12" y2="8"/><line x1="18" y1="20" x2="18" y2="4"/>',
    pie: '<path d="M21.21 15.89A10 10 0 1 1 8 2.83"/><path d="M22 12A10 10 0 0 0 12 2v10z"/>',
    eye: '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
    file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="16 2 16 8 22 8"/>',
    cloud: '<path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/>',
    palette: '<circle cx="13.5" cy="6.5" r=".5"/><circle cx="17.5" cy="10.5" r=".5"/><circle cx="8.5" cy="7.5" r=".5"/><circle cx="6.5" cy="12.5" r=".5"/><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.555C21.965 6.012 17.461 2 12 2z"/>',
    user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    info: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
    save: '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>',
    logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
    inbox: '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
    arrowDown: '<line x1="12" y1="5" x2="12" y2="19"/><polyline points="19 12 12 19 5 12"/>',
    zoomIn: '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/>',
    zoomOut: '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="8" y1="11" x2="14" y2="11"/>',
    // 比赛模块图标
    breakpoint: '<path d="M9 17H7A5 5 0 0 1 7 7h2"/><path d="M15 7h2a5 5 0 0 1 0 10h-2"/><line x1="8" y1="12" x2="16" y2="12"/><line x1="8" y1="12" x2="8" y2="12"/>',
    link: '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    layers: '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
    share2: '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>',
    image: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>',
    penTool: '<path d="M12 19l7-7 3 3-7 7-3-3z"/><path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z"/><path d="M2 2l7.586 7.586"/><circle cx="11" cy="11" r="2"/>',
    target: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>'
  };
  function icon(name) {
    var p = ICONS[name] || ICONS.dot;
    return '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + p + '</svg>';
  }

  var NAV = [
    { section: "任务一 · 图模质量校验及修正" },
    { key: "problem_list",   href: "problem_list.html",   icon: "anomalies",  label: "异常问题清单", clause: "任务一·1.1/1.4" },
    { key: "breakpoint",     href: "breakpoint.html",     icon: "breakpoint", label: "断点定位", clause: "任务一·1.2" },
    { key: "tie_switch",     href: "tie_switch.html",     icon: "link",       label: "联络开关梳理", clause: "任务一·1.3/1.4" },
    { key: "loop",           href: "loop.html",           icon: "refresh",    label: "合环识别", clause: "任务一·1.5" },
    { key: "graph_consistency", href: "graph_consistency.html", icon: "layers", label: "图模一致性", clause: "任务一·2.x" },
    { key: "elec_logic",     href: "elec_logic.html",     icon: "bolt",       label: "电气逻辑校验", clause: "任务一·3.1" },
    { key: "main_net",       href: "main_net.html",       icon: "share2",     label: "主配网接口", clause: "任务一·4.x" },
    { key: "quality",        href: "quality.html",        icon: "bar",        label: "质量评分对比", clause: "任务一·模块五" },
    { section: "任务二 · SVG 拓扑图形美化" },
    { key: "svg_beautify",   href: "svg_beautify.html",   icon: "image",      label: "SVG 美化与出图", clause: "任务二·5.1/5.3" },
    { key: "svg_edit",       href: "svg_edit.html",       icon: "penTool",    label: "交互式增删设备", clause: "任务二·5.2" },
    { section: "运营与交付" },
    { key: "dashboard",      href: "dashboard.html",      icon: "dashboard",  label: "总览仪表盘", clause: "总览" },
    { key: "reports",        href: "reports.html",        icon: "reports",    label: "报告中心", clause: "交付" },
    { key: "competition",    href: "competition.html",    icon: "highlights", label: "比赛验收证据", clause: "验收" },
    { section: "系统" },
    { key: "settings",       href: "settings.html",       icon: "settings",   label: "系统设置", clause: "系统" },
    { section: "演示与加分素材（不计入比赛评分）" },
    { key: "lab",           href: "../../v8_lab/index.html", icon: "palette", label: "AI 实验台（追加分）", clause: "加分" },
  ];

  function currentPage() {
    var file = (location.pathname.split("/").pop() || "").toLowerCase();
    return file.replace(/\.html$/, "");
  }

  function getUser() {
    try {
      var s = sessionStorage.getItem("v5-user");
      return s ? JSON.parse(s) : null;
    } catch (e) { return null; }
  }

  function renderShell(opts) {
    opts = opts || {};
    var pageKey = opts.page || currentPage();

    // 未登录拦截 (login.html 除外)
    if (pageKey !== "login" && !A.isLoggedIn()) {
      window.location.replace("../login.html");
      return;
    }

    document.documentElement.setAttribute("data-theme", C.THEME);

    // ===== v9 主题注入: 自动加载 theme-v9.css / comp-v9.css 并激活 data-v9 命名空间 =====
    (function injectV9() {
      var html = document.documentElement;
      if (html.getAttribute("data-v9") === "loaded") return; // 防止重复注入
      var base = (function () {
        var scripts = document.querySelectorAll("script[src]");
        for (var i = scripts.length - 1; i >= 0; i--) {
          var src = scripts[i].getAttribute("src") || "";
          if (src.indexOf("shell.js") >= 0) return src.replace(/shell\.js.*$/, "");
        }
        return "./assets/";
      })();
      function loadCSS(href) {
        if (document.querySelector('link[href$="' + href.split("/").pop() + '"]')) return;
        var link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = base + href;
        document.head.appendChild(link);
      }
      loadCSS("theme-v9.css");
      loadCSS("comp-v9.css");
      html.setAttribute("data-v9", "loaded");
    })();

    var sidebarItems = "";
    var curSection = null;
    for (var i = 0; i < NAV.length; i++) {
      var n = NAV[i];
      if (n.section !== undefined) {
        if (n.section) {
          curSection = n.section;
          sidebarItems += '<div class="sidebar-section">' + n.section + '</div>';
        }
        continue;
      }
      var active = n.key === pageKey ? " active" : "";
      var clauseAttr = n.clause ? ' title="对应评分要点：' + n.clause + '"' : '';
      var clauseSpan = n.clause ? '<span class="nav-clause">' + n.clause + '</span>' : '';
      sidebarItems += '<a class="nav-item' + active + '" href="' + n.href + '"' + clauseAttr +
        (active ? ' aria-current="page"' : '') + '><span class="nav-icon">' + icon(n.icon) + '</span><span>' + n.label + '</span>' + clauseSpan + '</a>';
    }

    var user = getUser();
    var demoTag = (A.isDemoMode && A.isDemoMode())
      ? ' <span class="user-demo-tag" style="font-size:10px;line-height:1;padding:2px 7px;border-radius:999px;background:rgba(34,197,94,.18);color:#22c55e;border:1px solid rgba(34,197,94,.4);margin-left:6px;vertical-align:middle;white-space:nowrap;">演示模式</span>'
      : "";
    var userBlock = user
      ? '<div class="user-menu" id="user-menu">' + demoTag + '<div class="user-avatar">' + (user.user || "U").substr(0, 1).toUpperCase() + '</div><div><div class="user-name">' + (user.user || "guest") + '</div><div class="user-role">' + (user.tenant || "default") + '</div></div></div>'
      : '<a class="btn btn-primary btn-sm" href="./login.html">登录</a>';

    var html = [
      '<a class="skip-link" href="#main-content">跳到主内容</a>',
      '<div class="win-titlebar" id="win-titlebar">',
      '  <span class="win-icon">' + icon("bolt") + '</span>',
      '  <span class="win-title-text">' + C.APP_NAME + ' · ' + (C.VERSION || "") + '</span>',
      '  <button class="win-cmdk-btn" id="win-cmdk" type="button" title="命令面板：快速跳转页面 / 导出 / 走查（Ctrl 或 Cmd+K）" aria-label="打开命令面板"><span class="win-cmdk-kbd">⌘K</span> 快速跳转</button>',
      '  <span class="win-spacer"></span>',
      '  <div class="win-traffic" role="group" aria-label="窗口控制">',
      '    <button class="win-ctrl-btn win-ctrl-min" id="win-min" type="button" title="紧凑模式 / 最小化" aria-label="最小化"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="5" y1="19" x2="19" y2="19"/></svg></button>',
      '    <button class="win-ctrl-btn win-ctrl-max" id="win-max" type="button" title="全屏 / 最大化" aria-label="最大化" aria-pressed="false"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="5" y="5" width="14" height="14" rx="1"/></svg></button>',
      '    <button class="win-ctrl-btn win-ctrl-close" id="win-close" type="button" title="收起 / 展开（不退出系统）" aria-label="收起或展开窗口"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/></svg></button>',
      '  </div>',
      '</div>',
      '<div class="app">',
      '  <aside class="sidebar">',
      '    <div class="sidebar-brand">',
      '      <div class="brand-mark">' + icon("bolt") + '</div>',
      '      <div><div class="brand-text">' + C.APP_NAME + '</div><div class="brand-sub">' + C.VERSION + ' · ' + C.APP_SUBTITLE + '</div></div>',
      '    </div>',
      '    <nav class="sidebar-nav" id="sidebar-nav" aria-label="主导航">' + sidebarItems + '</nav>',
      '  </aside>',
      '  <header class="topbar">',
      '    <div class="topbar-left">',
      '      <button class="btn btn-ghost btn-sm hamburger" id="sidebar-toggle" aria-label="打开导航菜单" aria-expanded="false" aria-controls="sidebar-nav">' + icon("menu") + '</button>',
      '      <span class="topbar-title">' + (opts.title || "") + '</span>',
      '      <span class="topbar-breadcrumb">' + normalizeBreadcrumb(opts.breadcrumb || (C.VERSION + " / " + pageKey)) + '</span>',
      '    </div>',
      '    <div class="topbar-right">',
      '      <span class="badge" id="api-base-badge" title="后端地址">' + C.API_BASE + '</span>',
      '      <button class="btn btn-ghost btn-sm" id="prefill-btn" title="在断点定位 / SVG 美化 / 交互编辑页一键填入示例数据（Ctrl/Cmd+K 打开命令面板）">用示例数据</button>',
      '      <button class="btn btn-ghost btn-sm" id="theme-toggle" title="切换主题" aria-label="切换明暗主题"></button>',
      userBlock,
      '    </div>',
      '  </header>',
      '  <main class="main" id="main-content">',
      '    <div id="page-body" class="page-fade">' + (opts.body || "") + '</div>',
      '  </main>',
      '</div>',
      '<div class="sidebar-backdrop" id="sidebar-backdrop"></div>',
      '<div class="toast-stack" id="toast-stack"></div>',
      '<div class="cmdk" id="cmdk" hidden>',
      '  <div class="cmdk-backdrop" id="cmdk-backdrop"></div>',
      '  <div class="cmdk-panel" role="dialog" aria-modal="true" aria-label="命令面板">',
      '    <div class="cmdk-input-wrap"><span class="cmdk-ico" id="cmdk-ico"></span><input class="cmdk-input" id="cmdk-input" type="text" placeholder="搜索页面 / 命令 / 导出…（↑↓ 选择 · Enter 跳转 · Esc 关闭）" aria-label="命令搜索" autocomplete="off"></div>',
      '    <div class="cmdk-list" id="cmdk-list" role="listbox" aria-label="命令结果"></div>',
      '    <div class="cmdk-foot">↑↓ 导航 · Enter 确认 · Esc 关闭 · 支持中文模糊搜索</div>',
      '  </div>',
      '</div>',
      '<div class="page-curtain" id="page-curtain" aria-hidden="true"><div class="curtain-mark">' + icon("bolt") + '</div></div>',
    ].join("\n");

    document.body.innerHTML = html;
    document.body.style.background = "var(--bg-page)";

    // P0-3: 首访引导走查邀请 banner (仅 dashboard, 纯 UX 层, 红线安全)
    if (pageKey === "dashboard") {
      try {
        if (!sessionStorage.getItem("v8-wt-seen")) {
          var _pb = document.getElementById("page-body");
          if (_pb) {
            var _b = document.createElement("div");
            _b.className = "wt-banner";
            _b.id = "wt-banner";
            _b.innerHTML = '<span class="wt-banner-ico">' + icon("play") + '</span>' +
              '<span class="wt-banner-text">首次使用？花 3 分钟跟着<strong>引导式走查</strong>快速看懂全部评分要点。</span>' +
              '<button class="wt-banner-go" id="wt-banner-go" type="button">开始走查 →</button>' +
              '<button class="wt-banner-x" id="wt-banner-x" type="button" aria-label="关闭提示">×</button>';
            _pb.insertBefore(_b, _pb.firstChild);
            var _go = _b.querySelector("#wt-banner-go");
            var _x = _b.querySelector("#wt-banner-x");
            if (_go) _go.addEventListener("click", function () {
              try { sessionStorage.setItem("v8-wt-seen", "1"); sessionStorage.setItem("v8-walkthrough", "1"); } catch (e) {}
              window.location.href = "competition.html";
            });
            if (_x) _x.addEventListener("click", function () {
              try { sessionStorage.setItem("v8-wt-seen", "1"); } catch (e) {}
              _b.remove();
            });
          }
        }
      } catch (e) {}
    }

    injectCmdkStyle();
    initCommandPalette();

    // PREMIUM POLISH: 追加加载 GSAP(本地 vendor, 保离线) + premium.js; 纯增强, 不改动既有契约
    (function loadPremium() {
      var base = (function () {
        var scripts = document.querySelectorAll("script[src]");
        for (var i = scripts.length - 1; i >= 0; i--) {
          var src = scripts[i].getAttribute("src") || "";
          if (src.indexOf("shell.js") >= 0) return src.replace(/shell\.js.*$/, "");
        }
        return "./assets/";
      })();
      function addScript(src, cb) {
        var s = document.createElement("script");
        s.src = base + src;
        s.onload = cb || function () {};
        s.onerror = function () { document.documentElement.classList.add("premium-ready"); };
        document.body.appendChild(s);
      }
      addScript("gsap.min.js", function () {
        addScript("premium.js", function () { if (window.premiumInit) window.premiumInit(); });
      });
      // 契约守卫: 纯增强, 不改任何比赛契约/class/内容
      addScript("contract_guard.js", function () { if (window.contractGuard) window.contractGuard.install(); });
    })();

    // 主题切换
    var tt = document.getElementById("theme-toggle");
    if (tt) {
      tt.innerHTML = (document.documentElement.getAttribute("data-theme") === "dark") ? icon("sun") : icon("moon");
      tt.addEventListener("click", function () {
        var next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", next);
        C.THEME = next;
        try { localStorage.setItem("v5-theme", next); } catch (e) {}
        tt.innerHTML = (next === "dark") ? icon("moon") : icon("sun");
        // 通知页面重绘 canvas 类图表 (CSS 变量在 canvas 中不可解析)
        window.dispatchEvent(new CustomEvent("themechange", { detail: { theme: next } }));
      });
    }

    // 移动端抽屉侧栏
    var sbEl = document.querySelector(".sidebar");
    var sbToggle = document.getElementById("sidebar-toggle");
    var sbBackdrop = document.getElementById("sidebar-backdrop");
    function closeDrawer() {
      if (sbEl) sbEl.classList.remove("open");
      if (sbToggle) sbToggle.setAttribute("aria-expanded", "false");
      if (sbBackdrop) sbBackdrop.style.display = "none";
    }
    if (sbToggle) sbToggle.addEventListener("click", function () {
      var open = sbEl.classList.toggle("open");
      sbToggle.setAttribute("aria-expanded", open ? "true" : "false");
      if (sbBackdrop) sbBackdrop.style.display = open ? "block" : "none";
    });
    if (sbBackdrop) sbBackdrop.addEventListener("click", closeDrawer);
    document.querySelectorAll(".nav-item").forEach(function (a) {
      a.addEventListener("click", function () { if (window.innerWidth <= 768) closeDrawer(); });
    });
    // 键盘可访问性: Escape 关闭抽屉并将焦点归还汉堡按钮 (WCAG 2.1.1 / 2.4.3)
    document.addEventListener("keydown", function (ev) {
      if ((ev.ctrlKey || ev.metaKey) && (ev.key === "k" || ev.key === "K")) {
        ev.preventDefault();
        toggleCmdk();
        return;
      }
      if (ev.key === "Escape" && sbEl && sbEl.classList.contains("open")) {
        closeDrawer();
        if (sbToggle) sbToggle.focus();
      }
    });

    // 用户菜单 (登出) — 跳转修正为 ../login.html (pages/ 下 ../ 指向 v8/ 根)
    var um = document.getElementById("user-menu");
    if (um) um.addEventListener("click", function () {
      if (confirm("确认登出?")) {
        A.logout();
        window.location.replace("../login.html");
      }
    });

    // ===== Windows 11 Fluent 窗口控制 (纯视觉增强, 不改动比赛契约) =====
    var appEl = document.querySelector(".app");
    var winMin = document.getElementById("win-min");
    var winMax = document.getElementById("win-max");
    var winClose = document.getElementById("win-close");
    if (winMin) winMin.addEventListener("click", function () {
      if (appEl) appEl.classList.toggle("win-compact");
    });
    if (winMax) winMax.addEventListener("click", function () {
      if (appEl) {
        var on = appEl.classList.toggle("win-max");
        winMax.setAttribute("aria-pressed", on ? "true" : "false");
      }
    });
    if (winClose) winClose.addEventListener("click", function () {
      if (appEl) {
        var collapsed = appEl.classList.toggle("win-collapsed");
        winClose.setAttribute("aria-pressed", collapsed ? "true" : "false");
        winClose.title = collapsed ? "展开窗口（不退出系统）" : "收起窗口（不退出系统）";
      }
    });
    // P1-1: 标题栏常驻命令面板入口 (红线安全: 仅调用既有 toggleCmdk)
    var winCmdk = document.getElementById("win-cmdk");
    if (winCmdk) winCmdk.addEventListener("click", function () { toggleCmdk(); });

    // 入场幕布 (page-curtain) 兜底移除: 即使 GSAP/JS 异常也保证内容可见 (防评委看到空白)
    setTimeout(function () {
      var c = document.getElementById("page-curtain");
      if (c) c.remove();
    }, 1500);
  }

  function toast(msg, kind) {
    var stack = document.getElementById("toast-stack") || (function () { var d = document.createElement("div"); d.className = "toast-stack"; d.id = "toast-stack"; document.body.appendChild(d); return d; })();
    var t = document.createElement("div");
    t.className = "toast toast-" + (kind || "info");
    t.setAttribute("role", "status");
    t.setAttribute("aria-live", "polite");
    t.textContent = msg;
    stack.appendChild(t);
    setTimeout(function () { t.style.opacity = "0"; t.style.transform = "translateX(20px)"; setTimeout(function () { t.remove(); }, 300); }, 3500);
  }

  function showLoading(show, text) {
    var id = "v5-loading";
    var layer = document.getElementById(id);
    if (show) {
      if (!layer) {
        layer = document.createElement("div");
        layer.id = id;
        layer.style.cssText = "position:fixed;inset:0;background:rgba(15,23,42,.5);display:flex;align-items:center;justify-content:center;z-index:9000;flex-direction:column;gap:12px;color:white;font-size:13px";
        layer.innerHTML = '<div class="spinner"></div><div>' + (text || "加载中...") + '</div>';
        document.body.appendChild(layer);
      } else {
        layer.style.display = "flex";
        var t = layer.querySelector("div:last-child");
        if (t) t.textContent = text || "加载中...";
      }
    } else if (layer) {
      layer.style.display = "none";
    }
  }

  // 全局 resize 分发 — 供 ECharts / D3 等 canvas/SVG 图表在窗口或侧栏尺寸变化时响应式重绘
  // (ECharts 不会自动响应容器尺寸变化, 必须显式调用实例 .resize())
  var resizeHandlers = [];
  var _resizeBound = false;
  function dispatchResize() {
    for (var i = 0; i < resizeHandlers.length; i++) {
      try { resizeHandlers[i](); } catch (e) {}
    }
  }
  function bindResize() {
    if (_resizeBound) return;
    _resizeBound = true;
    var t = null;
    window.addEventListener("resize", function () { clearTimeout(t); t = setTimeout(dispatchResize, 150); });
  }

  /* ============================================================
   * v8.3 全局命令面板 (Ctrl/Cmd+K) + 示例数据预填 — 纯叠加层 (不影响比赛实现)
   * ========================================================== */
  var CMDK_STYLE = "#cmdk{position:fixed;inset:0;z-index:9500;display:flex;align-items:flex-start;justify-content:center;padding-top:12vh}"
    + "#cmdk[hidden]{display:none}"
    + "#cmdk-backdrop{position:absolute;inset:0;background:rgba(15,23,42,.45)}"
    + "#cmdk-panel{position:relative;width:min(640px,92vw);background:var(--bg-elev);border:1px solid var(--border-strong);border-radius:var(--radius-lg);box-shadow:var(--shadow-lg);overflow:hidden}"
    + "#cmdk-ico{display:inline-flex;color:var(--fg-muted)}#cmdk-ico .icon{width:18px;height:18px}"
    + "#cmdk-input-wrap{display:flex;align-items:center;gap:10px;padding:14px 16px;border-bottom:1px solid var(--border)}"
    + "#cmdk-input{flex:1;border:none;outline:none;background:transparent;font-size:15px;color:var(--fg)}"
    + "#cmdk-input::placeholder{color:var(--fg-dim)}"
    + "#cmdk-list{max-height:52vh;overflow-y:auto;padding:6px}"
    + "#cmdk-list .opt{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:var(--radius);cursor:pointer;color:var(--fg)}"
    + "#cmdk-list .opt:hover{background:var(--bg-elev-2)}"
    + "#cmdk-list .opt.active{background:var(--accent);color:#fff}"
    + "#cmdk-list .opt .opt-label{font-size:14px}"
    + "#cmdk-list .opt .opt-hint{margin-left:auto;font-size:11px;opacity:.7}"
    + "#cmdk-list .opt.active .opt-hint{opacity:.9}"
    + "#cmdk-empty{padding:20px;text-align:center;color:var(--fg-dim);font-size:13px}"
    + "#cmdk-foot{padding:8px 14px;font-size:11px;color:var(--fg-dim);border-top:1px solid var(--border)}";
  function injectCmdkStyle() {
    if (document.getElementById("cmdk-style")) return;
    var s = document.createElement("style");
    s.id = "cmdk-style";
    s.textContent = CMDK_STYLE;
    document.head.appendChild(s);
  }

  var cmdkEl, cmdkInput, cmdkList, cmdkAll = [], cmdkFiltered = [], cmdkSel = 0, cmdkLastFocus = null;
  function buildCommands() {
    var cmds = [];
    NAV.forEach(function (n) {
      if (n.section !== undefined) return;
      cmds.push({ label: n.label, hint: "跳转页面", icon: n.icon, run: function () { window.location.href = n.href; } });
    });
    if (global.compCSV) {
      cmds.push({ label: "导出 标准6表 CSV（离线免依赖）", hint: "导出成果", icon: "download", run: function () {
        global.compCSV.exportAll6().then(function () { toast("已导出 6 张标准 CSV", "ok"); }).catch(function (e) { toast("导出失败: " + (e && e.message), "err"); });
      }});
    }
    cmds.push({ label: "演示走查（引导式）", hint: "演示", icon: "play", run: function () {
      try { sessionStorage.setItem("v8-walkthrough", "1"); } catch (e) {}
      window.location.href = "competition.html";
    }});
    cmds.push({ label: "示例数据预填（断点定位）", hint: "填充示例", icon: "bolt", run: function () {
      try { sessionStorage.setItem("v8-prefill", "1"); } catch (e) {}
      window.location.href = "breakpoint.html";
    }});
    cmds.push({ label: "切换明 / 暗主题", hint: "外观", icon: "sun", run: function () {
      var tt = document.getElementById("theme-toggle"); if (tt) tt.click();
    }});
    return cmds;
  }
  function renderCmdk() {
    cmdkAll = buildCommands();
    cmdkSel = 0;
    if (cmdkInput) cmdkInput.value = "";
    filterCmdk("");
    if (cmdkInput) cmdkInput.focus();
  }
  function filterCmdk(q) {
    if (!cmdkList) return;
    q = (q || "").trim().toLowerCase();
    cmdkFiltered = cmdkAll.filter(function (c) { return !q || (c.label + " " + c.hint).toLowerCase().indexOf(q) >= 0; });
    if (cmdkSel >= cmdkFiltered.length) cmdkSel = 0;
    if (!cmdkFiltered.length) { cmdkList.innerHTML = '<div id="cmdk-empty">无匹配命令</div>'; return; }
    cmdkList.innerHTML = cmdkFiltered.map(function (c, i) {
      return '<div class="opt' + (i === cmdkSel ? " active" : "") + '" role="option" aria-selected="' + (i === cmdkSel) + '" data-i="' + i + '">' +
        '<span class="opt-ico">' + icon(c.icon || "dot") + '</span>' +
        '<span class="opt-label">' + c.label + '</span>' +
        '<span class="opt-hint">' + c.hint + '</span></div>';
    }).join("");
    Array.prototype.forEach.call(cmdkList.querySelectorAll(".opt"), function (el) {
      var i = parseInt(el.dataset.i, 10);
      el.addEventListener("mousemove", function () { setCmdkSel(i); });
      el.addEventListener("click", function () { activateCmdk(cmdkFiltered[i]); });
    });
  }
  function setCmdkSel(i) {
    cmdkSel = i;
    var opts = cmdkList ? cmdkList.querySelectorAll(".opt") : [];
    for (var k = 0; k < opts.length; k++) {
      var on = k === i;
      opts[k].classList.toggle("active", on);
      opts[k].setAttribute("aria-selected", on ? "true" : "false");
    }
  }
  function scrollCmdkSel() {
    var opts = cmdkList ? cmdkList.querySelectorAll(".opt") : [];
    if (opts[cmdkSel]) opts[cmdkSel].scrollIntoView({ block: "nearest" });
  }
  function activateCmdk(cmd) {
    if (!cmd) return;
    closeCmdk();
    try { cmd.run(); } catch (e) { toast("命令执行失败: " + (e && e.message), "err"); }
  }
  function openCmdk() {
    if (!cmdkEl) return;
    cmdkLastFocus = document.activeElement;
    cmdkEl.hidden = false;
    renderCmdk();
  }
  function closeCmdk() {
    if (!cmdkEl) return;
    cmdkEl.hidden = true;
    if (cmdkLastFocus && cmdkLastFocus.focus) { try { cmdkLastFocus.focus(); } catch (e) {} }
  }
  function toggleCmdk() { if (cmdkEl && cmdkEl.hidden) openCmdk(); else closeCmdk(); }
  function initCommandPalette() {
    cmdkEl = document.getElementById("cmdk");
    cmdkInput = document.getElementById("cmdk-input");
    cmdkList = document.getElementById("cmdk-list");
    var ico = document.getElementById("cmdk-ico");
    if (ico) ico.innerHTML = icon("zoomIn");
    if (!cmdkEl || !cmdkInput || !cmdkList) return;
    cmdkInput.addEventListener("keydown", function (ev) {
      if (ev.key === "ArrowDown") { ev.preventDefault(); if (cmdkFiltered.length) { setCmdkSel((cmdkSel + 1) % cmdkFiltered.length); scrollCmdkSel(); } }
      else if (ev.key === "ArrowUp") { ev.preventDefault(); if (cmdkFiltered.length) { setCmdkSel((cmdkSel - 1 + cmdkFiltered.length) % cmdkFiltered.length); scrollCmdkSel(); } }
      else if (ev.key === "Enter") { ev.preventDefault(); activateCmdk(cmdkFiltered[cmdkSel]); }
      else if (ev.key === "Escape") { ev.preventDefault(); closeCmdk(); }
    });
    cmdkInput.addEventListener("input", function () { filterCmdk(cmdkInput.value); });
    var bd = document.getElementById("cmdk-backdrop");
    if (bd) bd.addEventListener("click", closeCmdk);
    var pfb = document.getElementById("prefill-btn");
    if (pfb) pfb.addEventListener("click", function () {
      try { sessionStorage.removeItem("v8-prefill"); } catch (e) {}
      window.dispatchEvent(new CustomEvent("appshell:prefill"));
      toast("已尝试在当前页填入示例数据", "info");
    });
  }

  global.appShell = {
    renderShell: renderShell,
    toast: toast,
    showLoading: showLoading,
    cssVar: cssVar,
    chartTheme: chartTheme,
    icon: icon,
    NAV: NAV,
    prefill: function () { window.dispatchEvent(new CustomEvent("appshell:prefill")); },
    bindResize: bindResize,
    addResizeHandler: function (fn) { if (typeof fn === "function") { resizeHandlers.push(fn); bindResize(); } }
  };
})(typeof window !== "undefined" ? window : globalThis);
