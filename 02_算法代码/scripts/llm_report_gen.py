# -*- coding: utf-8 -*-
"""LLM 最终报告初稿生成器：27B 一键生成，只审核不抄写。

数字全部来自 stdout / 状态文件：
- tasks 数组：从 output/llm_stage_state[.real].json 的 S0~S7 生成（verdict/detail 直接抄，天然与 stage 一致）
- data_source：状态文件记录的数据源（--data 路径）
- data_qa_interpretation：重跑一次 llm_data_qa 自动填模板（空转填空，无判断负担）
- known_gaps：判断性内容，留给 27B 填写（生成空数组 + 提示）

用法（在 02_算法代码 目录下）:
    python -X utf8 scripts/llm_report_gen.py                      # 合成模式
    python -X utf8 scripts/llm_report_gen.py --real --data "E:\真实数据目录\sql\"
    python -X utf8 scripts/llm_report_gen.py --model qwen3.6-27b --out 报告路径
生成后跑 scripts/llm_report_check.py [--real] 自检；REPORT_CHECK_OK = True 即通过。
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT.parent / "output" / "llm_stage_state.json"
REAL_STATE = ROOT.parent / "output" / "llm_stage_state.real.json"
REPORT = ROOT.parent / "output" / "llm_test_report.json"
PY = sys.executable

TASK_NAMES = {
    "T0": "S0 env", "T1": "S1 unit", "T2": "S2 bisha", "T3": "S3 e2e",
    "T4": "S4 workbook", "T5": "S5 grade", "T6": "S6 svg", "T7": "S7 data_qa",
}


def _run(args: list[str]) -> tuple[str, int]:
    r = subprocess.run([PY, "-X", "utf8"] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=str(ROOT))
    return (r.stdout or "") + (r.stderr or ""), r.returncode


def _parse_kv(stdout: str) -> dict:
    kv = {}
    for line in stdout.splitlines():
        if " = " in line and not line.startswith("DATA_QA_REPORT"):
            k, v = line.split(" = ", 1)
            kv[k] = v
    return kv


def _build_data_qa_interpretation(data: str) -> str:
    out, _ = _run(["scripts/llm_data_qa.py", data])
    qa = _parse_kv(out)
    rows = qa.get("PWREAL_ROWS", "?")
    dup = qa.get("PWREAL_DUP_KEYS", "?")
    bad1312 = qa.get("EQUIP_TYPE_1312_COUNT", "?")
    no_point = qa.get("SWITCH_NO_POINT_COUNT", "?")
    orphan = qa.get("TERMINAL_ORPHAN_COUNT", "?")
    no_cn = qa.get("TERMINAL_EMPTY_CN", "?")
    dist = qa.get("EQUIP_TYPE_DIST", "{}")
    volt = qa.get("VOLTAGE_DIST", "{}")
    try:
        dist_dict = json.loads(dist)
        switch_kinds = {"SWITCH", "BREAKER", "DISCONNECTOR", "LOAD_BREAK_SWITCH", "FUSE",
                        "刀闸", "负荷开关", "断路器", "UNKNOWN"}
        sw_total = sum(v for k, v in dist_dict.items() if k in switch_kinds)
    except Exception:
        sw_total = "?"
    try:
        pct = "%.1f%%" % (int(no_point) / sw_total * 100) if isinstance(sw_total, int) and sw_total else "?"
    except Exception:
        pct = "?"
    dup_note = "数据干净" if str(dup) == "0" else "存在重复，需按 TRAN_ID+DATA_DATE 去重处理"
    return (
        "【数据体检解读】1. 遥信遥测去重：共 %s 条记录，重复 %s 条 → %s。"
        "2. 设备类型 1312：%s 条。3. 开关类设备无遥信记录：%s 台，占开关类(%s 台)的 %s，"
        "需按官方口径默认合位处理。4. 拓扑端点孤儿：%s 个（与任务 4.1 主配接口相关）。"
        "5. 空连接节点(CN)端点：%s 个。6. 设备构成：%s；电压等级 %s。"
        "7. 结论：以 data_qa 实际 stdout 为准填写，重点核查无遥信开关占比与孤儿端点。"
        % (rows, dup, dup_note, bad1312, no_point, sw_total, pct, orphan, no_cn, dist, volt))


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser(description="LLM report draft generator")
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--data", default="data/snapshot.json",
                        help="数据源: .json / .sql / 含 *.sql 的目录")
    parser.add_argument("--model", default="qwen3.6-27b")
    parser.add_argument("--out", default=str(REPORT))
    args = parser.parse_args(argv)

    st_path = REAL_STATE if args.real else STATE
    if not st_path.exists():
        print("STAGE_STATE_MISSING = %s" % st_path)
        print("REPORT_GEN = False")
        return 1
    state = json.loads(st_path.read_text(encoding="utf-8"))
    stages = state.get("stages", {})
    tasks = []
    for i in range(8):
        sid = "S%d" % i
        s = stages.get(sid) or {"verdict": "NOT_RUN", "detail": "stage 未运行"}
        tasks.append({"id": "T%d" % i, "verdict": s.get("verdict"), "detail": s.get("detail", "")})
    fails = [t["id"] for t in tasks if t["verdict"] != "PASS"]
    summary = "T0~T7 全部 PASS" if not fails else "%s FAIL：%s" % (len(fails), " ".join(fails))

    report = {
        "report_date": date.today().isoformat(),
        "model": args.model,
        "data_source": "%s (%s)" % (state.get("data", args.data), "real" if args.real else "synthetic"),
        "summary": summary,
        "tasks": tasks,
        "data_qa_interpretation": _build_data_qa_interpretation(args.data),
        "known_gaps": [],
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("REPORT_GEN = %s" % out_path)
    print("GEN_SUMMARY = %s" % summary)
    print("GEN_VERDICTS = %s" % " ".join("%s=%s" % (t["id"], t["verdict"]) for t in tasks))
    print("GEN_NOTE = 请补充 known_gaps（判断性内容）；如 T2/T5/T6 想补明细数字，可手工在 detail 追加")
    chk, _ = _run(["scripts/llm_report_check.py"] + (["--real"] if args.real else []))
    print(chk.rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
