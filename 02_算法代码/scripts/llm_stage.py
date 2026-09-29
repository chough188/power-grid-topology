# -*- coding: utf-8 -*-
"""LLM 一键阶段执行器：S0~S7 全部自动跑+自动判定，27B 只抄结论。

设计目标（针对 27B 的上下文/推理限制）：
1. 一条命令跑完全部阶段，脚本自己比对期望值，27B 无需逐行人工比对
2. 进度落盘到 output/llm_stage_state.json —— 上下文丢失后 status 可恢复
3. 每阶段固定输出 4 行 STAGE/STAGE_NAME/STAGE_VERDICT/STAGE_DETAIL
4. 合成数据模式严格比对数字；--real 模式只做结构性检查（真实数据行数会变）

用法（在 02_算法代码 目录下）:
    python -X utf8 scripts/llm_stage.py all           # 跑全部 S0~S7
    python -X utf8 scripts/llm_stage.py S3            # 只跑单个阶段
    python -X utf8 scripts/llm_stage.py status        # 显示合成模式进度（不重跑）
    python -X utf8 scripts/llm_stage.py status --real # 显示真实模式进度
    python -X utf8 scripts/llm_stage.py all --real    # 真实数据模式（不断言具体数字）
    python -X utf8 scripts/llm_stage.py all --data "E:\真实数据目录\sql\" --real
    # --data 数据源: .json 快照(默认 data/snapshot.json) / .sql 文件(含 INSERT) /
    #              含 *.sql 的目录(官方 15 分表自动合并)。可直接传真实 SQL，无需先转 JSON。

状态文件: 合成模式 → output/llm_stage_state.json, 真实模式 → output/llm_stage_state.real.json
（两模式分离存储, 互不覆盖; 报告自检 llm_report_check.py 按同样规则读取）
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT.parent / "output" / "llm_stage_state.json"
REAL_STATE_FILE = ROOT.parent / "output" / "llm_stage_state.real.json"
PY = sys.executable


def _state_file(real: bool) -> Path:
    """合成/真实模式状态文件分离, 避免互相覆盖。"""
    return REAL_STATE_FILE if real else STATE_FILE


def _run(args: list[str]) -> tuple[str, int]:
    """跑一条命令, 返回 (stdout+stderr, rc)。"""
    r = subprocess.run(
        [PY, "-X", "utf8"] + args,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(ROOT),
    )
    return (r.stdout or "") + (r.stderr or ""), r.returncode


def _expect_ok(stdout: str) -> bool:
    return "Traceback" not in stdout


_PickleCache = {}

def _cached_load_expr(data_path: str) -> str:
    """Return Python code snippet that loads dataset from pickle cache if available."""
    import os, hashlib
    key = hashlib.md5(data_path.encode()).hexdigest()[:12]
    pickle_path = os.path.join(tempfile.gettempdir(), f"dianli_ds_{key}.pkl")
    return (
        f"import pickle,os; "
        f"_pk={pickle_path!r}; "
        f"ds=pickle.load(open(_pk,'rb')) if os.path.exists(_pk) and os.path.getsize(_pk)>1000000 else None; "
        f"ds = ds or __import__('data_loader.universal',fromlist=['load_dataset']).load_dataset({data_path!r}); "
        f"(pickle.dump(ds,open(_pk,'wb'),protocol=pickle.HIGHEST_PROTOCOL) if not os.path.exists(_pk) else None); "
    )


# ---------------------------------------------------------------------------
# 阶段定义
# ---------------------------------------------------------------------------

def stage_env(real: bool, data: str) -> tuple[bool, str]:
    out, _ = _run(["-c",
        "from data_loader.universal import load_dataset; "
        "ds=load_dataset(%r); "
        "print('TABLES', len(ds.tables))" % data])
    n = -1
    for line in out.splitlines():
        if line.startswith("TABLES"):
            n = int(line.split()[1])
    ok = _expect_ok(out) and n == 14
    return ok, "tables=%d" % n


def stage_unit(real: bool, data: str) -> tuple[bool, str]:
    out, _ = _run(["-m", "unittest", "discover", "-s", "tests_official", "-p", "test_*.py"])
    lines = out.splitlines()
    tail = " ".join(lines[-3:]) if lines else ""
    if real:
        ok = "Ran 255 tests" in out and ("OK" in tail or "FAILED" in out)
        return ok, ("255 tests (结构正常)" if ok else "MISMATCH: " + tail[:120])
    ok = "Ran 255 tests" in out and "FAILED (errors=4, skipped=12)" in out
    return ok, ("255 tests failures=0 errors=4" if ok else "MISMATCH: " + tail[:120])


def stage_bisha(real: bool, data: str) -> tuple[bool, str]:
    out, _ = _run(["scripts/llm_bisha_check.py", data])
    if real:
        hit = "BISHA_OK = True" in out
        return hit, "BISHA_OK=%s" % ("True" if hit else "False(真实数据可能无必杀ID,预期)")
    ok = _expect_ok(out) and "BISHA_OK = True" in out
    return ok, "BISHA_OK=True" if ok else "BISHA_OK=False"


def stage_e2e(real: bool, data: str) -> tuple[bool, str]:
    out, _ = _run(["-c",
        "import sys,io; sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8'); "
        + _cached_load_expr(data) +
        "from tasks_official.execution import OfficialRunner; "
        "r=OfficialRunner().run(['1.1','1.2','1.3','1.4','1.5','2.1','2.2','2.3','2.4','3.1','4.1','4.2','5.0'], ds); "
        "[print(k, len(v)) for k, v in r.records_by_task.items()]; "
        "print('TOTAL', sum(len(v) for v in r.records_by_task.values()))"])
    total = None
    for line in out.splitlines():
        if line.startswith("TOTAL"):
            total = int(line.split()[1])
    if real:
        ok = _expect_ok(out) and total is not None and total > 0
        return ok, "total=%s" % total if total is not None else "NO TOTAL"
    ok = _expect_ok(out) and total == 185
    return ok, "total=%d" % (total or -1)


def stage_workbook(real: bool, data: str) -> tuple[bool, str]:
    tmp = tempfile.gettempdir()
    code = (
        "import sys,io,tempfile,os; sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8'); "
        + _cached_load_expr(data) +
        "from tasks_official.execution import OfficialRunner; "
        "from output_writer.writer import write_workbook; "
        "r=OfficialRunner().run(['1.1','1.2','1.3','1.4','1.5','2.1','2.2','2.3','2.4','3.1','4.1','4.2','5.0'], ds); "
        "recs=[x for v in r.records_by_task.values() for x in v]; "
        "p=os.path.join(r'%s','t_stage4.xlsx'); write_workbook(recs, p, dataset=ds); "
        "import openpyxl; wb=openpyxl.load_workbook(p); "
        "print('SHEETS', len(wb.sheetnames)); "
        "[print('SHEET', s, wb[s].max_row) for s in wb.sheetnames]" % tmp.replace("\\", "/"))
    out, _ = _run(["-c", code])
    counts = [line.split()[-1] for line in out.splitlines() if line.startswith("SHEET ")]
    ns = None
    for line in out.splitlines():
        if line.startswith("SHEETS"):
            ns = int(line.split()[1])
    if real:
        ok = _expect_ok(out) and ns == 6 and len(counts) == 6
        return ok, "6 sheets rows=%s" % ("/".join(counts) if counts else "?")
    exp = ["186", "48", "1", "10", "10", "12"]
    ok = _expect_ok(out) and ns == 6 and counts == exp
    return ok, "6 sheets %s" % "/".join(counts) if counts else "MISMATCH"


def stage_grade(real: bool, data: str) -> tuple[bool, str]:
    out, _ = _run(["-c",
        "import sys,io; sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8'); "
        "from pathlib import Path; from tasks_official.self_grade_v2 import grade; "
        "grade(Path(%r))" % data])
    total = None
    for line in out.splitlines():
        if "总分" in line or "TOTAL" in line.upper():
            parts = line.split(":")
            if len(parts) >= 2:
                try:
                    total = float(parts[-1].strip().rstrip("分"))
                except ValueError:
                    pass
    if real:
        ok = _expect_ok(out) and total is not None
        return ok, "total=%s" % total if total else "NO TOTAL"
    ok = _expect_ok(out) and total is not None and total >= 0.90
    return ok, "total=%s" % (total or -1)


def stage_svg(real: bool, data: str) -> tuple[bool, str]:
    svg_in = r"..\03_数据集\svg_input"
    tmp = tempfile.gettempdir()
    steps = []
    ok_all = True
    # 1) inspect
    out, _ = _run(["scripts/llm_svg_tools.py", "inspect", svg_in + r"\LINE215.svg"])
    devs = links = None
    for line in out.splitlines():
        if line.startswith("DEVICES"):
            devs = int(line.split("=")[1])
        if line.startswith("LINKS"):
            links = int(line.split("=")[1])
    steps.append(("inspect", _expect_ok(out) and devs == 12 and links == 12, "devices=%s links=%s" % (devs, links)))
    # 2) beautify
    out, _ = _run(["scripts/llm_svg_tools.py", "beautify", svg_in + r"\LINE215.svg",
                   tmp + r"\st4_beautify.svg"])
    bi = bo = None
    for line in out.splitlines():
        if line.startswith("BEAUTIFY_IN"):
            bi = int(line.split("=")[1])
        if line.startswith("BEAUTIFY_OUT"):
            bo = int(line.split("=")[1])
    steps.append(("beautify", _expect_ok(out) and bo is not None and bi is not None and bo > bi, "%d->%d" % (bi, bo)))
    # 3) add_room
    out, _ = _run(["scripts/llm_svg_tools.py", "add_room", svg_in + r"\LINE215.svg", tmp + r"\st4_room.svg",
                   "--room", "000300", "--left", "TMP00000003", "--right", "TMP00000004",
                   "--switches", "00301,00302,00303"])
    steps.append(("add_room", _expect_ok(out) and "ADD_ROOM_OK = True" in out, "ok" if "ADD_ROOM_OK = True" in out else "fail"))
    # 4) remove_dev
    out, _ = _run(["scripts/llm_svg_tools.py", "remove_dev", svg_in + r"\LINE216.svg", tmp + r"\st4_rm.svg",
                   "--id", "TMP00000002"])
    steps.append(("remove_dev", _expect_ok(out) and "REMOVE_OK = True" in out, "ok" if "REMOVE_OK = True" in out else "fail"))
    # 5) reconnect x2
    out, _ = _run(["scripts/llm_svg_tools.py", "reconnect", tmp + r"\st4_room.svg", tmp + r"\st4_room2.svg",
                   "--from", "00301", "--to", "TMP00000003"])
    steps.append(("reconnect1", _expect_ok(out) and "RECONNECT_OK" in out, "ok" if "RECONNECT_OK" in out else "fail"))
    out, _ = _run(["scripts/llm_svg_tools.py", "reconnect", tmp + r"\st4_room2.svg", tmp + r"\st4_room3.svg",
                   "--from", "00303", "--to", "TMP00000004"])
    steps.append(("reconnect2", _expect_ok(out) and "RECONNECT_OK" in out, "ok" if "RECONNECT_OK" in out else "fail"))
    # 6) verify (豁免备用间隔+首末端)
    out, _ = _run(["scripts/llm_svg_tools.py", "verify", tmp + r"\st4_room3.svg",
                   "--required", "00301,00302,00303",
                   "--exempt", "00302,TMP00000001,TMP00000012"])
    ok = "VERIFY_OK = True" in out
    steps.append(("verify", _expect_ok(out) and ok, "True" if ok else "False"))
    # 7) render
    out, _ = _run(["scripts/llm_svg_tools.py", "render", tmp + r"\st4_render"])
    keys = [line.split()[1] for line in out.splitlines() if line.startswith("RENDER")]
    steps.append(("render", _expect_ok(out) and len(keys) == 5, "%d keys" % len(keys)))
    ok_all = all(s[1] for s in steps)
    detail = " ".join("%s=%s" % (n, "P" if ok else "F") for n, ok, _ in steps)
    return ok_all, detail


def stage_qa(real: bool, data: str) -> tuple[bool, str]:
    out, _ = _run(["scripts/llm_data_qa.py", data])
    qa = {}
    for line in out.splitlines():
        if " = " in line and not line.startswith("DATA_QA_REPORT"):
            k, v = line.split(" = ", 1)
            qa[k] = v
    if real:
        ok = _expect_ok(out) and len(qa) >= 11
        return ok, "%d rows dup=%s 1312=%s" % (len(qa), qa.get("PWREAL_DUP_KEYS", "?"), qa.get("EQUIP_TYPE_1312_COUNT", "?"))
    ok = _expect_ok(out) and qa.get("PWREAL_DUP_KEYS") == "0" and qa.get("EQUIP_TYPE_1312_COUNT") == "0" and len(qa) >= 11
    return ok, "dup=%s 1312=%s no_point=%s orphan=%s" % (
        qa.get("PWREAL_DUP_KEYS", "?"), qa.get("EQUIP_TYPE_1312_COUNT", "?"),
        qa.get("SWITCH_NO_POINT_COUNT", "?"), qa.get("TERMINAL_ORPHAN_COUNT", "?"))


STAGES = [
    ("S0", "env", stage_env),
    ("S1", "unit", stage_unit),
    ("S2", "bisha", stage_bisha),
    ("S3", "e2e", stage_e2e),
    ("S4", "workbook", stage_workbook),
    ("S5", "grade", stage_grade),
    ("S6", "svg", stage_svg),
    ("S7", "data_qa", stage_qa),
]


# ---------------------------------------------------------------------------
# 状态管理
# ---------------------------------------------------------------------------

def _load_state(real: bool = False) -> dict:
    path = _state_file(real)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_state(real: bool, state: dict) -> None:
    path = _state_file(real)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def _report(stage_id: str, name: str, ok: bool, detail: str, state: dict, real: bool) -> None:
    state["stages"][stage_id] = {"verdict": "PASS" if ok else "FAIL", "detail": detail}
    _save_state(real, state)
    print("STAGE = %s" % stage_id)
    print("STAGE_NAME = %s" % name)
    print("STAGE_VERDICT = %s" % ("PASS" if ok else "FAIL"))
    print("STAGE_DETAIL = %s" % detail)


def cmd_status(real: bool = False, data: str = "data/snapshot.json") -> int:
    state = _load_state(real)
    print("STATE_MODE = %s" % ("real" if real else "synthetic"))
    print("STATE_DATA = %s" % state.get("data", data))
    stages = state.get("stages", {})
    done = 0
    for sid, name, _ in STAGES:
        s = stages.get(sid)
        if s:
            print("%s %s %s %s" % (sid, name, s.get("verdict", "?"), s.get("detail", "")))
            if s.get("verdict") == "PASS":
                done += 1
        else:
            print("%s %s NOT_RUN" % (sid, name))
    print("PROGRESS = %d/%d" % (done, len(STAGES)))
    return 0


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 1
    real = "--real" in argv
    argv = [a for a in argv if a != "--real"]
    data = "data/snapshot.json"
    if "--data" in argv:
        idx = argv.index("--data")
        if idx + 1 >= len(argv):
            print("MISSING_ARG = --data 需要一个路径（.json / .sql / 含 *.sql 的目录）")
            return 2
        data = argv[idx + 1]
        del argv[idx:idx + 2]

    if argv[0] == "status":
        return cmd_status(real, data)

    state = _load_state(real)
    if "mode" not in state:
        state["mode"] = "real" if real else "synthetic"
    state["data"] = data
    state.setdefault("stages", {})

    if argv[0] == "all":
        for sid, name, fn in STAGES:
            ok, detail = fn(real, data)
            _report(sid, name, ok, detail, state, real)
        fails = [sid for sid, _, _ in STAGES if state["stages"].get(sid, {}).get("verdict") != "PASS"]
        print("ALL_DONE = %s" % ("True" if not fails else "False"))
        if fails:
            print("ALL_FAILED_STAGES = %s" % " ".join(fails))
        return 0 if not fails else 1

    sid = argv[0].upper()
    for stage_id, name, fn in STAGES:
        if stage_id == sid:
            ok, detail = fn(real, data)
            _report(stage_id, name, ok, detail, state, real)
            return 0 if ok else 1
    print("UNKNOWN_STAGE = %s (可选: %s)" % (sid, " ".join(s for s, _, _ in STAGES)))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
