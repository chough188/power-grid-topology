"""Top-level xlsx writer for the official 12-task submission track.

Usage:
    from output_writer.writer import write_workbook
    from data_loader.snapshot import load_json_snapshot
    from tasks_official.execution import OfficialRunner

    ds = load_json_snapshot("data/snapshot.json")
    result = OfficialRunner().run(["1.1", "1.2", "1.3", "3.1"], ds)
    records = [r for recs in result.records_by_task.values() for r in recs]
    write_official_result(records, dataset=ds)  # → output/YYYYMMDD/YYYYMMDDHHMM_official_result.xlsx
"""
from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from openpyxl import Workbook

from . import sheet1_problems, sheet2_breaks, sheet3_ties, sheet4_loops, sheet5_scores, sheet6_dropdown
from .workbook_schema import SHEETS_BY_NAME
from shared.contract_gate import validate_output_contract

# v8.4 三根分离 I/O 约定: project_io.py 位于项目根 (电力拓扑图修正/),
# 从本文件 (02_算法代码/output_writer/writer.py) 回溯 parents[2] 即到。
# 输出落到 OUTPUT_ROOT/YYYYMMDD/YYYYMMDDHHMM_<name>.<ext>。
_PROJECT_ROOT = Path(os.environ.get("DIANLI_PROJECT_ROOT") or Path(__file__).resolve().parents[2])
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
try:
    from project_io import make_output_path, make_input_path, validate_isolation, assert_output_outside_project  # type: ignore
    _HAS_PROJECT_IO = True
    # 非严格校验: 隔离配置有问题时仅告警, 不阻断 (调试友好)
    _iso_issues = validate_isolation(strict=False)
    if _iso_issues:
        import warnings as _w
        _w.warn(f"[project_io] 数据隔离警告: {'; '.join(_iso_issues)}", stacklevel=1)
except Exception:
    make_output_path = None  # type: ignore
    make_input_path = None   # type: ignore
    assert_output_outside_project = None  # type: ignore
    _HAS_PROJECT_IO = False


def _remove_existing(wb: Workbook, names: Sequence[str]) -> None:
    for n in names:
        if n in wb.sheetnames:
            del wb[n]


def write_workbook(
    records: Sequence[Any],
    output_path: str | Path,
    dataset: Any | None = None,
    *,
    strict: bool = True,
) -> Path:
    """Render all six sheets and save to output_path.

    D16 内容级契约门禁：写出前对全部记录做 ``validate_output_contract`` 校验，
    任何字段不完整（空 task_code / 空 description / task_code 含空白 / 非 info
    却缺 device_id）都会阻断交付物写出并抛出 ``ValueError``，避免把残缺记录
    灌入正式成果（这正是此前“列数对但内容错”假绿的根因之一）。
    ``strict=False`` 时仅告警不阻断，供调试使用。
    """
    issues = validate_output_contract(records)
    if issues:
        msg = "输出契约校验未通过，已阻断写出:\n  - " + "\n  - ".join(issues)
        if strict:
            raise ValueError(msg)
        import warnings
        warnings.warn(msg, stacklevel=2)

    output_path = Path(output_path)
    # 数据隔离守卫: 确保输出路径不在项目目录内
    # strict=True 时强制检查; strict=False 时可选检查
    if assert_output_outside_project is not None:
        assert_output_outside_project(output_path)
    elif strict:
        raise RuntimeError(
            "数据隔离检查不可用 (project_io 模块未加载)，"
            "strict=True 要求必须验证输出路径在项目目录外，请检查 project_io.py"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    # Remove the auto-created default sheet
    _remove_existing(wb, wb.sheetnames)

    sheet1_problems.render(records, wb)
    sheet2_breaks.render(records, wb)
    sheet3_ties.render(records, wb, dataset=dataset)
    sheet4_loops.render(records, wb, dataset=dataset)
    sheet5_scores.render(records, wb, dataset=dataset)
    sheet6_dropdown.render(records, wb, dataset=dataset)

    wb.save(str(output_path))
    return output_path


def write_official_result(
    records: Sequence[Any],
    dataset: Any | None = None,
    *,
    name: str = "official_result",
    ext: str = "xlsx",
    strict: bool = True,
) -> Path:
    """[v8.3 I/O 约定] 将官方 6 表 xlsx 写到 ``output/YYYYMMDD/YYYYMMDDHHMM_<name>.<ext>``。

    ``write_workbook`` 的便捷封装, 自动套用项目级"当日子文件夹 + 分钟时间戳"约定
    (见 ``project_io.py``)。``name`` 用于区分多次运行 (例如 ``"validation"``、
    ``"subset_1.1-1.4"``)。返回写出的绝对路径。

    若 ``project_io`` 不可用, 抛 ``RuntimeError`` (此时仍可直接调用
    ``write_workbook(records, path, dataset)`` 传入完整路径)。
    """
    if not _HAS_PROJECT_IO or make_output_path is None:
        raise RuntimeError(
            "project_io 模块不可用, 无法应用 I/O 约定。"
            "请确保项目根的 project_io.py 存在, 或显式调用 write_workbook(records, path, dataset) 传入完整路径。"
        )
    out = make_output_path(name, ext=ext)
    return write_workbook(records, out, dataset=dataset, strict=strict)


__all__ = ["write_workbook", "write_official_result", "SHEETS_BY_NAME"]