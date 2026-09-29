# -*- coding: utf-8 -*-
"""异常处置优先级排序（Phase 15.1）。

priority = severity_weight * impact * urgency
"""
from __future__ import annotations
from typing import Dict, Any, List

SEVERITY_WEIGHT = {"critical": 1.0, "warning": 0.6, "info": 0.3}


def _impact(anomaly, net=None):
    t = anomaly.get("type", "")
    if t in ("topo_interrupt", "model_mismatch", "ghost_topology",
             "voltage_collapse", "grounding_fault", "branch_contingency"):
        return 0.9
    if t in ("telemetry_mismatch", "signal_mismatch", "measurement_outlier",
             "harmonic_pollution", "protection_misconfig"):
        return 0.5
    return 0.3


def _urgency(anomaly):
    return min(1.0, float(anomaly.get("confidence", 0.5) or 0.5))


def estimate_resources(anomalies):
    BASE_HOURS = {
        "topo_interrupt": 2.0, "virtual_faulty": 1.5, "model_mismatch": 4.0,
        "ghost_topology": 3.0, "topo_obfuscation": 2.5, "bus_section_mismatch": 1.0,
        "telemetry_mismatch": 0.5, "signal_mismatch": 0.5, "measurement_outlier": 0.3,
        "stale_data": 0.2, "measurement_bias": 0.3, "duplicate_measurement": 0.2,
        "parameter_error": 1.0, "impedance_degradation": 2.0, "bypass_operation": 1.0,
        "load_transfer_residual": 0.5, "load_shift": 0.5, "reverse_power_flow": 1.0,
        "branch_contingency": 2.0, "voltage_collapse": 1.0, "voltage_regulation": 0.5,
        "dg_intermittent": 0.5, "communication_loss": 0.5, "protection_misconfig": 2.0,
        "trafo_tap_fault": 1.5, "grounding_fault": 1.0, "clock_drift": 0.2,
        "harmonic_pollution": 1.5,
    }
    total = 0.0
    by_type = {}
    for a in anomalies:
        t = a.get("type", "unknown")
        h = BASE_HOURS.get(t, 1.0)
        total += h
        by_type[t] = by_type.get(t, 0) + h
    return {
        "total_hours": round(total, 2),
        "headcount": max(1, int(total / 8 + 0.5)),
        "by_type": {k: round(v, 2) for k, v in sorted(by_type.items(), key=lambda x: -x[1])},
    }


def risk_assessment(anomalies, net=None):
    n = len(anomalies)
    crit = sum(1 for a in anomalies if a.get("severity") == "critical")
    warn = sum(1 for a in anomalies if a.get("severity") == "warning")
    info = sum(1 for a in anomalies if a.get("severity") == "info")
    affected = crit * 200 + warn * 50 + info * 10
    risk = min(100, crit * 25 + n * 2)
    return {
        "affected_users": affected,
        "overloaded_equipment": crit,
        "risk_score": risk,
        "critical_count": crit,
        "total_anomalies": n,
    }


def prioritize(anomalies, net=None):
    if not anomalies:
        return {"anomalies": [], "summary": estimate_resources([]), "risk": risk_assessment([])}
    scored = []
    for a in anomalies:
        sev = a.get("severity", "warning")
        sw = SEVERITY_WEIGHT.get(sev, 0.5)
        impact = _impact(a, net)
        urgency = _urgency(a)
        score = sw * impact * urgency
        scored.append({**a, "priority_score": round(score, 4)})
    scored.sort(key=lambda x: -x["priority_score"])
    return {
        "anomalies": scored,
        "summary": estimate_resources(anomalies),
        "risk": risk_assessment(anomalies),
    }


if __name__ == "__main__":
    s = [{"type": "topo_interrupt", "severity": "critical", "confidence": 0.95},
         {"type": "harmonic_pollution", "severity": "warning", "confidence": 0.7}]
    r = prioritize(s)
    print("top:", r["anomalies"][0]["type"])
    print("summary:", r["summary"])
    print("risk:", r["risk"])
