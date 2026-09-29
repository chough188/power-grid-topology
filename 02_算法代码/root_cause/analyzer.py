# -*- coding: utf-8 -*-
"""根因分析（Phase 10）。"""
from __future__ import annotations
import json
import os
from typing import Dict, Any, List

RULES_PATH = os.path.join(os.path.dirname(__file__), "rules.json")


def _load_rules() -> Dict[str, Any]:
    try:
        with open(RULES_PATH, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {}


def analyze(anomaly: Dict[str, Any], net_state: Dict[str, Any] = None) -> Dict[str, Any]:
    """对单个 anomaly 进行根因分析。

    Args:
        anomaly: {type, location, confidence, ...}
        net_state: 当前网络状态（可选）

    Returns:
        {root_cause, probability, evidence, alternatives}
    """
    rules = _load_rules()
    atype = anomaly.get("type", "")

    # 通用根因映射（找不到具体规则时的兜底）
    GENERIC_CAUSES = {
        "topo_interrupt": [("switch_open", 0.5), ("protection_trip", 0.3), ("maintenance", 0.2)],
        "virtual_faulty": [("wiring_error", 0.6), ("model_inconsistency", 0.4)],
        "model_mismatch": [("model_drift", 0.5), ("manual_edit", 0.3), ("import_error", 0.2)],
        "telemetry_mismatch": [("ct_pt_fault", 0.4), ("communication_error", 0.3), ("calibration_drift", 0.3)],
        "signal_mismatch": [("aux_contact_fault", 0.5), ("wiring_error", 0.3), ("controller_fault", 0.2)],
        "measurement_outlier": [("sensor_noise", 0.4), ("transient_event", 0.3), ("data_corruption", 0.3)],
        "stale_data": [("communication_loss", 0.6), ("device_offline", 0.4)],
        "duplicate_measurement": [("config_error", 0.7), ("redundant_install", 0.3)],
        "parameter_error": [("wrong_impedance", 0.5), ("wrong_tap", 0.3), ("wrong_rating", 0.2)],
        "impedance_degradation": [("cable_aging", 0.5), ("joint_deterioration", 0.3), ("corrosion", 0.2)],
        "bypass_operation": [("planned_bypass", 0.5), ("emergency_bypass", 0.3), ("misoperation", 0.2)],
        "load_transfer_residual": [("incomplete_transfer", 0.6), ("operator_error", 0.4)],
        "load_shift": [("feeder_reconfiguration", 0.5), ("load_growth", 0.3), ("seasonal_change", 0.2)],
        "reverse_power_flow": [("dg_overgeneration", 0.6), ("protection_blind_zone", 0.2), ("load_drop", 0.2)],
        "branch_contingency": [("physical_fault", 0.5), ("protection_operation", 0.3), ("scheduled_outage", 0.2)],
        "voltage_collapse": [("load_overload", 0.35), ("tap_fault", 0.3), ("impedance_increase", 0.25), ("dg_dropout", 0.1)],
        "voltage_regulation": [("tap_stuck", 0.4), ("cap_failure", 0.3), ("control_error", 0.3)],
        "dg_intermittent": [("cloud_cover", 0.5), ("wind_lull", 0.3), ("inverter_trip", 0.2)],
        "communication_loss": [("fiber_break", 0.4), ("device_offline", 0.3), ("network_congestion", 0.3)],
        "protection_misconfig": [("wrong_settings", 0.5), ("coordination_issue", 0.3), ("uninitialized", 0.2)],
        "trafo_tap_fault": [("motor_drive_fault", 0.4), ("control_circuit", 0.3), ("mechanical_wear", 0.3)],
        "grounding_fault": [("single_phase_ground", 0.5), ("cable_insulation", 0.3), ("lightning", 0.2)],
        "clock_drift": [("gps_loss", 0.5), ("local_oscillator_drift", 0.3), ("sync_pulse_loss", 0.2)],
        "harmonic_pollution": [("nonlinear_load", 0.45), ("arcing", 0.25), ("transformer_saturation", 0.2), ("capacitor_switching", 0.1)],
                    "ghost_topology": [("model_stale", 0.4), ("imported_wrong_topology", 0.3), ("sync_lag", 0.3)],
        "topo_obfuscation": [("bus_label_swap", 0.4), ("naming_inconsistency", 0.3), ("encoding_issue", 0.3)],
        "bus_section_mismatch": [("section_label_error", 0.4), ("merger_split_mismatch", 0.3), ("model_drift", 0.3)],
        "measurement_bias": [("ct_saturation", 0.4), ("calibration_offset", 0.3), ("temperature_drift", 0.3)],
}

    if atype in rules:
        causes = rules[atype].get("causes", [])
    elif atype in GENERIC_CAUSES:
        causes = [{"type": t, "weight": w, "indicators": []} for t, w in GENERIC_CAUSES[atype]]
    else:
        causes = [{"type": "unknown", "weight": 1.0, "indicators": []}]

    # 按权重排序
    causes.sort(key=lambda x: -x.get("weight", 0))
    top = causes[0]
    return {
        "anomaly_type": atype,
        "root_cause": top.get("type", "unknown"),
        "probability": top.get("weight", 0.0),
        "evidence": top.get("indicators", []),
        "alternatives": [{"type": c.get("type"), "probability": c.get("weight", 0)}
                         for c in causes[1:3]],
    }


def add_probability(anomalies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """给每个 anomaly 加上概率分布字段（Phase 9）。"""
    out = []
    for a in anomalies:
        a2 = dict(a)
        atype = a.get("type", "")
        conf = a.get("confidence", 0.5)
        # 生成 top-3 候选类型概率分布（主类型占主，其余按相似度分）
        related = {
            "topo_interrupt": ["virtual_faulty", "model_mismatch"],
            "virtual_faulty": ["topo_interrupt", "model_mismatch"],
            "telemetry_mismatch": ["signal_mismatch", "measurement_outlier"],
            "signal_mismatch": ["telemetry_mismatch", "measurement_outlier"],
            "voltage_collapse": ["voltage_regulation", "load_shift"],
            "parameter_error": ["impedance_degradation", "tap_fault"],
        }
        alts = related.get(atype, ["unknown1", "unknown2"])
        remainder = (1.0 - conf) * 0.9
        prob_dist = {atype: round(conf, 3)}
        for i, alt in enumerate(alts[:2]):
            share = remainder * (0.6 if i == 0 else 0.4)
            prob_dist[alt] = round(share, 3)
        # 确保总和≈1
        s = sum(prob_dist.values())
        for k in prob_dist:
            prob_dist[k] = round(prob_dist[k] / s, 3)

        a2["probability_distribution"] = prob_dist
        a2["confidence_interval"] = [max(0, conf - 0.1), min(1, conf + 0.1)]
        out.append(a2)
    return out


if __name__ == "__main__":
    sample = {"type": "voltage_collapse", "location": "bus_42", "confidence": 0.88}
    r = analyze(sample)
    print(f"Root cause: {r['root_cause']} ({r['probability']:.0%})")
    print(f"Evidence: {r['evidence']}")
    print(f"Alternatives: {r['alternatives']}")

    sample2 = {"type": "topo_interrupt", "location": "line_15", "confidence": 0.95}
    r2 = analyze(sample2)
    print(f"\nRoot cause: {r2['root_cause']} ({r2['probability']:.0%})")

    # Probability distribution
    enriched = add_probability([sample, sample2])
    for a in enriched:
        print(f"\n{a['type']}: {a['probability_distribution']}")