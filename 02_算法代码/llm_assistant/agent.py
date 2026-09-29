# -*- coding: utf-8 -*-
"""4B LLM Agent — 配电网异常报告生成（F2/F6 任务）

调用本地 llama-server（OpenAI 兼容 API），支持 Qwen3.5 原生 tool calling。
模型：Qwen3.5-4B-Claude-Opus-Reasoning-Distilled（Q4_K_M）
默认地址：http://localhost:8081/v1

设计要点：
1. native tool calling（Qwen3.5 chat template + <tool_call> block）
2. max_turns=12 防止无限循环
3. 失败 fallback 到模板化报告
4. reasoning via <think> tag
5. JSON 输出供前端展示
"""
from __future__ import annotations
import json
import time
import logging
import re
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from .postprocess import (
    process as _pp_process, AGENT_REPORT_SCHEMA,
    _validate_injection, _INJECTION_FATAL_THRESHOLD,
)


logger = logging.getLogger(__name__)

DEFAULT_SERVER_URL = "http://localhost:8081/v1"
DEFAULT_MODEL = "Qwen3.5-4B-Claude-Opus"
MAX_TURNS = 6
TIMEOUT_S = 180

# v18.7.12: delegate HTTP/backend plumbing to llm_client (eliminate dual stack)
from .llm_client import LLMClient


# ── 工具定义（Qwen3.5 native tools format） ──
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_network_info",
            "description": "获取指定网络的基本信息（母线数、线路数、描述）",
            "parameters": {
                "type": "object",
                "properties": {
                    "network_name": {"type": "string", "description": "网络名，如 case14"}
                },
                "required": ["network_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_anomalies",
            "description": "列出当前网络的所有检测异常",
            "parameters": {
                "type": "object",
                "properties": {
                    "filter_type": {"type": "string", "description": "可选，按类型过滤"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "anomaly_stats_by_type",
            "description": "按类型统计异常数量",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_corrections",
            "description": "获取高优先级修正方案",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "最多返回 N 条"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "finish_report",
            "description": "所有数据已收集，生成最终报告正文。必须填写全部 5 个叙事槽位。",
            "parameters": {
                "type": "object",
                "properties": {
                    "overall_assessment": {"type": "string", "description": "总体评估（200-300字，对网络整体健康状况的专业评价）"},
                    "top3_anomalies_explained": {"type": "string", "description": "重点异常分析（100-150字，解释前3类异常的成因、影响和处理建议）"},
                    "correction_priority_reasoning": {"type": "string", "description": "修正优先级分析（150-200字，说明为何某些修正优先处理）"},
                    "risk_forecast": {"type": "string", "description": "风险预警（100-150字，分析当前状态的潜在风险）"},
                    "recommendation_summary": {"type": "string", "description": "建议总结（150-200字，列出 3-5 条具体可执行的后续行动）"}
                },
                "required": ["overall_assessment", "top3_anomalies_explained", "correction_priority_reasoning", "risk_forecast", "recommendation_summary"]
            }
        }
    },
]


# ── 工具实现（本地调用 detector / corrector） ──
@dataclass
class AgentContext:
    network_name: str
    anomalies: List[Dict[str, Any]] = field(default_factory=list)
    corrections: List[Dict[str, Any]] = field(default_factory=list)
    network_meta: Dict[str, Any] = field(default_factory=dict)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)

    def get_network_info(self, network_name: str) -> Dict[str, Any]:
        return {"name": network_name, **self.network_meta}

    def list_anomalies(self, filter_type: Optional[str] = None) -> List[Dict[str, Any]]:
        if not filter_type:
            return self.anomalies
        return [a for a in self.anomalies if a.get("type") == filter_type]

    def anomaly_stats_by_type(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for a in self.anomalies:
            t = a.get("type", "unknown")
            out[t] = out.get(t, 0) + 1
        return out

    def get_top_corrections(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self.corrections[:limit]

    def dispatch(self, name: str, args: Dict[str, Any]) -> Any:
        fn = getattr(self, name, None)
        if fn is None:
            return {"error": "unknown tool: " + name}
        try:
            return fn(**args)
        except TypeError as e:
            return {"error": "bad args: " + str(e)}
        except Exception as e:
            return {"error": str(e)}


# ── 提示词 (v18.7.12: load from prompts/agent_v1.json, fallback to inline) ──
from llm_assistant.prompts import load_prompts as _load_prompts
from llm_assistant.prompts import DEFAULT_VERSION

import os as _os_v18  # noqa: E402


def _resolve_prompt_version():  # noqa: E402
    """Pick prompt version: DIANLI_PROMPT_VERSION env > default ('v1')."""
    v = _os_v18.environ.get("DIANLI_PROMPT_VERSION")
    return v if v else DEFAULT_VERSION


_PROMPTS = _load_prompts(_resolve_prompt_version())  # noqa: E402
_PROMPT_VERSION = _PROMPTS.get("version", "?")  # noqa: E402
_SYSTEM_PROMPT_FALLBACK = """你是配电网异常检测系统的高级评审专家（基于 4B Claude Opus 蒸馏模型）。

【可用工具】
你有以下工具可调用：
- get_network_info(network_name): 获取网络信息
- list_anomalies(filter_type?): 列出异常
- anomaly_stats_by_type(): 异常类型统计
- get_top_corrections(limit?): 高优先级修正方案
- finish_report(summary, expert_analysis, action_items): 生成最终评语

【铁律】
1. 禁止编造任何数字、百分比、类型名、网络名 — 所有数据必须来自工具调用结果
2. 每次只调用一个工具，拿到结果再决定下一步
3. 工具调用使用 <tool_call>...</tool_call> XML 块
4. 思考过程使用 <think>...</think> 块
5. 最后必须调用 finish_report 结束对话
6. 报告章节标题用中文：总体性能 / 异常分析 / 修正建议 / 行动项

【叙事槽位要求】以下 5 个字段必须全部填写，禁止留空：
- overall_assessment: 总体评估（200-300 字）
- top3_anomalies_explained: 重点异常分析（100-150 字）
- correction_priority_reasoning: 修正优先级分析（150-200 字）
- risk_forecast: 风险预警（100-150 字）
- recommendation_summary: 建议总结（150-200 字）"""

_USER_PROMPT_FALLBACK = """任务：为 {network_name} 网络生成检测报告评审。

【上下文】
- 网络：{network_name}
- 异常总数：{anomaly_count}
- 修正方案数：{correction_count}
- 已通过基准：51/51 网络通过（avg_recall=98.68%）

【工作流】
1. 先调用 get_network_info 确认网络元信息
2. 调用 anomaly_stats_by_type 了解异常分布
3. 调用 get_top_corrections 了解修正方案
4. 综合信息，调用 finish_report 提交最终评语

请开始。"""

SYSTEM_PROMPT = _PROMPTS.get("system_prompt") or _SYSTEM_PROMPT_FALLBACK
USER_PROMPT_TEMPLATE = _PROMPTS.get("user_template") or _USER_PROMPT_FALLBACK


# ── 工具调用解析（Qwen3.5 native format） ──
_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)
_THOUGHT_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)


def _parse_tool_calls(text: str) -> List[Dict[str, Any]]:
    """从 LLM 输出中解析 <tool_call>...</tool_call> 块"""
    matches = _TOOL_CALL_RE.findall(text)
    out = []
    for m in matches:
        try:
            obj = json.loads(m)
            if "name" in obj and "arguments" in obj:
                if isinstance(obj["arguments"], str):
                    obj["arguments"] = json.loads(obj["arguments"])
                out.append(obj)
        except Exception as e:
            logger.warning("bad tool_call JSON: %s", m[:200])
    return out


def _extract_thought(text: str) -> str:
    m = _THOUGHT_RE.search(text)
    return m.group(1).strip() if m else ""


# ── 主类 ──
class ReportAgent:
    """4B LLM 报告生成 Agent（兼容 Qwen3.5 native tool calling）"""

    def __init__(self, server_url: str = DEFAULT_SERVER_URL,
                 model: str = DEFAULT_MODEL,
                 max_turns: int = MAX_TURNS,
                 timeout: int = TIMEOUT_S):
        # v18.7.12: keep public field names for backwards compatibility,
        # but route every backend op through the unified LLMClient facade.
        self.server_url = server_url.rstrip("/")
        self.model = model
        self.max_turns = max_turns
        self.timeout = timeout
        self._client = LLMClient(
            backend="llama-server",
            server_url=server_url,
            model_name=model,
            timeout_s=timeout,
        )
        self._server_ok = False
        self._available = False
        self.status_cache = None

    def health(self) -> Dict[str, Any]:
        """检查 LLM 后端可用性 (v18.7.12: 委托给 LLMClient.health).

        Returns a dict that mirrors the legacy shape but is populated by
        LLMClient which probes llama-server / llama-cpp / rules fallback.
        """
        try:
            h = self._client.health()
            self._server_ok = bool(h.get("ok"))
            self._available = bool(h.get("available", self._server_ok))
            return {
                "ok": self._server_ok,
                "server": self.server_url,
                "model": self.model,
                "available": self._available,
                "backend": h.get("backend", "unknown"),
                "models": h.get("models", [])[:5],
                "error": h.get("error"),
            }
        except Exception as e:
            self._server_ok = False
            self._available = False
            return {"ok": False, "server": self.server_url, "error": str(e)}

    @property
    def available(self) -> bool:
        if self.status_cache is None:
            self.health()
            self.status_cache = self._available
        return self._available

    def _call_llm(self, messages: List[Dict], tools: Optional[List] = None) -> Dict[str, Any]:
        """调用 LLM 后端 (v18.7.12: delegate to LLMClient.chat, reshape to OpenAI shape).

        Previously did requests.post(self.server_url + "/chat/completions") directly,
        creating a dual-stack alongside the LLMClient facade. Now routes through
        self._client.chat() so backend choice (llama-server / llama-cpp / rules)
        is fully owned by LLMClient.
        """
        try:
            chat_resp = self._client.chat(
                messages=messages,
                tools=tools,
                temperature=0.3,
                max_tokens=2048,
            )
            return self._to_openai_shape(chat_resp, model=self.model)
        except Exception as e:
            logger.error("LLM call failed via LLMClient: %s", e)
            raise

    @staticmethod
    def _to_openai_shape(chat_resp, model: str = "") -> Dict[str, Any]:
        """Reshape LLMClient.ChatResponse into OpenAI-compat dict.

        Downstream _parse_tool_calls() reads the choices[0].message.content
        and message.tool_calls fields, so we faithfully reconstruct them.
        """
        tool_calls_out = []
        for tc in (chat_resp.tool_calls or []):
            # LLMClient emits {"name": ..., "arguments": <dict or str>}
            args = tc.get("arguments", {})
            if not isinstance(args, str):
                args = json.dumps(args, ensure_ascii=False)
            tool_calls_out.append({
                "id": tc.get("id", f"call_{len(tool_calls_out)}"),
                "type": "function",
                "function": {
                    "name": tc.get("name", ""),
                    "arguments": args,
                },
            })
        msg = {"role": "assistant", "content": chat_resp.text or ""}
        if tool_calls_out:
            msg["tool_calls"] = tool_calls_out
        return {
            "id": "chatcmpl-" + str(int(time.time() * 1000)),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model or chat_resp.backend or "unknown",
            "choices": [{
                "index": 0,
                "message": msg,
                "finish_reason": "tool_calls" if tool_calls_out else "stop",
            }],
            "usage": {
                "prompt_tokens": chat_resp.tokens_in,
                "completion_tokens": chat_resp.tokens_out,
                "total_tokens": chat_resp.tokens_in + chat_resp.tokens_out,
            },
        }


    def _grounding_ctx_for(self, ctx) -> List[str]:
        """Build grounding context strings from AgentContext."""
        out = []
        if hasattr(ctx, "network_name"):
            out.append(f"network={ctx.network_name}")
        if hasattr(ctx, "anomalies"):
            for a in (ctx.anomalies or [])[:50]:
                t = a.get("type", "")
                loc = a.get("location", "")
                conf = a.get("confidence", 0)
                # [v18.7.16.2] include description (was dropped - missed injection scan).
                # DB row descriptions can carry prompt-injection content.
                desc = a.get("description", "")
                if desc:
                    out.append(f"{t} at {loc} conf={conf}: {desc}")
                else:
                    out.append(f"{t} at {loc} conf={conf}")
        if hasattr(ctx, "corrections"):
            out.append(f"corrections_count={len(ctx.corrections or [])}")
        if hasattr(ctx, "tool_results"):
            out.append(f"tool_calls_count={len(ctx.tool_results or [])}")
        return out

    def run(self, ctx: AgentContext, network_name: str) -> Dict[str, Any]:
        """运行 Agent：多轮工具调用直到 finish_report 或 max_turns

        Returns: {success, turns, review, thoughts, tool_calls, fallback}
        """
        if not self.available:
            return {
                "success": False,
                "fallback": True,
                "review": self._fallback_review(ctx, network_name),
                "turns": 0,
                "reason": "llm server unavailable",
            }

        # [v18.7.16.2] Defense-in-depth: validate ctx_strings BEFORE they enter
        # the LLM prompt. If injection is detected in the upstream data (a
        # tampered DB row carrying injection content), abort early rather
        # than risk prompt poisoning. This is a pre-flight scan; postprocess
        # still does the authoritative check on the LLM response.
        _ctx_strings_for_scan = self._grounding_ctx_for(ctx)
        _ctx_inj_ok, _ctx_inj_hits = _validate_injection("", _ctx_strings_for_scan)
        if not _ctx_inj_ok:
            _ctx_inj_kw_hits = sum(1 for h in _ctx_inj_hits if h.startswith("kw=") or h.startswith("ctx_inj["))
            if _ctx_inj_kw_hits >= _INJECTION_FATAL_THRESHOLD:
                return {
                    "success": False,
                    "fallback": True,
                    "review": self._fallback_review(ctx, network_name),
                    "turns": 0,
                    "reason": "ctx injection detected (pre-flight): " + ";".join(_ctx_inj_hits[:3]),
                    "flagged": _ctx_inj_hits,
                }

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT_TEMPLATE.format(
                network_name=network_name,
                anomaly_count=len(ctx.anomalies),
                correction_count=len(ctx.corrections),
                bus_count=(ctx.network_meta or {}).get("bus_count", 0),
                line_count=(ctx.network_meta or {}).get("line_count", 0),
                trafo_count=(ctx.network_meta or {}).get("trafo_count", 0),
                max_bus_id=(ctx.network_meta or {}).get("max_bus_id", 999),
                max_line_id=(ctx.network_meta or {}).get("max_line_id", 999),
                max_trafo_id=(ctx.network_meta or {}).get("max_trafo_id", 999),
            )},
        ]

        all_thoughts: List[str] = []
        all_tool_calls: List[Dict] = []
        final_review: Optional[Dict[str, str]] = None
        final_narratives: Optional[Dict[str, str]] = None
        t0 = time.time()

        for turn in range(self.max_turns):
            try:
                resp = self._call_llm(messages, tools=TOOLS)
            except Exception as e:
                return {
                    "success": False,
                    "fallback": True,
                    "review": self._fallback_review(ctx, network_name),
                    "turns": turn,
                    "reason": "llm error: " + str(e),
                }

            choice = resp.get("choices", [{}])[0]
            msg = choice.get("message", {})
            content = msg.get("content", "")
            reasoning = msg.get("reasoning_content", "")
            # Qwen3.5 thinking model: if content is empty but reasoning exists, use reasoning
            if not content and reasoning:
                content = reasoning
            tool_calls_raw = msg.get("tool_calls", [])

            # 提取 reasoning
            thought = _extract_thought(content)
            if thought:
                all_thoughts.append(thought)

            # 处理 native tool_calls（Qwen3.5 同时支持原生和文本格式）
            tc_list: List[Dict] = []
            for tc in tool_calls_raw or []:
                fn = tc.get("function", {})
                name = fn.get("name")
                args_raw = fn.get("arguments", "{}")
                try:
                    args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                except Exception:
                    args = {}
                tc_list.append({"name": name, "arguments": args})

            # 兜底：从文本里解析 <tool_call>
            if not tc_list:
                tc_list = _parse_tool_calls(content)

            all_tool_calls.extend(tc_list)

            # 把 assistant 输出加入 messages
            messages.append({"role": "assistant", "content": content})

            # 无工具调用 → 已到自然结尾
            if not tc_list:
                break

            # 执行工具
            for tc in tc_list:
                name = tc.get("name", "")
                args = tc.get("arguments", {})
                result = ctx.dispatch(name, args)
                # 截断过大的结果
                if isinstance(result, list) and len(result) > 30:
                    result = result[:30] + [{"_truncated": "..."}]
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", "call_" + str(turn)),
                    "content": json.dumps(result, ensure_ascii=False, default=str)[:8000],
                })

                # 检测 finish_report (v18.7.12: post-process for schema + grounding + budget)
                if name == "finish_report" and isinstance(result, dict) and "error" not in result:
                    raw_text = json.dumps(result, ensure_ascii=False)
                    pp_result = _pp_process(
                        raw_text=raw_text,
                        ctx_strings=self._grounding_ctx_for(ctx),
                        tool_registry={},
                        schema=AGENT_REPORT_SCHEMA,
                        audit_stack="B",
                        audit_source="llm_assistant.agent.ReportAgent.run.finish_report",
                        audit_schema_name="AGENT_REPORT_SCHEMA",
                        audit_caller=f"ReportAgent.run network={getattr(ctx, 'network_name', '?')}",
                    )
                    narrative_keys = ["overall_assessment", "top3_anomalies_explained",
                                      "correction_priority_reasoning", "risk_forecast",
                                      "recommendation_summary"]
                    if pp_result.success and pp_result.payload:
                        # Postprocess passed: use clean payload.
                        result = pp_result.payload
                        final_review = result
                        if any(k in result for k in narrative_keys):
                            final_narratives = {k: result.get(k, "") for k in narrative_keys}
                    else:
                        # [v18.7.16.2] Postprocess FAILED: drop raw LLM body.
                        # Raw may contain injection/PII/schema violations.
                        # Set final_review to safe marker (so loop breaks) but
                        # leave final_narratives=None so template fills all 5 slots.
                        final_review = {
                            "overall_assessment": "(postprocess gates failed; using template fallback)",
                            "_gates_failed": list(getattr(pp_result, "gates_failed", [])),
                        }
                        final_narratives = None

            if final_review:
                break

        elapsed = time.time() - t0

        if not final_review:
            final_review = {
                "overall_assessment": "（Agent 未在 {} 轮内完成 finish_report，使用模板化评语）".format(self.max_turns),
                "top3_anomalies_explained": "请人工复核 LLM 输出。",
                "correction_priority_reasoning": "",
                "risk_forecast": "",
                "recommendation_summary": "1. 人工核对异常列表\n2. 验证修正方案可行性\n3. 安排现场核查",
            }

        # Ensure all 5 narrative slots exist (fill missing with template)
        if not final_narratives:
            final_narratives = self._template_narratives(ctx, network_name)
        else:
            template = self._template_narratives(ctx, network_name)
            for k, v in template.items():
                if not final_narratives.get(k):
                    final_narratives[k] = v

        # 拼装 markdown 评语
        # Build markdown from narratives
        md = ""
        if final_narratives:
            md = "## 总体性能\n" + final_narratives.get("overall_assessment", "") + "\n\n"
            md += "## 重点异常分析\n" + final_narratives.get("top3_anomalies_explained", "") + "\n\n"
            md += "## 修正优先级\n" + final_narratives.get("correction_priority_reasoning", "") + "\n\n"
            md += "## 风险预警\n" + final_narratives.get("risk_forecast", "") + "\n\n"
            md += "## 建议总结\n" + final_narratives.get("recommendation_summary", "")
        else:
            md = "## 总体性能\n" + final_review.get("summary", final_review.get("overall_assessment", "")) + "\n\n"
            md += "## 异常分析\n" + final_review.get("expert_analysis", final_review.get("top3_anomalies_explained", "")) + "\n\n"
            md += "## 行动项\n" + final_review.get("action_items", final_review.get("recommendation_summary", ""))

        return {
            "success": True,
            "fallback": False,
            "review": md,
            "review_structured": final_review,
            "narratives": final_narratives,
            "turns": turn + 1,
            "elapsed_s": round(elapsed, 1),
            "thoughts": all_thoughts,
            "tool_calls": [{"name": tc["name"], "args": tc.get("arguments", {})} for tc in all_tool_calls],
        }

    @staticmethod
    def _fallback_review(ctx: AgentContext, network_name: str) -> str:
        """LLM 不可用时的模板化评语"""
        n = len(ctx.anomalies)
        c = len(ctx.corrections)
        by_type = {}
        for a in ctx.anomalies:
            t = a.get("type", "unknown")
            by_type[t] = by_type.get(t, 0) + 1
        top3 = sorted(by_type.items(), key=lambda x: -x[1])[:3]
        top3_text = "、".join(t + "(" + str(cnt) + ")" for t, cnt in top3) if top3 else "无"

        return (
            f"## 总体性能\n"
            f"网络 {network_name} 共检出 {n} 条异常，生成 {c} 条修正建议。\n"
            f"本评语由模板生成（4B LLM 未在线），建议人工复核关键异常。\n\n"
            f"## 异常分析\n"
            f"主要异常类型：{top3_text}。"
            f"建议优先处理高置信度（≥0.8）异常，对参数错误和电压类异常重点关注。\n\n"
            f"## 行动项\n"
            f"1. 复核 top3 异常类型，确认数据质量\n"
            f"2. 验证修正方案可行性，必要时现场核查\n"
            f"3. 安排后续检测跟踪\n"
            f"4. 启用 4B LLM 评审以获得更深入分析"
        )

    @staticmethod
    def _template_narratives(ctx: AgentContext, network_name: str) -> Dict[str, str]:
        """Generate 5 narrative slots from data (no LLM needed)."""
        n = len(ctx.anomalies)
        c = len(ctx.corrections)
        by_type: Dict[str, int] = {}
        for a in ctx.anomalies:
            t = a.get("type", "unknown")
            by_type[t] = by_type.get(t, 0) + 1
        top3 = sorted(by_type.items(), key=lambda x: -x[1])[:3]
        top3_names = [t for t, _ in top3] if top3 else ["无"]
        avg_conf = (sum(a.get("confidence", 0) for a in ctx.anomalies) / n) if n else 0
        health = max(0, 100 - n * 5)

        return {
            "overall_assessment": (
                f"网络 {network_name} 共检出 {n} 条异常，生成 {c} 条修正建议。"
                f"平均置信度 {avg_conf:.0%}，系统健康评分 {health}/100。"
                f"建议优先处理高置信度异常，并对参数类和电压类异常进行深入分析。"
            ),
            "top3_anomalies_explained": (
                f"未检测到明显异常。" if n == 0 else
                f"前3类异常：{', '.join(f'{t}({cnt}条)' for t, cnt in top3)}。"
                f"其中 {top3_names[0]} 需重点关注，可能涉及拓扑结构或数据质量问题。"
            ),
            "correction_priority_reasoning": (
                f"当前生成 {c} 条修正建议。"
                f"建议按照异常置信度从高到低排序执行，优先处理拓扑类和参数类异常。"
                f"高置信度（≥0.8）异常应立即处理，低置信度异常需现场核查。"
            ),
            "risk_forecast": (
                f"当前健康评分 {health}/100。"
                + (f"共有 {n} 条未处理异常，存在连锁故障风险。" if n > 5
                   else f"异常数量较少，整体风险可控。")
                + "建议定期巡检，关注电压偏差和拓扑完整性。"
            ),
            "recommendation_summary": (
                "1. \u7acb\u5373\u5904\u7406\u9ad8\u7f6e\u4fe1\u5ea6\u5f02\u5e38\uff0c\u6062\u590d\u62d3\u6251\u5b8c\u6574\u6027\n"
                "2. \u5bf9\u53c2\u6570\u7c7b\u5f02\u5e38\u8fdb\u884c\u73b0\u573a\u6838\u67e5\u548c\u6821\u51c6\n"
                "3. \u5b89\u6392\u540e\u7eed\u68c0\u6d4b\u8ddf\u8e2a\uff0c\u786e\u4fdd\u4fee\u6b63\u6548\u679c\n"
                "4. \u5efa\u7acb\u5f02\u5e38\u8bb0\u5f55\u6863\u6848\uff0c\u4fbf\u4e8e\u5386\u53f2\u56de\u6eaf"
            ),
        }
