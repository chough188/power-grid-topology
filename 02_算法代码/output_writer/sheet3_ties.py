from .workbook_schema import SHEETS

SHEET = SHEETS[2]


def render(records, wb, dataset=None):
    """Sheet 3: 联络开关自动识别结果 — task 1.3 (确认联络) records.

    契约约束（offline_contracts.contract.validate_output_book）:
    「是否有联络」∈ {None, "是", "否"}，不允许 "疑似"。
    故 1.4 疑似联络不进入本表（其记录仍完整保留在 Sheet1 问题清单与
    5.3.2 馈线联络关系 SVG 图中），本表仅承载 1.3 确认联络（全部为「是」）。

    NO_TIE sentinel（extra.result == "no_TIE" / device_id == "NO_TIE"）不渲染：
    它不是联络开关，若以「是」+占位 ID 成行会误导评审；无确认联络时本表
    只保留表头（诚实输出），sentinel 仍完整保留在 Sheet1 问题清单中。
    """
    ws = wb.create_sheet(SHEET.name)
    ws.append(list(SHEET.columns))
    feeder_lookup = {}
    if dataset is not None:
        for f in dataset.tables.get("JBS_PWFEEDERLINE", ()):
            feeder_lookup[f.get("LINE_ID")] = f.get("LINE_NAME", "")
    station_lookup = {}
    if dataset is not None:
        for s in dataset.tables.get("JBS_ZWSUBSTATION", ()):
            station_lookup[s.get("ST_ID")] = s.get("ST_NAME", "")
    for rec in records:
        if rec.task_code != "1.3":
            continue
        extra = rec.extra or {}
        # NO_TIE sentinel 不成行（见 docstring）：无确认联络时本表仅留表头
        if extra.get("result") == "no_TIE" or str(rec.device_id) in ("", "NO_TIE"):
            continue
        # 1.3 确认联络 → 「是」（Bug#76 回退后本表无 filler 行, 无需「否」分支）
        has_tie = "是"
        stations = extra.get("stations", [])
        ws.append([
            rec.feeder_id or "",
            feeder_lookup.get(rec.feeder_id, ""),
            station_lookup.get(stations[0] if stations else "", ""),
            rec.device_id,
            rec.device_name,
            has_tie,
            extra.get("tie_line_id", ""),       # col7: 联络线路id
            extra.get("tie_line_name", ""),      # col8: 联络线路名称
            extra.get("tie_line_station", ""),   # col9: 联络线变电站名称
        ])
    return ws