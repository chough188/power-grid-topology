"""Run the offline startup sequence using synthetic data only."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from .api_contract import synthetic_request, synthetic_response, validate_request, validate_response
from .contract import CATEGORY_OPTIONS, TABLE_CONTRACTS, empty_output_book, validate_output_book, validate_tables
from .svg_contract import synthetic_svg, validate_svg_document
from .synthetic import build_synthetic_tables, write_synthetic_fixture


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_synthetic_bootstrap(output_dir: str | Path) -> dict[str, object]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    tables = build_synthetic_tables()
    table_issues = validate_tables(tables)
    book = empty_output_book()
    book["问题类型下拉选项"]["rows"] = [
        {"一级分类": level_one, "二级分类": level_two}
        for level_one, level_two in CATEGORY_OPTIONS
    ]
    output_issues = validate_output_book(book)
    api_request_issues = validate_request(synthetic_request())
    api_response_issues = validate_response(synthetic_response())
    svg_issues = validate_svg_document(synthetic_svg())
    fixture_path = write_synthetic_fixture(target / "synthetic_14_tables.json")
    fixture_hash = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
    generated_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "manifest_version": "offline-v1",
        "generated_at": generated_at,
        "dataset_kind": "synthetic",
        "real_competition_data_read": False,
        "database_connection_attempted": False,
        "sql_execution_attempted": False,
        "source": "offline_contracts.synthetic.build_synthetic_tables",
        "fixture": {"path": str(fixture_path), "sha256": fixture_hash},
        "tables": {
            table_name: {
                "rows": len(tables[table_name]),
                "fields": sorted(tables[table_name][0].keys()),
                "required_fields": list(contract.required_fields),
                "primary_fields": list(contract.primary_fields),
            }
            for table_name, contract in TABLE_CONTRACTS.items()
        },
    }
    schema_report = {
        "status": "PASS" if not table_issues else "FAIL",
        "dataset_kind": "synthetic",
        "table_count": len(tables),
        "expected_table_count": len(TABLE_CONTRACTS),
        "issues": table_issues,
        "measurement_field_count": 96,
    }
    quality_report = {
        "status": "PASS" if not table_issues else "FAIL",
        "scope": "synthetic_fixture_only",
        "issues": table_issues,
        "checks": [
            "all_14_tables_present",
            "required_fields_present",
            "primary_keys_nonempty_and_unique",
            "point_values_are_0_or_1_or_null",
            "no_real_data_read",
            "no_sql_executed",
        ],
    }
    output_report = {
        "status": "PASS" if not output_issues else "FAIL",
        "sheet_count": len(book),
        "issues": output_issues,
        "official_sheet_contract_checked": True,
        "category_count": len(CATEGORY_OPTIONS),
    }
    api_report = {
        "status": "PASS" if not api_request_issues and not api_response_issues else "FAIL",
        "request_issues": api_request_issues,
        "response_issues": api_response_issues,
    }
    svg_report = {"status": "PASS" if not svg_issues else "FAIL", "issues": svg_issues}
    _write_json(target / "manifest.json", manifest)
    _write_json(target / "schema_profile.json", schema_report)
    _write_json(target / "data_quality_report.json", quality_report)
    _write_json(target / "output_contract_report.json", output_report)
    _write_json(target / "api_contract_report.json", api_report)
    _write_json(target / "svg_contract_report.json", svg_report)
    _write_json(target / "synthetic_output_book_model.json", book)
    return {
        "manifest": manifest,
        "schema_report": schema_report,
        "quality_report": quality_report,
        "output_report": output_report,
        "api_report": api_report,
        "svg_report": svg_report,
        "output_dir": str(target),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline synthetic bootstrap; never reads real data")
    parser.add_argument("--output-dir", default="output/offline_bootstrap")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = run_synthetic_bootstrap(args.output_dir)
    report_keys = ("schema_report", "quality_report", "output_report", "api_report", "svg_report")
    all_passed = all(result[key]["status"] == "PASS" for key in report_keys)
    print(json.dumps({
        "status": "PASS" if all_passed else "FAIL",
        "output_dir": result["output_dir"],
        "real_competition_data_read": result["manifest"]["real_competition_data_read"],
        "sql_execution_attempted": result["manifest"]["sql_execution_attempted"],
    }, ensure_ascii=False))
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())