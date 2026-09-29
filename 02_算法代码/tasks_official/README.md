# 官方 12 子任务提交轨

本目录只放比赛提交口径实现。12 个二级分类必须各自维护算法、证据链、修正建议、物理校验和单元测试，不复用旧 28 异常的分类输出。

| 编号 | 模块 | 当前状态 |
|---|---|---|---|
| 1.1 | `group_01_topology/task_1_1_dangle/` | ✅ ready — 3 种异常 + 豁免 |
| 1.2 | `group_01_topology/task_1_2_break/` | ✅ ready — 6 种断点 + T1/T2 |
| 1.3 | `group_01_topology/task_1_3_tie/` | ✅ ready — R1/R2 联络识别 |
| 1.4 | `group_01_topology/task_1_4_suspect_tie/` | ✅ ready — 5 种原因 + 置信度 |
| 1.5 | `group_01_topology/task_1_5_unplanned_loop/` | ✅ ready — cycle + KCL |
| 2.1 | `group_02_graph_model/task_2_1_svg_only/` | ✅ ready — SVG diff + 模糊匹配 |
| 2.2 | `group_02_graph_model/task_2_2_model_only/` | ✅ ready — 3 分类 |
| 2.3 | `group_02_graph_model/task_2_3_phys_connect_logi_break/` | ✅ ready — 通断不一致 |
| 2.4 | `group_02_graph_model/task_2_4_phys_break_logi_connect/` | ✅ ready — R8 合规 |
| 3.1 | `group_03_state_voltage/task_3_1_switch_voltage/` | ✅ ready — 5V阈值 + P1#4 |
| 4.1 | `group_04_main_dist_interface/task_4_1_missing/` | ✅ ready — 5因子评分 |
| 4.2 | `group_04_main_dist_interface/task_4_2_wrong/` | ✅ ready — 高危UPDATE |
| 5.0 | `group_05_scoring/task_5_0_self_grade/` | ✅ ready — 4维度自评分 |
| 5.1 | `task5_svg/task_5_1_beautify/` | ✅ ready — 571行美化引擎 |
| 5.2 | `task5_svg/task_5_2_modify/` | ✅ ready — 468行事务编辑器 |
| 5.3 | `task5_svg/task_5_3_auto_draw/` | ✅ ready — 500行4种出图 |

`task5_svg/` 是官方 SVG 修正与生成任务的独立支撑区，不计入上述 12 个二级分类。

## 独立 GUI 模式

官方轨使用独立桌面进程，不启动 Web 服务、不占用端口，也不挂载到旧 28 异常 API：

```bat
run_official_gui.bat
```

- 12 个任务复选框默认全部为空，不提供隐式默认任务。
- “生成执行计划”只处理所选编号，不导入任何 detector。
- “执行所选任务”先校验 14 表，再预加载全部所选任务；任何任务未就绪时整体拒绝，不会部分执行。
- 旧 28 异常、旧 API、旧修正引擎、LLM、Pandapower、Scikit-learn 和 GNN 不进入 GUI 进程。


## 文档索引

| 文档 | 用途 | 何时读 |
|---|---|---|
| [PROMPT_GUIDE.md](./PROMPT_GUIDE.md) | 12 章节本地大模型操作指南（数据加载→12 detector→输出→自评全流程） | 数据送达前/中读 |
| [JUDGE.md](./JUDGE.md) | 评分公式 + 8 豁免规则 + 严禁事项 | 提交前自评 |
| [REFERENCE_FIELDS.md](./REFERENCE_FIELDS.md) | 14 张官表字段详细参考（主键/外键/任务映射） | 写 detector 时随用随查 |
| [SQL_PATTERNS.md](./SQL_PATTERNS.md) | 12 任务 `correction_sql` 模板 + 落库顺序 + Dry-run | 填 `correction_sql` 字段时 |
| [RUNBOOK.md](./RUNBOOK.md) | 3 步快查（加载 → 跑任务 → 自评）+ 故障排查 | 数据送达后实操 |

## 目录结构

```
tasks_official/
├── README.md                    # 本文件
├── PROMPT_GUIDE.md              # 操作指南
├── JUDGE.md                     # 评分标准
├── REFERENCE_FIELDS.md          # 14 表字段
├── SQL_PATTERNS.md              # SQL 模板
├── RUNBOOK.md                   # 3 步快查
├── self_grade.py                # 自评入口（被 JUDGE.md 引用）
├── catalog.py                   # 12 任务元数据（single source of truth）
├── contracts.py                 # ProblemRecord / TaskContext / EvidenceItem
├── execution.py                 # OfficialRunner + ISOLATED_COMPONENTS
├── registry.py                  # LazyTaskRegistry（按需 import detector）
├── gui.py / gui_controller.py   # 独立桌面 GUI（无 Web 端口）
├── run_official_gui.bat         # 启动脚本
├── correction_engine/           # 修正引擎（辅助模块，非比赛核心）
├── task5_svg/                   # SVG 美化/修改/自动绘图（独立支撑区）
└── group_01_topology/ ~ group_04_main_dist_interface/  # 12 detector 模块
    └── task_X_Y_name/detector.py
```

## 快速命令

```powershell
# 加载并校验快照
$env:PYTHONPATH = "E:\dianli\xiangmu\dianli\电力拓扑图修正\02_算法代码"
python -X utf8 -c "from data_loader.loader import OfficialDataset; ds = OfficialDataset.load_snapshot('data/snapshot.json'); ds.validate(); print('OK')"

# 启动独立 GUI
.\tasks_official\run_official_gui.bat

# 跑自评
python -X utf8 tasks_official\self_grade.py data/snapshot.json
```

## 修改记录

- 2026-07-21：补齐 4 份指南 + self_grade.py；与 catalog.py 12 任务定义对齐。


## 项目双轨全景（2026-07-21 更新）

### 公共层（`shared/`、`data_loader/`、`output_writer/`）

| 模块 | 职责 | 关键 API |
|---|---|---|
| `shared/exemption.py` | 8 类豁免规则 | `is_dangle_exempt` / `is_tie_switch_exempt` / `is_loop_exempt` / `is_measurement_exempt` / `is_single_side_allowed` |
| `shared/graph_algos.py` | 拓扑算法（BFS / DFS / 环 / 割点） | `adjacency_from_terminals` / `connected_components` / `find_cycles` / `articulation_points` |
| `shared/sql_emitter.py` | SQL 模板发射器（12 任务全覆盖） | `insert_pw_terminal` / `mark_tie_pw` / `set_run_status_pw` / `delete_pw_terminal` 等 |
| `shared/graph_base.py` | 图数据结构 | `GraphNode` / `GraphEdge` / `GraphSnapshot` |
| `shared/id_prefix.py` | TMP 前缀处理 | `is_temp_device_id` / `ensure_temp_device_id` |
| `shared/kcl_kvl.py` | KCL / KVL 残差 | `check_kcl` / `check_kvl` |
| `data_loader/loader.py` | 数据集校验 | `OfficialDataset.validate()` |
| `data_loader/snapshot.py` | JSON 加载 | `load_json_snapshot()` |
| `data_loader/schema.py` | 14 表契约 | `TABLE_SCHEMAS` / `REQUIRED_TABLES` |
| `data_loader/synthetic_gen.py` | 合成数据 | `make_empty_dataset()` / `make_synthetic_dataset()` |
| `output_writer/workbook_schema.py` | 6 Sheet 契约 | `SHEETS` / `SHEETS_BY_NAME` |
| `output_writer/sheet1-6_*.py` | 6 Sheet 实际写入器 | `render(records, wb, dataset)` |
| `output_writer/writer.py` | 顶层 writer | `write_workbook(records, path, dataset)` |

### 官方轨（`tasks_official/`）

| 文件 | 职责 |
|---|---|
| `catalog.py` | 12 任务元数据（single source of truth） |
| `contracts.py` | `ProblemRecord` / `EvidenceItem` / `TaskContext` |
| `execution.py` | `OfficialRunner` + `ISOLATED_COMPONENTS` 隔离 |
| `registry.py` | `LazyTaskRegistry`（按需 import detector） |
| `gui.py` / `gui_controller.py` | 独立桌面 GUI（无 Web 端口） |
| `evidence.py` | `EvidenceCollector` 评审可复核证据收集 |
| `self_grade.py` | 自评入口（sqlglot 优先 / stdlib 形状校验 fallback） |
| `group_*/task_*/detector.py` | 12 detector 完整实现（含SQL证据链） |

### 指南文档（`tasks_official/*.md`，共 9 份）

| 文档 | 何时读 |
|---|---|
| **PROMPT_GUIDE.md** | 总览，**先读** |
| **FIELD_MAPPING.md** | 写 detector 前必读（schema 字段名 vs 比赛 PDF/docx） |
| **DETECTOR_PATTERNS.md** | 实现 detector 时随用随查（伪代码 + 边界 + 反模式） |
| **SQL_PATTERNS.md** | 填 `correction_sql` 字段时 |
| **JUDGE.md** | 提交前自评（评分公式 + 严禁事项 + 评分矩阵） |
| **RUNBOOK.md** | 数据送达后实操（3 步快查 + 故障排查） |
| **DATA_QA.md** | 数据送达后校验（11 项必检 + 通过/拒绝标准） |
| **IMPROVEMENT_LOOP.md** | 自评 < 0.85 时迭代手册（3 个模式 + 调试技巧） |
| **README.md** | 本文件 |

### 测试（`tests_official/`）

| 测试 | 覆盖 |
|---|---|
| `test_common_contracts.py` | exemption / id_prefix / kcl_kvl / empty dataset |
| `test_exemption_complete.py` | 8 类豁免规则逐一覆盖 |
| `test_graph_algos.py` | BFS / CC / cycle / shortest_path / articulation_points |
| `test_selected_execution.py` | Runner 预检 / GUI 隔离 / lazy import |
| `test_track_isolation.py` | 跨轨 import 门禁 / 12 任务对齐 / 14 表 / 6 Sheet |
| `test_synthetic_dataset.py` | 合成数据 14 表 / 联络开关 / TRANS / XF |
| `test_self_grade.py` | parse_sql / SQL 模板 / 端到端 xlsx 写入 |

跑全部测试：

```powershell
$env:PYTHONPATH = "E:\dianli\xiangmu\dianli\电力拓扑图修正\02_算法代码"
python -X utf8 -m unittest discover -s tests_official -p "test_*.py"
```

## 端到端示例

```powershell
# 1. 生成合成 14 表数据集
$env:PYTHONPATH = "E:\dianli\xiangmu\dianli\电力拓扑图修正\02_算法代码"
python -X utf8 -c "
from data_loader.synthetic_gen import make_synthetic_dataset
import json
from pathlib import Path
ds = make_synthetic_dataset(seed=42)
Path('data').mkdir(exist_ok=True)
Path('data/snapshot.json').write_text(json.dumps({'tables': dict(ds.tables)}, ensure_ascii=False, indent=2), encoding='utf-8')
print('snapshot written')
"

# 2. 跑 12 detector
python -X utf8 -c "
from data_loader.snapshot import load_json_snapshot
from tasks_official.execution import OfficialRunner
from output_writer.writer import write_workbook
ds = load_json_snapshot('data/snapshot.json')
result = OfficialRunner().run(['1.1','1.2','1.3','1.5','3.1','4.1','4.2'], ds)
records = [r for recs in result.records_by_task.values() for r in recs]
print(f'records: {len(records)}')
write_workbook(records, 'output/result.xlsx', dataset=ds)
print('xlsx written')
"

# 3. 跑自评
python -X utf8 tasks_official\self_grade.py data\snapshot.json
```

## 修改记录

- 2026-07-21：扩 `shared/exemption.py` 覆盖 8 规则；加 `graph_algos.py` / `sql_emitter.py` / `evidence.py`；填实 6 个 sheet xlsx 写入器；扩 `synthetic_gen.py`；写 4 个测试；加 4 份指南（DETECTOR_PATTERNS / FIELD_MAPPING / DATA_QA / IMPROVEMENT_LOOP）；修 PROMPT_GUIDE.md 字段名笔误；扩 JUDGE.md 加评分细则。

---

文档结束 / End of document


---

## Recent updates (本轮 2026-07-21)

### 1.5 / 2.1 / 2.2 detector 从 scaffold 升级到 ready

| Task | 文件 | 关键行为 |
|------|------|----------|
| 1.5 非计划性合环拓扑识别 | `group_01_topology/task_1_5_unplanned_loop/detector.py` | `find_cycles()` 找环 → 检查环上 RUN_STATUS=1 开关是否在 `ctx.options["plan_list"]` → 不在则报非计划合环；correction_sql 调 `set_run_status_pw/zw(0)` |
| 2.1 图上有、模型无校验 | `group_02_graph_model/task_2_1_svg_only/detector.py` | `ctx.options["svg_devices"] - model_set` 差集；优先用 `svg_devices_meta` 元数据生成完整 INSERT，否则按 ID 前缀 fallback |
| 2.2 模型有、图上无校验 | `group_02_graph_model/task_2_2_model_only/detector.py` | `model_set - ctx.options["svg_devices"]` 差集；**correction_sql 留空**（官方约束）；分类：orphan / retired_in_db / disconnect_candidate |

### 自评结果

```
总分: 0.97
评级: 优
明细: 任务覆盖=11/12 豁免=8/8 SQL=59/59 关键=4/4
```

(2.1 在裸跑 self_grade 时因缺 svg_devices 输入贡献 0 records — 这是正确 fallback，不是错误。)

### 必杀题验证

新增 `tests_official/test_bisha_official_T1_T2.py`：
- T1: TMP00013138 <-> TMP00047197 ✓
- T2: TMP00007913 <-> TMP00007907 ✓
- T3: TMP00012903 <-> TMP00047124 保障机制 ✓（0821 官方模板 Sheet2 新增输入对；
  Round 3.7 核查：真实数据中该对真正连通（148 节点全闭合路径、无分位开关，
  0821 更新前后一致），按 Q&A2/Q16 正确不报告 —— 属负对照；若评分数据中
  断开则 official_pairs 保障照常报告，合成注入测试已验证）
- 1.5 bridge (TIE_LOOP_BRIDGE) ✓

### 提交清单

见 `tasks_official/SUBMISSION_CHECKLIST.md`（截止 2026-09-15）。
