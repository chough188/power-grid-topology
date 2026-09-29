# -*- coding: utf-8 -*-
"""
LLM辅助诊断模块 - 配电网异常智能分析与报告生成

架构设计:
  - DiagnosticEngine: 统一诊断引擎（规则引擎+可选LLM润色）
  - LLMEngine: 可迁移的LLM推理引擎
  - EnhancedKnowledgeBase: 28种异常类型知识库
  - AnomalyCorrelator: 异常关联分析
  - CorrectionAdvisor: 修正建议生成
  - DiagnosticReporter: 报告生成

设计原则:
  - LLM只做"润色"，不做"判定"
  - 检测由确定性算法完成
  - 无LLM时100%可用
  - 延迟<100ms（无LLM）/ 3-5秒（有LLM）
"""

# AUTO-GATEKEEPER: self-heals postprocess.py on every import
from llm_assistant._import_gatekeeper import run as _gatekeeper_run
_gatekeeper_run()

# 新版组件（推荐）
from llm_assistant.diagnostic_engine import DiagnosticEngine
from llm_assistant.llm_engine_v2 import LLMEngine

# 旧版组件（兼容）
from llm_assistant.enhanced_llm_v19 import (
    EnhancedKnowledgeBase,
    AnomalyCorrelator,
    CorrectionAdvisor,
    DiagnosticReporter,
)

__all__ = [
    # 新版
    "DiagnosticEngine",
    "LLMEngine",
    # 旧版
    "EnhancedKnowledgeBase",
    "AnomalyCorrelator",
    "CorrectionAdvisor",
    "DiagnosticReporter",
]
