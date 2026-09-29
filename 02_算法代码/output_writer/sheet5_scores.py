from .workbook_schema import SHEETS

SHEET = SHEETS[4]


def render(records, wb, dataset=None):
    """Sheet 5: 模型修正质量评分 — one row per (station, feeder).

    Priority of scores:
        1. Module 5 (5.0) self-grading records carry `before_score` /
           `after_score` in `extra`; use them directly.
        2. Otherwise fall back to a heuristic derived from record counts
           per (station, feeder) pair.
    """
    ws = wb.create_sheet(SHEET.name)
    ws.append(list(SHEET.columns))
    station_lookup = {}
    feeder_lookup = {}
    if dataset is not None:
        for s in dataset.tables.get("JBS_ZWSUBSTATION", ()):
            station_lookup[s.get("ST_ID")] = s.get("ST_NAME", "")
        for f in dataset.tables.get("JBS_PWFEEDERLINE", ()):
            feeder_lookup[f.get("LINE_ID")] = f.get("LINE_NAME", "")
    module5_by_key: dict = {}
    by_pair: dict = {}
    for rec in records:
        key = (rec.station_id, rec.feeder_id)
        if rec.task_code == "5.0":
            module5_by_key[key] = (
                rec.extra.get("before_score"),
                rec.extra.get("after_score"),
                rec.extra.get("station_name"),
                rec.extra.get("feeder_name"),
            )
        else:
            by_pair.setdefault(key, {"before": 0, "after": 0})
            by_pair[key]["before"] += 1
            by_pair[key]["after"] += 1
    rows: list = []
    for key, (before, after, st_name, fd_name) in sorted(module5_by_key.items(), key=lambda x: tuple(str(v) if v is not None else '' for v in x[0])):
        st, fd = key
        rows.append((
            station_lookup.get(st, st) or st_name or "",
            st,
            feeder_lookup.get(fd, fd) or fd_name or "",
            fd,
            round(before, 4) if before is not None else 0.0,
            round(after, 4) if after is not None else 0.0,
        ))
    if not rows:
        # Fallback: aggregate counts per pair
        for (st, fd), counts in sorted(by_pair.items(), key=lambda x: tuple(str(v) if v is not None else '' for v in x[0])):
            before_score = max(0.0, 1.0 - counts["before"] * 0.05)
            after_score = min(1.0, before_score + counts["after"] * 0.08)
            rows.append((
                station_lookup.get(st, st) or "",
                st,
                feeder_lookup.get(fd, fd) or "",
                fd,
                round(before_score, 3),
                round(after_score, 3),
            ))
    # Renumber from 1
    for i, row in enumerate(rows, start=1):
        ws.append((i,) + row)
    return ws
