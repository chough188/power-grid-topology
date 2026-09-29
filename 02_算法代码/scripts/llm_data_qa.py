# -*- coding: utf-8 -*-
"""LLM 数据体检脚本：一条命令输出官方答疑口径对应的 7 项数据质量检查结果。

用法（在 02_算法代码 目录下）:
    python -X utf8 scripts/llm_data_qa.py [数据路径，默认 data/snapshot.json]
数据路径支持：.json 快照 / .sql 文件（含 INSERT）/ 含 *.sql 的目录（15 分表自动合并）。

输出格式固定为 KEY = VALUE 文本，便于本地大模型逐行解析对比。
官方答疑口径来源：揭榜赛答疑问题分类整理.docx（Q8 去重 / Q7 1312→1321 / Q38 无遥信默认合位）。
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path


def _load(path: Path) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from data_loader.universal import load_dataset
    return load_dataset(path).tables


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    path = Path(argv[0]) if argv else Path("data/snapshot.json")
    if not path.exists():
        print("SNAPSHOT_NOT_FOUND = %s" % path)
        return 2
    tables = _load(path)
    real = tables.get("JBS_PWREAL", [])
    equip = tables.get("JBS_PWEQUIPINFO", [])
    term = tables.get("JBS_PWTERMINAL", [])
    zw_term = tables.get("JBS_ZWTERMINAL", [])

    keys = [(r.get("TRAN_ID"), r.get("DATA_DATE")) for r in real]
    n_dup = sum(1 for k, c in Counter(keys).items() if c > 1)

    bad1312 = sorted(
        {r.get("EQUIP_ID") for r in equip if str(r.get("EQUIP_TYPE")) == "1312"}
    )

    sw_types = {"SWITCH", "BREAKER", "LOAD_BREAK_SWITCH", "DISCONNECTOR", "刀闸", "负荷开关"}
    signals = {r.get("TRAN_ID") for r in real if r.get("POINT") not in (None, "")}
    no_point = sorted(
        r.get("EQUIP_ID")
        for r in equip
        if r.get("EQUIP_TYPE") in sw_types and r.get("EQUIP_ID") not in signals
    )

    eq_ids = {r.get("EQUIP_ID") for r in equip}
    orphan = sorted(
        {r.get("EQUIP_ID") for r in term + zw_term if r.get("EQUIP_ID") not in eq_ids}
    )

    no_cn = sum(1 for r in term + zw_term if not r.get("CONNECTIVITYNODE_ID"))

    print("DATA_QA_REPORT = %s" % path)
    print("PWREAL_ROWS = %d" % len(real))
    print("PWREAL_DUP_KEYS = %d" % n_dup)
    print("EQUIP_TYPE_1312_COUNT = %d" % len(bad1312))
    print("EQUIP_TYPE_1312_IDS = %s" % (bad1312 or "[]"))
    print("SWITCH_NO_POINT_COUNT = %d" % len(no_point))
    print("TERMINAL_ORPHAN_COUNT = %d" % len(orphan))
    print("TERMINAL_ORPHAN_IDS = %s" % (orphan or "[]"))
    print("TERMINAL_EMPTY_CN = %d" % no_cn)
    print("EQUIP_TOTAL = %d" % len(equip))
    print("EQUIP_TYPE_DIST = %s" % dict(sorted(Counter(r.get("EQUIP_TYPE") for r in equip).items())))
    print("VOLTAGE_DIST = %s" % dict(sorted(Counter(r.get("VOLTAGE_TYPE") for r in equip).items())))
    print("FEEDER_DIST = %s" % dict(sorted(Counter(r.get("FEEDER_ID") for r in equip).items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
