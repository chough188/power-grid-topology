# PowerGrid AI v8 — 设计 Token 规范 (UI Design Tokens)

> 配套 `assets/theme.css` 与 `assets/shell.js`。所有页面视觉值**只准走 Token**，禁止页面硬编码颜色/字号。
> 维护者：UI Designer（像素君） · 最近更新：2026-07-07

---

## 一、颜色 Token

### 明色主题（默认）
| Token | 值 | 用途 |
|-------|-----|------|
| `--bg-page` | `#f8fafc` | 页面底色 |
| `--bg-elev` | `#ffffff` | 卡片/浮层背景 |
| `--bg-elev-2` | `#f1f5f9` | 次级背景（hover/表头/副卡） |
| `--fg` | `#0f172a` | 主文字 |
| `--fg-muted` | `#475569` | 次要文字 |
| `--fg-dim` | `#64748b` | 弱化文字/占位（白底 ≥4.5:1） |
| `--border` | `#e2e8f0` | 描边/分割线 |
| `--border-strong` | `#cbd5e1` | 输入框描边/滚动条 |
| `--accent` | `#1d4ed8` | 品牌主色 / 链接 / 强调文字 |
| `--accent-soft` | `#dbeafe` | 主色浅底（选中/焦点环） |
| `--accent-fg` | `#ffffff` | 主色上的文字 |
| `--success` | `#16a34a` | 成功/健康（图表/状态点） |
| `--warn` | `#f59e0b` | 警告（图表/状态点） |
| `--err` | `#dc2626` | 错误/严重（图表/状态点） |
| `--info` | `#0891b2` | 信息（图表/状态点） |
| `--fg-err` | `#b91c1c` | 错误**文字**（白底 ≥5.9:1） |
| `--fg-warn` | `#b45309` | 警告**文字**（白底 ≥4.5:1） |
| `--fg-ok` | `#166534` | 成功**文字**（白底 ≥4.5:1） |
| `--fg-info` | `#0e7490` | 信息**文字**（白底 ≥4.5:1） |
| `--btn-primary-bg` | `#2563eb` | 主按钮底色 |
| `--btn-primary-fg` | `#ffffff` | 主按钮文字（白字 ≥5.17:1） |
| `--btn-primary-hover` | `#1d4ed8` | 主按钮 hover 底色 |

### 暗色主题（`[data-theme="dark"]`）
| Token | 值 |
|-------|-----|
| `--bg-page` | `#0b1220` |
| `--bg-elev` | `#111827` |
| `--bg-elev-2` | `#122028` |
| `--fg` | `#f8fafc` |
| `--fg-muted` | `#cbd5e1` |
| `--fg-dim` | `#94a3b8` |
| `--border` | `#1f2937` |
| `--border-strong` | `#334155` |
| `--accent` | `#3b82f6` |
| `--accent-soft` | `#0e1a30` |
| `--success` | `#22c55e` |
| `--warn` | `#fbbf24` |
| `--err` | `#f87171` |
| `--info` | `#22d3ee` |
| `--fg-err` | `#fca5a5` |
| `--fg-warn` | `#fbbf24` |
| `--fg-ok` | `#4ade80` |
| `--fg-info` | `#22d3ee` |
| `--btn-primary-bg` | `#2563eb` |
| `--btn-primary-fg` | `#ffffff` |
| `--btn-primary-hover` | `#1d4ed8` |

### 向后兼容别名（保留，防止老页面静默失效）
`--danger` → `--err`；`--bg-surface-2` → `--bg-elev-2`

> **对比度**：主/次文字对背景均满足 WCAG AA（正文 ≥ 4.5:1，大字 ≥ 3:1）。暗色主题已重新标定色值以保证可读。

### 对比度校验（已量化，2026-07-07）
用相对亮度公式对 **24 组真实文本场景**（明/暗各 24）全量计算，**结论：双主题 0 失败项，全部 ≥ 4.5:1**。
重点修正：
- 亮色 `--fg-dim` `#94a3b8` → `#64748b`（白底 2.56→4.76:1）
- 暗色 `--fg-dim` `#64748b` → `#94a3b8`（暗底 3.73→6.92:1）
- 亮色 `--accent` `#2563eb` → `#1d4ed8`（链接/选中 4.24→5.49:1）
- 暗色 `--accent-soft` `#1e3a8a` → `#0e1a30`（选中蓝字 2.82→4.42→达标）
- 新增 `--fg-err/warn/ok/info`：**隔离语义文字色**，避免用图表色（amber/green 在白底天生低对比）作为文字
- 新增 `--btn-primary-bg/fg/hover`：暗色主按钮白字原配 `--accent` 仅 3.68:1，现统一走专用 token（5.17:1）
- 暗色 `--bg-elev-2` 压暗至 `#122028`，链接落 hover 表面由 3.99→4.52:1

> 校验脚本：`_archive/_temp_scripts_frozen/contrast_check.py`（解析 theme.css token，枚举 FG/BG 组合，输出对比度与达标判定）。

---

## 二、字号比例 (Type Scale)
`--fs-xs:11px` · `--fs-sm:12px` · `--fs-base:13px` · `--fs-md:14px` · `--fs-lg:16px` · `--fs-xl:18px` · `--fs-2xl:24px`

## 三、间距比例 (Spacing, 4px 基准)
`--sp-1:4px` · `--sp-2:8px` · `--sp-3:12px` · `--sp-4:16px` · `--sp-5:20px` · `--sp-6:24px` · `--sp-8:32px`

## 四、圆角 / 阴影 / 过渡 / 焦点环
- 圆角：`--radius:10px` · `--radius-sm:6px` · `--radius-lg:14px` · `--radius-pill:999px`
- 阴影：`--shadow-sm` · `--shadow` · `--shadow-lg`（暗色下自动加深）
- 过渡：`--tr-fast:120ms` · `--tr:160ms` · `--tr-slow:240ms`
- 焦点环：`--ring: 0 0 0 3px var(--accent-soft)`（配合 `:focus-visible` 使用）

## 五、布局尺寸
`--sidebar-w:240px` · `--topbar-h:56px` · `--font-sans` · `--font-mono`

---

## 六、统一图标体系（线性 SVG）

所有图标走 `appShell.icon(name)`，返回内联 `<svg>`（`stroke="currentColor"`，随主题上色，支持暗色）。
**禁止再使用 emoji 作为界面图标**（跨平台渲染不一致、无法上色）。

可用名称：`dashboard` `trends` `reports` `topology` `highlights` `anomalies` `corrections` `feedback` `mobile` `settings` `back` `bolt` `menu` `sun` `moon` `dot`

用法示例：
```html
<!-- 静态页 (dashboard 已采用) -->
<span class="sec-ico"><svg class="icon" viewBox="0 0 24 24" ...>PATH</svg></span>

<!-- JS 中 -->
el.innerHTML = appShell.icon('anomalies') + ' 异常列表';
```
样式：`.icon{width:18px;height:18px}` · `.nav-icon` 已内置 flex 居中 · `.sec-ico` 用于区块标题前的 16px 强调图标。

---

## 七、canvas 类图表取色（关键硬规则）

ECharts / D3 渲染到 `<canvas>`，**无法解析 CSS 变量**。必须先用 `appShell.chartTheme()` 解析为真实 rgb/hex 再传入：

```js
var T = appShell.chartTheme();      // { fg, muted, accent, success, warn, err, info, grid, tooltipBg, ... }
chart.setOption({
  axisLabel: { color: T.muted },
  itemStyle: { color: T.accent },
  tooltip: { backgroundColor: T.tooltipBg, borderColor: T.tooltipBorder, textStyle: { color: T.tooltipText } },
});
```

主题切换时 `shell.js` 会派发 `window` 事件 `themechange`，页面监听并重绘：
```js
window.addEventListener("themechange", function () {
  var inst = echarts.getInstanceByDom(el); if (inst) inst.dispose();
  renderChart(LAST);   // 用最新数据重新 setOption（自动取新主题色）
});
```

---

## 八、组件速查
- 卡片：`.card`（hover 抬升）/ `.kpi`（左侧语义色条：`.ok` `.warn` `.err`）
- 按钮：`.btn` `.btn-primary` `.btn-danger` `.btn-success` `.btn-ghost` `.btn-sm`
- 徽章：`.badge` `.badge-ok` `.badge-warn` `.badge-err` `.badge-info`
- 表格：`.table`（斑马 hover）
- 表单：`.input` `.select`（`:focus` 主色环）
- 反馈：`.toast` `.toast-ok/err/warn/info`（带 `role=status aria-live=polite`）· `.modal` · `.empty`（统一空态，可加 `.icon-lg` 插画）· `.skeleton` 骨架屏 · `.spinner` 加载
- 状态点：`.status-dot` `.ok/.warn/.err`
- 拓扑检查器：`.topo-detail`（`.open` 显隐）· `.topo-detail-head/body` · `.td-row/td-key/td-val/td-section` · 节点选中 `.node.selected` + 相连高亮 `.link.connected` + 其余 `.node.dimmed`

---

## 九、可访问性基线（已落地）
- `:focus-visible` 全局焦点环（键盘可达）
- `@media (prefers-reduced-motion: reduce)` 降级动画
- 跳转链接 `.skip-link` → `#main-content`
- `<nav aria-label="主导航">` + 当前页 `aria-current="page"`
- 主题切换按钮 `aria-label`；44px 级点击区（导航 42px）
- 语义 HTML：`aside/header/main/nav` 地标齐全
- 拓扑图节点可键盘选中（`tabindex` + `role=button` + Enter/Space 触发 `selectNode`）

> **硬规则**：新增/修改界面时，颜色走 Token、图标走 `appShell.icon()`、canvas 取色走 `appShell.chartTheme()`、动画尊重 reduced-motion。任何裸 `#xxxx` 或 `var(--xxx)` 出现在 canvas 配置里都视为缺陷。
