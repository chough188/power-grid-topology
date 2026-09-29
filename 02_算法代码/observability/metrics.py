# -*- coding: utf-8 -*-
"""Prometheus metrics (B.1 + B.2).

暴露 Counter / Histogram / Gauge，run_detect / run_correct / 工单 / 通知 / LLM
关键路径全部打点。/metrics 端点通过 api/routes.py 暴露。
"""
from __future__ import annotations
from prometheus_client import (
    Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST, REGISTRY,
)
from typing import Iterable

# Counter
DETECT_COUNT = Counter(
    "detect_total",
    "Total detect calls",
    ["network", "inject"],
)
ANOMALY_TOTAL = Counter(
    "anomaly_total",
    "Total anomalies emitted",
    ["anomaly_type", "severity"],
)
WORKORDER_COUNT = Counter(
    "workorder_total",
    "Workorder lifecycle events",
    ["event"],
)
NOTIFY_COUNT = Counter(
    "notify_total",
    "Push notifications dispatched",
    ["channel", "result"],
)

# Histogram
DETECT_LATENCY = Histogram(
    "detect_latency_seconds",
    "Detect latency per network",
    ["network"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
)
LLM_LATENCY = Histogram(
    "llm_latency_seconds",
    "LLM inference latency",
    ["model"],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 60.0, 120.0),
)

# Gauge
CACHE_HIT_RATIO = Gauge(
    "cache_hit_ratio",
    "Detection cache hit ratio (rolling)",
)


def render_latest() -> tuple:
    """Return (body, content_type) for /metrics endpoint."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


__all__ = [
    "DETECT_COUNT", "ANOMALY_TOTAL", "WORKORDER_COUNT", "NOTIFY_COUNT",
    "DETECT_LATENCY", "LLM_LATENCY", "CACHE_HIT_RATIO",
    "render_latest",
]
