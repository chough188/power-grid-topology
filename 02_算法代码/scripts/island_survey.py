# -*- coding: utf-8 -*-
"""批量调查问题文件中的孤岛设备：类型、自有引用、悬空引用与岛ID的数值关系、周边同层设备。

用法: python -X utf8 scripts/island_survey.py <svg目录或文件...> [--limit N]
输出: 每文件一段紧凑摘要（stdout）。
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT_NS = "{http://www.w3.org/2000/svg}"
NS2 = "{http://iec.ch/TC57/2005/SVG-schema#}"

STATION_BUILDING_TYPES = {
    "zf01", "zf04", "zf06", "zf07", "zf08", "zf09", "0323", "0324",
    "ZF01", "substation", "STATION", "BUILDING", "ROOM",
    "站房", "配电房", "环网柜", "箱变",
}


def _num(oid: str) -> int | None:
    m = re.search(r"(\d+)$", oid)
    return int(m.group(1)) if m else None


def survey(path: Path) -> list[dict]:
    tree = ET.parse(str(path))
    root = tree.getroot()
    devs = {}
    for g in root.iter(ROOT_NS + "g"):
        gid = g.get("id", "")
        if not gid.startswith("TMP_"):
            continue
        psr = None
        refs = []
        layer = "?"
        for md in g.findall(ROOT_NS + "metadata"):
            for mc in md:
                t = mc.tag.replace(NS2, "")
                if t == "PSR_Ref":
                    psr = mc
                elif t == "GLink_Ref":
                    refs.append(mc.get("ObjectID", ""))
                elif t == "Layer_Ref":
                    layer = mc.get("ObjectName", "?")
        if psr is None:
            continue
        oid = psr.get("ObjectID", "")
        if not oid or oid in devs:
            continue
        devs[oid] = {"layer": layer, "psr": psr.get("PSRType", ""), "name": psr.get("ObjectName", ""), "refs": refs}

    deg = {o: 0 for o in devs}
    for o, d in devs.items():
        for r in d["refs"]:
            if r != o and r in devs:
                deg[o] += 1
                deg[r] += 1

    out = []
    for o, d in devs.items():
        if deg[o] == 0 and d["psr"] not in STATION_BUILDING_TYPES:
            missing = [r for r in d["refs"] if r not in devs]
            existing = [r for r in d["refs"] if r in devs]
            rec = {
                "id": o, "layer": d["layer"], "psr": d["psr"], "name": d["name"],
                "refs": d["refs"], "missing": missing, "existing": existing,
                "id_num": _num(o),
            }
            # 悬空引用与岛ID的差值
            for m in missing:
                mn = _num(m)
                rec[f"delta_{m}"] = (mn - rec["id_num"]) if (mn is not None and rec["id_num"] is not None) else None
            # 同层非孤岛设备中，ID数值最接近的3个
            same_layer = [(abs((_num(x) or 0) - (rec["id_num"] or 0)), x) for x, dd in devs.items()
                          if x != o and dd["layer"] == d["layer"] and deg[x] > 0 and _num(x) is not None]
            same_layer.sort()
            rec["near_ids"] = [x for _, x in same_layer[:4]]
            out.append(rec)
    return out


def main():
    paths = []
    limit = 5
    args = sys.argv[1:]
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])
        args = [a for i, a in enumerate(args) if a != "--limit" and (i == 0 or args[i - 1] != "--limit")]
    for a in args:
        p = Path(a)
        if p.is_dir():
            paths.extend(sorted(p.glob("*.svg")))
        elif p.is_file():
            paths.append(p)
    paths = paths[:limit]
    for p in paths:
        try:
            islands = survey(p)
        except Exception as e:
            print(f"### {p.name}: ERROR {e}")
            continue
        print(f"### {p.name}: islands={len(islands)}")
        for r in islands:
            deltas = {k.split("_", 1)[1]: v for k, v in r.items() if k.startswith("delta_")}
            print(f"  {r['id']} {r['layer']}/{r['psr']} '{r['name']}' refs={r['refs']} "
                  f"missing={r['missing']} deltas={deltas} near_same_layer={r['near_ids']}")
    print("SURVEY_DONE files=%d" % len(paths))


if __name__ == "__main__":
    main()
