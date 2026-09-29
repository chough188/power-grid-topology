"""Official SQL table inventory and minimum field contracts (D12 加固).

- ``required_fields``：缺失即视为数据不完整（validate 报错）。
- ``optional_fields``：声明但非强制，用于契约完整性与值域校验（解 D12）。
- ``validate_values``：对“已出现”的字段做宽松值域校验，提前暴露脏数据。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TableSchema:
    name: str
    domain: str
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...] = ()


# RUN_STATUS / POINT 允许的取值（含常见脏值写法，避免误报）
_STATUS_ALLOWED = {0, 1, "0", "1", "Y", "N", "y", "n", None, ""}


def _is_voltage_ok(v) -> bool:
    if v is None or v == "":
        return True
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


TABLE_SCHEMAS = {
    "JBS_ZWSUBSTATION": TableSchema(
        "JBS_ZWSUBSTATION", "main_grid",
        ("ST_ID", "ST_NAME", "TOP_AC_VOLTAGE_TYPE"),
        ("IS_END_DEVICE",),
    ),
    "JBS_ZWEQUIPINFO": TableSchema(
        "JBS_ZWEQUIPINFO", "main_grid",
        ("EQUIP_ID", "EQUIP_NAME", "EQUIP_TYPE", "ST_ID", "VOLTAGE_TYPE"),
        ("RUN_STATUS", "OBJ_CODE", "LIFECYCLE"),
    ),
    "JBS_ZWLINEEND": TableSchema(
        "JBS_ZWLINEEND", "main_grid",
        ("LINEEND_ID", "LINEEND_NAME", "VOLTAGE_TYPE", "ST_ID"),
        (),
    ),
    "JBS_ZWTERMINAL": TableSchema(
        "JBS_ZWTERMINAL", "main_grid",
        ("ID", "EQUIP_ID", "CONNECTIVITYNODE_ID"),
        ("PORT_NO", "VALID_FLAG"),
    ),
    "JBS_ZWMEA": TableSchema(
        "JBS_ZWMEA", "main_grid",
        ("CREATE_DATE", "ID", "MEAS_TYPE"),
        (),
    ),
    "JBS_ZWSIGNAL": TableSchema(
        "JBS_ZWSIGNAL", "main_grid",
        ("ID", "POINT"),
        (),
    ),
    "JBS_PWFEEDERLINE": TableSchema(
        "JBS_PWFEEDERLINE", "distribution_grid",
        ("LINE_ID", "LINE_NAME", "START_ST_ID", "VOLTAGE_TYPE"),
        (),
    ),
    "JBS_PWROOM": TableSchema(
        "JBS_PWROOM", "distribution_grid",
        ("ROOM_ID", "ROOM_NAME", "TOP_VOLTAGE_TYPE", "FEEDER_ID"),
        ("IS_END_DEVICE",),
    ),
    "JBS_PWEQUIPINFO": TableSchema(
        "JBS_PWEQUIPINFO", "distribution_grid",
        ("EQUIP_ID", "EQUIP_NAME", "EQUIP_TYPE", "VOLTAGE_TYPE", "FEEDER_ID", "DSUBSTATION_ID", "COMPOSITESWITCH"),
        ("RUN_STATUS", "LIFECYCLE", "IS_END_DEVICE", "OBJ_CODE"),
    ),
    "JBS_PWTERMINAL": TableSchema(
        "JBS_PWTERMINAL", "distribution_grid",
        ("ID", "EQUIP_ID", "CONNECTIVITYNODE_ID"),
        ("PORT_NO", "VALID_FLAG"),
    ),
    "JBS_PWREAL": TableSchema(
        "JBS_PWREAL", "distribution_grid",
        ("NUM", "TRAN_ID", "DATA_DATE", "POINT", "BDZ_ID", "FEEDER_ID"),
        ("UA", "UB", "UC", "IA", "IB", "IC", "AP", "RP"),
    ),
    "JBS_ZD_OBJECT": TableSchema(
        "JBS_ZD_OBJECT", "dictionary",
        ("OBJ_ID", "OBJ_CODE", "OBJ_CNNAME", "OBJ_ENNAME"),
        (),
    ),
    "JBS_ZD_VOLTAGETYPE": TableSchema(
        "JBS_ZD_VOLTAGETYPE", "dictionary",
        ("VOLTAGE_ID", "VOLTAGE_NAME"),
        (),
    ),
    "JBS_ZD_MEASTYPE": TableSchema(
        "JBS_ZD_MEASTYPE", "dictionary",
        ("CODE", "NAME_CHN"),
        (),
    ),
}

REQUIRED_TABLES = tuple(TABLE_SCHEMAS)


def value_errors(tables: "Mapping[str, Sequence[Mapping]]") -> "tuple[str, ...]":  # type: ignore[name-defined]
    """对“已出现”的字段做宽松值域校验（解 D12：加载阶段暴露脏数据）。"""
    errors: list[str] = []
    for table_name, rows in tables.items():
        schema = TABLE_SCHEMAS.get(table_name)
        if schema is None or not rows:
            continue
        for row in rows:
            dev = row.get("RUN_STATUS")
            if dev is not None and dev != "" and dev not in _STATUS_ALLOWED:
                errors.append(f"{table_name}: RUN_STATUS={dev!r} 非法（应∈{{0,1}}）")
            pt = row.get("POINT")
            if pt is not None and pt != "" and pt not in _STATUS_ALLOWED:
                errors.append(f"{table_name}: POINT={pt!r} 非法（应∈{{0,1}}）")
            vt = row.get("VOLTAGE_TYPE")
            if not _is_voltage_ok(vt):
                errors.append(f"{table_name}: VOLTAGE_TYPE={vt!r} 非数值")
    return tuple(errors)
