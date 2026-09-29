# 算法代码双轨工作区

本目录按比赛提交口径拆成两个互不混用的板块：旧轨保留现有 28 异常内部 Demo，新轨只实现官方 12 个二级分类及其提交输出。

## 双轨边界

| 板块 | 目录 | 用途 | 口径 |
|---|---|---|---|
| 旧轨 | `_legacy_28anomaly/` | 内部 Demo、现有前端、历史 Benchmark | 28 异常 |
| 新轨 | `tasks_official/` | 比赛算法开发与最终提交 | 官方 12 个二级分类 |

强制依赖方向：

1. `tasks_official/` 不得导入 `_legacy_28anomaly/` 或旧轨顶层包。
2. `_legacy_28anomaly/` 不得导入 `tasks_official/`。
3. 公共能力只能放在 `shared/`、`data_loader/`、`output_writer/`，且公共层不得反向依赖任一业务轨。
4. 旧轨检测结果不得直接转换成官方 12 类作为提交结果；新轨必须按官方算法、证据链、修正原则和 Excel 契约独立实现。

## 目录结构

```text
02_算法代码/
├── _legacy_28anomaly/       # 旧轨：28 异常内部 Demo
├── tasks_official/          # 新轨：官方 12 个二级分类
├── shared/                  # 新轨公共物理/图模型工具
├── data_loader/             # 新轨 14 张 SQL 表输入边界
├── output_writer/           # 新轨 6 Sheet 输出边界
├── tests_official/          # 新轨测试，禁止放旧轨测试
├── llm_assistant/           # 旧 Demo 现有辅助服务，暂不迁改
└── output/                  # 现有模型与运行产物
```

## Python 环境

项目统一使用上一级项目根目录的 `.venv/`。旧 API、Benchmark 和开发启动器会自动优先选择该解释器：

```bat
cd ..
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -r 02_算法代码\requirements.txt pytest httpx
```

## 旧轨运行

旧前端继续连接原 FastAPI 端口，不修改前端代码：

```bat
_legacy_28anomaly\run_legacy.bat
```

旧 51 网络 Benchmark 文件不改，通过独立入口运行：

```bat
_legacy_28anomaly\run_benchmark.bat
```

## 新轨开发

- 任务清单：`tasks_official/catalog.py`
- 桌面入口：`tasks_official/run_official_gui.bat`
- 输入表契约：`data_loader/schema.py`
- Excel 契约：`output_writer/workbook_schema.py`
- 结构隔离门禁：`tests_official/test_track_isolation.py`
- 官方依据：`../比赛要求/00_官方要求权威整合清单.md`
- 算法依据：`../比赛要求/00_12个二级分类算法伪代码.md`
- 测试依据：`../比赛要求/00_12子任务单元测试清单.md`

当前新轨是独立开发骨架，不代表 12 个算法已经完成。每个子任务完成后，必须同时补充对应实现、官方测试、证据链和 Sheet 输出映射。
