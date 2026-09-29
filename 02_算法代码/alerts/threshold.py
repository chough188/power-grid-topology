# -*- coding: utf-8 -*-
"""告警阈值过滤（Phase 2.2）。

从 YAML 加载可配置阈值，按严重度+置信度过滤异常。
"""
from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml

_DEFAULT = {
    "critical_conf_min": 0.70,
    "warning_conf_min": 0.60,
    "info_conf_min": 0.50,
    "large_network_relax": 0.05,
    "per_type_overrides": {},
}

_CACHE: Dict[str, Any] = {}

CONFIG_PATHS = [
    Path(__file__).resolve().parent.parent / "config" / "alert_thresholds.yaml",
    Path(__file__).resolve().parent.parent.parent / "config" / "alert_thresholds.yaml",
]


def _load_config() -> Dict[str, Any]:
    if _CACHE:
        return _CACHE
    cfg = dict(_DEFAULT)
    for p in CONFIG_PATHS:
        if p.exists():
            try:
                with open(p, encoding="utf-8") as f:
                    user = yaml.safe_load(f) or {}
                cfg.update({k: v for k, v in user.items() if v is not None})
                break
            except Exception:
                pass
    _CACHE.clear()
    _CACHE.update(cfg)
    return cfg


def get_thresholds() -> Dict[str, Any]:
    return dict(_load_config())


def set_thresholds(new_cfg: Dict[str, Any]) -> Dict[str, Any]:
    _CACHE.clear()
    _CACHE.update(_DEFAULT)
    _CACHE.update({k: v for k, v in new_cfg.items() if v is not None})
    return dict(_CACHE)


def filter_by_threshold(
    anomalies: List[Dict[str, Any]],
    severity_config: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    cfg = severity_config or _load_config()
    min_conf = {
        "critical": cfg.get("critical_conf_min", 0.70),
        "warning": cfg.get("warning_conf_min", 0.60),
        "info": cfg.get("info_conf_min", 0.50),
    }
    per_type = cfg.get("per_type_overrides", {}) or {}
    out = []
    for a in anomalies:
        sev = a.get("severity", "warning")
        conf = float(a.get("confidence", 0.0) or 0.0)
        t = a.get("type", "")
        threshold = per_type.get(t, min_conf.get(sev, 0.5))
        if conf >= threshold:
            out.append(a)
    return out


if __name__ == "__main__":
    cfg = get_thresholds()
    print("thresholds:", cfg)
    sample = [
        {"type": "topo_interrupt", "severity": "critical", "confidence": 0.95},
        {"type": "harmonic_pollution", "severity": "warning", "confidence": 0.55},
    ]
    print("filtered:", len(filter_by_threshold(sample)), "of", len(sample))
