# 配电网图模拓扑异常智能检测与自动修正系统

面向新型电力系统的配电网图模（图形 + 模型）拓扑质量治理系统。系统读取配电网图模快照数据，自动完成 **拓扑结构完整性检测、图模一致性校验、电气逻辑校验、主配网接口校验**，输出标准化问题清单与可执行修正 SQL，并支持 SVG 接线图的标准化美化、交互式增删设备与自动成图。

---

## 在线演示

前端为纯静态页面，零构建、零依赖，可直接在浏览器中打开：

**https://chough188.github.io/power-grid-topology/v8/index.html?demo=1**

其中 `demo=1` 为免登录演示态，去掉该参数则进入登录页。该地址由 `docs/` 目录发布，需在仓库 `Settings → Pages` 中将 Source 设为 `main` 分支的 `/docs` 目录后生效。

> `docs/` 是 `03_前端Demo/` 的镜像副本（Pages 只支持从仓库根目录或 `/docs` 发布）。前端有改动时，需同步复制一份到 `docs/`。

---

## 核心能力

### 官方 12 项二级任务

| 分类 | 任务 | 说明 |
|---|---|---|
| 1 拓扑结构完整性 | 1.1 | 设备拓扑悬空检测 |
| 1 拓扑结构完整性 | 1.2 | 拓扑连通性异常诊断与断点定位 |
| 1 拓扑结构完整性 | 1.3 | 联络开关自动识别与可视化梳理 |
| 1 拓扑结构完整性 | 1.4 | 疑似联络开关智能识别与复核研判 |
| 1 拓扑结构完整性 | 1.5 | 非计划性合环拓扑识别 |
| 2 图模一致性校验 | 2.1 | 图上有、模型无校验 |
| 2 图模一致性校验 | 2.2 | 模型有、图上无校验 |
| 2 图模一致性校验 | 2.3 | 图形物理连通、拓扑逻辑断开校验 |
| 2 图模一致性校验 | 2.4 | 图形物理断开、拓扑逻辑误连通校验 |
| 3 电气逻辑校验 | 3.1 | 开关-电压状态匹配校验 |
| 4 主配网接口校验 | 4.1 | 主配接口漏拼接校验 |
| 4 主配网接口校验 | 4.2 | 主配接口错拼接校验 |

### 质量自评分与 SVG 图形专项

| 任务 | 说明 |
|---|---|
| 5.0 | 模型修正质量自评分（4 维度） |
| 5.1 | SVG 图形标准化美化排版 |
| 5.2 | SVG 图形交互式增删设备 |
| 5.3 | 自动生成 SVG 接线图 |

---

## 目录结构

```text
power-grid-topology/
├── 02_算法代码/                    # 算法与后端主工程
│   ├── run.py                     # 一站式 CLI 入口（检测 + 修正 + 出表 + 自评）
│   ├── tasks_official/            # 官方 16 项任务实现（12 项校验 + 自评分 + SVG 专项）
│   │   ├── group_01_topology/     # 拓扑结构完整性
│   │   ├── group_02_graph_model/  # 图模一致性
│   │   ├── group_03_state_voltage/# 电气逻辑
│   │   ├── group_04_main_dist_interface/  # 主配网接口
│   │   ├── group_05_scoring/      # 质量自评分
│   │   ├── task5_svg/             # SVG 专项
│   │   └── catalog.py             # 任务清单（单一事实来源）
│   ├── data_loader/               # 图模快照加载与字段映射
│   ├── output_writer/             # 6 Sheet 标准 Excel 输出
│   ├── svg_engine/                # SVG 生成、美化与设备增删
│   ├── decision/                  # 修正决策与 SQL 生成
│   ├── root_cause/                # 根因分析
│   ├── knowledge_base/            # 配电网知识库与规则
│   ├── llm_assistant/             # 本地大模型辅助分析服务
│   ├── realtime/ observability/   # 实时处理与可观测性
│   ├── gui/                       # 桌面 / Web GUI 与自动化流水线
│   ├── data/                      # 图模快照数据（snapshot.json 等）
│   ├── tests_official/ tests_e2e/ # 官方轨单测与端到端测试
│   └── requirements.txt
├── 03_前端Demo/v8/                 # 前端演示（纯静态，零构建）
│   ├── index.html                 # 主界面
│   ├── pages/                     # 任务详情页
│   ├── assets/                    # 样式、脚本、图表库、图标
│   ├── shots/                     # 界面截图
│   └── 使用指南.md
├── docs/                          # GitHub Pages 发布目录（03_前端Demo 的镜像）
└── requirements.txt               # 全项目合并依赖
```

---

## 快速开始

### 环境要求

- Python 3.11 及以上
- Windows / Linux / macOS

### 安装依赖

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 一键运行官方流水线

在 `02_算法代码/` 目录下执行：

```bash
# 自动查找 data/snapshot.json 并运行全部任务
python run.py

# 指定输入快照与输出目录
python run.py data/snapshot_v4.json -o out/

# 仅运行部分任务
python run.py --tasks 1.1,1.2,1.3

# 列出全部任务及实现状态
python run.py --list

# 仅做模型修正质量自评分
python run.py --grade data/snapshot_v4.json
```

运行结束后在输出目录生成：

| 文件 | 说明 |
|---|---|
| `official_result.xlsx` | 6 Sheet 标准输出（问题清单、断点定位、联络开关、合环、图模一致性、质量评分） |
| `run_summary.json` | 运行明细摘要 |
| `run_manifest.json` | 运行清单 |
| `score.txt` | 自评分数 |

### 启动前端演示

前端为纯静态页面，无需构建，在 `03_前端Demo/` 目录下起静态服务器即可：

```bash
cd 03_前端Demo
python -m http.server 8000
```

浏览器打开 `http://localhost:8000/v8/index.html?demo=1`（`demo=1` 为免登录演示态）。

---

## 技术栈

| 层次 | 技术 |
|---|---|
| 图模建模 | pandapower、networkx、rdflib |
| 数值计算 | numpy、scipy、scikit-learn |
| 服务与接口 | FastAPI、uvicorn、pydantic |
| 报告与输出 | openpyxl、reportlab、matplotlib |
| 前端 | 原生 HTML/CSS/JavaScript、ECharts、D3.js、GSAP |
| 部署 | Docker、docker-compose |
| 可观测性 | prometheus-client |

---

## 说明

- `03_前端Demo/v8/` 中“AI 实验台”入口指向 `v8_lab/`。该实验台为不参与评分的附加功能，未随源码包提供，`v8_lab/index.html` 仅为一个占位说明页。
- `docs/` 为 `03_前端Demo/` 的镜像，用于 GitHub Pages 发布，除镜像内容外另含 `index.html`（跳转入口）与 `.nojekyll`。
- `02_算法代码/data/snapshot.json` 为完整图模快照数据，用于全量校验复现。
