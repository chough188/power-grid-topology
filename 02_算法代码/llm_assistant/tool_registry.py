# -*- coding: utf-8 -*-
"""Dynamic tool registry for industrial agent use.

v18.7.12 \u2014 extensible tool list with parameter schemas and dispatcher.
Tools are loaded from JSON sidecar, validated against schema, dispatched to
local handlers. Safety blocklist applied at registration.
"""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Callable, List, Optional

logger = logging.getLogger(__name__)


DEFAULT_TOOLS_PATH = Path(__file__).parent / "tools.json"

_SAFETY_BLOCKLIST_PREFIX = ("delete_", "format_", "shutdown_", "purge_", "exec_", "write_")
_SAFETY_BLOCKLIST_NAME = {"system_cmd", "execute_sql", "send_email"}


def default_tool_specs() -> List[Dict[str, Any]]:
    """Built-in tool specs (the 5 the project ships)."""
    return [
        {
            "name": "get_network_info",
            "description": "\u83b7\u53d6\u6307\u5b9a\u7f51\u7edc\u7684\u57fa\u672c\u4fe1\u606f\uff08\u6bcd\u7ebf\u6570\u3001\u7ebf\u8def\u6570\u3001\u63cf\u8ff0\uff09",
            "parameters": {
                "type": "object",
                "properties": {
                    "network_name": {"type": "string", "description": "\u7f51\u7edc\u540d"}
                },
                "required": ["network_name"],
            },
        },
        {
            "name": "list_anomalies",
            "description": "\u5217\u51fa\u5f53\u524d\u7f51\u7edc\u7684\u6240\u6709\u68c0\u6d4b\u5f02\u5e38",
            "parameters": {
                "type": "object",
                "properties": {
                    "filter_type": {"type": "string", "description": "\u53ef\u9009\uff0c\u6309\u7c7b\u578b\u8fc7\u6ee4"}
                },
            },
        },
        {
            "name": "anomaly_stats_by_type",
            "description": "\u6309\u7c7b\u578b\u7edf\u8ba1\u5f02\u5e38\u6570\u91cf",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "get_top_corrections",
            "description": "\u83b7\u53d6\u9ad8\u4f18\u5148\u7ea7\u4fee\u6b63\u65b9\u6848",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "\u6700\u591a\u8fd4\u56de N \u6761"}
                },
            },
        },
        {
            "name": "finish_report",
            "description": "\u6240\u6709\u6570\u636e\u5df2\u6536\u96c6\uff0c\u751f\u6210\u6700\u7ec8\u62a5\u544a\u6b63\u6587\u3002\u5fc5\u987b\u586b\u5199\u5168\u90e8 5 \u4e2a\u53d9\u4e8b\u69fd\u4f4d\u3002",
            "parameters": {
                "type": "object",
                "properties": {
                    "overall_assessment": {"type": "string"},
                    "top3_anomalies_explained": {"type": "string"},
                    "correction_priority_reasoning": {"type": "string"},
                    "risk_forecast": {"type": "string"},
                    "recommendation_summary": {"type": "string"},
                },
                "required": [
                    "overall_assessment",
                    "top3_anomalies_explained",
                    "correction_priority_reasoning",
                    "risk_forecast",
                    "recommendation_summary",
                ],
            },
        },
    ]


class ToolRegistry:
    """Holds tool specs + handlers; provides dispatch."""

    def __init__(self, specs: Optional[List[Dict[str, Any]]] = None,
                 handlers: Optional[Dict[str, Callable]] = None,
                 tools_path: Optional[Path] = None):
        self.specs = list(specs or default_tool_specs())
        self.handlers: Dict[str, Callable] = dict(handlers or {})
        if tools_path is None:
            tools_path = DEFAULT_TOOLS_PATH
        self.tools_path = tools_path
        self._validate_specs()

    def _validate_specs(self) -> None:
        for spec in self.specs:
            name = spec.get("name", "")
            if not name:
                raise ValueError("tool spec missing name")
            if name in _SAFETY_BLOCKLIST_NAME:
                raise ValueError(f"tool name blocked: {name}")
            if any(name.startswith(p) for p in _SAFETY_BLOCKLIST_PREFIX):
                raise ValueError(f"tool prefix blocked: {name}")
            if "description" not in spec:
                raise ValueError(f"tool {name} missing description")
            if "parameters" not in spec:
                raise ValueError(f"tool {name} missing parameters")

    def register_handler(self, name: str, fn: Callable) -> None:
        spec_names = {s["name"] for s in self.specs}
        if name not in spec_names:
            raise KeyError(f"tool spec not registered: {name}")
        self.handlers[name] = fn

    def as_openai_tools(self) -> List[Dict[str, Any]]:
        """Convert internal specs to OpenAI function-calling format."""
        out = []
        for spec in self.specs:
            out.append({
                "type": "function",
                "function": {
                    "name": spec["name"],
                    "description": spec.get("description", ""),
                    "parameters": spec.get("parameters", {"type": "object", "properties": {}}),
                },
            })
        return out

    def spec_map(self) -> Dict[str, Dict[str, Any]]:
        return {s["name"]: s for s in self.specs}

    def call(self, name: str, args: Dict[str, Any]) -> Any:
        if name not in self.handlers:
            return {"error": "no handler registered for: " + name}
        try:
            return self.handlers[name](**args)
        except TypeError as e:
            return {"error": "bad args: " + str(e)}
        except Exception as e:
            return {"error": str(e)}

    def save_to_file(self, path: Optional[Path] = None) -> Path:
        """Persist tool specs to a JSON file for human editing."""
        target = Path(path or self.tools_path)
        target.write_text(
            json.dumps(self.specs, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return target

    @classmethod
    def load_from_file(cls, path: Path,
                      handlers: Optional[Dict[str, Callable]] = None) -> "ToolRegistry":
        specs = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(specs=specs, handlers=handlers, tools_path=path)


# ──────────────────────────────────────────────────────────────────────
# v18.7.12 — Convenience helpers used by API endpoints
# ──────────────────────────────────────────────────────────────────────

def build_default_registry() -> Dict[str, Any]:
    """Return a name→spec dict suitable for postprocess.tool_registry param."""
    return {s["name"]: s for s in default_tool_specs()}


def registry_health() -> Dict[str, Any]:
    """Inspect default registry health: count, names, blocked.

    Used by GET /api/v1/agent/tool_health.
    """
    specs = default_tool_specs()
    names = [s["name"] for s in specs]
    blocked = [n for n in names if any(n.startswith(p) for p in _SAFETY_BLOCKLIST_PREFIX) or n in _SAFETY_BLOCKLIST_NAME]
    return {
        "available": True,
        "tool_count": len(specs),
        "tool_names": names,
        "blocked_tools": blocked,
        "safety_blocklist_prefix": list(_SAFETY_BLOCKLIST_PREFIX),
        "safety_blocklist_name": sorted(_SAFETY_BLOCKLIST_NAME),
        "per_tool_max_calls": 3,
    }


def estimate_cost(network_name: str = "case14", max_tokens: int = 2048) -> Dict[str, Any]:
    """Estimate token/time budget for a typical agent run.

    Heuristic: ~6 turns × (system 600 + user 200 + 4 × tool 150) + finish_report 500
    Total prompt ≈ 2,200 tokens, output ≈ max_tokens.
    Time ≈ tokens / 80 tok/s for 4B Q4_K_M on RTX 3060.
    """
    prompt_tokens_est = 2200
    output_tokens_est = max_tokens
    total = prompt_tokens_est + output_tokens_est
    # Rough GPU speed for 4B Q4_K_M
    tok_per_s = 80
    estimated_seconds = round(total / tok_per_s, 1)
    return {
        "network_name": network_name,
        "prompt_tokens_est": prompt_tokens_est,
        "output_tokens_est": output_tokens_est,
        "total_tokens_est": total,
        "estimated_seconds": estimated_seconds,
        "estimated_minutes": round(estimated_seconds / 60, 2),
        "tok_per_s_assumed": tok_per_s,
        "max_tokens_param": max_tokens,
    }
