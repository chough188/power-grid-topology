# -*- coding: utf-8 -*-
from __future__ import annotations
"""EQUIP_TYPE 归一映射层（解 D8 系统性静默失效风险）。

官方《数据集结构说明》明确：``JBS_PWEQUIPINFO.EQUIP_TYPE`` 引用
``JBS_ZD_OBJECT``（真实值是 ``OBJ_CODE`` / ``OBJ_ID`` 这类外键，如 ``0102``），
而各检测器内部比较的是**规范英文枚举**（``BREAKER`` / ``SWITCH`` / ...）。

若不做归一，真实数据下所有依赖设备类型的分支（1.1/1.3/1.4/1.5/2.2/2.3/2.4/
4.1/5.0/5.1）会整体走 default 分支而不报错——即审计所指「静默失效」。

本模块在**加载阶段**把原始 ``EQUIP_TYPE`` 归一为规范枚举：
- 已是规范英文/中文 → 直接映射；
- 是 ``OBJ_CODE`` → 经 ``JBS_ZD_OBJECT`` 映射（缺失时回退到种子表）；
- 仍无法识别 → 保留原值（与改动前行为一致，不丢信息）。

对外暴露：
- :func:`build_obj_code_map`：由 ``JBS_ZD_OBJECT`` 行构建 ``OBJ_CODE -> 规范枚举``。
- :func:`normalize_equip_type`：单值归一。
- :func:`normalize_dataset_types`：整表归一（新增 ``EQUIP_TYPE_RAW`` 保留原值）。
"""

from collections.abc import Mapping, Sequence

# 检测器内部统一使用的规范英文枚举
CANONICAL_EQUIP_TYPES = frozenset(
    {
        "BREAKER",
        "SWITCH",
        "DISCONNECTOR",
        "TRANSFORMER",
        "BUS",
        "LINE",
        "SOURCE",
        "CONNECTOR",
        "CABLE_HEAD",
        "LOAD",
        "CAPACITOR",
        "REACTOR",
        "MEASURE",
    }
)

# 中文 / 英文别名 -> 规范枚举（静态兜底，JBS_ZD_OBJECT 缺失时仍可用）
_TYPE_ALIAS = {
    # 英文（与规范枚举同形，等价）
    "BREAKER": "BREAKER",
    "SWITCH": "SWITCH",
    "DISCONNECTOR": "DISCONNECTOR",
    "TRANSFORMER": "TRANSFORMER",
    "BUS": "BUS",
    "LINE": "LINE",
    "SOURCE": "SOURCE",
    "CONNECTOR": "CONNECTOR",
    "CABLE_HEAD": "CABLE_HEAD",
    "LOAD": "LOAD",
    "CAPACITOR": "CAPACITOR",
    "REACTOR": "REACTOR",
    "MEASURE": "MEASURE",
    # 中文
    "断路器": "BREAKER",
    "开关": "SWITCH",
    "负荷开关": "SWITCH",
    "隔离开关": "DISCONNECTOR",
    "刀闸": "DISCONNECTOR",
    # 配网开关家族（真实数据 JBS_ZD_OBJECT OBJ_ENNAME/OBJ_CNNAME，D8 补全）：
    # 官方 §1.3/§1.4/§1.5 候选集 = 开关/刀闸家族；缺此映射时真实数据下
    # DBREAKER(1705) 等占分位设备 81% 的类型被检测器静默排除（系统性失效）。
    "DBREAKER": "BREAKER",          # 1705 配网断路器
    "配网断路器": "BREAKER",
    "DLOADSWITCH": "SWITCH",        # 1706 配网负荷开关
    "配网负荷开关": "SWITCH",
    "DDIS": "DISCONNECTOR",         # 1708 配网刀闸
    "配网刀闸": "DISCONNECTOR",
    # 注意: GROUNDDIS(1323 接地刀闸)/DGROUNDDIS(1709 配网接地刀闸) 刻意**不**并入
    # DISCONNECTOR —— 接地刀闸是安全接地装置而非线路刀闸：并入后 4.1 会把主网
    # 234 台地刀误报为"馈线接口漏拼"（Run 7 实测全部 added 记录均为 1323），
    # 且地刀永远不是联络开关候选（一侧接接地母线）。1.1 单侧豁免经名称兜底
    # （is_single_side_allowed 含"刀闸"子串）仍覆盖真实地刀设备。
    # COMPOSITESWITCH(1720 组合开关) 同样刻意不映射 —— 官方 §1.1 对组合开关
    # 有独立复合规则（COMPOSITESWITCH 字段判定），且真实数据中无分位信号。
    # 真实数据 JBS_ZD_OBJECT OBJ_ENNAME 补全（QC 终检 G2 修复，2026-09）：
    # 此前这些 ENNAME 回退保留原值，导致 (a) 5.1 beautify() 全部落到默认矩形
    # （100% default style），(b) trace_to_source 的 SOURCE_ROOT_CLASSES 在真实
    # 数据下几乎不可达（1311/1703 变压器不归一为 TRANSFORMER），1.3 严格路径
    # 双侧溯源大面积失败。以下映射目标均为唯一、无歧义的规范枚举：
    "DIS": "DISCONNECTOR",           # 1322 主网隔离开关
    "BUSBAR": "BUS",                 # 1301 母线
    "DBUS": "BUS",                   # 1710 配网母线段
    "PWRTRANSFM": "TRANSFORMER",     # 1311 变压器
    "DPWRTRANSFM": "TRANSFORMER",    # 1703 配网变压器
    "EARTHINGTRANSFORMER": "TRANSFORMER",  # 1318 接地变
    "TERM": "TRANSFORMER",           # 1317 站用变
    "LOWVOLLINE": "LINE",            # 1702 馈线段
    "CONVERGENCELINE": "LINE",       # 1108 汇集线
    "DCUSTOMER": "LOAD",             # 1719 配网电力用户
    "CT": "MEASURE",                 # 1313 电流互感器
    "PT": "MEASURE",                 # 1314 电压互感器
    "DPT": "MEASURE",                # 1713 配网 PT
    "SHUNTREACTOR": "REACTOR",       # 1401 并联电抗器
    "ARCSUPPRESSIONCO": "REACTOR",   # 1325 消弧线圈
    "DSEAIESREACTOR": "REACTOR",     # 1704 配网串联电抗器
    "SHUNTCAPACITOR": "CAPACITOR",   # 1402 并联电容器
    # DFUSE(1707)/ARRESTER(1328)/DPOLE(1714) 无对应规范枚举，保留原值。
    "变压器": "TRANSFORMER",
    "配变": "TRANSFORMER",
    "母线": "BUS",
    "线路": "LINE",
    "电源": "SOURCE",
    "连接器": "CONNECTOR",
    "电缆终端头": "CABLE_HEAD",
    "负荷": "LOAD",
    "电容器": "CAPACITOR",
    "电抗器": "REACTOR",
    "量测": "MEASURE",
}

# 种子 OBJ_CODE 表（与 synthetic_gen 中 JBS_ZD_OBJECT 默认行保持一致）。
# 真实环境下应优先使用数据自带的 JBS_ZD_OBJECT 覆盖本表。
SEED_OBJ_CODE_MAP = {
    "O001": "BREAKER",
    "O002": "SWITCH",
    "O003": "DISCONNECTOR",
    "O004": "TRANSFORMER",
    "O011": "BUS",
    "O012": "LINE",
    "O013": "SOURCE",
    "O005": "CONNECTOR",
    "O006": "CABLE_HEAD",
    "O007": "LOAD",
    "O008": "CAPACITOR",
    "O009": "REACTOR",
    "O010": "MEASURE",
}

# 需要归一 EQUIP_TYPE 的表
_EQUIP_TABLES = ("JBS_PWEQUIPINFO", "JBS_ZWEQUIPINFO")


def _canon_from_zd_row(row: Mapping) -> str | None:
    """由 JBS_ZD_OBJECT 一行推断规范枚举。"""
    en = (row.get("OBJ_ENNAME") or "").strip()
    cn = (row.get("OBJ_CNNAME") or "").strip()
    for raw in (en, cn):
        if not raw:
            continue
        key = raw.upper() if raw in CANONICAL_EQUIP_TYPES else raw
        if raw in _TYPE_ALIAS:
            return _TYPE_ALIAS[raw]
        if raw.upper() in _TYPE_ALIAS:
            return _TYPE_ALIAS[raw.upper()]
        if key in CANONICAL_EQUIP_TYPES:
            return key
    # 退而求其次：保留英文原值（即便不在规范集合内也不丢信息）
    return en or cn or None


def build_obj_code_map(zd_object_rows: Sequence[Mapping]) -> dict[str, str]:
    """由 ``JBS_ZD_OBJECT`` 构建 ``OBJ_CODE -> 规范枚举`` 映射。

    真实数据的 OBJ_CODE（如 ``0102``）通过本映射归一，避免检测器
    直接比对英文字面量而在真实数据下静默失效。
    """
    obj_map: dict[str, str] = {}
    obj_map.update(SEED_OBJ_CODE_MAP)  # 种子兜底
    for row in zd_object_rows or ():
        code = (row.get("OBJ_CODE") or "").strip()
        if not code:
            continue
        canon = _canon_from_zd_row(row)
        if canon:
            obj_map[code] = canon
    return obj_map


def normalize_equip_type(raw: object, obj_code_map: Mapping[str, str] | None = None) -> str:
    """把单个 EQUIP_TYPE 原值归一为规范枚举。

    返回规范枚举；无法识别时返回原值（字符串），不丢弃信息。
    """
    obj_code_map = obj_code_map or SEED_OBJ_CODE_MAP
    s = "" if raw is None else str(raw).strip()
    if not s:
        return ""
    if s in CANONICAL_EQUIP_TYPES:
        return s
    key = s.upper() if s in CANONICAL_EQUIP_TYPES else s
    if s in _TYPE_ALIAS:
        return _TYPE_ALIAS[s]
    if s.upper() in _TYPE_ALIAS:
        return _TYPE_ALIAS[s.upper()]
    if key in CANONICAL_EQUIP_TYPES:
        return key
    if s in obj_code_map:
        return obj_code_map[s]
    if s.upper() in obj_code_map:
        return obj_code_map[s.upper()]
    # 未知类型：保留原值，交由检测器按 default 处理（与改动前一致）
    return s


def normalize_dataset_types(tables: Mapping[str, Sequence[Mapping]]) -> dict[str, list[dict]]:
    """整表归一 EQUIP_TYPE。

    返回**新的** tables（不修改入参）：每个设备行新增
    ``EQUIP_TYPE_RAW``（原始值）并把 ``EQUIP_TYPE`` 覆写为归一值。

    真实数据（EQUIP_TYPE=OBJ_CODE）下，本函数把类型修正为规范枚举，
    使下游检测器正确工作；合成数据（已是英文）下为近似恒等变换。
    """
    obj_code_map = build_obj_code_map(tables.get("JBS_ZD_OBJECT", ()) or ())
    out: dict[str, list[dict]] = {}
    for table_name, rows in tables.items():
        if table_name in _EQUIP_TABLES:
            new_rows: list[dict] = []
            for row in rows or ():
                new_row = dict(row)
                raw = new_row.get("EQUIP_TYPE")
                new_row["EQUIP_TYPE_RAW"] = raw
                new_row["EQUIP_TYPE"] = normalize_equip_type(raw, obj_code_map)
                new_rows.append(new_row)
            out[table_name] = new_rows
        else:
            # 非设备表原样保留（保持结构，便于下游按表名取数）
            out[table_name] = list(rows) if isinstance(rows, (list, tuple)) else rows
    return out


__all__ = [
    "CANONICAL_EQUIP_TYPES",
    "SEED_OBJ_CODE_MAP",
    "build_obj_code_map",
    "normalize_equip_type",
    "normalize_dataset_types",
]
