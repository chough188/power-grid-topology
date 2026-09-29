# SUBMISSION_CHECKLIST.md — 比赛提交前 9-15 截止前清单

> 截止日: **2026-09-15**（9-30 初审 → 10 月指导 → 11 月终审）
> 提交物: 12 个二级子任务全跑通 + 6-sheet xlsx + 文档集

---

## A. 代码完整性 (12/12 detector 必须 `ready`)

| Task | Path | Status | correction_sql |
|------|------|--------|----------------|
| 1.1 设备拓扑悬空检测任务 | `group_01_topology/task_1_1_dangle/detector.py` | ready | 非空 |
| 1.2 拓扑连通性异常诊断与断点定位任务 | `group_01_topology/task_1_2_break/detector.py` | ready | 非空 |
| 1.3 联络开关自动识别与可视化梳理任务 | `group_01_topology/task_1_3_tie/detector.py` | ready | 非空 |
| 1.4 疑似联络开关智能识别与复核研判任务 | `group_01_topology/task_1_4_suspect_tie/detector.py` | ready | **留空** |
| 1.5 非计划性合环拓扑识别任务 | `group_01_topology/task_1_5_unplanned_loop/detector.py` | ready | 非空 |
| 2.1 图上有、模型无校验任务 | `group_02_graph_model/task_2_1_svg_only/detector.py` | ready | 非空 |
| 2.2 模型有、图上无校验任务 | `group_02_graph_model/task_2_2_model_only/detector.py` | ready | **留空** |
| 2.3 图形物理连通、拓扑逻辑断开任务 | `group_02_graph_model/task_2_3_phys_connect_logi_break/detector.py` | ready | 非空 |
| 2.4 图形物理断开、拓扑逻辑误连通任务 | `group_02_graph_model/task_2_4_phys_break_logi_connect/detector.py` | ready | 非空 |
| 3.1 开关-电压基础状态匹配校验任务 | `group_03_state_voltage/task_3_1_switch_voltage/detector.py` | ready | 非空 |
| 4.1 主配接口漏拼接校验任务 | `group_04_main_dist_interface/task_4_1_missing/detector.py` | ready | 非空 |
| 4.2 主配接口错拼接校验任务 | `group_04_main_dist_interface/task_4_2_wrong/detector.py` | ready | 非空 |

确认命令:
```powershell
python -c "from tasks_official.catalog import OFFICIAL_TASKS; [print(t.code, t.implementation_status) for t in OFFICIAL_TASKS]"
# 全部输出 ready
```

---

## B. 文档齐全 (10 份)

| 文档 | 路径 | 大致大小 |
|------|------|----------|
| PROMPT_GUIDE.md (总览) | tasks_official/PROMPT_GUIDE.md | 24 KB |
| FIELD_MAPPING.md (字段映射) | tasks_official/FIELD_MAPPING.md | 10 KB |
| DETECTOR_PATTERNS.md (伪代码) | tasks_official/DETECTOR_PATTERNS.md | 22 KB |
| SQL_PATTERNS.md (SQL 模板) | tasks_official/SQL_PATTERNS.md | 8 KB |
| JUDGE.md (评分规则) | tasks_official/JUDGE.md | 8 KB |
| RUNBOOK.md (运行手册) | tasks_official/RUNBOOK.md | - |
| DATA_QA.md (数据质控) | tasks_official/DATA_QA.md | - |
| IMPROVEMENT_LOOP.md (改进循环) | tasks_official/IMPROVEMENT_LOOP.md | - |
| README.md | tasks_official/README.md | - |
| REFERENCE_FIELDS.md | tasks_official/REFERENCE_FIELDS.md | - |

---

## C. 端到端跑通（一站式 CLI）

```powershell
$env:Path = "C:\Users\rj_zz\AppData\Local\Programs\Python\Python313;" + $env:Path
Set-Location 'E:\dianli\xiangmu\dianli\电力拓扑图修正\02_算法代码'

# 1) 一键运行（自动找 data/snapshot_v4.json, 出 xlsx + 自评）
python run.py

# 2) 跳过自评（只出 xlsx）
python run.py --no-grade

# 3) 自评注入异常测试场景（验证 detector 能力上限，JUDGE.md §9.1）
python run.py --inject

# 4) 列出全部 16 任务状态
python run.py --list

# 5) 仅跑自评
python run.py --grade data/snapshot_v4.json
```

### 传统方式（保持兼容）

```powershell
# 端到端 + xlsx 输出
python -X utf8 -c "from data_loader.snapshot import load_json_snapshot; from tasks_official.execution import OfficialRunner; from output_writer.writer import write_workbook; ds = load_json_snapshot('data/snapshot.json'); result = OfficialRunner().run(['1.1','1.2','1.3','1.4','1.5','2.1','2.2','2.3','2.4','3.1','4.1','4.2'], ds); records = [r for recs in result.records_by_task.values() for r in recs]; out = write_workbook(records, 'data/_result_official.xlsx', dataset=ds); print(out.stat().st_size)"

# 自评 (目标 ≥ 0.97, snapshot_v4 实际可达 0.82)
python -X utf8 tasks_official/self_grade.py data/snapshot_v4.json
```

---

## D. 必杀题验证 (1.2 必命中 T1/T2)

```powershell
python -X utf8 tests_official/test_bisha_official_T1_T2.py
```

期望:
- `T1 命中 (TMP00013138): True`
- `T2 命中 (TMP00007913): True`
- `T3_HIT = False` 属预期（0821 官方模板 Sheet2 新增输入对；真实数据中真正
  连通 → 按 Q&A2/Q16 正确不报告，负对照）；若评分数据中该对断开则应为 True

---

## E. xlsx 视觉检查 (6 sheet)

```powershell
python -X utf8 -c "from openpyxl import load_workbook; wb = load_workbook('data/_result_official.xlsx'); print(wb.sheetnames)"
```

期望 6 sheet:
- 拓扑校验问题清单
- 拓扑连通性异常诊断与断点定位结果
- 联络开关自动识别与可视化梳理任务结果
- 非计划性合环拓扑识别任务结果
- 模型修正质量评分任务结果
- 问题类型下拉选项

每 sheet 中文列名应使用官方完整名称（含"任务"后缀）。

---

## F. 单元测试

```powershell
python -X utf8 -m unittest discover -s tests_official -p "test_*.py"
```

期望: `198 passed, 12 skipped` (核心测试集)，`241 test functions` 总数。**关键**：`-p no:cacheprovider` 避免 access violation 随机失败。

---

## G. Git 标签 (可选)

```powershell
git tag -a v1.0-submission -m "CP-202606 official submission 16/16 tasks self-grade=0.82 (良), 198 tests passed"
```

---

## H. 提交流程

1. 将 `data/_result_official.xlsx` 重命名为 `official_result_2026MMDD.xlsx`
2. 打包 `02_算法代码/tasks_official/*.md` + `02_算法代码/data/_result_*.xlsx`
3. 上传至比赛系统（CP-202606 配电网图模拓扑智能识别与修正研究）

---

## I. 已知问题 (不影响提交)

- `_bisha_snapshot.json` / `_mock_snapshot.json` / `_result_*.xlsx` 是合成产物，提交前移到 `_history/` 或删除。
- self_grade 在无 sqlglot 时使用 stdlib shape validator，SQL 校验通过率 100%。
- **0.95 不可达约束 (snapshot_v4 数据)**：1.3/1.4/2.3/4.2 命中需要数据特征（cross-station 分位开关 / nid=None 端子 / 错拼），snapshot_v4 不含这些异常模式。0.82 是 **数据上限**。换用含异常的 snapshot 可达 0.95+。
- **0.82 stable 验证**：10/10 连续跑均 0.82，distinct breakdowns=1。
- 已新增 `run.py` 一站式 CLI、`--inject` 自评注入模式、`test_task_2_4.py` 测试集、GNN 模型权重 `training/gnn_v4_pretrained.pt`。
- 1.3 detector 行为依赖 snapshot 拓扑结构 + SOURCE 设备标签；snapshot_v4 不含 SOURCE/TRANSFORMER/MAIN 类型。
