# -*- coding: utf-8 -*-
"""JSON logging configuration (B.3).

输出每行 JSON 到 stderr/stdout，便于 logstash/fluentbit 抓取。
"""
from __future__ import annotations
import json
import logging
import sys
import time
from typing import Any

_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
                  + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # 透传 trace_id / request_id 等 context 字段
        for k in ("trace_id", "request_id", "tenant", "user", "network", "anomaly_type"):
            v = getattr(record, k, None)
            if v is not None:
                payload[k] = v
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_json_logging(level: str = "INFO") -> None:
    """初始化一次即可。多次调用幂等。"""
    global _CONFIGURED
    if _CONFIGURED:
        return
    root = logging.getLogger()
    root.setLevel(level)
    # 清理已有 handler 避免重复输出
    for h in list(root.handlers):
        root.removeHandler(h)
    h = logging.StreamHandler(stream=sys.stdout)
    h.setFormatter(JsonFormatter())
    root.addHandler(h)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    if not _CONFIGURED:
        configure_json_logging()
    return logging.getLogger(name)


__all__ = ["configure_json_logging", "get_logger", "JsonFormatter"]
