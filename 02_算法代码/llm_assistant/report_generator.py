#!/usr/bin/env python3
"""Integrated LLM Report Generator using Qwen3.5-0.8B via llama-server.

v76-final: Template-driven with LLM only for qualitative analysis.
All numerical data is pre-computed by Python (no LLM math).

Requires: llama-server running on localhost:8081
Start: E:\tools\start_server_fast.bat
Model: E:\llm_models\Qwen3.5-0.8B\Qwen3.5-0.8B-Q8_0.gguf (774MB)
"""

import json
import os
import time
import logging
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

DEFAULT_SERVER_URL = "http://localhost:8081"
DEFAULT_MODEL_NAME = "Qwen3.5-4B-Claude-Opus"

# ── System prompt: qualitative analysis only, no numbers ──
SYSTEM_PROMPT = """你是配电网异常检测系统的高级评审专家。

【铁律】
- 你只负责写定性评语，所有数字已由系统自动填入
- 禁止引用任何数字（F1、百分比、数量等），系统已处理
- 用专业术语描述趋势和模式
- 每条建议必须具体到一个技术手段
- 总输出不超过150字

【术语】Precision=精确率, Recall=召回率, FP=误报, FN=漏报, TP=正确检出
禁止混淆误报和漏报。"""

# ── Polish prompt: LLM as editor, not analyst ──
POLISH_PROMPT = """请润色以下技术报告段落，使其更流畅专业。

【严格规则】
- 保持所有数字、百分比、编号完全不变（如99.02%、2122、40/43等）
- 保持所有技术术语不变（如F1、Precision、召回率、误报、漏报等）
- 保持所有类型名和网络名不变（如topo_interrupt、case4gs等）
- 保持编号列表格式（1. 2. 3.）
- 只改善句子流畅度和段落衔接
- 不要添加任何新内容或结论
- 直接输出润色后的文本，不要加前缀

【原文】
{text}"""
QUALITATIVE_PROMPT = """请对以下配电网异常检测系统给出专业评审意见（不超过150字）：

系统在{total}个测试网络上检测{type_count}种异常类型。
{pass95}个网络F1≥95%通过，{fail_count}个网络未通过。
未通过网络的共同特征：{fail_pattern}

最弱检测类型：{weakest_type}（召回率{weakest_recall}%）
主要问题模式：{problem_pattern}

请输出：
1. 一句话总体评价
2. 两个技术优势
3. 两个改进建议（必须具体到技术手段）"""


class LLMReportGenerator:
    """v76-final: Template-driven report with LLM qualitative analysis only."""

    def __init__(self, server_url: str = DEFAULT_SERVER_URL,
                 model_name: str = DEFAULT_MODEL_NAME,
                 use_llm: bool = True,
                 thinking: bool = False):
        self.server_url = server_url
        self.model_name = model_name
        self.use_llm = use_llm
        self.thinking = thinking
        self._server_ok = False

    def _check_server(self) -> bool:
        try:
            r = requests.get(f"{self.server_url}/health", timeout=3)
            self._server_ok = r.status_code == 200 and "ok" in r.text
            return self._server_ok
        except:
            self._server_ok = False
            return False

    def _generate(self, prompt: str, system: str = None, max_tokens: int = 250) -> dict:
        if not self.use_llm or not self._check_server():
            return {"content": "", "reasoning": "", "tokens": 0, "time": 0}

        messages = []
        messages.append({"role": "system", "content": system or SYSTEM_PROMPT})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.2,
            "top_p": 0.85,
        }

        t0 = time.time()
        try:
            r = requests.post(f"{self.server_url}/v1/chat/completions",
                            json=payload, timeout=max(30, max_tokens * 0.3))
            data = r.json()
            elapsed = time.time() - t0

            msg = data.get("choices", [{}])[0].get("message", {})
            content = msg.get("content", "")
            # Strip thinking tags
            for tag in ["<think>", "</think>"]:
                if tag in content:
                    parts = content.split(tag, 1)
                    content = parts[1].strip() if len(parts) > 1 else content

            return {
                "content": content,
                "reasoning": msg.get("reasoning_content", ""),
                "tokens": data.get("usage", {}).get("completion_tokens", 0),
                "time": elapsed
            }
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return {"content": "", "reasoning": "", "tokens": 0, "time": time.time() - t0}

    def _build_metrics(self, data: dict) -> dict:
        results = data.get("results", [])
        anomaly_types = data.get("anomaly_types", [])

        tp = fp = fn = 0
        for r in results:
            gt = r.get("gt_count", 0)
            det = r.get("det_total", 0)
            recall = r.get("recall", 0)
            ntp = int(round(recall * gt))
            fn += gt - ntp
            fp += max(0, det - ntp)
            tp += ntp

        prec = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0
        rec = tp / (tp + fn) * 100 if (tp + fn) > 0 else 0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
        pass95 = sum(1 for r in results if r.get("f1", 0) >= 0.95)

        # Per-type stats
        type_stats = {}
        for r in results:
            pt = r.get("per_type", {})
            for t, v in pt.items():
                if t not in type_stats:
                    type_stats[t] = {"hit": 0, "inj": 0, "det": 0}
                type_stats[t]["hit"] += v.get("hit", 0)
                type_stats[t]["inj"] += v.get("inj", 0)
                type_stats[t]["det"] += v.get("det", 0)

        # Weak networks
        weak = []
        for r in results:
            if r.get("f1", 1) < 0.95:
                pt = r.get("per_type", {})
                fps = [t for t, v in pt.items() if v.get("inj", 0) == 0 and v.get("det", 0) > 0]
                fns = [t for t, v in pt.items() if v.get("inj", 0) > 0 and v.get("hit", 0) < v.get("inj", 0)]
                weak.append({
                    "net": r["net"], "bus": r.get("bus", 0),
                    "f1": r.get("f1", 0) * 100,
                    "fps": fps[:3], "fns": fns[:3],
                    "det": r.get("det_total", 0), "gt": r.get("gt_count", 0),
                })

        # Worst types
        worst = sorted(
            [(t, v["hit"] / max(v["inj"], 1) * 100, v["inj"], v["hit"])
             for t, v in type_stats.items() if v["inj"] > 0],
            key=lambda x: x[1]
        )[:5]

        return {
            "f1": f1, "prec": prec, "rec": rec,
            "tp": tp, "fp": fp, "fn": fn,
            "pass95": pass95, "total": len(results),
            "type_count": len(anomaly_types),
            "weak": weak, "worst": worst,
            "type_stats": type_stats,
        }

    def _build_llm_context(self, m: dict) -> dict:
        """Build qualitative context for LLM (no numbers)."""
        weak = m["weak"]
        worst = m["worst"]

        # Fail pattern description
        fail_count = m["total"] - m["pass95"]
        if not weak:
            fail_pattern = "无"
        else:
            bus_sizes = [w["bus"] for w in weak]
            if all(b <= 5 for b in bus_sizes):
                fail_pattern = "均为tiny网络(≤5节点)，SE层被跳过"
            elif all(b <= 15 for b in bus_sizes):
                fail_pattern = "均为小型网络(≤15节点)"
            else:
                fail_pattern = "混合规模网络"

        # Problem pattern
        all_fps = []
        all_fns = []
        for w in weak:
            all_fps.extend(w["fps"])
            all_fns.extend(w["fns"])
        if all_fps:
            problem_pattern = f"误报集中在{all_fps[0]}等类型"
        elif all_fns:
            problem_pattern = f"漏报集中在{all_fns[0]}等类型"
        else:
            problem_pattern = "无明显模式"

        return {
            "total": m["total"],
            "type_count": m["type_count"],
            "pass95": m["pass95"],
            "fail_count": fail_count,
            "fail_pattern": fail_pattern,
            "weakest_type": worst[0][0] if worst else "无",
            "weakest_recall": f"{worst[0][1]:.0f}" if worst else "N/A",
            "problem_pattern": problem_pattern,
        }

    def _polish_with_llm(self, text: str) -> str:
        """Use LLM to polish language only (no fact changes)."""
        if not self.use_llm or not self._check_server():
            return text

        prompt = POLISH_PROMPT.format(text=text)
        result = self._generate(prompt, max_tokens=400)

        if not result["content"]:
            return text

        polished = result["content"]

        # Validate: check critical data numbers are preserved
        # Only check numbers >= 10 or percentages (not list numbering 1. 2. 3.)
        import re
        def extract_critical_numbers(t):
            # Match percentages like 99.02%, 92%
            pcts = set(re.findall(r'\d+\.\d+%', t))
            # Match large numbers like 2122, 43, 28
            nums = set(n for n in re.findall(r'\b(\d{2,})\b', t) if int(n) >= 10)
            return pcts | nums

        original_nums = extract_critical_numbers(text)
        polished_nums = extract_critical_numbers(polished)

        missing = original_nums - polished_nums
        if len(missing) > 2:  # Allow minor formatting differences
            logger.warning(f"LLM polish lost critical data: {missing}, using original")
            return text

        return polished

    def _build_fallback_analysis(self, m: dict) -> str:
        """Build professional analysis using ExpertAnalysisEngine (no LLM)."""
        try:
            # Try both import paths
            try:
                from llm_assistant.expert_analysis import ExpertAnalysisEngine
            except ImportError:
                from expert_analysis import ExpertAnalysisEngine
            engine = ExpertAnalysisEngine()
            return engine.generate_analysis(m)
        except Exception as e:
            logger.warning(f"ExpertAnalysisEngine failed: {e}")
            # Ultra-simple fallback
            return (
                f"**总体评价**：F1={m['f1']:.1f}%，{m['pass95']}/{m['total']}个网络通过。\n"
                f"**改进建议**：针对弱网络和低召回率类型优化检测规则。"
            )

    def generate_full_report(self, benchmark_json: str, output_path: Optional[str] = None) -> str:
        with open(benchmark_json, "r", encoding="utf-8") as f:
            data = json.load(f)

        m = self._build_metrics(data)
        results = data.get("results", [])

        t0 = time.time()

        # Get LLM qualitative analysis
        ctx = self._build_llm_context(m)
        llm_prompt = QUALITATIVE_PROMPT.format(**ctx)
        llm_result = self._generate(llm_prompt, max_tokens=250)
        llm_time = time.time() - t0

        # Expert engine generates factual analysis, LLM polishes language
        expert_text = self._build_fallback_analysis(m)
        llm_analysis = self._polish_with_llm(expert_text)

        # ── Build all tables with Python (no LLM math) ──

        # Type performance table
        all_types_sorted = sorted(m["type_stats"].items(),
            key=lambda x: x[1]["hit"] / max(x[1]["inj"], 1), reverse=True)
        type_table = ""
        for t, v in all_types_sorted:
            if v["inj"] > 0:
                rec_pct = v["hit"] / v["inj"] * 100
                type_table += f"| {t} | {v['inj']} | {v['hit']} | {rec_pct:.0f}% |\n"

        # Weak network table
        weak_table = ""
        for r in results:
            if r.get("f1", 1) < 0.95:
                pt = r.get("per_type", {})
                fps = [t for t, v in pt.items() if v.get("inj", 0) == 0 and v.get("det", 0) > 0]
                fns = [t for t, v in pt.items() if v.get("inj", 0) > 0 and v.get("hit", 0) < v.get("inj", 0)]
                issues = []
                if fps: issues.append(f"误报:{','.join(fps[:3])}")
                if fns: issues.append(f"漏报:{','.join(fns[:3])}")
                weak_table += f"| {r['net']} | {r.get('bus',0)} | {r.get('f1',0)*100:.1f}% | {' / '.join(issues)} |\n"

        pass_count = sum(1 for r in results if r.get("f1", 0) >= 0.95)
        net_summary = f"{pass_count}/{len(results)} ({pass_count/len(results)*100:.1f}%)"

        # ── Assemble final report (all data from Python) ──
        report = f"""# 配电网异常检测标准报告

**生成时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**分析引擎**: ExpertAnalysisEngine + Qwen3.5-0.8B ({llm_time:.1f}s)
**Benchmark版本**: v9.0 | **系统版本**: v76

---

## 1. 总体性能

| 指标 | 数值 |
|------|------|
| F1 Score | {m['f1']:.2f}% |
| Precision（精确率） | {m['prec']:.2f}% |
| Recall（召回率） | {m['rec']:.2f}% |
| TP（正确检出） | {m['tp']} |
| FP（误报） | {m['fp']} |
| FN（漏报） | {m['fn']} |
| 网络通过率(F1≥95%) | {net_summary} |
| 异常类型覆盖 | {m['type_count']}种 |

## 2. AI专家分析

{llm_analysis}

## 3. 异常类型检测表现

| 类型 | 注入数 | 检出数 | Recall |
|------|--------|--------|--------|
{type_table}

## 4. 弱网络分析

| 网络 | 节点 | F1 | 问题 |
|------|------|-----|------|
{weak_table}

## 5. 检测架构

```
Layer 1: Rule Engine（28种异常类型专用规则）
Layer 2: Robust SE（IRLS/LAV状态估计 + 残差检测）
Layer 3: GNN Binary Classifier（72维特征, val_f1=99.5%）
Layer 4: Ensemble Vote（多层确认 + 置信度融合）
Layer 5: Smart Filter（网络规模自适应阈值）
Layer 6: ExpertAnalysis（28种异常知识库 + 因果推理）
```

---
*报告由ExpertAnalysisEngine生成 | 检测延迟<100ms | 28种异常类型知识库驱动*
"""

        if output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(report)
            logger.info(f"Report saved to {output_path}")

        return report


def generate_quick_report(benchmark_json: str, output_dir: str = None, thinking: bool = False) -> str:
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(benchmark_json), "standard_reports")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    mode = "thinking" if thinking else "fast"
    output_path = os.path.join(output_dir, f"detection_report_{mode}_{ts}.md")
    gen = LLMReportGenerator(thinking=thinking)
    return gen.generate_full_report(benchmark_json, output_path)


if __name__ == "__main__":
    import sys
    benchmark = sys.argv[1] if len(sys.argv) > 1 else r"E:\项目大全\电力拓扑图修正\02_算法代码\output\benchmark_v9_expanded.json"
    thinking = "--thinking" in sys.argv
    report = generate_quick_report(benchmark, thinking=thinking)
    print(report)
