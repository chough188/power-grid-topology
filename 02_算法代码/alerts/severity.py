# -*- coding: utf-8 -*-
"""告警分级与置信度阈值（Phase 2）。"""
from __future__ import annotations
from typing import Dict, Any, List

CRITICAL = "critical"
WARNING = "warning"
INFO = "info"

TYPE_BASE_SEVERITY = {
    "topo_interrupt": CRITICAL, "virtual_faulty": CRITICAL,
    "model_mismatch": CRITICAL, "ghost_topology": CRITICAL,
    "topo_obfuscation": CRITICAL, "bus_section_mismatch": CRITICAL,
    "branch_contingency": CRITICAL, "voltage_collapse": CRITICAL,
    "protection_misconfig": CRITICAL, "trafo_tap_fault": CRITICAL,
    "grounding_fault": CRITICAL,
    "telemetry_mismatch": WARNING, "signal_mismatch": WARNING,
    "measurement_outlier": WARNING, "stale_data": WARNING,
    "measurement_bias": WARNING, "duplicate_measurement": WARNING,
    "parameter_error": WARNING, "impedance_degradation": WARNING,
    "bypass_operation": WARNING, "load_transfer_residual": WARNING,
    "load_shift": WARNING, "reverse_power_flow": WARNING,
    "voltage_regulation": WARNING, "dg_intermittent": WARNING,
    "communication_loss": WARNING, "harmonic_pollution": WARNING,
    "clock_drift": INFO,
}

DEFAULT_THRESHOLDS = {
    "critical_conf_min": 0.70,
    "warning_conf_min": 0.60,
    "info_conf_min": 0.50,
    "large_network_relax": 0.05,
}


def classify_severity(anomaly_type: str, confidence: float, n_buses: int = 100) -> str:
    """根据异常类型+置信度+网络规模返回严重度。"""
    base = TYPE_BASE_SEVERITY.get(anomaly_type, INFO)
    relax = DEFAULT_THRESHOLDS["large_network_relax"] if n_buses > 500 else 0.0

    if base == CRITICAL:
        if confidence >= DEFAULT_THRESHOLDS["critical_conf_min"] - relax:
            return CRITICAL
        return WARNING
    elif base == WARNING:
        if confidence >= DEFAULT_THRESHOLDS["warning_conf_min"] - relax:
            return WARNING
        return INFO
    else:
        if confidence >= DEFAULT_THRESHOLDS["info_conf_min"]:
            return INFO
        return None


def filter_by_threshold(anomalies: List[Dict[str, Any]],
                        n_buses: int = 100,
                        config: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """给每个 anomaly 补 severity 字段并按阈值过滤。"""
    out = []
    for a in anomalies:
        sev = classify_severity(a.get("type", ""), a.get("confidence", 0), n_buses)
        if sev is None:
            continue
        a2 = dict(a)
        a2["severity"] = sev
        out.append(a2)
    order = {CRITICAL: 0, WARNING: 1, INFO: 2}
    out.sort(key=lambda x: (order.get(x.get("severity", INFO), 3), -x.get("confidence", 0)))
    return out


if __name__ == "__main__":
    assert classify_severity("topo_interrupt", 0.9, 100) == "critical"
    assert classify_severity("telemetry_mismatch", 0.85, 100) == "warning"
    assert classify_severity("clock_drift", 0.6, 100) == "info"
    assert classify_severity("topo_interrupt", 0.5, 100) == "warning"
    print("alerts.severity self-test PASS")