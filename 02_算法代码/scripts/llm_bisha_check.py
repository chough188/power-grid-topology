# -*- coding: utf-8 -*-
"""LLM 必杀题核验脚本：检查 1.2 断点定位输出是否包含官方必杀对 + T3 输入对。

用法（在 02_算法代码 目录下）:
    python -X utf8 scripts/llm_bisha_check.py [数据路径，默认 data/snapshot.json]
数据路径支持：.json 快照 / .sql 文件（含 INSERT）/ 含 *.sql 的目录（15 分表自动合并）。

输出固定格式，供本地大模型逐行解析：
    T1_HIT = True/False    (TMP00013138 <-> TMP00047197, 必杀)
    T2_HIT = True/False    (TMP00007913 <-> TMP00007907, 必杀)
    T3_HIT = True/False    (TMP00012903 <-> TMP00047124, 0821 新增输入对/负对照)
    BISHA_OK = True/False  (仅由真正的必杀对 T1&T2 决定; T3 为信息项)

说明: T3 在真实数据中真正连通(148 节点全闭合路径、无分位开关), 按 Q&A2/Q16
正确不报告 → T3_HIT 通常为 False 属预期; 仅当数据中该对断开时才应为 True。
"""
from __future__ import annotations

import sys
from pathlib import Path


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    path = Path(argv[0]) if argv else Path("data/snapshot.json")
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from data_loader.universal import load_dataset
    from tasks_official.execution import OfficialRunner

    ds = load_dataset(path)
    result = OfficialRunner().run(["1.2"], ds)
    recs = result.records_by_task.get("1.2", ())

    def hit(a: str, b: str) -> bool:
        return any(
            (r.device_id == a and (r.extra or {}).get("target_id") == b)
            or (r.device_id == b and (r.extra or {}).get("target_id") == a)
            for r in recs
        )

    t1 = hit("TMP00013138", "TMP00047197")
    t2 = hit("TMP00007913", "TMP00007907")
    t3 = hit("TMP00012903", "TMP00047124")
    print("SNAPSHOT = %s" % path)
    print("T1_HIT = %s" % t1)
    print("T2_HIT = %s" % t2)
    print("T3_HIT = %s" % t3)
    # BISHA_OK 仅由真正的必杀对 T1&T2 决定; T3 为负对照/信息项(真实数据连通, 正确不报告)
    print("BISHA_OK = %s" % (t1 and t2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
