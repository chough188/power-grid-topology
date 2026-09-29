# -*- coding: utf-8 -*-
"""D16 内容级输出契约门禁（置于 shared 公共层，供 output_writer 与 tasks_official 共用）.

仅依赖记录的鸭子类型接口（``task_code`` / ``device_id`` / ``severity`` /
``description`` 属性），不引入 ``tasks_official`` 依赖，以满足架构分层约束：
common 层（shared / data_loader / output_writer）不得依赖 official 任务轨道。

用于写出 Excel 前的最后一道检查，避免把字段缺失的记录写进交付物。
说明：correction_sql 允许为空（1.4/3.1/5.0 等"仅注不修"类任务合法），
此处不强制。
"""
from __future__ import annotations

from collections.abc import Sequence


def validate_output_contract(records: Sequence[object]) -> tuple[str, ...]:
    """Dry-run 门禁：校验记录核心字段完整性，返回问题清单（空元组=通过）。

    用于写出 Excel 前的最后一道检查，避免把字段缺失的记录写进交付物。
    说明：correction_sql 允许为空（1.4/3.1/5.0 等"仅注不修"类任务合法），
    此处不强制。
    """
    issues: list[str] = []
    for rec in records:
        task_code = getattr(rec, "task_code", None)
        if not task_code:
            issues.append("记录缺少 task_code")
            # 不 continue：空 task_code 的记录仍需校验 description 等其余字段
        device_id = getattr(rec, "device_id", None)
        severity = getattr(rec, "severity", None)
        if not device_id and severity != "info":
            issues.append(f"{task_code}: device_id 为空")
        description = getattr(rec, "description", None)
        if not description:
            issues.append(f"{task_code}/{device_id or '?'}: description 为空")
        if task_code != task_code.strip():
            issues.append(f"{task_code}: task_code 含空白")
    return tuple(issues)


__all__ = ["validate_output_contract"]
