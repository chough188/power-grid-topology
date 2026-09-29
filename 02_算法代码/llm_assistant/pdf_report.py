# -*- coding: utf-8 -*-
"""PDF 报告生成器（紧凑版 v4）

改进点 v4:
- 超紧凑排版：1.0cm 边距，5.5-6.5pt 表格字体，最小间距
- 丰富图标：Unicode 符号标记严重度/类型/优先级/状态/阶段
- KPI 卡片：4 大关键指标 + 颜色编码
- 修改方案：28类异常全覆盖，每条附带 before→after + 分步操作
- 修正优先级矩阵：按 高/中/低 分组展示修正步骤
- 多图表：严重度饼图 + 类型条形图 + 置信度分布
- 修正流水线：按优先级分阶段展示修正步骤
"""
from __future__ import annotations
import io
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether,
)
from reportlab.graphics.shapes import Drawing, String, Circle, Rect, Line
from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics import renderPDF

import json

logger = logging.getLogger(__name__)

# ── 中文字体注册 ──
def _register_chinese_font() -> str:
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyh.ttf",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ]
    for path in candidates:
        try:
            pdfmetrics.registerFont(TTFont("ZH", path))
            return "ZH"
        except Exception:
            continue
    logger.warning("no Chinese font found, using Helvetica")
    return "Helvetica"


ZH = _register_chinese_font()
ZH_BOLD = ZH

# ── 颜色 ──
C_PRIMARY = colors.HexColor("#1e40af")
C_ACCENT = colors.HexColor("#3b82f6")
C_SUCCESS = colors.HexColor("#16a34a")
C_WARNING = colors.HexColor("#d97706")
C_DANGER = colors.HexColor("#dc2626")
C_MUTED = colors.HexColor("#6b7280")
C_BG_LIGHT = colors.HexColor("#f8fafc")
C_BG_ROW = colors.HexColor("#f1f5f9")
C_BORDER = colors.HexColor("#e2e8f0")
C_WHITE = colors.white
C_BG_DANGER = colors.HexColor("#fef2f2")
C_BG_WARNING = colors.HexColor("#fffbeb")
C_BG_SUCCESS = colors.HexColor("#f0fdf4")
C_INFO = colors.HexColor("#0ea5e9")
C_BG_INFO = colors.HexColor("#f0f9ff")

# ── 图标符号 ──
ICO_HIGH = "\u25cf"       # ● 红色圆点
ICO_MED = "\u25c6"        # ◆ 橙色菱形
ICO_LOW = "\u25cb"        # ○ 绿色空心圆
ICO_CHECK = "\u2713"      # ✓
ICO_CROSS = "\u2717"      # ✗
ICO_ARROW = "\u2192"      # →
ICO_ARROW_R = "\u25b6"    # ▶
ICO_BULLET = "\u2022"     # •
ICO_WARN = "\u26a0"       # ⚠
ICO_STAR = "\u2605"       # ★
ICO_GEAR = "\u2699"       # ⚙
ICO_SHIELD = "\u26e8"     # ⚨
ICO_LIGHTNING = "\u26a1"  # ⚡
ICO_CLOCK = "\u231a"      # ⌚
ICO_TARGET = "\u2316"     # ⌖
ICO_CLIPBOARD = "\u270e"  # ✎
ICO_LOCK = "\u26bf"       # ⚿
ICO_STEP1 = "\u2460"      # ①
ICO_STEP2 = "\u2461"      # ②
ICO_STEP3 = "\u2462"      # ③
ICO_STEP4 = "\u2463"      # ④
ICO_STEP5 = "\u2464"      # ⑤
ICO_PHASE_CONFIRM = "\u25ce"  # ◎
ICO_PHASE_ISOLATE = "\u25d1"  # ◑
ICO_PHASE_CORRECT = "\u25cf"  # ●
ICO_PHASE_VERIFY = "\u25cb"   # ○
ICO_BOX_CHECK = "\u2611"      # ☑
ICO_BOX_EMPTY = "\u2610"      # ☐
ICO_WRENCH = "\u2692"     # ⚒
ICO_TOOL = "\u2697"       # ⚗
ICO_MEDICAL = "\u2695"    # ⚕
ICO_MAGNIFY = "\u2315"    # ⌕
ICO_REFRESH = "\u27f3"    # ⟳
ICO_CAUTION = "\u2622"    # ☢
ICO_OK = "\u2705"         # ✅
ICO_NO = "\u274c"         # ❌
ICO_LIGHT = "\u2600"      # ☀
ICO_CLOUD = "\u2601"      # ☁
ICO_HEART = "\u2764"      # ❤
ICO_CIRCLE_UP = "\u25b2"  # ▲
ICO_CIRCLE_DN = "\u25bc"  # ▼

# 类型图标映射
TYPE_ICO = {
    "topo_interrupt": "\u2192",       # → 断路
    "virtual_faulty": "\u2717",       # ✗ 错接
    "model_mismatch": "\u26a0",       # ⚠ 不符
    "telemetry_mismatch": "\u2260",   # ≠ 矛盾
    "signal_mismatch": "\u2260",      # ≠
    "measurement_outlier": "\u2191",  # ↑ 异常
    "stale_data": "\u231b",           # ⌱ 过期
    "parameter_error": "\u2716",      # ✖
    "load_shift": "\u21c5",           # ⇅
    "reverse_power_flow": "\u21ba",   # ↺
    "communication_loss": "\u2297",   # ⊗
    "voltage_collapse": "\u2193",     # ↓
    "ghost_topology": "\u20e0",       # ⃠
    "duplicate_measurement": "\u2261",# ≡
    "protection_misconfig": "\u26e8", # ⚨
    "trafo_tap_fault": "\u2699",      # ⚙
    "grounding_fault": "\u26a1",      # ⚡
    "clock_drift": "\u231a",          # ⌚
    "harmonic_pollution": "\u223c",   # ∼
    "impedance_degradation": "\u2198",# ↘
    "dg_intermittent": "\u21c4",      # ⇄
    "measurement_bias": "\u2260",     # ≠
    "branch_contingency": "\u2192",   # →
    "topo_obfuscation": "\u2753",     # ❓
    "voltage_regulation": "\u2191",   # ↑
    "bus_section_mismatch": "\u2260", # ≠
    "bypass_operation": "\u21cc",     # ⇌
    "load_transfer_residual": "\u2198",# ↘
}

# 中文类型名
TYPE_CN = {
    "topo_interrupt": "拓扑中断", "virtual_faulty": "虚接错接",
    "model_mismatch": "图模不符", "telemetry_mismatch": "遥测矛盾",
    "signal_mismatch": "遥信矛盾", "measurement_outlier": "量测异常",
    "stale_data": "数据过期", "parameter_error": "参数错误",
    "load_shift": "负荷突变", "reverse_power_flow": "反向潮流",
    "communication_loss": "通信中断", "voltage_collapse": "电压崩溃",
    "ghost_topology": "幽灵拓扑", "duplicate_measurement": "重复量测",
    "protection_misconfig": "保护误配", "trafo_tap_fault": "分接头故障",
    "grounding_fault": "接地故障", "clock_drift": "时钟偏移",
    "harmonic_pollution": "谐波污染", "impedance_degradation": "阻抗退化",
    "dg_intermittent": "DG间歇", "measurement_bias": "量测偏差",
    "branch_contingency": "支路停运", "topo_obfuscation": "拓扑混淆",
    "voltage_regulation": "电压调节", "bus_section_mismatch": "母线失配",
    "bypass_operation": "旁路运行", "load_transfer_residual": "转供残差",
    # 兼容中文名
    "不良数据": "不良数据",
    "CIM独有设备": "图模不符",
}

# 修正方案关键词 → 具体修改建议映射（28 类全覆盖）
ACTION_DETAIL = {
    "sync_model": {
        "title": "同步图模",
        "before": "CIM模型与SVG图形不一致",
        "after": "补全缺失设备映射，确保CIM-SVG一一对应",
        "steps": ["1.导出CIM设备清单", "2.比对SVG图形元素", "3.补充缺失映射关系", "4.验证图模一致性"],
    },
    "check_switch_or_line": {
        "title": "排查开关/线路",
        "before": "拓扑连通性中断，存在孤立供电区",
        "after": "恢复连通路径，消除供电孤岛",
        "steps": ["1.定位断点位置", "2.检查开关状态", "3.确认线路完整性", "4.恢复连通运行"],
    },
    "check_connection": {
        "title": "检查接线",
        "before": "设备连接关系异常",
        "after": "修正接线，恢复正确拓扑",
        "steps": ["1.核查设备端子连接", "2.验证拓扑节点映射", "3.修正错误连接", "4.确认潮流方向"],
    },
    "calibrate_sensor": {
        "title": "校准量测",
        "before": "量测值偏差超出允许范围",
        "after": "校准后量测值与状态估计一致",
        "steps": ["1.比对量测与估计值", "2.检查传感器状态", "3.校准或更换设备", "4.验证量测精度"],
    },
    "verify_switch_state": {
        "title": "核实开关状态",
        "before": "遥信状态与实际拓扑矛盾",
        "after": "遥信与拓扑状态一致",
        "steps": ["1.核查SCADA遥信", "2.现场确认开关位置", "3.修正遥信信号", "4.验证一致性"],
    },
    "remove_or_correct": {
        "title": "剔除/修正坏数据",
        "before": "量测含不良数据，残差异常",
        "after": "使用状态估计值替代，残差归一",
        "steps": ["1.识别可疑量测", "2.交叉验证", "3.剔除坏数据", "4.用估计值替代"],
    },
    "emergency_rebalance": {
        "title": "紧急再平衡",
        "before": "电压越限，存在崩溃风险",
        "after": "电压恢复至0.95-1.05p.u.安全范围",
        "steps": ["1.启动紧急调压", "2.切负荷或投电容", "3.调整变压器分接头", "4.监测电压恢复"],
    },
    # ── 28 类全覆盖修正方案 ──
    "restore_topology": {
        "title": "恢复拓扑连通",
        "before": "线路或开关断开导致供电孤岛",
        "after": "拓扑连通性恢复正常，无孤立节点",
        "steps": ["1.扫描全网拓扑连通分量", "2.定位断点设备", "3.合闸或修复断线", "4.验证连通性"],
    },
    "fix_wiring": {
        "title": "修正虚接/错接",
        "before": "设备端子连接错误，潮流路径异常",
        "after": "接线正确，潮流路径符合设计",
        "steps": ["1.核查设备端子编号", "2.比对设计图纸", "3.修正错误接线", "4.绝缘测试"],
    },
    "refresh_data": {
        "title": "刷新过期数据",
        "before": "量测数据时间戳过旧，不反映当前状态",
        "after": "量测数据实时更新，时间戳新鲜",
        "steps": ["1.检查通道通信状态", "2.重启数据采集服务", "3.手动触发数据刷新", "4.验证时间戳"],
    },
    "reconfigure_protection": {
        "title": "重配保护定值",
        "before": "保护定值与运行方式不匹配",
        "after": "保护定值与当前运行方式匹配",
        "steps": ["1.获取当前运行方式", "2.计算保护定值", "3.下装新定值", "4.传动试验验证"],
    },
    "adjust_tap": {
        "title": "调整分接头",
        "before": "变压器分接头位置与电压需求不匹配",
        "after": "分接头位置正确，电压合格",
        "steps": ["1.检查分接头当前位置", "2.计算目标电压比", "3.调节分接头档位", "4.验证输出电压"],
    },
    "repair_grounding": {
        "title": "修复接地",
        "before": "接地回路阻抗异常或断开",
        "after": "接地电阻合格，接地回路完整",
        "steps": ["1.测量接地电阻", "2.检查接地引下线", "3.修复断点或补打接地极", "4.复测接地电阻"],
    },
    "sync_clock": {
        "title": "同步时钟",
        "before": "设备时钟偏差导致量测时间戳不一致",
        "after": "全网设备时钟同步，偏差<1ms",
        "steps": ["1.检查NTP/PTP服务状态", "2.校准主时钟源", "3.逐级同步子站时钟", "4.验证时间戳一致性"],
    },
    "filter_harmonics": {
        "title": "滤除谐波",
        "before": "谐波含量超标，电能质量下降",
        "after": "THD降至标准限值以内",
        "steps": ["1.频谱分析定位谐波源", "2.安装或调整滤波器", "3.监测谐波含量变化", "4.验证THD合格"],
    },
    "replace_degraded": {
        "title": "更换退化设备",
        "before": "阻抗参数偏离额定值，损耗增加",
        "after": "阻抗恢复正常，损耗达标",
        "steps": ["1.阻抗测试定位退化设备", "2.评估老化程度", "3.更换或维修设备", "4.复测阻抗参数"],
    },
    "manage_dg": {
        "title": "管理DG出力",
        "before": "分布式电源间歇性出力导致电压波动",
        "after": "DG出力平滑，电压稳定",
        "steps": ["1.检查DG并网逆变器", "2.调整无功补偿", "3.启用功率平滑控制", "4.监测电压波动"],
    },
    "fix_communication": {
        "title": "修复通信链路",
        "before": "通信中断导致遥信/遥测数据丢失",
        "after": "通信恢复正常，数据完整",
        "steps": ["1.检查光缆/载波通道", "2.测试通信设备", "3.重启或更换故障节点", "4.验证数据完整性"],
    },
    "transfer_load": {
        "title": "转移负荷",
        "before": "局部负荷过重，设备过载风险",
        "after": "负荷均匀分布，无过载风险",
        "steps": ["1.分析负荷分布", "2.识别过载区域", "3.制定转供方案", "4.执行负荷转移"],
    },
    "reverse_flow_fix": {
        "title": "消除反向潮流",
        "before": "反向潮流导致保护误动风险",
        "after": "潮流方向正常，保护可靠",
        "steps": ["1.定位反向潮流区段", "2.分析DG出力与负荷平衡", "3.调整运行方式", "4.验证潮流方向"],
    },
    "n1_contingency": {
        "title": "N-1安全校核",
        "before": "支路停运后系统不满足N-1准则",
        "after": "满足N-1安全准则，无过载",
        "steps": ["1.枚举N-1故障场景", "2.计算各场景潮流", "3.识别薄弱环节", "4.制定加固方案"],
    },
    "resection_bus": {
        "title": "重新分段母线",
        "before": "母线分段与实际拓扑不匹配",
        "after": "母线分段正确，拓扑模型一致",
        "steps": ["1.核查母线分段开关状态", "2.比对模型与实际", "3.修正分段定义", "4.验证拓扑正确性"],
    },
    "clear_ghost": {
        "title": "清除幽灵设备",
        "before": "模型中存在不存在的幽灵设备/节点",
        "after": "模型干净，无冗余幽灵元素",
        "steps": ["1.比对现场设备清单", "2.识别幽灵设备", "3.从模型中删除", "4.验证模型完整性"],
    },
    "deduplicate": {
        "title": "去重量测",
        "before": "同一物理量存在多个重复量测",
        "after": "去重后唯一量测，数据源可信",
        "steps": ["1.聚类相同物理量量测", "2.评估各数据源可信度", "3.保留最优量测", "4.标记废弃数据"],
    },
    "deobfuscate": {
        "title": "消除拓扑混淆",
        "before": "拓扑命名/编号混乱，难以维护",
        "after": "命名规范统一，拓扑清晰可读",
        "steps": ["1.分析命名规则冲突", "2.制定统一命名规范", "3.批量重命名", "4.更新关联引用"],
    },
    "investigate": {
        "title": "现场核查",
        "before": "自动检测发现异常，需人工确认",
        "after": "异常确认并处理",
        "steps": ["1.导出异常详情", "2.现场巡检确认", "3.制定处理方案", "4.执行并闭环"],
    },
    "check_bypass": {
        "title": "检查旁路状态",
        "before": "旁路开关状态异常，影响正常供电路径",
        "after": "旁路状态正确，供电路径正常",
        "steps": ["1.核查旁路开关位置", "2.确认旁路投入/退出状态", "3.修正开关状态", "4.验证供电路径"],
    },
    "resolve_residual": {
        "title": "消除转供残差",
        "before": "负荷转供后残留异常，部分区域未恢复",
        "after": "转供完成，全部区域供电正常",
        "steps": ["1.扫描转供后拓扑", "2.识别残留异常区段", "3.完成剩余转供操作", "4.全面验证供电恢复"],
    },
}

# 异常类型 → 默认修正动作映射
TYPE_ACTION_MAP = {
    "topo_interrupt": "restore_topology",
    "virtual_faulty": "fix_wiring",
    "model_mismatch": "sync_model",
    "telemetry_mismatch": "calibrate_sensor",
    "signal_mismatch": "verify_switch_state",
    "measurement_outlier": "remove_or_correct",
    "stale_data": "refresh_data",
    "parameter_error": "remove_or_correct",
    "load_shift": "transfer_load",
    "reverse_power_flow": "reverse_flow_fix",
    "communication_loss": "fix_communication",
    "voltage_collapse": "emergency_rebalance",
    "ghost_topology": "clear_ghost",
    "duplicate_measurement": "deduplicate",
    "protection_misconfig": "reconfigure_protection",
    "trafo_tap_fault": "adjust_tap",
    "grounding_fault": "repair_grounding",
    "clock_drift": "sync_clock",
    "harmonic_pollution": "filter_harmonics",
    "impedance_degradation": "replace_degraded",
    "dg_intermittent": "manage_dg",
    "measurement_bias": "calibrate_sensor",
    "branch_contingency": "n1_contingency",
    "topo_obfuscation": "deobfuscate",
    "voltage_regulation": "emergency_rebalance",
    "bus_section_mismatch": "resection_bus",
    "bypass_operation": "check_bypass",
    "load_transfer_residual": "resolve_residual",
    "不良数据": "remove_or_correct",
}

# 检测层中文名
LAYER_CN = {
    "rule_engine": "规则引擎",
    "state_estimator": "状态估计",
    "signal_mismatch": "遥信失配",
    "gnn": "GNN检测",
    "physics": "物理验证",
    "outlier": "异常值检测",
    "robust": "鲁棒检测",
    "telemetry": "遥测检测",
    "stale": "过期检测",
    "parameter": "参数检测",
    "load": "负荷检测",
    "rpf": "反向潮流",
    "comm": "通信检测",
    "vc": "电压检测",
    "ghost": "幽灵检测",
    "se": "状态估计",
    "signal": "遥信检测",
}


# ── 样式表 ──
def _build_styles() -> Dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontName=ZH_BOLD,
                                 fontSize=13, leading=16, textColor=C_PRIMARY,
                                 alignment=TA_CENTER, spaceAfter=1),
        "subtitle": ParagraphStyle("subtitle", parent=base["BodyText"], fontName=ZH,
                                    fontSize=6.5, leading=8.5, textColor=C_MUTED,
                                    alignment=TA_CENTER, spaceAfter=0),
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontName=ZH_BOLD,
                              fontSize=8, leading=10.5, textColor=C_PRIMARY,
                              spaceBefore=2, spaceAfter=1),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName=ZH_BOLD,
                              fontSize=7, leading=9, textColor=C_ACCENT,
                              spaceBefore=1, spaceAfter=0),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontName=ZH,
                                fontSize=6, leading=8, alignment=TA_JUSTIFY,
                                spaceAfter=1),
        "body_tight": ParagraphStyle("body_tight", parent=base["BodyText"], fontName=ZH,
                                      fontSize=5.5, leading=7.5, spaceAfter=0),
        "small": ParagraphStyle("small", parent=base["BodyText"], fontName=ZH,
                                 fontSize=5, leading=6.5, textColor=C_MUTED),
        "kpi_val": ParagraphStyle("kpi_val", parent=base["BodyText"], fontName=ZH_BOLD,
                                   fontSize=11, leading=14, alignment=TA_CENTER,
                                   textColor=C_PRIMARY),
        "kpi_label": ParagraphStyle("kpi_label", parent=base["BodyText"], fontName=ZH,
                                     fontSize=5, leading=6.5, alignment=TA_CENTER,
                                     textColor=C_MUTED),
        "quote": ParagraphStyle("quote", parent=base["BodyText"], fontName=ZH,
                                 fontSize=6, leading=8, leftIndent=3, rightIndent=3,
                                 textColor=colors.HexColor("#374151"),
                                 backColor=C_BG_LIGHT,
                                 borderPadding=1, spaceAfter=1),
        "corr_title": ParagraphStyle("corr_title", parent=base["BodyText"], fontName=ZH_BOLD,
                                      fontSize=6.5, leading=8.5, spaceAfter=0),
        "corr_body": ParagraphStyle("corr_body", parent=base["BodyText"], fontName=ZH,
                                     fontSize=5.5, leading=7.5, leftIndent=4,
                                     textColor=colors.HexColor("#4b5563"), spaceAfter=0),
        "step": ParagraphStyle("step", parent=base["BodyText"], fontName=ZH,
                                fontSize=5, leading=6.5, leftIndent=6,
                                textColor=C_MUTED, spaceAfter=0),
        "badge": ParagraphStyle("badge", parent=base["BodyText"], fontName=ZH_BOLD,
                                 fontSize=5, leading=6.5, alignment=TA_CENTER),
        "phase_title": ParagraphStyle("phase_title", parent=base["BodyText"], fontName=ZH_BOLD,
                                       fontSize=6, leading=7.5, spaceAfter=0),
        "modify_detail": ParagraphStyle("modify_detail", parent=base["BodyText"], fontName=ZH,
                                         fontSize=5, leading=6.5, leftIndent=4,
                                         textColor=colors.HexColor("#374151"), spaceAfter=0),
        # v5 new: phase step style (icon + short label)
        "phase_step": ParagraphStyle("phase_step", parent=base["BodyText"], fontName=ZH,
                                      fontSize=5, leading=6.5, leftIndent=8,
                                      textColor=C_MUTED, spaceAfter=0),
        # v5 new: priority tag inside modify plan summary box
        "prio_tag": ParagraphStyle("prio_tag", parent=base["BodyText"], fontName=ZH_BOLD,
                                    fontSize=6.5, leading=8, alignment=TA_CENTER,
                                    textColor=C_WHITE),
    }


def _sev_color(confidence: float) -> colors.Color:
    if confidence >= 0.8: return C_DANGER
    if confidence >= 0.6: return C_WARNING
    return C_SUCCESS

def _sev_icon(confidence: float) -> str:
    if confidence >= 0.8: return ICO_HIGH
    if confidence >= 0.6: return ICO_MED
    return ICO_LOW

def _sev_label(confidence: float) -> str:
    if confidence >= 0.8: return "高危"
    if confidence >= 0.6: return "中等"
    return "低危"

def _prio_color(prio: str) -> colors.Color:
    p = str(prio).lower()
    if p in ("高", "high", "紧急", "urgent"): return C_DANGER
    if p in ("中", "med", "medium"): return C_WARNING
    return C_SUCCESS

def _prio_icon(prio: str) -> str:
    p = str(prio).lower()
    if p in ("高", "high", "紧急", "urgent"): return ICO_HIGH
    if p in ("中", "med", "medium"): return ICO_MED
    return ICO_LOW

def _prio_bg(prio: str) -> colors.Color:
    p = str(prio).lower()
    if p in ("高", "high", "紧急", "urgent"): return C_BG_DANGER
    if p in ("中", "med", "medium"): return C_BG_WARNING
    return C_BG_SUCCESS

def _colored(text: str, color: colors.Color) -> str:
    return f'<font color="#{color.hexval()[2:]}">{text}</font>'

def _badge(text: str, bg: colors.Color, fg: colors.Color = C_WHITE) -> str:
    return f'<font color="#{fg.hexval()[2:]}" backColor="#{bg.hexval()[2:]}">{text}</font>'


class PDFReportGenerator:
    """PDF 报告生成器：检测 + 修正 + 修改方案 + (可选) LLM 评语 → PDF bytes"""

    def __init__(self):
        self.styles = _build_styles()
        self.llm_review: Optional[str] = None
        self.narratives: Optional[Dict[str, str]] = None

    def generate(self, data: Dict[str, Any], llm_review: Optional[str] = None,
                 narratives: Optional[Dict[str, str]] = None) -> bytes:
        self.llm_review = llm_review
        self.narratives = narratives
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=A4,
            leftMargin=1.0*cm, rightMargin=1.0*cm,
            topMargin=1.0*cm, bottomMargin=1.0*cm,
            title="配电网拓扑智能识别与修正报告",
        )
        story = self._build_story(data, narratives)
        doc.build(story, onFirstPage=self._footer, onLaterPages=self._footer)
        pdf = buf.getvalue()
        buf.close()
        return pdf

    def _build_story(self, data: Dict[str, Any], narratives: Optional[Dict[str, str]] = None) -> List:
        s = self.styles
        story = []
        net = data.get("network_name", "?")
        dets = data.get("anomalies") or data.get("detections") or []
        cors = data.get("corrections") or []
        summary = data.get("summary") or {}
        meta = data.get("network_meta") or {}

        n_anom = len(dets)
        n_corr = len(cors)
        avg_conf = (sum(d.get("confidence", 0) for d in dets) / n_anom) if n_anom else 0
        health = max(0, 100 - n_anom * 5)

        # ── 封面（超紧凑） ──
        story.append(Paragraph("配电网拓扑智能识别与修正报告", s["title"]))
        story.append(Paragraph("Distribution Topology Anomaly Detection & Correction Report", s["subtitle"]))
        story.append(Spacer(1, 2))
        cover_info = (
            f"<b>{ICO_GEAR} 网络</b>：{net}　"
            f"<b>{ICO_BULLET} 母线</b>：{meta.get('buses', '?')}　"
            f"<b>{ICO_BULLET} 线路</b>：{meta.get('lines', '?')}　"
            f"<b>{ICO_CLOCK} 时间</b>：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        story.append(Paragraph(cover_info, s["body"]))

        # ── KPI 卡片（4 格，紧凑） ──
        story.append(Spacer(1, 3))
        h_color = "#16a34a" if health >= 80 else "#d97706" if health >= 60 else "#dc2626"
        kpi_data = [
            [Paragraph(f'<font size="12" color="#1e40af"><b>{n_anom}</b></font>', s["kpi_val"]),
             Paragraph(f'<font size="12" color="#16a34a"><b>{avg_conf:.0%}</b></font>', s["kpi_val"]),
             Paragraph(f'<font size="12" color="#d97706"><b>{n_corr}</b></font>', s["kpi_val"]),
             Paragraph(f'<font size="12" color="{h_color}"><b>{health}</b></font>', s["kpi_val"])],
            [Paragraph(f"{ICO_WARN} 检出异常", s["kpi_label"]),
             Paragraph(f"{ICO_TARGET} 平均置信度", s["kpi_label"]),
             Paragraph(f"{ICO_CLIPBOARD} 修正方案", s["kpi_label"]),
             Paragraph(f"{ICO_SHIELD} 健康评分", s["kpi_label"])],
        ]
        kpi_table = Table(kpi_data, colWidths=[4.3*cm]*4)
        kpi_table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), C_BG_LIGHT),
            ("BOX", (0,0), (-1,-1), 0.5, C_BORDER),
            ("INNERGRID", (0,0), (-1,-1), 0.3, C_BORDER),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("TOPPADDING", (0,0), (-1,0), 3),
            ("BOTTOMPADDING", (0,1), (-1,1), 3),
            ("LEFTPADDING", (0,0), (-1,-1), 2),
            ("RIGHTPADDING", (0,0), (-1,-1), 2),
        ]))
        story.append(kpi_table)

        # ── 1. 修改方案总览（重点提升） ──
        story.append(Spacer(1, 2))
        story.append(Paragraph(
            f"1 {ICO_STAR} {ICO_WRENCH} 修改方案总览", s["h1"]))
        all_corrs = cors if cors else self._build_suggested_corrections(dets)
        story.append(self._build_modify_plan_prominent(all_corrs))

        # ── 2. 异常分布 ──
        story.append(Spacer(1, 2))
        story.append(Paragraph(f"2 {ICO_STAR} 异常分布", s["h1"]))

        # 严重度统计（紧凑行内显示）
        high_n = sum(1 for d in dets if d.get("confidence", 0) >= 0.8)
        med_n = sum(1 for d in dets if 0.6 <= d.get("confidence", 0) < 0.8)
        low_n = sum(1 for d in dets if d.get("confidence", 0) < 0.6)
        if n_anom > 0:
            sev_text = (
                f'{_colored(ICO_HIGH, C_DANGER)} 高危 <b>{high_n}</b>　'
                f'{_colored(ICO_MED, C_WARNING)} 中等 <b>{med_n}</b>　'
                f'{_colored(ICO_LOW, C_SUCCESS)} 低危 <b>{low_n}</b>　'
                f'共 <b>{n_anom}</b> 条'
            )
            story.append(Paragraph(sev_text, s["body"]))

        # 类型分布（紧凑 3 列表格）
        by_type: Dict[str, int] = {}
        for d in dets:
            t = d.get("type", "unknown")
            by_type[t] = by_type.get(t, 0) + 1

        if by_type:
            story.append(Spacer(1, 1))
            cols = 3
            items = sorted(by_type.items(), key=lambda x: -x[1])
            rows = []
            for chunk_start in range(0, len(items), cols):
                row = []
                for j in range(cols):
                    idx = chunk_start + j
                    if idx < len(items):
                        t, c = items[idx]
                        cn = TYPE_CN.get(t, t)
                        ico = TYPE_ICO.get(t, ICO_BULLET)
                        pct = c / n_anom * 100 if n_anom else 0
                        row.append(Paragraph(
                            f'{ico} {cn} <font color="#6b7280">x{c}({pct:.0f}%)</font>',
                            s["body_tight"]))
                    else:
                        row.append(Paragraph("", s["body_tight"]))
                rows.append(row)
            if rows:
                t = Table(rows, colWidths=[5.8*cm]*cols)
                t.setStyle(TableStyle([
                    ("BACKGROUND", (0,0), (-1,-1), C_WHITE),
                    ("BOX", (0,0), (-1,-1), 0.3, C_BORDER),
                    ("INNERGRID", (0,0), (-1,-1), 0.2, C_BORDER),
                    ("TOPPADDING", (0,0), (-1,-1), 1),
                    ("BOTTOMPADDING", (0,0), (-1,-1), 1),
                    ("LEFTPADDING", (0,0), (-1,-1), 2),
                ]))
                story.append(t)

        # 类型分布条形图（仅 >1 种类型时显示）
        if by_type and len(by_type) > 1:
            story.append(Spacer(1, 1))
            story.append(self._make_bar_chart(by_type))

        # ── 3. 异常明细表 ──
        story.append(Spacer(1, 2))
        story.append(Paragraph(f"3 {ICO_STAR} 异常明细 (Top 30)", s["h1"]))
        if dets:
            rows = [[
                Paragraph("<b>#</b>", s["body_tight"]),
                Paragraph("<b>类型</b>", s["body_tight"]),
                Paragraph("<b>位置</b>", s["body_tight"]),
                Paragraph("<b>置信</b>", s["body_tight"]),
                Paragraph("<b>等级</b>", s["body_tight"]),
                Paragraph("<b>层</b>", s["body_tight"]),
            ]]
            for i, d in enumerate(dets[:30], 1):
                t = d.get("type", "unknown")
                cn = TYPE_CN.get(t, t)
                ico = TYPE_ICO.get(t, ICO_BULLET)
                conf = d.get("confidence", 0)
                sev_c = _sev_color(conf)
                sev_i = _sev_icon(conf)
                sev_l = _sev_label(conf)
                layer = d.get("layer", d.get("source", "?"))
                layer_cn = LAYER_CN.get(str(layer), str(layer))
                rows.append([
                    Paragraph(str(i), s["body_tight"]),
                    Paragraph(f'{ico} {cn}', s["body_tight"]),
                    Paragraph(str(d.get("location", d.get("element", "?")))[:20], s["body_tight"]),
                    Paragraph(f'<font color="#{sev_c.hexval()[2:]}">{conf:.0%}</font>', s["body_tight"]),
                    Paragraph(f'<font color="#{sev_c.hexval()[2:]}">{sev_i}{sev_l}</font>', s["body_tight"]),
                    Paragraph(layer_cn, s["body_tight"]),
                ])
            t = Table(rows, colWidths=[0.7*cm, 2.5*cm, 4*cm, 1.5*cm, 1.5*cm, 2.5*cm])
            t.setStyle(TableStyle([
                ("FONTNAME", (0,0), (-1,-1), ZH),
                ("FONTSIZE", (0,0), (-1,-1), 5.5),
                ("BACKGROUND", (0,0), (-1,0), C_PRIMARY),
                ("TEXTCOLOR", (0,0), (-1,0), C_WHITE),
                ("ROWBACKGROUNDS", (0,1), (-1,-1), [C_WHITE, C_BG_ROW]),
                ("GRID", (0,0), (-1,-1), 0.2, C_BORDER),
                ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                ("TOPPADDING", (0,0), (-1,-1), 1),
                ("BOTTOMPADDING", (0,0), (-1,-1), 1),
                ("LEFTPADDING", (0,0), (-1,-1), 2),
                ("RIGHTPADDING", (0,0), (-1,-1), 2),
            ]))
            story.append(t)
        else:
            story.append(Paragraph(f"{ICO_CHECK} 未检测到异常", s["body"]))

        # ── 4. 修改方案详情 ──
        story.append(Spacer(1, 1.5))
        story.append(Paragraph(f"4 {ICO_STAR} 修改方案详情", s["h1"]))

        if cors:
            # 统计摘要
            prio_high = sum(1 for c in cors if str(c.get("priority", "")).lower() in ("高", "high", "紧急", "urgent"))
            prio_med = sum(1 for c in cors if str(c.get("priority", "")).lower() in ("中", "med", "medium"))
            prio_low = len(cors) - prio_high - prio_med
            verified = sum(1 for c in cors if c.get("verification_passed"))
            story.append(Paragraph(
                f'共 <b>{len(cors)}</b> 条方案　'
                f'{_colored(ICO_HIGH, C_DANGER)} 高优<b>{prio_high}</b>　'
                f'{_colored(ICO_MED, C_WARNING)} 中优<b>{prio_med}</b>　'
                f'{_colored(ICO_LOW, C_SUCCESS)} 低优<b>{prio_low}</b>　'
                f'{_colored(ICO_BOX_CHECK, C_INFO)} 已验证<b>{verified}</b>',
                s["body"]))
            story.append(Spacer(1, 1))

            for i, c in enumerate(cors[:20], 1):
                story.append(self._build_correction_card(i, c))
        else:
            # 无修正方案时，为每个异常类型生成修改建议
            if dets:
                story.append(Paragraph(
                    f"{ICO_WARN} 修正引擎未返回方案，以下为基于异常类型的建议修改：",
                    s["body"]))
                story.append(Spacer(1, 1))
                # 按异常类型分组生成建议
                seen_types = set()
                idx = 0
                for d in dets[:15]:
                    atype = d.get("type", "unknown")
                    if atype in seen_types:
                        continue
                    seen_types.add(atype)
                    idx += 1
                    # 生成伪修正方案
                    pseudo_corr = {
                        "anomaly_type": atype,
                        "action": self._suggest_action(atype),
                        "priority": "高" if d.get("confidence", 0) >= 0.8 else "中",
                        "target": d.get("location", d.get("element", "?")),
                        "description": f'{TYPE_CN.get(atype, atype)}: {d.get("description", "需现场核查")}',
                        "confidence": d.get("confidence", 0),
                        "verification_passed": False,
                        "_suggested": True,
                    }
                    story.append(self._build_correction_card(idx, pseudo_corr))
            else:
                story.append(Paragraph(f"{ICO_CHECK} 无需修正", s["body"]))

        # ── 5. 修正优先级矩阵 ──
        story.append(Spacer(1, 1.5))
        story.append(Paragraph(f"5 {ICO_STAR} 修正优先级矩阵", s["h1"]))

        # 构建优先级矩阵表格
        all_corrs = cors if cors else self._build_suggested_corrections(dets)
        if all_corrs:
            prio_rows = [[
                Paragraph("<b>优先级</b>", s["body_tight"]),
                Paragraph("<b>类型</b>", s["body_tight"]),
                Paragraph("<b>修正动作</b>", s["body_tight"]),
                Paragraph("<b>关键步骤</b>", s["body_tight"]),
                Paragraph("<b>状态</b>", s["body_tight"]),
            ]]
            for i, c in enumerate(all_corrs[:15], 1):
                prio = c.get("priority", "中")
                pc = _prio_color(prio)
                pi = _prio_icon(prio)
                atype = c.get("anomaly_type", "?")
                cn = TYPE_CN.get(atype, atype)
                ico = TYPE_ICO.get(atype, ICO_BULLET)
                action = c.get("action", "investigate")
                action_info = ACTION_DETAIL.get(action, {})
                action_title = action_info.get("title", action)
                steps = action_info.get("steps", [])
                key_step = steps[0] if steps else "—"
                verified = c.get("verification_passed", False)
                status_ico = ICO_BOX_CHECK if verified else ICO_BOX_EMPTY
                prio_rows.append([
                    Paragraph(f'<font color="#{pc.hexval()[2:]}">{pi} {prio}</font>', s["body_tight"]),
                    Paragraph(f'{ico} {cn}', s["body_tight"]),
                    Paragraph(f'{ICO_WRENCH} {action_title}', s["body_tight"]),
                    Paragraph(key_step[:25], s["body_tight"]),
                    Paragraph(status_ico, s["body_tight"]),
                ])
            pt = Table(prio_rows, colWidths=[1.3*cm, 2.2*cm, 3*cm, 5*cm, 1*cm])
            pt.setStyle(TableStyle([
                ("FONTNAME", (0,0), (-1,-1), ZH),
                ("FONTSIZE", (0,0), (-1,-1), 5.5),
                ("BACKGROUND", (0,0), (-1,0), C_ACCENT),
                ("TEXTCOLOR", (0,0), (-1,0), C_WHITE),
                ("ROWBACKGROUNDS", (0,1), (-1,-1), [C_WHITE, C_BG_ROW]),
                ("GRID", (0,0), (-1,-1), 0.2, C_BORDER),
                ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                ("TOPPADDING", (0,0), (-1,-1), 1),
                ("BOTTOMPADDING", (0,0), (-1,-1), 1),
                ("LEFTPADDING", (0,0), (-1,-1), 2),
                ("RIGHTPADDING", (0,0), (-1,-1), 2),
            ]))
            story.append(pt)

        # ── 6. LLM 评语 ──
        story.append(Spacer(1, 2))
        story.append(Paragraph(f"6 {ICO_STAR} LLM 智能评语", s["h1"]))
        if narratives is None:
            narratives = self.narratives or {}
        if narratives:
            slots = [
                ("overall_assessment", f"{ICO_TARGET} 总体评估"),
                ("top3_anomalies_explained", f"{ICO_LIGHTNING} 重点异常"),
                ("correction_priority_reasoning", f"{ICO_CLIPBOARD} 修正优先级"),
                ("risk_forecast", f"{ICO_WARN} 风险预警"),
                ("recommendation_summary", f"{ICO_CHECK} 建议总结"),
            ]
            for key, label in slots:
                text = narratives.get(key, "")
                if text:
                    story.append(Paragraph(label, s["h2"]))
                    story.append(Paragraph(text, s["quote"]))
        elif self.llm_review:
            story.append(Paragraph(f"{ICO_TARGET} 专家评语：", s["h2"]))
            story.append(Paragraph(self.llm_review, s["quote"]))
        else:
            story.append(Paragraph(f"{ICO_WARN} LLM 不可用，未生成智能评语", s["body"]))

        # ── 7. 技术参数 ──
        story.append(Spacer(1, 1.5))
        story.append(Paragraph(f"7 {ICO_STAR} 技术参数", s["h1"]))
        appendix_data = [
            ["算法版本", "v18.0（28类检测）"],
            ["异常类型", "28类（6大组：拓扑/测量/参数/潮流/电压/其他）"],
            ["测试网络", "51个 PandaPower 标准网络"],
            ["基线指标", "51/51 通过，avg_recall=99.65%，avg_f1=93.52%"],
            ["前端", "D3.js v7 + G6.js + 原生 JS"],
            ["API", "FastAPI v18.0，39+ 端点"],
            ["LLM", "Qwen3.5-4B (GGUF Q4_K_M)，GPU 加速 47 tok/s"],
        ]
        for k, v in appendix_data:
            story.append(Paragraph(f'{ICO_BULLET} <b>{k}</b>：{v}', s["body_tight"]))

        story.append(Spacer(1, 5))
        story.append(Paragraph("— 报告结束 —", s["small"]))

        return story

    def _build_modify_plan_prominent(self, all_corrs: List[Dict]) -> Table:
        """v5 突出的修改方案总览 — 按优先级彩色分组 + 阶段图标"""
        s = self.styles
        if not all_corrs:
            return Paragraph(f"{ICO_CHECK} 无需修正", s["body"])

        groups = {"高": [], "中": [], "低": []}
        for c in all_corrs[:24]:
            prio = str(c.get("priority", "中"))
            if prio in ("高", "high", "紧急", "urgent"):
                k = "高"
            elif prio in ("低", "low"):
                k = "低"
            else:
                k = "中"
            groups[k].append(c)

        rows = []
        for prio_key, label_text, fg, ico in [
            ("高", "高危", C_DANGER, ICO_HIGH),
            ("中", "中危", C_WARNING, ICO_MED),
            ("低", "低危", C_SUCCESS, ICO_LOW),
        ]:
            items = groups.get(prio_key, [])
            count = len(items)
            header = Paragraph(
                f'<font color="#{fg.hexval()[2:]}"><b>{ico} {label_text}</b></font>'
                f' <font color="#374151"><b>×{count}</b></font>',
                s["phase_title"])
            if not items:
                rows.append([header, Paragraph(
                    f'<font color="#9ca3af">{ICO_CHECK} 无</font>', s["body_tight"])])
                continue
            phase_icons = (
                f"{ICO_PHASE_CONFIRM}定位 "
                f"{ICO_PHASE_ISOLATE}隔离 "
                f"{ICO_PHASE_CORRECT}修正 "
                f"{ICO_PHASE_VERIFY}验证")
            rows.append([header, Paragraph(
                f'<font color="#6b7280" size="4.5">{phase_icons}</font>',
                s["body_tight"])])
            type_parts = []
            for c in items[:4]:
                atype = c.get("anomaly_type", "?")
                cn = TYPE_CN.get(atype, atype)
                ti = TYPE_ICO.get(atype, ICO_BULLET)
                verified = c.get("verification_passed", False)
                status = ICO_BOX_CHECK if verified else ICO_BOX_EMPTY
                type_parts.append(f"{ti}{cn} {status}")
            rows.append([Paragraph(
                '<font color="#6b7280" size="4.5">覆盖类型</font>',
                s["body_tight"]),
                Paragraph(
                " ".join(type_parts) if type_parts else "—",
                s["body_tight"])])
            if items:
                first = items[0]
                action = first.get("action", "investigate")
                action_info = ACTION_DETAIL.get(action, {})
                action_title = action_info.get("title", action)
                rows.append([Paragraph(
                    '<font color="#6b7280" size="4.5">首要操作</font>',
                    s["body_tight"]),
                    Paragraph(f"{ICO_WRENCH} {action_title}",
                              s["body_tight"])])

        col_widths = [2.0 * cm, 14.7 * cm]
        table = Table(rows, colWidths=col_widths)
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), ZH),
            ("FONTSIZE", (0, 0), (-1, -1), 5.5),
            ("BACKGROUND", (0, 0), (-1, -1), C_BG_LIGHT),
            ("BOX", (0, 0), (-1, -1), 0.6, C_PRIMARY),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, C_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        return table

    def _build_correction_card(self, idx: int, c: Dict) -> KeepTogether:
        """构建单条修正方案卡片（紧凑）"""
        s = self.styles
        elements = []

        atype = c.get("anomaly_type", "?")
        cn = TYPE_CN.get(atype, atype)
        prio = c.get("priority", "中")
        pc = _prio_color(prio)
        pi = _prio_icon(prio)
        ico = TYPE_ICO.get(atype, ICO_GEAR)
        target = c.get("target", c.get("location", "?"))
        action = c.get("action", "")
        desc = c.get("description", "")
        conf = c.get("confidence", 0)
        verified = c.get("verification_passed", False)
        is_suggested = c.get("_suggested", False)

        # 标题行：编号 + 图标 + 类型 + 优先级徽章 + 位置
        title_parts = [
            f'{ico} <b>{idx}. {cn}</b>　',
            f'<font color="#{pc.hexval()[2:]}">{pi} {prio}</font>　',
            f'{_colored(ICO_TARGET, C_ACCENT)} {target}',
        ]
        if verified:
            title_parts.append(f'　{_colored(ICO_BOX_CHECK, C_SUCCESS)} 已验证')
        elif is_suggested:
            title_parts.append(f'　{_colored(ICO_BOX_EMPTY, C_MUTED)} 建议')
        elements.append(Paragraph("".join(title_parts), s["corr_title"]))

        # 获取操作详情
        action_info = ACTION_DETAIL.get(action, {})

        if action_info:
            # 有详细方案：显示 before → after
            atitle = action_info.get("title", action)
            before = action_info.get("before", "")
            after = action_info.get("after", "")
            steps = action_info.get("steps", [])

            elements.append(Paragraph(
                f'{_colored(ICO_ARROW_R, C_ACCENT)} <b>{atitle}</b>：'
                f'{_colored(before, C_DANGER)} {_colored(ICO_ARROW, C_MUTED)} {_colored(after, C_SUCCESS)}',
                s["modify_detail"]))

            for step in steps[:4]:
                elements.append(Paragraph(f'{ICO_BULLET} {step}', s["step"]))
        else:
            # 无详细方案：显示原始信息
            if action:
                elements.append(Paragraph(
                    f'{_colored(ICO_ARROW_R, C_ACCENT)} 操作：{action}',
                    s["corr_body"]))
            if desc:
                elements.append(Paragraph(str(desc)[:120], s["corr_body"]))

            # 原始步骤
            steps = c.get("steps", [])
            for step in steps[:4]:
                elements.append(Paragraph(f'{ICO_BULLET} {step}', s["step"]))

        # 置信度 + 风险
        if conf:
            conf_c = _sev_color(conf)
            risk = c.get("risk", "")
            risk_text = ""
            if risk:
                risk_c = C_DANGER if risk in ("high", "critical") else C_WARNING if risk == "medium" else C_SUCCESS
                risk_text = f'　{_colored(ICO_SHIELD, risk_c)} 风险:{risk}'
            elements.append(Paragraph(
                f'置信度：{_colored(f"{conf:.0%}", conf_c)}{risk_text}',
                s["step"]))

        elements.append(Spacer(1, 0.3))
        return KeepTogether(elements)

    def _build_suggested_corrections(self, dets: List[Dict]) -> List[Dict]:
        """为无修正方案的异常生成建议修正列表"""
        seen = set()
        result = []
        for d in dets[:15]:
            atype = d.get("type", "unknown")
            if atype in seen:
                continue
            seen.add(atype)
            result.append({
                "anomaly_type": atype,
                "action": self._suggest_action(atype),
                "priority": "高" if d.get("confidence", 0) >= 0.8 else "中",
                "target": d.get("location", d.get("element", "?")),
                "confidence": d.get("confidence", 0),
                "verification_passed": False,
            })
        return result

    @staticmethod
    def _suggest_action(atype: str) -> str:
        """根据异常类型推荐修正动作"""
        return TYPE_ACTION_MAP.get(atype, "investigate")

    @staticmethod
    def _make_bar_chart(by_type: Dict[str, int]) -> Drawing:
        items = sorted(by_type.items(), key=lambda x: -x[1])[:10]
        if not items:
            return Drawing(400, 10)
        n = len(items)
        h = max(80, n * 18 + 25)
        d = Drawing(460, h)
        bc = HorizontalBarChart()
        bc.x = 110
        bc.y = 12
        bc.width = 320
        bc.height = h - 30
        bc.data = [[c for _, c in items]]
        bc.categoryAxis.categoryNames = [TYPE_CN.get(t, t)[:5] for t, _ in items]
        bc.categoryAxis.labels.fontName = ZH
        bc.categoryAxis.labels.fontSize = 5.5
        bc.valueAxis.valueMin = 0
        bc.valueAxis.valueMax = max(c for _, c in items) + 2
        bc.valueAxis.labels.fontSize = 5.5
        bc.bars[0].fillColor = C_ACCENT
        bc.bars[0].strokeColor = C_PRIMARY
        bc.barWidth = 12
        d.add(bc)
        return d

    @staticmethod
    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 6)
        canvas.setFillColor(colors.HexColor("#94a3b8"))
        canvas.drawString(1.0*cm, 0.6*cm,
                          f"配电网拓扑智能识别与修正报告 | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        canvas.drawRightString(A4[0] - 1.0*cm, 0.6*cm, f"第 {doc.page} 页")
        canvas.restoreState()
