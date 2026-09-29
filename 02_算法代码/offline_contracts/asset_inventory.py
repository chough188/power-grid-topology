"""Metadata-only project inventory for offline handoff."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

SKIP_DIR_NAMES = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "venv_lora",
    ".venv",
    "_archive",
    "_codex_dumps",
}


def classify(relative_path: Path) -> str:
    parts = relative_path.parts
    suffix = relative_path.suffix.lower()
    if parts and parts[0] == "比赛要求":
        return "official_requirement"
    if parts and parts[0] == "03_数据集":
        return "external_reference_data"
    if parts and parts[0] == "docs":
        return "context_or_documentation"
    if parts and parts[0] == "output":
        return "generated_output"
    if suffix in {".py", ".ps1", ".bat", ".sh", ".js", ".ts", ".html", ".css"}:
        return "source_or_tooling"
    if suffix in {".json", ".yaml", ".yml", ".toml", ".ini"}:
        return "configuration_or_metadata"
    return "other"


def inventory_project(project_root: str | Path, output_path: str | Path) -> dict[str, object]:
    root = Path(project_root).resolve()
    output = Path(output_path)
    entries: list[dict[str, object]] = []
    skipped: Counter[str] = Counter()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative_path = path.relative_to(root)
        if any(part in SKIP_DIR_NAMES for part in relative_path.parts):
            skipped[next(part for part in relative_path.parts if part in SKIP_DIR_NAMES)] += 1
            continue
        entries.append({
            "path": relative_path.as_posix(),
            "size": path.stat().st_size,
            "suffix": path.suffix.lower(),
            "category": classify(relative_path),
        })
    entries.sort(key=lambda item: str(item["path"]))
    category_counts = Counter(str(entry["category"]) for entry in entries)
    report = {
        "inventory_version": "metadata-only-v1",
        "project_root": str(root),
        "content_read": False,
        "hashes_generated": False,
        "files_moved": False,
        "database_connected": False,
        "sql_executed": False,
        "entry_count": len(entries),
        "category_counts": dict(sorted(category_counts.items())),
        "skipped_directory_file_counts": dict(sorted(skipped.items())),
        "entries": entries,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Metadata-only offline project inventory")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--output", default="output/offline_bootstrap/local_asset_inventory.json")
    args = parser.parse_args()
    report = inventory_project(args.project_root, args.output)
    print(json.dumps({
        "status": "PASS",
        "entry_count": report["entry_count"],
        "category_counts": report["category_counts"],
        "content_read": report["content_read"],
        "files_moved": report["files_moved"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())