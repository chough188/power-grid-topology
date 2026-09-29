/* PowerGrid AI Operations — v8 公用配置 (config.js)
 * 仅用 CDN (Tailwind v3 / D3 / ECharts), 0 npm / 0 node_modules
 * 唯一需迁移的设定: 修改 API_BASE 指向新后端
 */
(function (global) {
  global.CONFIG = {
    APP_NAME: "配电网图模拓扑智能识别与修正平台",
    APP_SUBTITLE: "CP-202606 · 泰豪软件",
    VERSION: "v8.1.0 比赛对齐",
    API_BASE: (function () {
      try {
        if (location.protocol === "file:") return "http://127.0.0.1:8001";
        return location.origin;
      } catch (e) { return "http://127.0.0.1:8001"; }
    })(),
    API_TIMEOUT_MS: 30000,
    API_RETRY: 1,
    THEME: (function () {
      try {
        var t = localStorage.getItem("v5-theme");
        if (t === "dark" || t === "light") return t;
        return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
      } catch (e) { return "light"; }
    })(),
    DEFAULT_TREND_DAYS: 14,
    DEFAULT_NETWORK: "LINE215",
    // 演示模式免登录 (Demo / Kiosk Mode):
    //   false = 默认关闭, 仍走正常登录拦截网关
    //   true  = 全站永久免登录 (kiosk); 也可不改此处, 用 URL 参数 index.html?demo=1 临时开启
    // 见 api.js getDemoMode()/isLoggedIn()
    DEMO_SKIP_LOGIN: false,
  };
})(typeof window !== "undefined" ? window : globalThis);
