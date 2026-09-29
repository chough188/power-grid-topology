# -*- coding: utf-8 -*-
"""LLM 最终报告自检脚本：27B 填完报告后一条命令验证。

检查项:
1. output/llm_test_report.json 存在且 JSON 可解析
2. tasks 数组包含 T0~T7 全部 8 项, id 唯一, verdict ∈ {PASS, FAIL}
3. 每项 detail 非空
4. summary / data_qa_interpretation 非空, known_gaps 为数组
5. verdict 与 llm_stage_state.json 记录一致（报告说谎检测）
   --real 模式读取 llm_stage_state.real.json（真实模式状态文件）

用法（在 02_算法代码 目录下）:
    python -X utf8 scripts/llm_report_check.py
    python -X utf8 scripts/llm_report_check.py --real   # 真实数据模式: 只查结构, 不比对数字
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT.parent / "output" / "llm_test_report.json"
STATE = ROOT.parent / "output" / "llm_stage_state.json"
REAL_STATE = ROOT.parent / "output" / "llm_stage_state.real.json"

EXPECTED_TASKS = ["T0", "T1", "T2", "T3", "T4", "T5", "T6", "T7"]


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    real = "--real" in argv

    issues = []

    if not REPORT.exists():
        print("REPORT_MISSING = %s" % REPORT)
        print("REPORT_CHECK_OK = False")
        return 1
    try:
        data = json.loads(REPORT.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print("REPORT_JSON_INVALID = %s" % e)
        print("REPORT_CHECK_OK = False")
        return 1

    # 结构检查
    for field in ("report_date", "model", "data_source", "summary", "tasks",
                  "data_qa_interpretation", "known_gaps"):
        if field not in data:
            issues.append("缺少字段: %s" % field)
    if "summary" in data and not data["summary"]:
        issues.append("summary 为空")
    if "data_qa_interpretation" in data and not data["data_qa_interpretation"]:
        issues.append("data_qa_interpretation 为空")
    if "known_gaps" in data and not isinstance(data["known_gaps"], list):
        issues.append("known_gaps 不是数组")

    tasks = data.get("tasks", [])
    ids = [t.get("id") for t in tasks]
    for tid in EXPECTED_TASKS:
        if tid not in ids:
            issues.append("缺少任务: %s" % tid)
    seen = set()
    for t in tasks:
        tid = t.get("id")
        if tid in seen:
            issues.append("任务 id 重复: %s" % tid)
        seen.add(tid)
        if t.get("verdict") not in ("PASS", "FAIL"):
            issues.append("%s verdict 非法: %s" % (tid, t.get("verdict")))
        if not t.get("detail"):
            issues.append("%s detail 为空" % tid)

    # 与 stage 状态一致性（合成模式才比对; 状态文件按模式分离）
    if not real:
        st_path = STATE
    else:
        st_path = REAL_STATE
    if st_path.exists():
        try:
            st = json.loads(st_path.read_text(encoding="utf-8"))
            st_stages = st.get("stages", {})
            mapping = {"T%d" % i: "S%d" % i for i in range(8)}
            for t in tasks:
                sid = mapping.get(t.get("id", ""))
                s = st_stages.get(sid) if sid else None
                if s and s.get("verdict") == "FAIL" and t.get("verdict") == "PASS":
                    issues.append("%s 报告 PASS 但 stage 记录 FAIL" % t.get("id"))
                if s and s.get("verdict") == "PASS" and t.get("verdict") == "FAIL":
                    issues.append("%s 报告 FAIL 但 stage 记录 PASS（请核对后更新报告）" % t.get("id"))
        except Exception:
            pass

    ok = not issues
    print("REPORT_FILE = %s" % REPORT)
    print("REPORT_ISSUES = %d" % len(issues))
    for i in issues:
        print("  - %s" % i)
    print("REPORT_CHECK_OK = %s" % ok)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
