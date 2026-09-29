# CP-202606 官方轨 RUNBOOK（一站式 CLI）

## 最简用法（推荐）

```powershell
cd E:\dianli\xiangmu\dianli\电力拓扑图修正\02_算法代码
python run.py
```

自动完成：定位快照 → 运行 12 任务 → 出 xlsx → 自评打分 → 写摘要。

## 常用命令

```powershell
# 指定输入
python run.py data/snapshot_v4.json

# 指定输出目录
python run.py data/snapshot_v4.json -o my_out/

# 只跑部分任务
python run.py --tasks 1.1,1.2,1.3

# 跳过自评（只产出 xlsx）
python run.py --no-grade

# 列出全部 16 任务状态
python run.py --list

# 只跑自评
python run.py --grade data/snapshot_v4.json
```

## 输出位置

默认写到 `_dianli_output/<snapshot名>_<时间戳>/`：
- `official_result.xlsx` — 6-sheet 标准输出
- `run_summary.json` — JSON 摘要
- `run_manifest.json` — 运行清单
- `score.txt` — 自评分数

## 步骤 0 — 前置条件

- 工作目录：`02_算法代码/`
- Python：3.13+
- 可选依赖：`sqlglot`（装了用真解析，没装自动降级到形状校验 — `self_grade.py` 内置）
- 14 表快照：`data/snapshot.json`（键名严格匹配 `JBS_*`）
- 隔离：不启动旧 API / Pandapower / LLM / GNN

## 故障排查

### 找不到 snapshot

`run.py` 会按以下顺序自动找：
1. `data/snapshot_v4.json`
2. `data/snapshot.json`
3. `data/_bisha_snapshot.json`
4. `data/*.json` 中文件名含 `snapshot` 的第一个

如果没有，把快照放到 `data/snapshot.json`，或显式指定：`python run.py <path>`。

### ModuleNotFoundError: tasks_official.group_xx.task_yy.detector

确认每层包目录都有 `__init__.py`。如果新加 detector，必须同步在 `group_xx/__init__.py` 加 import。

### TaskUnavailableError: ... is scaffold

`catalog.py` 中该任务的 `implementation_status` 字段不是 `ready`。本批 16 个全为 `ready`，如某条改回，runner 会拒绝执行。

### 输出 xlsx 空

- detector 返回 `()` 而非生成 `ProblemRecord`：任务覆盖扣分。
- records 长度 0 但数据集中本应有异常：检查 detector 逻辑。

### sqlglot 缺失警告

`self_grade.py` 自动降级到形状校验。功能不影响，仅精度略低。

### 修改 detector 后没生效

`__pycache__` 缓存陈旧。运行 `python run.py` 前先：

```powershell
Remove-Item tasks_official\__pycache__ -Recurse -Force -ErrorAction SilentlyContinue
```

### self_grade 返回 1

总分 < 0.60。看明细里哪一项扣分最多。

## 关键约束

- **不导入** 28 异常目录（`ISOLATED_COMPONENTS` 隔离）。
- **不引入** LLM / Pandapower / GNN / 旧 FastAPI。
- **selected_only 模式**：选几个跑几个，不强制全跑。
- **GUI 不启动 Web 端口**，不挂载到旧 API。

## 进阶用法

### 直接调用 Python API

```python
from data_loader.snapshot import load_json_snapshot
from tasks_official.execution import OfficialRunner
from tasks_official.registry import LazyTaskRegistry

ds = load_json_snapshot("data/snapshot_v4.json")
runner = OfficialRunner(LazyTaskRegistry.with_module_resolver())
result = runner.run(["1.1", "1.2", "1.3", "1.4", "1.5",
                     "2.1", "2.2", "2.3", "2.4",
                     "3.1", "4.1", "4.2"], ds)
print(f"total: {result.total_records}")
for code, recs in result.records_by_task.items():
    print(f"  {code}: {len(recs)}")
```

### 独立 GUI

```powershell
.\tasks_official\run_official_gui.bat
```

GUI 操作流程：
1. 复选框勾选任务
2. 生成执行计划
3. 执行任务
4. 导出 xlsx

详细 contract 见 `contracts.py`（`ProblemRecord` / `EvidenceItem` / `TaskContext`）。

---

文档结束