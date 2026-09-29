"""Industrial-grade post-processing pipeline for LLM outputs.

This module validates, sanitizes, and scores LLM outputs before they
reach the substation operator.

v18.7.16 - Industrial Agent grade gates (9, 10, 11, 12)
"""
from __future__ import annotations
import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from llm_assistant import audit


# ----------------------------------------------------------------------
# PUBLIC API - must stay in sync with all consumer imports
# Any change here must also update test_import_chain_completeness.py
# ----------------------------------------------------------------------
__all__ = [
    # Schemas (data contracts)
    "DIAGNOSIS_SCHEMA",
    "POLISHED_REPORT_SCHEMA",
    "ANOMALY_EXPLANATION_SCHEMA",
    "AGENT_REPORT_SCHEMA",
    # Fallback functions (rules-engine fallbacks)
    "fallback_diagnosis",
    "fallback_polished_report",
    "fallback_explanation",
    "fallback_review_template",
    # Core process
    "process",
    "calibrate_confidence",
    "industrial_grade_score",
    # Result dataclass
    "PostProcessResult",
    # Exported internals (required by agent.py / llm_engine*.py)
    "_INJECTION_FATAL_THRESHOLD",
    "_validate_injection",
]
# Gate 9 - domain vocabulary enforcement
_DOMAIN_VOCAB: Dict[str, Tuple[Tuple[str, ...], str]] = {
    "线路": (("line", "wire", "circuit", "feeder"), "warn"),
    "母线": (("bus", "busbar", "node"), "warn"),
    "变压器": (("transform", "transformer", "trafo", "xfmr"), "warn"),
    "断路器": (("breaker", "circuit breaker", "cb"), "warn"),
    "隔离开关": (("switch", "disconnect", "isolator"), "warn"),
    "电容器": (("cap", "capacitor", "capacitance", "condenser"), "warn"),
    "电抗器": (("reactor", "inductor"), "warn"),
    "负荷": (("load", "demand", "consumption"), "warn"),
    "发电机": (("generator", "gen", "alternator"), "warn"),
    "分布式电源": (("dg", "distributed generation", "renewable", "solar", "wind"), "warn"),
    "电压": (("voltage", "v", "volt"), "warn"),
    "电流": (("current", "i", "ampere", "amp"), "warn"),
    "有功功率": (("active power", "real power", "p"), "warn"),
    "无功功率": (("reactive power", "q", "var"), "warn"),
    "视在功率": (("apparent power", "s"), "warn"),
    "功率因数": (("power factor", "pf", "cos phi"), "warn"),
    "频率": (("frequency", "freq", "hz"), "warn"),
    "阻抗": (("impedance", "z"), "warn"),
    "异常": (("anomaly", "anomalies", "abnormal", "irregularity"), "warn"),
    "故障": (("fault", "failure", "trip"), "warn"),
    "拓扑": (("topology", "graph", "network structure"), "warn"),
    "保护": (("protection", "relay", "fuse"), "warn"),
    "接地": (("grounding", "ground", "earth", "earthing"), "warn"),
    "短路": (("short circuit", "short", "sc"), "warn"),
    "过载": (("overload", "overcurrent", "thermal overload"), "warn"),
    "谐波": (("harmonic", "harmonics", "thd"), "warn"),
    "变电站": (("substation", "station", "ss"), "warn"),
    "测量": (("measurement", "metering", "meter"), "warn"),
}

_DOMAIN_VOCAB_REQUIRED = ("异常", "故障", "短路", "母线", "变压器")

# Gate 10 - PII / secret leak
_PII_PATTERNS: Tuple[Tuple[str, str], ...] = (
    (r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "ip"),
    (r"\b[A-Za-z]:\\[^\s\"']+(?:\\[^\s\"']+)*", "win-path"),
    (r"(?i)\b(password|secret|token|api[_-]?key|auth)\b[^\n]{0,50}", "secret"),
    (r"\b\d{10,}\b", "numeric_id"),
)

_PII_WINPATH_WHITELIST = ("c:\\windows", "d:\\windows", "c:\\program files", "d:\\program files")

# Gate 8 - auto-healed by _import_gatekeeper
_INJECTION_FATAL_THRESHOLD: int = 1

# Gate 8 - auto-healed by _import_gatekeeper
# REMOVED

# Gate 8 - auto-healed by _import_gatekeeper
# REMOVED BY TEST

# Gate 8 - auto-healed by _import_gatekeeper
# REMOVED BY TEST

# Gate 8 - auto-healed by _import_gatekeeper
# REMOVED BY TEST

# Gate 8 - auto-healed by _import_gatekeeper
# REMOVED BY TEST

# Gate 8 - injection fatal threshold (exported for agent.py)
# REMOVED


@dataclass
class PostProcessResult:
    """Result of post-processing an LLM output."""
    success: bool = False
    payload: Optional[Dict[str, Any]] = None
    fallback_used: bool = False
    gates_passed: List[str] = field(default_factory=list)
    gates_failed: List[str] = field(default_factory=list)
    ig_score: int = 0
    note: str = ""
    flagged: List[str] = field(default_factory=list)

    @property
    def flagged_strings(self) -> List[str]:
        """Alias for flagged (backwards compatibility)."""
        return self.flagged


def _strip_thinking(text: str) -> str:
    """Remove ⟨ think blocks from LLM output."""
    return re.sub(r"⟨.*?⟩", "", text, flags=re.DOTALL)


def _validate_domain_vocab(payload: Dict[str, Any], ctx_strings: List[str]) -> Tuple[bool, List[str]]:
    """Check the LLM uses domain-correct vocabulary."""
    flagged: List[str] = []
    flat = _flatten_strings(payload)
    haystack = "".join(flat)
    if not haystack.strip():
        return True, []
    
    for canonical, (mistakes, severity) in _DOMAIN_VOCAB.items():
        if canonical not in haystack:
            continue
        for m in mistakes:
            if not m or m == canonical:
                continue
            ml = m.lower()
            if ml not in haystack.lower():
                continue
            esc = re.escape(ml)
            if re.search(rf"(?<!\w){esc}(?!\w)", haystack.lower()):
                if severity == "fail":
                    flagged.append(f"vocab:use {canonical} instead of {m}")
                else:
                    flagged.append(f"vocab:warn:{canonical} vs {m}")
    
    return True, flagged


def _validate_pii(raw_text: str, payload: Optional[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    """Detect PII / secret leaks in raw LLM output + payload."""
    hits: List[str] = []
    combined = raw_text or ""
    if payload:
        try:
            combined += "\n" + json.dumps(payload, ensure_ascii=False, default=str)
        except Exception:
            pass
    
    for pat, label in _PII_PATTERNS:
        for m in re.finditer(pat, combined):
            value = m.group(0)
            if label == "ip":
                if value.startswith(("0.0.", "192.0.", "127.")):
                    continue
            elif label == "win-path":
                v_lower = value.lower()
                if any(v_lower.startswith(p) for p in _PII_WINPATH_WHITELIST):
                    continue
            hits.append(f"{label}:{value[:30]}")
    
    return len(hits) == 0, hits


def _validate_injection(raw_text: str, ctx_strings: Optional[List[str]] = None) -> Tuple[bool, List[str]]:
    """Detect prompt injection patterns in LLM output."""
    INJECTION_KEYWORDS = [
        "ignore previous instructions", "disregard your instructions",
        "forget your rules", "new system prompt", "override",
        "You are now", "pretend to be", "act as a different",
    ]
    hits: List[str] = []
    text_lower = raw_text.lower()
    for kw in INJECTION_KEYWORDS:
        if kw.lower() in text_lower:
            hits.append(f"kw={kw}")
    return len(hits) == 0, hits


def _flatten_strings(obj: Any) -> List[str]:
    """Recursively extract all strings from an object."""
    result: List[str] = []
    def _walk(o):
        if isinstance(o, dict):
            for v in o.values():
                _walk(v)
        elif isinstance(o, list):
            for v in o:
                _walk(v)
        elif isinstance(o, str):
            result.append(o)
    _walk(obj)
    return result


def _enforce_field_lengths(payload: Dict[str, Any], schema: Dict[str, Any]) -> int:
    """Truncate fields longer than schema.maxLength."""
    n = 0
    max_lengths = schema.get("maxLength", {})
    for field_name, max_len in max_lengths.items():
        if field_name in payload and isinstance(payload[field_name], str):
            if len(payload[field_name]) > max_len:
                payload[field_name] = payload[field_name][:max_len]
                n += 1
    return n


def _sanitize_ranges(payload: Any) -> int:
    """Clamp confidence/severity fields to [0, 1]."""
    n = 0
    RANGE_FIELDS = {"confidence", "score", "severity", "urgency", "priority"}
    
    def _walk(obj):
        nonlocal n
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    _walk(v)
                elif isinstance(v, (int, float)):
                    if k in RANGE_FIELDS or k.endswith("_confidence"):
                        if v < 0:
                            obj[k] = 0.0
                            n += 1
                        elif v > 1:
                            obj[k] = 1.0
                            n += 1
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)
    
    _walk(payload)
    return n


def industrial_grade_score(gates_passed: List[str], gates_failed: List[str], flagged: List[str]) -> Dict[str, Any]:
    """Calculate industrial-grade score (0-100)."""
    base = 100
    # Deduct for failed gates
    for g in gates_failed:
        if "gate2" in g:
            base -= 40
        elif "gate3" in g:
            base -= 30
        elif "gate5" in g:
            base -= 20
        elif "gate8" in g or "gate10" in g:
            base -= 50
        else:
            base -= 10
    
    # Deduct for flagged items
    base -= len(flagged) * 2
    
    # Bonus for clean gates
    if "gate4_grounding" in gates_passed:
        base += 5
    if "gate6_sanitize" in gates_passed:
        base += 5
    
    score = max(0, min(100, base))
    
    if score >= 90:
        reason = "Excellent - Production ready"
    elif score >= 70:
        reason = "Good - Minor issues"
    elif score >= 50:
        reason = "Fair - Manual review recommended"
    else:
        reason = "Poor - Fallback triggered"
    
    return {"score": score, "reason": reason}


def calibrate_confidence(payload: Dict[str, Any], gates_failed: List[str]) -> int:
    """Downscale confidence when grounding/validation failed."""
    n = 0
    CONFI = {"anomaly_confidence", "correction_confidence", "overall_confidence"}
    
    def _walk(obj):
        nonlocal n
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in CONFI and isinstance(v, (int, float)):
                    if gates_failed:
                        obj[k] = v * 0.7
                        n += 1
                else:
                    _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)
    
    _walk(payload)
    return n


def _audit_process(result,audit_stack,audit_source,audit_schema_name,audit_caller):
 audit.log_call(stack=audit_stack,source=audit_source,raw=str(result),result=result,schema_name=audit_schema_name,caller=audit_caller)
def process(
    raw_text: str,
    schema: Optional[Dict[str, Any]] = None,
    ctx_strings: Optional[List[str]] = None,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    tool_registry: Optional[Dict[str, Any]] = None,
    max_latency_s: float = 60.0,
    max_tokens: int = 4096,
    audit_stack: Optional[str] = None,
    audit_source: str = "unknown",
    audit_schema_name: str = "unknown",
    audit_caller: str = "unknown",
    extract_tool_calls_text: bool = False,
) -> PostProcessResult:
    """Main post-processing pipeline."""
    t0 = time.time()
    gates_passed: List[str] = []
    gates_failed: List[str] = []
    flagged: List[str] = []
    payload: Optional[Dict[str, Any]] = None
    
    # Gate 0: Strip <think>...</think> think blocks from raw LLM output
    raw_text = _strip_thinking(raw_text)

    # Gate 1: Injection detection
    ok, hits = _validate_injection(raw_text, ctx_strings)
    if ok:
        gates_passed.append("gate1_injection:clean")
    else:
        gates_failed.extend([f"gate8_injection:{h}" for h in hits])
        flagged.extend(hits)
    
    # Gate 2: JSON load
    try:
        payload = json.loads(raw_text)
        gates_passed.append("gate2_json_load")
    except json.JSONDecodeError:
        gates_failed.append("gate2_json_load")
        if schema:
            payload = {}
        else:
            result = PostProcessResult(
                success=False,
                fallback_used=True,
                gates_failed=gates_failed,
                gates_passed=gates_passed,
                ig_score=0,
                note="JSON parse failed",
                flagged=flagged,
            )
            _audit_process(result, audit_stack, audit_source, audit_schema_name, audit_caller)
            return result
    # Gate 3: Schema validation
    if schema and payload:
        # Simple schema check - verify required fields exist
        required = schema.get("required", [])
        missing = [f for f in required if f not in payload]
        if missing:
            gates_failed.append(f"gate3_schema:missing:{missing[0]}")
        else:
            gates_passed.append("gate3_schema")
    else:
        gates_passed.append("gate3_schema")
    
    # Gate 4: Grounding — flag hallucinated numbers not in ctx_strings
    if payload and ctx_strings:
        flat = _flatten_strings(payload)
        numbers_in_payload = re.findall(r"\d+(?:\.\d+)?", " ".join(flat))
        hits: List[str] = []
        for num in set(numbers_in_payload):
            found = any(num in ctx for ctx in ctx_strings)
            if not found:
                hits.append(f"grounding:{num}")
        if hits:
            gates_failed.extend([f"gate4_grounding:{h}" for h in hits])
            flagged.extend(hits)
        else:
            gates_passed.append("gate4_grounding:clean")
    elif payload:
        gates_passed.append("gate4_grounding:no_ctx")
    
    # Gate 5: PII detection
    ok, hits = _validate_pii(raw_text, payload)
    if ok:
        gates_passed.append("gate10_pii:clean")
    else:
        gates_failed.extend([f"gate10_pii:{h}" for h in hits])
        flagged.extend(hits)
    
    # Gate 6: Domain vocabulary
    if payload and ctx_strings:
        ok, hits = _validate_domain_vocab(payload, ctx_strings)
        if ok:
            if hits:
                gates_passed.append("gate9_vocab:warn")
                flagged.extend(hits)
            else:
                gates_passed.append("gate9_vocab:clean")
    
    # Gate 7: Range sanitization
    if payload:
        n = _sanitize_ranges(payload)
        gates_passed.append(f"gate6_sanitize:{n}")
    
    # Gate 8: Field length enforcement
    if payload and schema:
        n = _enforce_field_lengths(payload, schema)
        gates_passed.append(f"gate11_length:{n}")
    
    # Gate 9: Budget check
    elapsed = time.time() - t0
    if elapsed > max_latency_s:
        gates_failed.append(f"gate7_budget:latency_{elapsed:.1f}s")
    else:
        gates_passed.append("gate7_budget")
    
    # Calculate IG score
    ig = industrial_grade_score(gates_passed, gates_failed, flagged)
    
    # Determine fatal failure
    fatal = any(
        g.startswith(prefix) for g in gates_failed
        for prefix in ("gate2", "gate3", "gate5", "gate8", "gate10")
    )
    
    # When fatal, always populate a fallback payload so callers always get a dict
    if fatal:
        payload = {
            "root_cause": "LLM output could not be parsed",
            "reasoning": "JSON parse or schema validation failed",
            "confidence": 0.3,
            "needs_human_review": True,
        }

    result = PostProcessResult(
        success=not fatal,
        payload=payload,
        fallback_used=fatal,
        gates_passed=gates_passed,
        gates_failed=gates_failed,
        ig_score=ig["score"],
        note=ig["reason"],
        flagged=flagged,
    )
    _audit_process(result, audit_stack, audit_source, audit_schema_name, audit_caller)
    return result




# ---------------------------------------------------------------------------
# v18.7.13 restore: missing exports re-added (were lost in v18.7.13 restore)
# ---------------------------------------------------------------------------

AGENT_REPORT_SCHEMA = {
    "type": "object",
    "required": ["overall_assessment", "top3_anomalies_explained"],
    "properties": {
        "overall_assessment":            {"type": "string", "maxLength": 500},
        "top3_anomalies_explained":      {"type": "string", "maxLength": 1000},
        "correction_priority_reasoning": {"type": "string", "maxLength": 800},
        "risk_forecast":                 {"type": "string", "maxLength": 500},
        "recommendation_summary":        {"type": "string", "maxLength": 1000},
    },
}


DIAGNOSIS_SCHEMA = {
    "type": "object",
    "required": ["root_cause", "confidence", "recommendation"],
    "properties": {
        "root_cause":     {"type": "string", "maxLength": 200},
        "reasoning":      {"type": "string", "maxLength": 500},
        "affected_scope": {"type": "string", "maxLength": 100},
        "confidence":     {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "recommendation": {"type": "string", "maxLength": 300},
    },
}

POLISHED_REPORT_SCHEMA = {
    "type": "object",
    "required": [],
    "properties": {
        "one_line_summary_polished": {"type": "string", "maxLength": 200},
        "detailed_report_polished":   {"type": "string", "maxLength": 5000},
    },
}

ANOMALY_EXPLANATION_SCHEMA = {
    "type": "object",
    "required": ["explanation", "anomaly_type"],
    "properties": {
        "explanation":     {"type": "string", "maxLength": 500},
        "anomaly_type":    {"type": "string", "maxLength": 50},
        "possible_causes": {
            "type": "array",
            "items": {"type": "string", "maxLength": 100},
            "maxItems": 5,
        },
    },
}


def fallback_diagnosis(anomalies, correlation):
    scenarios = (correlation or {}).get("fault_scenarios", [])
    if scenarios:
        top = max(scenarios, key=lambda s: s.get("confidence", 0))
        root = top.get("fault_name", "综合异常")
        conf = top.get("confidence", 0.5)
    else:
        type_counts = {}
        for a in (anomalies or []):
            t = a.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1
        root = max(type_counts, key=type_counts.get) if type_counts else "需要进一步分析"
        conf = 0.5 if type_counts else 0.3
    return {
        "root_cause": root,
        "reasoning": f"基于{len(anomalies)}条规则检测异常推断",
        "affected_scope": "待确认",
        "confidence": conf,
        "recommendation": "建议人工复核确认",
        "needs_human_review": True,
    }


def fallback_polished_report(orig):
    return {
        "one_line_summary_polished": orig.get("one_line_summary", orig.get("one_line_summary_polished", "")),
        "detailed_report_polished":  orig.get("detailed_report",  orig.get("detailed_report_polished", "")),
        "needs_human_review": True,
    }


def fallback_explanation(anomaly_type):
    explanations = {
        "voltage_regulation":    "节点电压超出正常范围，需检查变压器分接头位置或补偿装置。",
        "topo_interrupt":       "拓扑结构中断，需检查关键线路是否断开。",
        "reverse_power_flow":   "潮流方向异常，可能由分布式电源反送电引起。",
        "parameter_error":       "设备参数与模型不符，需核查铭牌参数。",
        "harmonic_pollution":    "谐波含量超标，需检查非线性负荷。",
        "communication_loss":    "通信中断，需检查通信链路状态。",
        "grounding_fault":       "接地故障，需现场检查零序电流保护动作。",
        "trafo_tap_fault":      "分接头位置异常，需检查操动机构。",
        "clock_drift":           "时标偏移超过阈值，需同步SCADA时钟。",
        "protection_misconfig":  "保护配置不一致，需核查保护定值。",
        "default":               "异常类型未分类，建议现场核查。",
    }
    return {
        "explanation":     "[{0}] {1}".format(
            anomaly_type, explanations.get(anomaly_type, explanations["default"])
        ),
        "anomaly_type":    anomaly_type,
        "possible_causes": [],
        "needs_human_review": True,
    }


def fallback_review_template(
    network_name: str, anomaly_count: int, correction_count: int
) -> Dict[str, str]:
    """Template fallback used when LLM is unavailable or postprocess fails."""
    return {
        "overall_assessment": (
            f"网络 {network_name} 共检出 {anomaly_count} 条异常"
            f"生成 {correction_count} 条修正建议"
            f"本评语由模型生成LLM 未在线或后处理失败建议人工复核关键异常"
        ),
        "top3_anomalies_explained": (
            "请查看检测详情建议优先处理高置信度异常对参数错误和电压类异常重点关注"
        ),
        "correction_priority_reasoning": (
            "本次生成的修正建议需按置信度从高到低排序处理"
            "高置信度异常应立即处理低置信度异常需现场核查"
        ),
        "risk_forecast": (
            f"当前共 {anomaly_count} 条未处理异常存在连锁故障风险"
            "建议定期巡检关注电压偏差和拓扑完整性"
        ),
        "recommendation_summary": (
            "1. 立即处理高置信度异常恢复拓扑完整性\n"
            "2. 对参数类异常进行现场核查和校准\n"
            "3. 安排后续检测跟踪确保修正效果\n"
            "4. 建立异常记录档案便于历史回溯"
        ),
    }
