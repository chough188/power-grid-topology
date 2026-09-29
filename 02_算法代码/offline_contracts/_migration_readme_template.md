# 迁移清单与使用说明（运行时版本）

> 适用于 `topology_migration_v0.zip` 解压后的项目根目录。
> 该迁移包不携带任何真实比赛数据、SQLite 中间库或 API 凭据。

## 1. 打包内容

| 路径 | 说明 |
|---|---|
| `AGENTS.md` | 全局约束、安全规则、Codex CLI 工具调用铁律 |
| `.codex_state.json` | self-defense 状态，默认 `state=idle phase=需求冻结 + 数据接入（W1）` |
| `docs/` | 官方资料包解读、技术蓝图、离线接续方案、本地模型入口 |
| `02_算法代码/offline_contracts/` | 离线契约包 |
| `02_算法代码/tests/` | 离线契约单元测试 |
| `_codex_self_defense/` | bootstrap.py、sync_agents_header.py 与 codex wrapper |
| `scripts/` | `codex_safe_exec.ps1`、`detect_2013_recovery.ps1` |
| `比赛要求/` | 5 份官方原始资料 |
| `tools/migration_verify.py` | 新机器一键自检脚本 |
| `manifest.json` | 迁移清单与安全状态 |
| `README.md` | 解压后使用说明 |

## 2. 已剔除内容

- 真实比赛数据集、参考论文、本地权威数据库
- `_archive/`、`output/_codex_dumps/`、`local_data/`
- 历次临时脚本和大型生成 JSON/SQLite
- 外部插件目录（`.codex/`、`.local_dev_setup/`、`.workbuddy/`、`.skills/dianli/` 大型参考库）

## 3. 在新电脑上落地

```text
pwsh -NoProfile -File scripts/detect_2013_recovery.ps1 -SelfTest
C:\\Users\\lenovo\\AppData\\Local\\Programs\\Python\\Python311\\python.exe tools/migration_verify.py --project-root .
C:\\Users\\lenovo\\AppData\\Local\\Programs\\Python\\Python311\\python.exe -m offline_contracts.context_check --project-root .
C:\\Users\\lenovo\\AppData\\Local\\Programs\\Python\\Python311\\python.exe -m offline_contracts.bootstrap --output-dir ./output_bootstrap
```

## 4. 安全边界

- `manifest.json` 中 `real_competition_data_included=false`、`sql_execution_enabled=false`、`database_write_enabled=false`。
- 真实比赛数据如需引入，应放入 `local_data/raw/`，并先运行 `context_check` 校验。
- 生成物（SQLite 桥、合成表、报告）放 `dist/` 之外。

## 5. 下一步

- 通过 `migration_verify.py` 后即可进入 `docs/本地模型启动提示词.md` 所述的本地模型流程。
- 若自检 `FAIL`，检查缺失文件并对照 `manifest.json`。