from .workbook_schema import SHEETS

SHEET = SHEETS[3]


def render(records, wb, dataset=None):
    """Sheet 4: 非计划合环识别结果 — task 1.5 records."""
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
        if rec.task_code != "1.5":
            continue
        feeders = (rec.extra or {}).get("feeders", [])
        f0 = feeders[0] if feeders else ""
        f1 = feeders[1] if len(feeders) > 1 else ""
        # R11: fill 上级变电站名称 (column 3) from station_lookup of the loop's station
        upper_station = station_lookup.get(rec.station_id, "")
        ws.append([
            f0,
            feeder_lookup.get(f0, ""),
            upper_station,  # col3: 上级变电站名称
            f1,
            feeder_lookup.get(f1, ""),
            station_lookup.get(rec.station_id, ""),
            rec.device_id,
            rec.device_name,
            rec.correction_sql,
        ])
    return ws
