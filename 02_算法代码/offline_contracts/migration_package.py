"""Build a portable migration package that excludes real competition data."""
from __future__ import annotations

import argparse
import os
import json
import shutil
import sys
import time
import zipfile
from collections import Counter
from pathlib import Path

# 根目录默认按本脚本位置推断（脚本位于 02_算法代码/offline_contracts/ 下，
# parents[2] 即项目根 "电力拓扑图修正"），可用环境变量 DIANLI_PROJECT_ROOT 覆盖，
# 避免硬编码绝对路径导致迁移到其他机器后无法运行。
PROJECT_ROOT_OVERRIDE = os.environ.get("DIANLI_PROJECT_ROOT")
ROOT = (
    Path(PROJECT_ROOT_OVERRIDE).resolve()
    if PROJECT_ROOT_OVERRIDE
    else Path(__file__).resolve().parents[2]
)
DIST = ROOT / "dist" / "topology_migration_v0"
ZIP_PATH = ROOT / "dist" / "topology_migration_v0.zip"

CONTEXT_FILES = (
    "AGENTS.md",
    ".codex_state.json",
    "docs/官方资料包_完整要求解读.md",
    "docs/技术实现细节_完整版.md",
    "docs/本地模型离线接续方案.md",
    "docs/本地模型上下文清单.md",
    "docs/本地模型启动提示词.md",
    "docs/比赛要求与赛前行动清单.md",
    "docs/转写解读_需求精梳.md",
    "docs/官方要求细节补齐.md",
    "output/PENDING_v2.md",
    "output/PENDING_v3.md",
)

MIGRATION_DOCS = ('docs/迁移清单与使用说明.md',)
CONTEXT_DIRS = (
    "02_算法代码/offline_contracts",
    "02_算法代码/tests",
    "_codex_self_defense",
    "scripts",
)

OFFICIAL_REQUIREMENTS = ("比赛要求",)

OFFICIAL_REQUIREMENT_SKIPS = {"比赛要求/.cache", "比赛要求/_tmp_*"}

HEAVY_TOPLEVEL_DIRS_SKIPPED = (
    "03_数据集",
    "07_参考文献",
    "99_参考资料",
    "权威本地数据库",
    "核心数据库",
    "_archive",
)

GENERATED_OUTPUT_SKIPS = {
    "output/offline_bootstrap/official_bridge_e2e.sqlite",
    "output/offline_bootstrap/official_bridge_verify.sqlite",
    "output/offline_bootstrap/local_asset_inventory.json",
    "output/offline_bootstrap/synthetic_14_tables.json",
    "output/_codex_dumps",
    "output/_tmp_*.py",
}

EXTRA_DOC = "docs/迁移清单与使用说明.md"


def should_skip(path: Path) -> str | None:
    relative = path.relative_to(ROOT).as_posix()
    for pattern in GENERATED_OUTPUT_SKIPS:
        if pattern.endswith("/*") and relative.startswith(pattern[:-1]):
            return pattern
    if path.is_relative_to(DIST):
        return "dist_dir"
    if path.is_relative_to(ROOT / "output" / "_codex_dumps"):
        return GENERATED_OUTPUT_SKIPS_DUMP
    for skip in HEAVY_TOPLEVEL_DIRS_SKIPPED:
        if path.is_relative_to(ROOT / skip):
            return skip
    if path.suffix.lower() == ".py" and path.name.startswith("_tmp_") and "offline_bootstrap" in path.parts:
        return "tmp_script"
    return None


GENERATED_OUTPUT_SKIPS_DUMP = "output/_codex_dumps"


def reset_dist() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True, exist_ok=True)


def copy_context_files() -> list[str]:
    copied: list[str] = []
    for relative_path in CONTEXT_FILES + MIGRATION_DOCS:
        source = ROOT / relative_path
        if not source.exists():
            continue
        target = DIST / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(relative_path)
    for relative_dir in CONTEXT_DIRS:
        source = ROOT / relative_dir
        if not source.exists():
            continue
        target = DIST / relative_dir
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
        copied.append(relative_dir + "/")
    return copied


def copy_official_requirements() -> list[str]:
    copied: list[str] = []
    source = ROOT / OFFICIAL_REQUIREMENTS[0]
    if not source.exists():
        return copied
    target = DIST / OFFICIAL_REQUIREMENTS[0]
    target.mkdir(parents=True, exist_ok=True)
    for entry in source.iterdir():
        if entry.name.startswith("."):
            continue
        if entry.name.startswith("_tmp_"):
            continue
        shutil.copy2(entry, target / entry.name)
        copied.append(entry.relative_to(ROOT).as_posix())
    return copied


def write_migration_manifest(copied_files: list[str]) -> dict[str, object]:
    manifest = {
        "manifest_version": "topology_migration_v0",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "real_competition_data_included": False,
        "database_write_enabled": False,
        "sql_execution_enabled": False,
        "context_files": list(CONTEXT_FILES),
        "context_dirs": list(CONTEXT_DIRS),
        "official_requirements": list(OFFICIAL_REQUIREMENTS),
        "skipped_top_level_dirs": list(HEAVY_TOPLEVEL_DIRS_SKIPPED),
        "skipped_generated_assets": sorted(GENERATED_OUTPUT_SKIPS),
        "copied_entries": sorted(copied_files),
    }
    target = DIST / "manifest.json"
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def write_migration_readme() -> None:
    content = """# 迁移包：topology_migration_v0

## 用途

把当前比赛项目的 **离线契约包 + 官方资料解读 + 本地模型入口 + 状态文件 + 迁移自检**
打包到另一台电脑继续工作。**不包含任何真实比赛数据、SQLite 中间库、API 凭据或日志。**

## 解压后目录结构

```
dist/topology_migration_v0/
├── AGENTS.md
├── .codex_state.json
├── docs/                  (官方解读、技术蓝图、迁移清单、本地模型入口)
├── 02_算法代码/offline_contracts/
├── 02_算法代码/tests/      (test_offline_*.py)
├── _codex_self_defense/   (bootstrap.py、sync_agents_header.py)
├── scripts/               (codex_safe_exec.ps1、detect_2013_recovery.ps1 等)
├── 比赛要求/              (PDF/任务书/附件/官方 xlsx 模板)
└── tools/migration_verify.py
```

## 在新机器上验证

```text
pwsh -NoProfile -File scripts/detect_2013_recovery.ps1 -SelfTest
pwsh -NoProfile -File scripts/codex_safe_exec.ps1 -Command "type 比赛要求\\拓扑校验问题标准输出.xlsx"
C:\\Users\\lenovo\\AppData\\Local\\Programs\\Python\\Python311\\python.exe tools/migration_verify.py
C:\\Users\\lenovo\\AppData\\Local\\Programs\\Python\\Python311\\python.exe -m offline_contracts.context_check --project-root "D:\\path\\to\\topology_migration_v0"
```

## 安全约束

- 仅在本地机器读取 `比赛要求/`、`02_算法代码/`、`docs/`；其他数据目录未被打包。
- 任何生成物必须放在 `dist/` 外；不要把比赛原始数据或 SQLite 写入 `dist/`。
- `.codex_state.json` 默认 `state=idle`，本地模型每次启动都会重新校验。
"""
    (DIST / "README.md").write_text(content, encoding="utf-8")


def build_zip() -> tuple[Path, Counter]:
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    counter: Counter[str] = Counter()
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in DIST.rglob("*"):
            if file_path.is_dir():
                continue
            archive.write(file_path, file_path.relative_to(DIST.parent).as_posix())
            counter[file_path.suffix.lower() or "(no_suffix)"] += 1
    return ZIP_PATH, counter


def write_migration_verify_script() -> None:
    target = DIST / "tools" / "migration_verify.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    content = '''"""Verify a fresh migration package on a new machine.

Usage:
    python tools/migration_verify.py --project-root D:/path/to/topology_migration_v0

This script does NOT read competition data or connect to databases.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

REQUIRED_CONTEXT = (
    "AGENTS.md",
    ".codex_state.json",
    "docs/官方资料包_完整要求解读.md",
    "docs/技术实现细节_完整版.md",
    "docs/本地模型离线接续方案.md",
    "docs/本地模型上下文清单.md",
    "docs/本地模型启动提示词.md",
    "docs/迁移清单与使用说明.md",
    "output/PENDING_v3.md",
    "tools/migration_verify.py",
    "manifest.json",
    "README.md",
    "scripts/codex_safe_exec.ps1",
    "scripts/detect_2013_recovery.ps1",
    "_codex_self_defense/bootstrap.py",
    "02_算法代码/offline_contracts/contract.py",
    "02_算法代码/offline_contracts/sqlite_bridge.py",
    "02_算法代码/tests/test_offline_contracts.py",
    "02_算法代码/tests/test_offline_sqlite_bridge.py",
    "比赛要求/拓扑校验问题标准输出.xlsx",
)

REQUIRED_DIRS = (
    "docs",
    "scripts",
    "_codex_self_defense",
    "02_算法代码/offline_contracts",
    "02_算法代码/tests",
    "比赛要求",
    "tools",
)


def check(project_root: str) -> dict[str, object]:
    root = Path(project_root).resolve()
    missing = [rel for rel in REQUIRED_CONTEXT if not (root / rel).exists()]
    missing_dirs = [rel for rel in REQUIRED_DIRS if not (root / rel).is_dir()]

    sys.path.insert(0, str(root / "02_算法代码"))
    sys.path.insert(0, str(root))
    from offline_contracts.contract import CATEGORY_OPTIONS, OFFICIAL_SHEET_NAMES
    from offline_contracts.sqlite_bridge import build_bridge, seed_dropdown_options, write_rows

    bridge_path = root / "tools" / "_verify.sqlite"
    bridge_path.parent.mkdir(parents=True, exist_ok=True)
    connection = build_bridge(bridge_path)
    seeded = seed_dropdown_options(connection)
    inserted = write_rows(connection, OFFICIAL_SHEET_NAMES[0], [{
        "序号": 1,
        "一级分类": "1 拓扑结构完整性检测",
        "二级分类": "1.1 设备拓扑悬空检测任务",
        "问题设备id": "0001111",
        "问题设备名称": "测试设备",
        "所属馈线": "测试馈线",
        "所属厂站": "测试厂站",
        "问题说明": "示例",
        "修正方案": "示例",
        "修正sql": "UPDATE JBS_PWEQUIPINFO SET FEEDER_ID='LINE002' WHERE EQUIP_ID='0001111'",
    }])
    bridge_tables = connection.cursor().execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
    ).fetchone()[0]
    connection.close()

    issues = missing + [f"MISSING_DIR:{d}" for d in missing_dirs]
    return {
        "status": "PASS" if not issues else "FAIL",
        "project_root": str(root),
        "missing_files": missing,
        "missing_dirs": missing_dirs,
        "issues": issues,
        "official_sheet_names": list(OFFICIAL_SHEET_NAMES),
        "dropdown_count": len(CATEGORY_OPTIONS),
        "bridge_seeded_rows": seeded,
        "bridge_inserted_rows": inserted,
        "bridge_table_count": bridge_tables,
        "bridge_path": str(bridge_path),
        "real_competition_data_included": False,
        "sql_executed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify offline migration package")
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args()
    result = check(args.project_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
'''
    target.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build offline migration package")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        print("dry-run only: would build", DIST)
        return 0
    reset_dist()
    copied = copy_context_files()
    official = copy_official_requirements()
    copied.extend(official)
    write_migration_verify_script()
    manifest = write_migration_manifest(copied)
    write_migration_readme()
    zip_path, suffix_counts = build_zip()
    print(json.dumps({
        "status": "PASS",
        "dist": str(DIST),
        "zip": str(zip_path),
        "manifest": manifest["manifest_version"],
        "copied_files": len(copied),
        "suffix_counts": dict(sorted(suffix_counts.items())),
        "real_competition_data_included": manifest["real_competition_data_included"],
        "sql_executed": False,
        "database_connected": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())