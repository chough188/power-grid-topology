# -*- coding: utf-8 -*-
"""根因抑制（A.2）。

已知根因的下游衍生告警降级为 info。
"""
from __future__ import annotations
from typing import Dict, Any, List

SUPPRESSION_RULES = {
    "topo_interrupt": ["load_shift", "voltage_collapse", "branch_contingency"],
    "voltage_collapse": ["bus_section_mismatch"],
    "protection_misconfig": ["trafo_tap_fault"],
    "model_mismatch": ["ghost_topology", "topo_obfuscation"],
    "grounding_fault": ["voltage_regulation"],
}


def _infer_root_causes(anomalies):
    rc = set()
    for a in anomalies:
        t = a.get("type", "")
        c = float(a.get("confidence", 0) or 0)
        if t in SUPPRESSION_RULES and c >= 0.8:
            rc.add(t)
    return rc


def suppress(anomalies, network_data=None):
    """抑制下游衍生告警。被抑制的加 _suppressed_by, severity 改 info。"""
    root_causes = _infer_root_causes(anomalies)
    if not root_causes:
        return anomalies
    rev = {}
    for rc, derivatives in SUPPRESSION_RULES.items():
        if rc in root_causes:
            for d in derivatives:
                rev.setdefault(d, []).append(rc)
    for a in anomalies:
        t = a.get("type", "")
        if t in rev:
            a["_suppressed_by"] = rev[t][0]
            a["_suppressed_all"] = rev[t]
            a["severity"] = "info"
            a["_suppressed"] = True
    return anomalies


if __name__ == "__main__":
    sample = [
        {"type":"topo_interrupt","location":"line_1","confidence":0.95},
        {"type":"load_shift","location":"line_1","confidence":0.85},
        {"type":"voltage_collapse","location":"bus_5","confidence":0.90},
        {"type":"branch_contingency","location":"line_3","confidence":0.75},
    ]
    out = suppress(sample)
    for a in out:
        print(a["type"], "sev=" + a.get("severity","-"), "sup=" + str(a.get("_suppressed", False)))
