"""Offline-first data and output contracts for the competition handoff.

This module deliberately contains no database connector and no SQL executor.
It validates in-memory payloads and produces diagnostics that are safe to run
before real competition data is available.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class TableContract:
    name: str
    required_fields: tuple[str, ...]
    primary_fields: tuple[str, ...]


def _measurement_fields() -> tuple[str, ...]:
    fields: list[str] = []
    for point_index in range(96):
        minutes = point_index * 15
        hour, minute = divmod(minutes, 60)
        fields.append(f"V{hour:02d}{minute:02d}")
    return tuple(fields)


MEASUREMENT_FIELDS = _measurement_fields()

TABLE_CONTRACTS: dict[str, TableContract] = {
    "JBS_ZWSUBSTATION": TableContract("JBS_ZWSUBSTATION", ("ST_ID", "ST_NAME", "TOP_AC_VOLTAGE_TYPE"), ("ST_ID",)),
    "JBS_ZWEQUIPINFO": TableContract("JBS_ZWEQUIPINFO", ("EQUIP_ID", "EQUIP_NAME", "EQUIP_TYPE", "ST_ID", "VOLTAGE_TYPE"), ("EQUIP_ID",)),
    "JBS_ZWLINEEND": TableContract("JBS_ZWLINEEND", ("LINEEND_ID", "LINEEND_NAME", "VOLTAGE_TYPE", "ST_ID"), ("LINEEND_ID",)),
    "JBS_ZWTERMINAL": TableContract("JBS_ZWTERMINAL", ("ID", "EQUIP_ID", "CONNECTIVITYNODE_ID"), ("ID",)),
    "JBS_ZWMEA": TableContract("JBS_ZWMEA", ("CREATE_DATE", "ID", "MEAS_TYPE", *MEASUREMENT_FIELDS), ("ID", "CREATE_DATE")),
    "JBS_ZWSIGNAL": TableContract("JBS_ZWSIGNAL", ("ID", "POINT"), ("ID",)),
    "JBS_PWFEEDERLINE": TableContract("JBS_PWFEEDERLINE", ("LINE_ID", "LINE_NAME", "START_ST_ID", "VOLTAGE_TYPE"), ("LINE_ID",)),
    "JBS_PWROOM": TableContract("JBS_PWROOM", ("ROOM_ID", "ROOM_NAME", "TOP_VOLTAGE_TYPE", "FEEDER_ID"), ("ROOM_ID",)),
    "JBS_PWEQUIPINFO": TableContract("JBS_PWEQUIPINFO", ("EQUIP_ID", "EQUIP_NAME", "EQUIP_TYPE", "VOLTAGE_TYPE", "FEEDER_ID", "DSUBSTATION_ID", "COMPOSITESWITCH"), ("EQUIP_ID",)),
    "JBS_PWTERMINAL": TableContract("JBS_PWTERMINAL", ("ID", "EQUIP_ID", "CONNECTIVITYNODE_ID"), ("ID",)),
    "JBS_PWREAL": TableContract("JBS_PWREAL", ("NUM", "TRAN_ID", "DATA_DATE", "UA", "UB", "UC", "IA", "IB", "IC", "AP", "RP", "POINT", "BDZ_ID", "FEEDER_ID"), ("NUM", "TRAN_ID", "DATA_DATE")),
    "JBS_ZD_OBJECT": TableContract("JBS_ZD_OBJECT", ("OBJ_ID", "OBJ_CODE", "OBJ_CNNAME", "OBJ_ENNAME"), ("OBJ_ID",)),
    "JBS_ZD_VOLTAGETYPE": TableContract("JBS_ZD_VOLTAGETYPE", ("VOLTAGE_ID", "VOLTAGE_NAME"), ("VOLTAGE_ID",)),
    "JBS_ZD_MEASTYPE": TableContract("JBS_ZD_MEASTYPE", ("CODE", "NAME_CHN"), ("CODE",)),
}

OFFICIAL_SHEET_NAMES = (
    "拓扑校验问题清单",
    "拓扑连通性异常诊断与断点定位结果",
    "联络开关自动识别与可视化梳理任务结果",
    "非计划性合环拓扑识别任务结果",
    "模型修正质量评分任务结果",
    "问题类型下拉选项",
)

SHEET_HEADERS: dict[str, tuple[str | None, ...]] = {
    OFFICIAL_SHEET_NAMES[0]: ("序号", "一级分类", "二级分类", "问题设备id", "问题设备名称", "所属馈线", "所属厂站", "问题说明", "修正方案", "修正sql"),
    OFFICIAL_SHEET_NAMES[1]: ("序号", "起点设备id", "终点设备id", "断点类型", "本侧疑似断点设备id", "本侧疑似断点设备名称", "对侧疑似断点设备id", "对侧疑似断点设备名称", "修正方案", "修正sql", None),
    OFFICIAL_SHEET_NAMES[2]: ("线路id", "线路名称", "上级变电站名称", "联络开关id", "联络开关名称", "是否有联络", "联络线路id", "联络线路名称", "联络线变电站名称"),
    OFFICIAL_SHEET_NAMES[3]: ("线路id", "线路名称", "上级变电站名称", "合环线路id", "合环线路名称", "合环线变电站名称", "疑似联络开关id", "疑似联络开关名称", "修正sql"),
    OFFICIAL_SHEET_NAMES[4]: ("序号", "厂站名称", "厂站id", "馈线名称", "馈线id", "修正前评分", "修正后评分"),
    OFFICIAL_SHEET_NAMES[5]: ("一级分类", "二级分类"),
}

CATEGORY_OPTIONS = (
    ("1 拓扑结构完整性检测", "1.1 设备拓扑悬空检测任务"),
    ("1 拓扑结构完整性检测", "1.2 拓扑连通性异常诊断与断点定位任务"),
    ("1 拓扑结构完整性检测", "1.3 联络开关自动识别与可视化梳理任务"),
    ("1 拓扑结构完整性检测", "1.4 疑似联络开关智能识别与复核研判任务"),
    ("1 拓扑结构完整性检测", "1.5 非计划性合环拓扑识别任务"),
    ("2 图模一致性校验", "2.1 图上有、模型无校验任务"),
    ("2 图模一致性校验", "2.2 模型有、图上无校验任务"),
    ("2 图模一致性校验", "2.3 图形物理连通、拓扑逻辑断开校验任务"),
    ("2 图模一致性校验", "2.4 图形物理断开、拓扑逻辑误连通校验任务"),
    ("3 电气逻辑校验", "3.1 开关-电压基础状态匹配校验任务"),
    ("4 主配网接口拓扑完整性校验", "4.1 主配接口漏拼接校验任务"),
    ("4 主配网接口拓扑完整性校验", "4.2 主配接口错拼接校验任务"),
)


def canonicalize_identifier(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        raise ValueError("boolean is not a valid identifier")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError("non-integral numeric value is not a valid identifier")
    return str(value).strip()


def validate_tables(tables: Mapping[str, Sequence[Mapping[str, Any]]]) -> list[str]:
    issues: list[str] = []
    for table_name, contract in TABLE_CONTRACTS.items():
        if table_name not in tables:
            issues.append(f"MISSING_TABLE:{table_name}")
            continue
        rows = tables[table_name]
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            issues.append(f"INVALID_ROWS:{table_name}")
            continue
        if not rows:
            issues.append(f"EMPTY_TABLE:{table_name}")
            continue
        field_names: set[str] = set()
        for row_index, row in enumerate(rows):
            if not isinstance(row, Mapping):
                issues.append(f"INVALID_ROW:{table_name}:{row_index}")
                continue
            field_names.update(str(field) for field in row.keys())
            for field in contract.required_fields:
                if field not in row:
                    issues.append(f"MISSING_FIELD:{table_name}:{field}:{row_index}")
            for primary_field in contract.primary_fields:
                if primary_field in row and row[primary_field] in (None, ""):
                    issues.append(f"EMPTY_PRIMARY:{table_name}:{primary_field}:{row_index}")
        for field in contract.required_fields:
            if field not in field_names:
                issues.append(f"MISSING_COLUMN:{table_name}:{field}")
        seen_keys: set[tuple[str, ...]] = set()
        for row_index, row in enumerate(rows):
            if not isinstance(row, Mapping):
                continue
            try:
                key = tuple(canonicalize_identifier(row.get(field)) for field in contract.primary_fields)
            except ValueError:
                issues.append(f"INVALID_PRIMARY:{table_name}:{row_index}")
                continue
            if not all(key):
                continue
            if key in seen_keys:
                issues.append(f"DUPLICATE_PRIMARY:{table_name}:{key}")
            seen_keys.add(key)
        if table_name in ("JBS_ZWSIGNAL", "JBS_PWREAL"):
            for row_index, row in enumerate(rows):
                if isinstance(row, Mapping) and row.get("POINT") not in (0, 1, None):
                    issues.append(f"INVALID_POINT:{table_name}:{row_index}")
    return issues


def validate_output_book(book: Mapping[str, Mapping[str, Any]]) -> list[str]:
    issues: list[str] = []
    missing = [name for name in OFFICIAL_SHEET_NAMES if name not in book]
    extra = [name for name in book if name not in OFFICIAL_SHEET_NAMES]
    issues.extend(f"MISSING_SHEET:{name}" for name in missing)
    issues.extend(f"EXTRA_SHEET:{name}" for name in extra)
    for sheet_name, expected_headers in SHEET_HEADERS.items():
        if sheet_name not in book:
            continue
        payload = book[sheet_name]
        actual_headers = tuple(payload.get("headers", ()))
        if actual_headers != expected_headers:
            issues.append(f"HEADER_MISMATCH:{sheet_name}:expected={expected_headers}:actual={actual_headers}")
        rows = payload.get("rows", ())
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            issues.append(f"INVALID_OUTPUT_ROWS:{sheet_name}")
            continue
        if sheet_name == OFFICIAL_SHEET_NAMES[2]:
            for row_index, row in enumerate(rows):
                if isinstance(row, Mapping) and row.get("是否有联络") not in (None, "是", "否"):
                    issues.append(f"INVALID_TIE_VALUE:{sheet_name}:{row_index}")
        if sheet_name == OFFICIAL_SHEET_NAMES[1]:
            for row_index, row in enumerate(rows):
                if isinstance(row, Mapping) and row.get("断点类型") not in (None, "开关分断", "拓扑断连"):
                    issues.append(f"INVALID_BREAK_VALUE:{sheet_name}:{row_index}")
        if sheet_name == OFFICIAL_SHEET_NAMES[5]:
            allowed = set(CATEGORY_OPTIONS)
            for row_index, row in enumerate(rows):
                if not isinstance(row, Mapping):
                    issues.append(f"INVALID_CATEGORY_ROW:{sheet_name}:{row_index}")
                    continue
                pair = (row.get("一级分类"), row.get("二级分类"))
                if pair not in allowed:
                    issues.append(f"INVALID_CATEGORY:{sheet_name}:{row_index}:{pair}")
    return issues


def validate_sql_preview(sql: Any) -> list[str]:
    if sql in (None, ""):
        return []
    if not isinstance(sql, str):
        return ["SQL_NOT_STRING"]
    normalized = sql.strip()
    issues: list[str] = []
    if not re.match(r"^update\b", normalized, re.IGNORECASE):
        issues.append("SQL_NOT_UPDATE")
    if not re.search(r"\bwhere\b", normalized, re.IGNORECASE):
        issues.append("SQL_MISSING_WHERE")
    if re.search(r"\b(delete|drop|insert|alter|truncate|merge)\b", normalized, re.IGNORECASE):
        issues.append("SQL_DANGEROUS_KEYWORD")
    if ";" in normalized.rstrip(";"):
        issues.append("SQL_MULTIPLE_STATEMENTS")
    return issues


def empty_output_book() -> dict[str, dict[str, Any]]:
    return {sheet_name: {"headers": list(headers), "rows": []} for sheet_name, headers in SHEET_HEADERS.items()}