/* v8 API 客户端 (沿用 v5 结构; 原头部注释因 GBK/UTF-8 转码损坏, Round 3.8 重写)
 * - apiFetch(path, options): 统一 URL 拼接 + GET/POST + 超时/重试/错误归一化
 * - authHeader(): Bearer token 自动注入 (token 存 sessionStorage "v5-token")
 * - 端点助手: health / networks / topology / detect / correct / trend /
 *   handoverSummary / highlights / agentReport / feedback* / dashboardSummary
 * - getDemoMode / ensureDemoIdentity: 后端不可达时演示数据降级
 */
(function (global) {
  var C = global.CONFIG;
  if (!C) { console.error("CONFIG not loaded"); return; }

  function ApiError(status, message, data) {
    var e = new Error(message); e.name = "ApiError";
    e.status = status; e.data = data; return e;
  }

  function authHeader() {
    var t;
    try { t = sessionStorage.getItem("v5-token"); } catch (e) {}
    return t ? { "Authorization": "Bearer " + t } : {};
  }

  function apiUrl(path) {
    var base = (C.API_BASE || "").replace(/\/+$/, "");
    return base + (path.startsWith("/") ? path : "/" + path);
  }

  async function apiFetch(path, options) {
    options = options || {};
    var method = (options.method || "GET").toUpperCase();
    var retries = options.retries !== undefined ? options.retries :
                  (method === "GET" ? C.API_RETRY : 0);
    var timeoutMs = options.timeoutMs !== undefined ? options.timeoutMs : C.API_TIMEOUT_MS;
    var lastErr;
    for (var attempt = 0; attempt <= retries; attempt++) {
      var ctrl = new AbortController();
      var timer = setTimeout(function () { ctrl.abort(); }, timeoutMs);
      try {
        var r = await fetch(apiUrl(path), {
          method: method,
          signal: ctrl.signal,
          headers: Object.assign(
            { "Content-Type": "application/json", "X-Client": "v5-web" },
            authHeader(),
            options.headers || {}
          ),
          body: options.body ? (typeof options.body === "string" ? options.body : JSON.stringify(options.body)) : undefined,
        });
        clearTimeout(timer);
        var data = null;
        var ct = r.headers.get("content-type") || "";
        if (ct.indexOf("application/json") >= 0) {
          try { data = await r.json(); } catch (e) { data = null; }
        } else if (ct.indexOf("text/") === 0) {
          try { data = await r.text(); } catch (e) { data = null; }
        } else if (ct.indexOf("application/octet-stream") >= 0 || ct.indexOf("application/pdf") >= 0) {
          data = await r.blob();
        }
        return { ok: r.ok, status: r.status, data: data, headers: r.headers, url: apiUrl(path) };
      } catch (e) {
        clearTimeout(timer);
        lastErr = e;
        if (e.name === "AbortError") {
          lastErr = new ApiError(0, "Request timeout after " + timeoutMs + "ms");
        }
        if (attempt >= retries) break;
        await new Promise(function (res) { setTimeout(res, 500 * (attempt + 1)); });
      }
    }
    throw lastErr || new ApiError(0, "Unknown network error");
  }

  // ===== 演示模式免登录开关 (Demo / Kiosk Mode) =====
  // 触发方式 (任选其一):
  //   1) URL 查询参数 ?demo=1 或 ?kiosk=1 —— 推荐答辩演示: 打开 index.html?demo=1
  //   2) 在 config.js 设 CONFIG.DEMO_SKIP_LOGIN = true —— 永久 kiosk 免登录
  // 命中后写入 sessionStorage('v8-demo'), 使页面间跳转保持免登录
  // (重定向会丢失 URL 参数, 故以 sessionStorage 为准, 而非每次读 location.search)
  function getDemoMode() {
    try {
      if (sessionStorage.getItem("v8-demo") === "1") return true;
      var q = new URLSearchParams((global.location && global.location.search) || "");
      var d = (q.get("demo") || q.get("kiosk") || "").toLowerCase();
      if (d === "1" || d === "true" || d === "yes") {
        sessionStorage.setItem("v8-demo", "1");
        return true;
      }
    } catch (e) {}
    try { if (C && C.DEMO_SKIP_LOGIN === true) return true; } catch (e) {}
    return false;
  }
  // 演示模式: 确保存在一个演示身份, 使全站按"已登录"呈现 (userBlock/getUser/登出菜单同步生效)
  function ensureDemoIdentity() {
    try {
      if (!sessionStorage.getItem("v5-token")) {
        sessionStorage.setItem("v5-token", "demo:kiosk");
        sessionStorage.setItem("v5-user", JSON.stringify({ tenant: "demo", user: "演示模式", _demo: true }));
      }
    } catch (e) {}
  }

  var api = {
    apiUrl: apiUrl,
    apiFetch: apiFetch,
    ApiError: ApiError,
    health: function () { return apiFetch("/api/v1/health"); },
    networks: function () { return apiFetch("/api/v1/networks"); },
    topology: function (name) { return apiFetch("/api/v1/network/" + encodeURIComponent(name) + "/topology"); },
    detect: function (payload) { return apiFetch("/api/v9/detect", { method: "POST", body: payload, timeoutMs: 60000 }); },
    correct: function (payload) { return apiFetch("/api/v1/correct", { method: "POST", body: payload, timeoutMs: 60000 }); },
    trend: function (element_id, metric, days) {
      var q = new URLSearchParams({ metric: metric || "all", days: days || C.DEFAULT_TREND_DAYS });
      return apiFetch("/api/v1/trend/" + encodeURIComponent(element_id) + "?" + q.toString());
    },
    handoverSummary: function () { return apiFetch("/api/v1/handover/summary"); },
    topologyHighlights: function (network) {
      return apiFetch("/api/v1/topology/highlights?network=" + encodeURIComponent(network || C.DEFAULT_NETWORK));
    },
    reportPdf: function (params) {
      var q = new URLSearchParams(params || {});
      return apiFetch("/api/v1/agent/report.pdf?" + q.toString(), { timeoutMs: 60000 });
    },
    feedbackStats: function () { return apiFetch("/api/v1/feedback/stats"); },
    feedbackFP: function (payload) { return apiFetch("/api/v1/feedback/fp", { method: "POST", body: payload }); },
    feedbackFN: function (payload) { return apiFetch("/api/v1/feedback/fn", { method: "POST", body: payload }); },
    listFP: function (limit) { return apiFetch("/api/v1/feedback/fp?limit=" + (limit || 20)); },
    listFN: function (limit) { return apiFetch("/api/v1/feedback/fn?limit=" + (limit || 20)); },
    dashboardSummary: function (network) {
      return apiFetch("/api/v1/dashboard/summary?network=" + encodeURIComponent(network || C.DEFAULT_NETWORK));
    },
    login: function (tenant, user, password) {
      // Demo auth: token = "tenant:user"; 瀵嗙爜铏氬亣, 瀹炴垯鎻愪氦 -> 浣忚壊 panel
      var token = tenant + ":" + user;
      return Promise.resolve({ ok: true, status: 200, data: { token: token, tenant: tenant, user: user } });
    },
    logout: function () {
      try { sessionStorage.removeItem("v5-token"); sessionStorage.removeItem("v5-user"); } catch (e) {}
    },
    isLoggedIn: function () {
      try {
        if (getDemoMode()) { ensureDemoIdentity(); return true; }
        return !!sessionStorage.getItem("v5-token");
      } catch (e) { return false; }
    },
    isDemoMode: function () { return getDemoMode(); },
  };
  global.api = api;
})(typeof window !== "undefined" ? window : globalThis);
