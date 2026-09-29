from .workbook_schema import SHEETS

SHEET = SHEETS[1]


def render(records, wb):
    """Sheet 2: 拓扑连通性异常诊断与断点定位结果 — task 1.2 records.

    严格对齐官方 xlsx: 11 列(10 个有名称 + 1 个表头为 None 的备注列,数据行用于备注/示例说明)。
    """
    ws = wb.create_sheet(SHEET.name)
    # 表头取 schema.columns(已含 11 个槽位,最后一列为 None),不要重复追加。
    ws.append(list(SHEET.columns))
    for idx, rec in enumerate(records, start=1):
        if rec.task_code != "1.2":
            continue
        extra = rec.extra or {}
        suspect_id = extra.get("suspect_switch_id", rec.device_id)
        suspect_name = extra.get("suspect_switch_name", rec.device_name)
        peer_id = extra.get("peer_switch_id", extra.get("target_id", ""))
        peer_name = extra.get("peer_switch_name", extra.get("target_name", ""))
        ws.append([
            idx,
            rec.device_id,
            extra.get("target_id", ""),
            extra.get("break_type", "馈线内断点"),
            suspect_id,
            suspect_name,
            peer_id,
            peer_name,
            rec.correction,
            rec.correction_sql,
            "",  # 第 11 列备注
        ])
    return ws
