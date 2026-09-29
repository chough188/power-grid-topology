"""Verify the offline local-model context without touching data directories."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REQUIRED_CONTEXT = (
    "AGENTS.md",
    "docs/本地模型上下文清单.md",
    "docs/本地模型启动提示词.md",
    "docs/官方资料包_完整要求解读.md",
    "docs/技术实现细节_完整版.md",
    "docs/本地模型离线接续方案.md",
)


def find_project_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "AGENTS.md").is_file():
            return candidate
    raise FileNotFoundError("AGENTS.md was not found from the current directory")


def pending_sort_key(path: Path) -> int:
    match = re.search(r"PENDING_v(\d+)\.md$", path.name, re.IGNORECASE)
    return int(match.group(1)) if match else -1


def check_context(project_root: str | Path) -> dict[str, object]:
    root = Path(project_root).resolve()
    missing = [relative_path for relative_path in REQUIRED_CONTEXT if not (root / relative_path).is_file()]
    pending_files = sorted((root / "output").glob("PENDING_v*.md"), key=pending_sort_key)
    latest_pending = pending_files[-1].relative_to(root).as_posix() if pending_files else None
    return {
        "status": "PASS" if not missing and latest_pending else "FAIL",
        "project_root": str(root),
        "required_context": list(REQUIRED_CONTEXT),
        "missing_context": missing,
        "latest_pending": latest_pending,
        "real_data_scanned": False,
        "database_connected": False,
        "sql_executed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline context check without data access")
    parser.add_argument("--project-root", default=None)
    args = parser.parse_args()
    root = find_project_root(Path(args.project_root).resolve()) if args.project_root else find_project_root(Path.cwd())
    result = check_context(root)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())