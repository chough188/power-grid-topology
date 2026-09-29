"""Transport-level API contracts with no web server or database dependency."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

REQUEST_REQUIRED = ("dataset_ref", "scope", "dry_run")
RESPONSE_REQUIRED = ("request_id", "status", "snapshot_hash", "rule_version", "data_quality", "findings", "artifacts", "warnings", "errors")
ALLOWED_STATUS = {"success", "partial", "failed"}


def validate_request(payload: Any) -> list[str]:
    if not isinstance(payload, Mapping):
        return ["REQUEST_NOT_OBJECT"]
    issues: list[str] = []
    for field in REQUEST_REQUIRED:
        if field not in payload:
            issues.append(f"MISSING_REQUEST_FIELD:{field}")
    if not isinstance(payload.get("dataset_ref"), str) or not payload.get("dataset_ref", "").strip():
        issues.append("INVALID_DATASET_REF")
    if not isinstance(payload.get("scope"), Mapping):
        issues.append("INVALID_SCOPE")
    if not isinstance(payload.get("dry_run"), bool):
        issues.append("INVALID_DRY_RUN")
    detector_ids = payload.get("detector_ids", [])
    if not isinstance(detector_ids, list) or any(not isinstance(item, str) for item in detector_ids):
        issues.append("INVALID_DETECTOR_IDS")
    options = payload.get("options", {})
    if not isinstance(options, Mapping):
        issues.append("INVALID_OPTIONS")
    if "raw_data" in payload:
        issues.append("RAW_DATA_MUST_NOT_BE_IN_REQUEST")
    return issues


def validate_response(payload: Any) -> list[str]:
    if not isinstance(payload, Mapping):
        return ["RESPONSE_NOT_OBJECT"]
    issues: list[str] = []
    for field in RESPONSE_REQUIRED:
        if field not in payload:
            issues.append(f"MISSING_RESPONSE_FIELD:{field}")
    if payload.get("status") not in ALLOWED_STATUS:
        issues.append("INVALID_STATUS")
    for field in ("findings", "warnings", "errors"):
        if field in payload and not isinstance(payload[field], list):
            issues.append(f"INVALID_RESPONSE_LIST:{field}")
    if "artifacts" in payload and not isinstance(payload["artifacts"], Mapping):
        issues.append("INVALID_ARTIFACTS")
    if "data_quality" in payload and not isinstance(payload["data_quality"], Mapping):
        issues.append("INVALID_DATA_QUALITY")
    if payload.get("status") == "success" and payload.get("errors"):
        issues.append("SUCCESS_WITH_ERRORS")
    return issues


def synthetic_request() -> dict[str, Any]:
    return {
        "dataset_ref": "synthetic://offline-contract-v1",
        "scope": {"station_ids": ["SUB001"], "feeder_ids": ["LINE001"]},
        "detector_ids": ["all_official_categories"],
        "options": {"include_evidence": True},
        "dry_run": True,
    }


def synthetic_response() -> dict[str, Any]:
    return {
        "request_id": "offline-request-001",
        "status": "success",
        "snapshot_hash": "synthetic-snapshot",
        "rule_version": "offline-v1",
        "data_quality": {"status": "pass", "real_data_read": False},
        "findings": [],
        "artifacts": {"output_contract_report": "output_contract_report.json"},
        "warnings": [],
        "errors": [],
    }