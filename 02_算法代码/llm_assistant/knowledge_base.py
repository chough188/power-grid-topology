# -*- coding: utf-8 -*-
"""
电力系统领域知识库 - 28种异常类型的关联关系、因果链和修正策略

知识结构:
  - ANOMALY_KNOWLEDGE: 每种异常的详细属性(原因、影响、严重度、修正方法)
  - FAULT_CORRELATION: 异常之间的关联关系(哪些异常可能由同一故障引起)
  - CAUSAL_CHAINS: 因果链(故障→中间异常→最终表现)
  - CORRECTION_RULES: 修正规则(按异常类型和严重度的修正策略)
"""

from typing import Dict, List, Set, Tuple

# ============================================================
# 28种异常类型知识库
# ============================================================

ANOMALY_KNOWLEDGE: Dict[str, Dict] = {
    # === 原始5种 ===
    "topo_interrupt": {
        "name_cn": "拓扑中断",
        "category": "topology",
        "severity": "high",
        "description": "线路或开关断开导致拓扑不连续",
        "possible_causes": [
            "线路故障跳闸", "计划检修停电", "开关误动作", "保护误动"
        ],
        "physical_effects": [
            "负荷转移", "电压跌落", "潮流重新分布", "可能出现孤岛"
        ],
        "detection_methods": ["Rule", "GNN", "DiffPhys"],
        "correction_strategies": [
            {"action": "确认断线位置和原因", "priority": 1, "risk": "low"},
            {"action": "检查是否有备用路径", "priority": 2, "risk": "low"},
            {"action": "合闸恢复或转供", "priority": 3, "risk": "medium"},
            {"action": "N-1安全校验", "priority": 4, "risk": "low"},
        ],
        "related_anomalies": ["branch_contingency", "load_transfer_residual"],
    },
    "virtual_faulty": {
        "name_cn": "虚拟故障",
        "category": "measurement",
        "severity": "medium",
        "description": "电压量测偏离正常范围, 可能是量测故障或真实电压异常",
        "possible_causes": [
            "PT断线", "量测设备故障", "通信干扰", "真实电压越限"
        ],
        "physical_effects": [
            "状态估计偏差", "保护可能误动"
        ],
        "detection_methods": ["SE", "Rule", "DiffPhys"],
        "correction_strategies": [
            {"action": "对比多源量测确认是否为量测故障", "priority": 1, "risk": "low"},
            {"action": "检查PT/CT回路", "priority": 2, "risk": "low"},
            {"action": "切换至备用量测源", "priority": 3, "risk": "medium"},
        ],
        "related_anomalies": ["telemetry_mismatch", "measurement_bias"],
    },
    "model_mismatch": {
        "name_cn": "模型不匹配",
        "category": "model",
        "severity": "medium",
        "description": "CIM/SVG模型与实际网络拓扑不一致",
        "possible_causes": [
            "设备投退未同步", "模型版本过期", "人为录入错误"
        ],
        "physical_effects": [
            "拓扑分析错误", "潮流计算不收敛"
        ],
        "detection_methods": ["Rule", "Signal"],
        "correction_strategies": [
            {"action": "对比SCADA实时状态与模型", "priority": 1, "risk": "low"},
            {"action": "更新CIM模型", "priority": 2, "risk": "low"},
        ],
        "related_anomalies": ["ghost_topology", "topo_obfuscation"],
    },
    "telemetry_mismatch": {
        "name_cn": "遥测不匹配",
        "category": "measurement",
        "severity": "medium",
        "description": "遥测值与量测值不一致, 超出正常误差范围",
        "possible_causes": [
            "CT/PT精度问题", "通信丢包", "量测越限"
        ],
        "physical_effects": [
            "状态估计残差增大", "可能误判为坏数据"
        ],
        "detection_methods": ["SE", "Telemetry", "RSE"],
        "correction_strategies": [
            {"action": "检查遥测通道状态", "priority": 1, "risk": "low"},
            {"action": "对比多源量测", "priority": 2, "risk": "low"},
            {"action": "标记可疑量测并降权使用", "priority": 3, "risk": "low"},
        ],
        "related_anomalies": ["virtual_faulty", "communication_loss"],
    },
    "signal_mismatch": {
        "name_cn": "信号不匹配",
        "category": "signal",
        "severity": "high",
        "description": "开关/刀闸位置信号与电气量测矛盾",
        "possible_causes": [
            "开关辅助触点故障", "信号传输延迟", "开关实际位置与信号不一致"
        ],
        "physical_effects": [
            "拓扑识别错误", "可能导致带负荷拉刀闸"
        ],
        "detection_methods": ["Signal", "Rule"],
        "correction_strategies": [
            {"action": "现场确认开关实际位置", "priority": 1, "risk": "high"},
            {"action": "检查开关辅助触点", "priority": 2, "risk": "medium"},
            {"action": "更新拓扑模型", "priority": 3, "risk": "low"},
        ],
        "related_anomalies": ["topo_interrupt", "model_mismatch"],
    },
    # === v8新增10种 ===
    "measurement_outlier": {
        "name_cn": "量测异常值",
        "category": "measurement",
        "severity": "medium",
        "description": "单个或少量量测值偏离正常范围",
        "possible_causes": ["传感器故障", "电磁干扰", "接线松动"],
        "physical_effects": ["状态估计偏差", "坏数据检测触发"],
        "detection_methods": ["OUT", "SE"],
        "correction_strategies": [
            {"action": "识别并剔除异常量测", "priority": 1, "risk": "low"},
            {"action": "使用冗余量测替代", "priority": 2, "risk": "low"},
        ],
        "related_anomalies": ["stale_data", "measurement_bias"],
    },
    "stale_data": {
        "name_cn": "陈旧数据",
        "category": "measurement",
        "severity": "low",
        "description": "量测数据长时间未更新",
        "possible_causes": ["通信中断", "RTU故障", "采样周期异常"],
        "physical_effects": ["状态估计使用过时数据", "可能漏检新发生的异常"],
        "detection_methods": ["STALE", "Comm"],
        "correction_strategies": [
            {"action": "检查通信链路状态", "priority": 1, "risk": "low"},
            {"action": "切换至备用通信通道", "priority": 2, "risk": "medium"},
        ],
        "related_anomalies": ["communication_loss"],
    },
    "parameter_error": {
        "name_cn": "参数错误",
        "category": "model",
        "severity": "medium",
        "description": "线路/变压器参数与实际不符",
        "possible_causes": ["录入错误", "设备老化参数漂移", "单位换算错误"],
        "physical_effects": ["潮流计算偏差", "短路计算错误"],
        "detection_methods": ["PARAM", "SE"],
        "correction_strategies": [
            {"action": "对比铭牌参数与模型参数", "priority": 1, "risk": "low"},
            {"action": "实测线路参数", "priority": 2, "risk": "medium"},
        ],
        "related_anomalies": ["impedance_degradation"],
    },
    "load_shift": {
        "name_cn": "负荷突变",
        "category": "operation",
        "severity": "medium",
        "description": "负荷在短时间内发生大幅变化",
        "possible_causes": ["大负荷投切", "天气突变", "分布式电源出力波动"],
        "physical_effects": ["电压波动", "潮流越限"],
        "detection_methods": ["LOAD", "SE"],
        "correction_strategies": [
            {"action": "确认负荷变化是否正常", "priority": 1, "risk": "low"},
            {"action": "调整无功补偿", "priority": 2, "risk": "low"},
            {"action": "必要时切负荷", "priority": 3, "risk": "high"},
        ],
        "related_anomalies": ["dg_intermittent", "voltage_collapse"],
    },
    "reverse_power_flow": {
        "name_cn": "反向潮流",
        "category": "operation",
        "severity": "medium",
        "description": "功率流向与预期方向相反",
        "possible_causes": ["分布式电源出力大于本地负荷", "环网运行", "量测错误"],
        "physical_effects": ["电压升高", "保护可能误动"],
        "detection_methods": ["RPF", "SE"],
        "correction_strategies": [
            {"action": "确认是否为DG出力导致的正常反向", "priority": 1, "risk": "low"},
            {"action": "检查保护定值是否适应反向潮流", "priority": 2, "risk": "medium"},
            {"action": "调整DG出力或投切负荷", "priority": 3, "risk": "medium"},
        ],
        "related_anomalies": ["dg_intermittent", "voltage_regulation"],
    },
    "communication_loss": {
        "name_cn": "通信中断",
        "category": "communication",
        "severity": "medium",
        "description": "与终端设备通信中断",
        "possible_causes": ["光缆故障", "交换机故障", "RTU死机"],
        "physical_effects": ["量测缺失", "遥控失效"],
        "detection_methods": ["COMM", "Stale"],
        "correction_strategies": [
            {"action": "检查通信链路", "priority": 1, "risk": "low"},
            {"action": "切换备用通道", "priority": 2, "risk": "low"},
            {"action": "派人现场检查RTU", "priority": 3, "risk": "medium"},
        ],
        "related_anomalies": ["stale_data"],
    },
    "voltage_collapse": {
        "name_cn": "电压崩溃",
        "category": "security",
        "severity": "critical",
        "description": "电压持续下降至危险水平",
        "possible_causes": ["无功不足", "负荷过重", "线路阻抗过大"],
        "physical_effects": ["设备损坏风险", "大面积停电"],
        "detection_methods": ["VC", "SE"],
        "correction_strategies": [
            {"action": "紧急投入无功补偿", "priority": 1, "risk": "medium"},
            {"action": "切除非重要负荷", "priority": 2, "risk": "high"},
            {"action": "调整变压器分接头", "priority": 3, "risk": "medium"},
        ],
        "related_anomalies": ["load_shift", "impedance_degradation"],
    },
    "ghost_topology": {
        "name_cn": "幽灵拓扑",
        "category": "topology",
        "severity": "medium",
        "description": "模型中存在实际不存在的设备或连接",
        "possible_causes": ["退役设备未从模型删除", "临时接线未撤除"],
        "physical_effects": ["拓扑分析错误", "潮流计算偏差"],
        "detection_methods": ["GHOST", "Rule"],
        "correction_strategies": [
            {"action": "现场核实设备存在性", "priority": 1, "risk": "low"},
            {"action": "更新CIM模型删除幽灵设备", "priority": 2, "risk": "low"},
        ],
        "related_anomalies": ["model_mismatch", "topo_obfuscation"],
    },
    "duplicate_measurement": {
        "name_cn": "重复量测",
        "category": "measurement",
        "severity": "low",
        "description": "同一物理量有多个冲突量测",
        "possible_causes": ["量测点重复配置", "主备量测同时上送"],
        "physical_effects": ["状态估计权重混乱"],
        "detection_methods": ["DUP", "SE"],
        "correction_strategies": [
            {"action": "识别并去除重复量测", "priority": 1, "risk": "low"},
            {"action": "检查量测点配置", "priority": 2, "risk": "low"},
        ],
        "related_anomalies": ["measurement_outlier"],
    },
    "protection_misconfig": {
        "name_cn": "保护误配置",
        "category": "protection",
        "severity": "high",
        "description": "保护定值或配置不正确",
        "possible_causes": ["定值计算错误", "未随运行方式调整", "整定单录入错误"],
        "physical_effects": ["保护拒动或误动", "故障扩大"],
        "detection_methods": ["PROT", "Rule"],
        "correction_strategies": [
            {"action": "核查保护定值单", "priority": 1, "risk": "low"},
            {"action": "校核定值与当前运行方式的适应性", "priority": 2, "risk": "medium"},
            {"action": "必要时调整定值", "priority": 3, "risk": "high"},
        ],
        "related_anomalies": ["signal_mismatch"],
    },
    # === v9新增10种 ===
    "trafo_tap_fault": {
        "name_cn": "变压器分接头故障",
        "category": "equipment",
        "severity": "medium",
        "description": "变压器分接头位置异常或机械故障",
        "possible_causes": ["机构卡涩", "控制器故障", "限位开关失灵"],
        "physical_effects": ["电压调节失效", "变比异常"],
        "detection_methods": ["TRAFO_TAP", "SE"],
        "correction_strategies": [
            {"action": "检查分接头控制器状态", "priority": 1, "risk": "low"},
            {"action": "手动调整分接头", "priority": 2, "risk": "medium"},
            {"action": "安排检修", "priority": 3, "risk": "low"},
        ],
        "related_anomalies": ["voltage_regulation"],
    },
    "grounding_fault": {
        "name_cn": "接地故障",
        "category": "fault",
        "severity": "high",
        "description": "单相接地或接地电阻异常",
        "possible_causes": ["绝缘老化", "外力破坏", "受潮"],
        "physical_effects": ["零序电流", "电压不平衡", "人身安全风险"],
        "detection_methods": ["GROUNDING", "SE"],
        "correction_strategies": [
            {"action": "确认接地故障位置", "priority": 1, "risk": "medium"},
            {"action": "隔离故障段", "priority": 2, "risk": "high"},
            {"action": "安排抢修", "priority": 3, "risk": "low"},
        ],
        "related_anomalies": ["voltage_collapse"],
    },
    "clock_drift": {
        "name_cn": "时钟漂移",
        "category": "communication",
        "severity": "low",
        "description": "终端设备时钟与主站不同步",
        "possible_causes": ["GPS天线故障", "时钟芯片老化", "NTP服务中断"],
        "physical_effects": ["SOE时序错误", "故障录波时间不准"],
        "detection_methods": ["CLOCK", "Comm"],
        "correction_strategies": [
            {"action": "检查GPS天线和对时模块", "priority": 1, "risk": "low"},
            {"action": "手动对时", "priority": 2, "risk": "low"},
        ],
        "related_anomalies": ["communication_loss"],
    },
    "harmonic_pollution": {
        "name_cn": "谐波污染",
        "category": "power_quality",
        "severity": "medium",
        "description": "电压或电流谐波含量超标",
        "possible_causes": ["非线性负荷", "变频器", "电容器谐振"],
        "physical_effects": ["设备过热", "保护误动", "电能质量下降"],
        "detection_methods": ["HARMONIC", "SE"],
        "correction_strategies": [
            {"action": "识别谐波源", "priority": 1, "risk": "low"},
            {"action": "投入滤波器", "priority": 2, "risk": "medium"},
            {"action": "调整电容器组避免谐振", "priority": 3, "risk": "medium"},
        ],
        "related_anomalies": ["measurement_outlier"],
    },
    "impedance_degradation": {
        "name_cn": "阻抗退化",
        "category": "equipment",
        "severity": "medium",
        "description": "线路阻抗因老化或损伤而增大",
        "possible_causes": ["导线老化", "接头氧化", "绝缘劣化"],
        "physical_effects": ["线损增大", "电压降增大", "载流量下降"],
        "detection_methods": ["IMPEDANCE", "SE"],
        "correction_strategies": [
            {"action": "对比实测参数与模型参数", "priority": 1, "risk": "low"},
            {"action": "安排线路检测", "priority": 2, "risk": "low"},
            {"action": "必要时更换线路", "priority": 3, "risk": "high"},
        ],
        "related_anomalies": ["parameter_error", "voltage_collapse"],
    },
    "dg_intermittent": {
        "name_cn": "DG间歇性出力",
        "category": "distributed_gen",
        "severity": "medium",
        "description": "分布式电源出力快速波动",
        "possible_causes": ["光伏云遮", "风速突变", "逆变器故障"],
        "physical_effects": ["电压波动", "频率偏差", "潮流方向变化"],
        "detection_methods": ["DG", "LOAD"],
        "correction_strategies": [
            {"action": "确认DG出力变化原因", "priority": 1, "risk": "low"},
            {"action": "调整无功补偿平抑电压", "priority": 2, "risk": "low"},
            {"action": "必要时限制DG出力", "priority": 3, "risk": "medium"},
        ],
        "related_anomalies": ["load_shift", "reverse_power_flow"],
    },
    "measurement_bias": {
        "name_cn": "量测偏差",
        "category": "measurement",
        "severity": "medium",
        "description": "量测值存在系统性偏差",
        "possible_causes": ["CT/PT变比错误", "零漂", "校准过期"],
        "physical_effects": ["状态估计系统性偏差", "决策依据失真"],
        "detection_methods": ["BIAS", "SE"],
        "correction_strategies": [
            {"action": "检查CT/PT变比设置", "priority": 1, "risk": "low"},
            {"action": "重新校准量测设备", "priority": 2, "risk": "medium"},
        ],
        "related_anomalies": ["telemetry_mismatch", "measurement_outlier"],
    },
    "branch_contingency": {
        "name_cn": "支路停运",
        "category": "security",
        "severity": "high",
        "description": "多条支路同时停运, 威胁N-1安全",
        "possible_causes": ["级联故障", "计划检修重叠", "恶劣天气"],
        "physical_effects": ["供电可靠性下降", "潮流越限", "电压越限"],
        "detection_methods": ["CONTINGENCY", "N1"],
        "correction_strategies": [
            {"action": "评估N-1安全性", "priority": 1, "risk": "low"},
            {"action": "恢复关键支路", "priority": 2, "risk": "medium"},
            {"action": "转移负荷减轻过载", "priority": 3, "risk": "high"},
        ],
        "related_anomalies": ["topo_interrupt", "voltage_collapse"],
    },
    "topo_obfuscation": {
        "name_cn": "拓扑混淆",
        "category": "topology",
        "severity": "medium",
        "description": "拓扑结构被错误标记或混淆",
        "possible_causes": ["设备编号混乱", "接线图与实际不符", "环网/辐射混淆"],
        "physical_effects": ["拓扑分析错误", "保护配合混乱"],
        "detection_methods": ["OBF", "Rule"],
        "correction_strategies": [
            {"action": "现场核实拓扑", "priority": 1, "risk": "low"},
            {"action": "更新拓扑模型", "priority": 2, "risk": "low"},
        ],
        "related_anomalies": ["ghost_topology", "model_mismatch"],
    },
    "voltage_regulation": {
        "name_cn": "电压调节异常",
        "category": "operation",
        "severity": "medium",
        "description": "电压调节设备(电容器/SVG/OLTC)控制异常",
        "possible_causes": ["控制器故障", "通信中断", "定值不合理"],
        "physical_effects": ["电压越限", "无功分布不合理"],
        "detection_methods": ["VREG", "SE"],
        "correction_strategies": [
            {"action": "检查调压设备状态", "priority": 1, "risk": "low"},
            {"action": "切换至手动控制", "priority": 2, "risk": "medium"},
            {"action": "调整控制定值", "priority": 3, "risk": "medium"},
        ],
        "related_anomalies": ["trafo_tap_fault", "voltage_collapse"],
    },
    # === v16新增3种 ===
    "bus_section_mismatch": {
        "name_cn": "母线分段不匹配",
        "category": "topology",
        "severity": "medium",
        "description": "母线分段开关状态与拓扑模型不一致",
        "possible_causes": ["分段开关操作后未更新模型", "开关位置信号错误"],
        "physical_effects": ["母线连接关系错误", "潮流计算偏差"],
        "detection_methods": ["BSM", "Rule"],
        "correction_strategies": [
            {"action": "核实分段开关实际位置", "priority": 1, "risk": "low"},
            {"action": "更新拓扑模型", "priority": 2, "risk": "low"},
        ],
        "related_anomalies": ["signal_mismatch", "topo_obfuscation"],
    },
    "bypass_operation": {
        "name_cn": "旁路代路",
        "category": "operation",
        "severity": "medium",
        "description": "旁路代路操作后拓扑未及时更新",
        "possible_causes": ["代路操作未同步到模型", "旁路开关信号缺失"],
        "physical_effects": ["拓扑与实际不一致", "保护配合混乱"],
        "detection_methods": ["BYPASS", "Rule"],
        "correction_strategies": [
            {"action": "确认代路操作状态", "priority": 1, "risk": "low"},
            {"action": "更新拓扑模型反映代路状态", "priority": 2, "risk": "low"},
        ],
        "related_anomalies": ["model_mismatch", "topo_interrupt"],
    },
    "load_transfer_residual": {
        "name_cn": "负荷转供残留",
        "category": "operation",
        "severity": "low",
        "description": "负荷转供操作完成后, 原路径拓扑未清理",
        "possible_causes": ["转供操作后未恢复原拓扑", "临时接线未撤除"],
        "physical_effects": ["拓扑冗余", "潮流路径非最优"],
        "detection_methods": ["LTR", "Rule"],
        "correction_strategies": [
            {"action": "检查转供操作记录", "priority": 1, "risk": "low"},
            {"action": "清理残留拓扑", "priority": 2, "risk": "low"},
        ],
        "related_anomalies": ["topo_interrupt", "load_shift"],
    },
}

# ============================================================
# 故障关联规则: 哪些异常可能由同一根因引起
# ============================================================

FAULT_CORRELATION: Dict[str, Dict] = {
    "线路故障": {
        "trigger_anomalies": ["topo_interrupt", "branch_contingency"],
        "cascade_anomalies": ["voltage_collapse", "load_shift", "reverse_power_flow"],
        "confidence_boost": 0.15,
        "description": "线路故障跳闸, 导致拓扑中断和负荷转移",
    },
    "量测系统故障": {
        "trigger_anomalies": ["communication_loss", "stale_data"],
        "cascade_anomalies": ["measurement_outlier", "telemetry_mismatch", "measurement_bias"],
        "confidence_boost": 0.10,
        "description": "通信中断导致量测数据异常",
    },
    "分布式电源波动": {
        "trigger_anomalies": ["dg_intermittent"],
        "cascade_anomalies": ["load_shift", "reverse_power_flow", "voltage_regulation"],
        "confidence_boost": 0.12,
        "description": "DG出力快速波动引起电压和潮流变化",
    },
    "设备老化": {
        "trigger_anomalies": ["impedance_degradation"],
        "cascade_anomalies": ["parameter_error", "voltage_collapse", "grounding_fault"],
        "confidence_boost": 0.10,
        "description": "设备老化导致参数漂移和故障风险增加",
    },
    "模型维护不及时": {
        "trigger_anomalies": ["model_mismatch", "ghost_topology"],
        "cascade_anomalies": ["topo_obfuscation", "bus_section_mismatch", "bypass_operation"],
        "confidence_boost": 0.08,
        "description": "模型更新不及时导致与实际不一致",
    },
    "保护系统异常": {
        "trigger_anomalies": ["protection_misconfig"],
        "cascade_anomalies": ["signal_mismatch", "topo_interrupt"],
        "confidence_boost": 0.12,
        "description": "保护定值或配置问题导致误动/拒动",
    },
}

# ============================================================
# 严重度等级定义
# ============================================================

SEVERITY_LEVELS = {
    "critical": {"priority": 1, "response_time": "立即", "color": "red"},
    "high":     {"priority": 2, "response_time": "30分钟内", "color": "orange"},
    "medium":   {"priority": 3, "response_time": "2小时内", "color": "yellow"},
    "low":      {"priority": 4, "response_time": "24小时内", "color": "green"},
}


class KnowledgeBase:
    """电力系统领域知识库查询接口"""

    def __init__(self):
        self.anomalies = ANOMALY_KNOWLEDGE
        self.correlations = FAULT_CORRELATION
        self.severity = SEVERITY_LEVELS

    def get_anomaly_info(self, anomaly_type: str) -> Dict:
        """获取异常类型的详细信息"""
        return self.anomalies.get(anomaly_type, {
            "name_cn": anomaly_type,
            "category": "unknown",
            "severity": "medium",
            "description": f"未知异常类型: {anomaly_type}",
            "correction_strategies": [
                {"action": "人工确认异常类型", "priority": 1, "risk": "low"}
            ],
        })

    def get_related_anomalies(self, anomaly_type: str) -> List[str]:
        """获取与指定异常类型相关的其他异常"""
        info = self.anomalies.get(anomaly_type, {})
        return info.get("related_anomalies", [])

    def find_fault_scenarios(self, anomaly_types: List[str]) -> List[Dict]:
        """根据异常类型列表, 识别可能的故障场景"""
        scenarios = []
        type_set = set(anomaly_types)

        for fault_name, fault_info in self.correlations.items():
            trigger = set(fault_info["trigger_anomalies"])
            cascade = set(fault_info["cascade_anomalies"])
            all_related = trigger | cascade

            # 计算匹配度
            matched = type_set & all_related
            if len(matched) >= 2:
                match_ratio = len(matched) / len(all_related)
                scenarios.append({
                    "fault_name": fault_name,
                    "description": fault_info["description"],
                    "matched_anomalies": list(matched),
                    "match_ratio": match_ratio,
                    "confidence": min(0.95, match_ratio + fault_info["confidence_boost"]),
                })

        scenarios.sort(key=lambda x: x["confidence"], reverse=True)
        return scenarios

    def get_correction_plan(self, anomaly_type: str, severity: str = None) -> List[Dict]:
        """获取修正方案(按优先级排序)"""
        info = self.get_anomaly_info(anomaly_type)
        strategies = info.get("correction_strategies", [])

        if severity:
            # 根据严重度调整策略
            for s in strategies:
                if severity == "critical" and s["priority"] <= 2:
                    s["urgency"] = "immediate"
                elif severity == "high" and s["priority"] <= 3:
                    s["urgency"] = "soon"
                else:
                    s["urgency"] = "normal"

        return sorted(strategies, key=lambda x: x["priority"])

    def explain_anomaly(self, anomaly_type: str, location: str = "", 
                        confidence: float = 0.0) -> str:
        """生成异常的自然语言解释"""
        info = self.get_anomaly_info(anomaly_type)
        name = info.get("name_cn", anomaly_type)
        desc = info.get("description", "")
        causes = info.get("possible_causes", [])
        effects = info.get("physical_effects", [])

        explanation = f"检测到{name}异常"
        if location:
            explanation += f", 位于{location}"
        if confidence > 0:
            explanation += f", 置信度{confidence:.0%}"
        explanation += f"。\n\n{desc}\n\n"

        if causes:
            explanation += "可能原因: " + "、".join(causes[:3]) + "。\n"
        if effects:
            explanation += "物理影响: " + "、".join(effects[:3]) + "。\n"

        return explanation
