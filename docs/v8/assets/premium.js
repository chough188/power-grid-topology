/* PowerGrid AI — PREMIUM POLISH (premium.js)
 * 纯增强层: KPI 数字跳动 / 磁性按钮 / 滚动入场 stagger
 * 不依赖任何比赛契约; 无 GSAP 或 prefers-reduced-motion 时自动跳过并保内容可见。
 */
(function (global) {
  var root = document.documentElement;

  function markReady() { root.classList.add("premium-ready"); }

  // 命令面板发现性: 浮动提示徽标 (复用既有 Ctrl/Cmd+K 唤起, 不改 shell.js)
  function injectCommandHint() {
    if (document.getElementById("cmdk-hint")) return;
    var badge = document.createElement("div");
    badge.id = "cmdk-hint";
    badge.className = "cmdk-hint";
    badge.setAttribute("role", "button");
    badge.setAttribute("tabindex", "0");
    badge.setAttribute("title", "打开命令面板 · 快速跳转任意模块");
    badge.innerHTML = '<span class="hint-dot"></span><kbd>\u2318K</kbd><span>快速导航</span>';
    function open() {
      var ev = new KeyboardEvent("keydown", { key: "k", code: "KeyK", ctrlKey: true, metaKey: true, bubbles: true });
      window.dispatchEvent(ev);
    }
    badge.addEventListener("click", open);
    badge.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
    });
    document.body.appendChild(badge);

    // 首次访问提示一次 (避免每次跳转都弹)
    try {
      if (global.appShell && appShell.toast && !sessionStorage.getItem("cmdk_hint_shown")) {
        sessionStorage.setItem("cmdk_hint_shown", "1");
        setTimeout(function () { appShell.toast("按 \u2318K / Ctrl+K 可快速跳转任意模块", "info"); }, 1400);
      }
    } catch (e) {}
  }

  function setupReveal() {
    // Fluent Reveal: 光标跟随高光 (纯 CSS 变量驱动, 无 GSAP 也工作)
    document.querySelectorAll(".card, .kpi, .task-card, .btn").forEach(function (el) {
      el.addEventListener("mousemove", function (e) {
        var r = el.getBoundingClientRect();
        var x = ((e.clientX - r.left) / r.width) * 100;
        var y = ((e.clientY - r.top) / r.height) * 100;
        el.style.setProperty("--reveal-x", x.toFixed(1) + "%");
        el.style.setProperty("--reveal-y", y.toFixed(1) + "%");
      });
    });
  }

  function autoCount() {
    // 自动识别 .kpi-value / .cov-num 中的数字并做跳动 (不依赖 data-count 属性)
    document.querySelectorAll(".kpi-value, .cov-num").forEach(function (el) {
      var raw = (el.textContent || "").replace(/[^0-9.\-]/g, "");
      var end = parseFloat(raw);
      if (isNaN(end)) return;
      var dec = (raw.split(".")[1] || "").length;
      var reduce = global.matchMedia && global.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (global.gsap && !reduce) {
        var obj = { v: 0 };
        global.gsap.to(obj, { v: end, duration: 1.4, ease: "power2.out", onUpdate: function () { el.textContent = obj.v.toFixed(dec); } });
      }
    });
  }

  function fadeCurtain(useGsap) {
    var c = document.getElementById("page-curtain");
    if (!c) return;
    if (useGsap && global.gsap) {
      global.gsap.to(c, { opacity: 0, duration: 0.5, delay: 0.35, ease: "power2.out", onComplete: function () { c.remove(); } });
    } else {
      c.style.transition = "opacity .4s ease";
      requestAnimationFrame(function () { c.style.opacity = "0"; setTimeout(function () { c.remove(); }, 450); });
    }
  }

  function init() {
    if (!document.body) { document.addEventListener("DOMContentLoaded", init); return; }
    injectCommandHint();

    // 纯 CSS 增强 (有无 GSAP 均生效)
    setupReveal();
    autoCount();

    var hasGsap = !!global.gsap;
    var reduce = global.matchMedia && global.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!hasGsap || reduce) {
      fadeCurtain(false);
      markReady();
      return;
    }

    var gsap = global.gsap;

    // 0) 入场幕布淡出
    fadeCurtain(true);

    // 1) 入场 stagger: 视口内元素淡入上移
    var selectors = [".main .card", ".main .kpi", ".main .task-card", ".main .page-section", ".main .metric"];
    selectors.forEach(function (sel) {
      var els = Array.prototype.slice.call(document.querySelectorAll(sel));
      if (!els.length) return;
      gsap.set(els, { opacity: 0, y: 16 });
      if (!("IntersectionObserver" in global)) {
        gsap.to(els, { opacity: 1, y: 0, duration: 0.7, ease: "power3.out", stagger: 0.05 });
        return;
      }
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (!e.isIntersecting) return;
          var i = els.indexOf(e.target);
          gsap.to(e.target, { opacity: 1, y: 0, duration: 0.7, ease: "power3.out", delay: Math.min(i, 8) * 0.06 });
          io.unobserve(e.target);
        });
      }, { threshold: 0.12 });
      els.forEach(function (el) { io.observe(el); });
    });

    // 1b) 侧栏导航项依次入场 (Fluent 风格)
    var navEls = Array.prototype.slice.call(document.querySelectorAll(".sidebar-nav .nav-item"));
    if (navEls.length) {
      gsap.set(navEls, { opacity: 0, x: -10 });
      gsap.to(navEls, { opacity: 1, x: 0, duration: 0.5, ease: "power2.out", stagger: 0.035, delay: 0.1 });
    }

    // 2) KPI 数字跳动 (data-count 显式属性)
    document.querySelectorAll("[data-count]").forEach(function (el) {
      var end = parseFloat(el.getAttribute("data-count")) || 0;
      var dec = parseInt(el.getAttribute("data-decimals") || "0", 10);
      var obj = { v: 0 };
      gsap.to(obj, {
        v: end, duration: 1.4, ease: "power2.out",
        onUpdate: function () { el.textContent = obj.v.toFixed(dec); }
      });
    });

    // 3) 磁性按钮 (仅精确指针设备)
    var coarse = global.matchMedia && global.matchMedia("(pointer: coarse)").matches;
    if (!coarse) {
      document.querySelectorAll(".btn-primary, .magnetic").forEach(function (btn) {
        btn.addEventListener("mousemove", function (e) {
          var r = btn.getBoundingClientRect();
          var x = (e.clientX - r.left - r.width / 2) * 0.18;
          var y = (e.clientY - r.top - r.height / 2) * 0.25;
          gsap.to(btn, { x: x, y: y, duration: 0.3, ease: "power2.out" });
        });
        btn.addEventListener("mouseleave", function () {
          gsap.to(btn, { x: 0, y: 0, duration: 0.4, ease: "elastic.out(1, 0.4)" });
        });
      });
    }

    markReady();
  }

  // 暴露给 shell.js 在注入后调用
  global.premiumInit = init;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    // 动态注入时文档已就绪, 立即初始化 (否则 init 永不触发)
    init();
  }
})(window);
