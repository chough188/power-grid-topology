# -*- coding: utf-8 -*-
"""[v4.0] RAG Vector DB Builder - 完整版3000+ chunks"""
import os
import json
import uuid
from pathlib import Path
from typing import List, Dict
import chromadb
from chromadb.utils import embedding_functions

DB_DIR = "output/rag_vector_db_v4"
CHUNK_SIZE = 250

print("[1/8] Initializing ChromaDB v4...", flush=True)
ef = embedding_functions.ONNXMiniLM_L6_V2()
client = chromadb.PersistentClient(path=DB_DIR)

try:
    client.delete_collection("power_topology_kb_v4")
except:
    pass

collection = client.create_collection(
    name="power_topology_kb_v4",
    metadata={"description": "电力拓扑异常检测工业知识库v4", "version": "4.0"},
    embedding_function=ef
)

all_docs = []

# ========== 1. 28种异常完整定义 ==========
print("[2/8] Adding 28 anomaly definitions...", flush=True)

ANOMALY_DEFS = {
    # 拓扑类 (5)
    "topology_interrupt": {
        "name": "拓扑中断",
        "desc": "网络中某条关键支路断开导致供电区域被隔离",
        "severity": "紧急",
        "causes": ["线路故障", "开关跳闸", "设备损坏", "人为操作失误"],
        "symptoms": ["区域停电", "功率中断", "负荷失电", "网络分割"],
        "solutions": ["定位断开点", "评估转供路径", "执行转供操作", "通知受影响用户"],
        "tools": ["SCADA操作员站", "地理信息系统GIS", "故障指示器"],
        "prevention": ["定期巡检", "自动化监控", "状态检修"]
    },
    "virtual_faulty": {
        "name": "虚接/错接",
        "desc": "设备连接存在虚接或错接现象，接触电阻过大导致发热或供电中断",
        "severity": "高",
        "causes": ["接触不良", "接线错误", "松脱", "腐蚀氧化"],
        "symptoms": ["发热", "供电中断", "局部异常", "接触电阻增大"],
        "solutions": ["现场检查物理连接", "测量接触电阻", "紧固或更换连接件", "复测验证"],
        "tools": ["红外热像仪", "万用表", "接触电阻测试仪"],
        "prevention": ["新设备验收测试", "定期热成像检测", "紧固力矩检查"]
    },
    "model_mismatch": {
        "name": "图模不符",
        "desc": "图形表示与实际设备模型不一致，如容量参数不匹配、连接关系错误",
        "severity": "中",
        "causes": ["数据未同步", "参数错误", "版本不一致", "人为录入错误"],
        "symptoms": ["容量不匹配", "连接错误", "参数差异", "状态不一致"],
        "solutions": ["对比GIS和SCADA模型", "同步不一致参数", "更新生产系统", "验证同步效果"],
        "tools": ["GIS系统", "SCADA系统", "模型校验工具"],
        "prevention": ["模型版本管理", "自动校验机制", "变更审核流程"]
    },
    "ghost_topology": {
        "name": "幽灵拓扑",
        "desc": "存在孤岛或虚假连接，可能是数据残留或拓扑识别错误",
        "severity": "中",
        "causes": ["数据残留", "拓扑识别错误", "清理不彻底", "合并遗留"],
        "symptoms": ["孤岛节点", "虚假连接", "无效拓扑", "孤立设备"],
        "solutions": ["清除无效拓扑", "更新网络模型", "验证连通性", "检查数据来源"],
        "tools": ["拓扑分析工具", "网络可视化", "连通性检查"],
        "prevention": ["数据清理机制", "定期拓扑验证", "自动化孤岛检测"]
    },
    "topo_obfuscation": {
        "name": "拓扑混淆",
        "desc": "连接关系过于复杂难以解析，可能存在环网或交叉连接",
        "severity": "中",
        "causes": ["环网结构", "交叉连接", "多电源", "网络重构"],
        "symptoms": ["拓扑复杂", "路径不清晰", "分析困难", "保护配合复杂"],
        "solutions": ["简化拓扑结构", "明确网络层级", "标注关键节点", "重构网络"],
        "tools": ["网络可视化工具", "拓扑简化软件"],
        "prevention": ["网络规划设计", "自动化简化工具", "定期拓扑审核"]
    },
    # 测量类 (6)
    "telemetry_mismatch": {
        "name": "遥测与拓扑不匹配",
        "desc": "量测数据与网络拓扑逻辑矛盾，如线路功率方向与拓扑不一致",
        "severity": "中",
        "causes": ["量测错误", "通信延迟", "拓扑错误", "数据同步问题"],
        "symptoms": ["功率不平衡", "方向异常", "数据矛盾", "残差增大"],
        "solutions": ["校验量测设备", "检查通信状态", "修正拓扑错误", "标记可疑数据"],
        "tools": ["量测校验仪", "通信分析仪", "状态估计软件"],
        "prevention": ["量测冗余配置", "实时校验", "异常检测告警"]
    },
    "signal_mismatch": {
        "name": "遥信与遥测不匹配",
        "desc": "开关状态与电气量测逻辑不符，如开关断开但功率不为零",
        "severity": "高",
        "causes": ["信号上传错误", "继电器故障", "采集延迟", "采集点配置错误"],
        "symptoms": ["状态矛盾", "功率非零", "逻辑不符", "告警异常"],
        "solutions": ["核实状态上传", "检查继电器输出", "验证采集点配置", "标记可疑状态"],
        "tools": ["继电保护测试仪", "信号采集分析仪"],
        "prevention": ["定期信号校验", "状态一致性检查", "自动化告警"]
    },
    "measurement_outlier": {
        "name": "测量异常值",
        "desc": "量测数据明显超出正常范围，可能是传感器故障或不良数据",
        "severity": "中",
        "causes": ["传感器故障", "通信干扰", "极端工况", "设备漂移"],
        "symptoms": ["数值跳变", "超出阈值", "不合理值", "历史趋势异常"],
        "solutions": ["分析历史数据趋势", "检查传感器状态", "剔除异常值", "标记待检修"],
        "tools": ["历史数据库", "统计分析软件", "传感器测试仪"],
        "prevention": ["传感器定期校准", "阈值告警机制", "冗余量测"]
    },
    "stale_data": {
        "name": "数据过期",
        "desc": "量测数据超时未更新，可能通信中断或RTU故障",
        "severity": "高",
        "causes": ["通信中断", "RTU故障", "通道故障", "设备断电"],
        "symptoms": ["数据不刷新", "时间戳陈旧", "值长期不变"],
        "solutions": ["检查通信链路", "修复RTU故障", "切换备用通道", "通知通信运维"],
        "tools": ["通信分析仪", "网络测试仪", "RTU诊断工具"],
        "prevention": ["通信监控", "RTU状态监测", "自动切换机制"]
    },
    "measurement_bias": {
        "name": "测量偏差",
        "desc": "存在系统性量测误差，需校准量测设备",
        "severity": "中",
        "causes": ["传感器漂移", "校准失效", "温度影响", "老化"],
        "symptoms": ["恒定偏差", "趋势偏移", "精度下降"],
        "solutions": ["校准量测设备", "修正偏差值", "定期维护校准"],
        "tools": ["量测校准仪", "标准源", "精度测试设备"],
        "prevention": ["定期校准", "精度监测", "预防性维护"]
    },
    "duplicate_measurement": {
        "name": "重复测量",
        "desc": "同一量测点存在重复采集，需合并去重",
        "severity": "低",
        "causes": ["配置错误", "多点采集", "数据重复导入"],
        "symptoms": ["数据重复", "值相同", "冗余数据"],
        "solutions": ["合并去重处理", "保留有效数据源", "修正采集配置"],
        "tools": ["数据清洗工具", "配置管理系统"],
        "prevention": ["配置审核", "数据去重机制"]
    },
    # 参数类 (4)
    "parameter_error": {
        "name": "参数错误",
        "desc": "设备参数设置错误，如阻抗值、变比等",
        "severity": "中",
        "causes": ["手动输入错误", "系统同步失败", "默认值未更新", "单位错误"],
        "symptoms": ["阻抗错误", "变比错误", "容量错误", "潮流计算偏差"],
        "solutions": ["核对参数表", "更新SCADA模型参数", "验证计算结果"],
        "tools": ["参数校验工具", "潮流计算软件", "参数管理系统"],
        "prevention": ["参数版本管理", "自动化校验", "变更审核"]
    },
    "impedance_degradation": {
        "name": "阻抗退化",
        "desc": "线路阻抗异常增大，可能老化或接触不良",
        "severity": "高",
        "causes": ["线路老化", "接触不良", "接头损坏", "腐蚀"],
        "symptoms": ["压降增大", "损耗增加", "阻抗超标", "发热"],
        "solutions": ["检查线路状态", "测试绝缘电阻", "更换导线或接头", "红外检测"],
        "tools": ["红外热像仪", "绝缘电阻测试仪", "线路参数测试仪"],
        "prevention": ["定期线路检测", "红外巡检", "状态检修"]
    },
    "bypass_operation": {
        "name": "旁路运行",
        "desc": "设备被旁路导致保护失效",
        "severity": "紧急",
        "causes": ["旁路开关闭合", "保护退出", "应急操作", "维护期间"],
        "symptoms": ["保护失效", "选择性丧失", "越级跳闸风险"],
        "solutions": ["恢复旁路前状态", "重新配置保护定值", "验证保护动作"],
        "tools": ["继电保护测试仪", "保护定值管理系统"],
        "prevention": ["旁路操作审批", "保护投退管理", "定期检查"]
    },
    "load_transfer_residual": {
        "name": "转供残差",
        "desc": "转供操作未完全执行，需确认所有开关状态",
        "severity": "中",
        "causes": ["开关未到位", "操作中断", "条件不满足", "自动化失败"],
        "symptoms": ["部分转供", "负荷不均衡", "开关状态不一致"],
        "solutions": ["确认所有开关状态", "完成转供闭环操作", "验证转供效果"],
        "tools": ["SCADA操作员站", "开关状态监控"],
        "prevention": ["操作票管理", "自动化联锁", "状态确认机制"]
    },
    # 潮流类 (4)
    "load_shift": {
        "name": "负荷转移",
        "desc": "负荷在支路间异常迁移，可能是拓扑变化或开关操作",
        "severity": "中",
        "causes": ["拓扑变化", "开关操作", "负荷波动", "故障转移"],
        "symptoms": ["支路负荷变化", "功率迁移", "潮流再分配"],
        "solutions": ["评估转移影响", "调整运行方式", "监控潮流变化"],
        "tools": ["SCADA监控系统", "潮流计算软件"],
        "prevention": ["潮流监控", "负荷预测", "自动告警"]
    },
    "reverse_power_flow": {
        "name": "反向潮流",
        "desc": "功率方向异常，可能DG出力过大或网络结构变化",
        "severity": "高",
        "causes": ["DG出力过大", "网络结构变化", "开关状态错误", "负荷降低"],
        "symptoms": ["功率反向", "电压升高", "保护误动风险"],
        "solutions": ["调整DG出力限制", "网络重构", "修正开关状态", "调整保护定值"],
        "tools": ["DG监控系统", "SCADA", "保护定值管理系统"],
        "prevention": ["DG渗透率控制", "电压监控", "保护适应性调整"]
    },
    "branch_contingency": {
        "name": "支路N-1",
        "desc": "支路断开但系统仍可供电，需评估N-1安全",
        "severity": "中",
        "causes": ["计划检修", "故障隔离", "设备退出", "操作转移"],
        "symptoms": ["单供运行", "过载风险", "电压波动"],
        "solutions": ["评估N-1安全", "准备应急转供方案", "加强运行监控"],
        "tools": ["N-1安全分析软件", "潮流计算工具"],
        "prevention": ["N-1安全评估", "转供方案准备", "实时监控"]
    },
    "bus_section_mismatch": {
        "name": "母线分段不匹配",
        "desc": "母线分段与实际不符，需调整分段开关状态",
        "severity": "中",
        "causes": ["分段开关状态错误", "GIS不一致", "操作未执行"],
        "symptoms": ["分段配置不符", "潮流异常", "保护误动"],
        "solutions": ["调整分段开关状态", "同步图形和实际", "验证配置正确性"],
        "tools": ["SCADA", "GIS系统"],
        "prevention": ["开关状态校验", "GIS同步管理"]
    },
    # 电压类 (3)
    "voltage_collapse": {
        "name": "电压崩溃",
        "desc": "电压急剧下降接近崩溃，需紧急减载或增加补偿",
        "severity": "紧急",
        "causes": ["负荷过重", "无功不足", "故障连锁", "电压稳定性丧失"],
        "symptoms": ["电压急降", "无功耗尽", "系统不稳定", "电压低于0.9pu"],
        "solutions": ["紧急减载", "增加无功补偿", "调整发电机出力", "必要时切负荷"],
        "tools": ["AVC系统", "调度操作员站", "电压稳定分析工具"],
        "prevention": ["电压稳定监控", "自动减载装置", "无功备用"]
    },
    "voltage_regulation": {
        "name": "电压调节异常",
        "desc": "调压设备动作不当，电压偏高或偏低",
        "severity": "中",
        "causes": ["分接头故障", "电容组失效", "控制逻辑错误", "量测错误"],
        "symptoms": ["电压偏高", "电压偏低", "调压失效", "设备不动作"],
        "solutions": ["调整变压器分接头", "修复或更换电容组", "修正控制逻辑"],
        "tools": ["分接开关测试仪", "电容组控制器", "AVC系统"],
        "prevention": ["定期调压测试", "AVC自动控制", "设备状态监测"]
    },
    "dg_intermittent": {
        "name": "分布式电源间歇",
        "desc": "DG出力波动较大，需配置储能平抑波动",
        "severity": "中",
        "causes": ["天气变化", "DG类型特性", "控制策略不当"],
        "symptoms": ["出力波动大", "电压波动", "功率不稳定"],
        "solutions": ["配置储能系统", "改进预测算法", "平抑出力波动", "限制变化率"],
        "tools": ["DG监控系统", "储能管理系统", "功率预测系统"],
        "prevention": ["出力预测", "储能配置", "变化率限制"]
    },
    # 其他类 (6)
    "communication_loss": {
        "name": "通信中断",
        "desc": "RTU或通信链路故障，需检查通信设备",
        "severity": "高",
        "causes": ["光纤断裂", "设备故障", "网络故障", "电源故障"],
        "symptoms": ["数据中断", "站点离线", "遥控失效"],
        "solutions": ["检查通信设备状态", "测试通信链路", "切换备用通道", "通知通信运维"],
        "tools": ["通信分析仪", "网络测试仪", "OTN/SDH设备"],
        "prevention": ["通信监控", "双通道配置", "定期巡检"]
    },
    "protection_misconfig": {
        "name": "保护误配置",
        "desc": "保护定值或逻辑错误，需重新整定",
        "severity": "紧急",
        "causes": ["定值错误", "逻辑错误", "配合不当", "整定计算错误"],
        "symptoms": ["保护误动", "保护拒动", "越级跳闸"],
        "solutions": ["重新整定保护定值", "测试保护动作", "验证保护配合"],
        "tools": ["继电保护测试仪", "保护定值管理系统", "整定计算软件"],
        "prevention": ["定期保护校验", "定值审核", "整定计算规范"]
    },
    "trafo_tap_fault": {
        "name": "变压器分接头故障",
        "desc": "分接位置异常无法正常调压，需检修OLTC机构",
        "severity": "高",
        "causes": ["OLTC机构故障", "控制信号错误", "电机故障", "传动机构损坏"],
        "symptoms": ["分接位置异常", "电压调节失效", "机构异响", "油温异常"],
        "solutions": ["检查OLTC机构", "验证控制信号", "测试电机和传动", "更换故障部件"],
        "tools": ["分接开关测试仪", "继电保护测试仪", "油色谱分析"],
        "prevention": ["定期分接测试", "油温监控", "机构维护"]
    },
    "grounding_fault": {
        "name": "接地故障",
        "desc": "单相接地或相间短路，需定位故障点",
        "severity": "紧急",
        "causes": ["绝缘损坏", "雷击", "设备故障", "外力破坏"],
        "symptoms": ["接地告警", "零序电流", "保护动作", "单相电压降低"],
        "solutions": ["定位故障点", "隔离故障区域", "修复绝缘故障"],
        "tools": ["故障定位仪", "绝缘电阻测试仪", "零序电流监测"],
        "prevention": ["定期绝缘检测", "防雷措施", "状态监测"]
    },
    "clock_drift": {
        "name": "时钟偏移",
        "desc": "时间同步偏差超限，需同步时钟源",
        "severity": "低",
        "causes": ["NTP服务器故障", "晶振漂移", "同步中断"],
        "symptoms": ["时间偏差", "数据时序错乱", "事件先后矛盾"],
        "solutions": ["同步时钟源", "检查NTP服务器状态", "修复同步链路"],
        "tools": ["时钟同步系统", "NTP监控工具"],
        "prevention": ["时钟监控", "双时钟配置", "定期同步"]
    },
    "harmonic_pollution": {
        "name": "谐波污染",
        "desc": "谐波含量超标，需检查谐波源",
        "severity": "中",
        "causes": ["非线性负荷", "电力电子设备", "谐波源接入"],
        "symptoms": ["谐波含量超标", "设备发热", "计量误差增大"],
        "solutions": ["检测谐波源", "安装谐波滤波器", "限制谐波设备接入"],
        "tools": ["谐波分析仪", "电能质量监测仪"],
        "prevention": ["谐波监测", "谐波源管理", "滤波器配置"]
    }
}

# 添加异常定义
for anom_id, defs in ANOMALY_DEFS.items():
    text = f"""异常类型【{anom_id}】
名称：{defs['name']}
严重程度：{defs['severity']}
描述：{defs['desc']}
可能原因：{'、'.join(defs['causes'])}
表现症状：{'、'.join(defs['symptoms'])}
处理措施：{'、'.join(defs['solutions'])}
使用工具：{'、'.join(defs['tools'])}
预防措施：{'、'.join(defs['prevention'])}"""
    
    all_docs.append({
        "id": f"anomaly_def_{anom_id}",
        "text": text,
        "metadata": {"source": "anomaly_definitions_v4", "category": "异常类型定义", "file": "28_anomaly_definitions.json", "type": "definition", "anomaly_id": anom_id, "severity": defs["severity"]}
    })

print(f"  Added {len(ANOMALY_DEFS)} anomaly definitions", flush=True)

# ========== 2. 修正策略库 ==========
print("[3/8] Adding correction strategies...", flush=True)

CORRECTION_RULES = []
for anom_id, defs in ANOMALY_DEFS.items():
    priority_map = {"紧急": "P0", "高": "P1", "中": "P2", "低": "P3"}
    priority = priority_map.get(defs["severity"], "P2")
    
    CORRECTION_RULES.append({
        "anomaly_id": anom_id,
        "anomaly_name": defs["name"],
        "priority": priority,
        "priority_desc": defs["severity"],
        "actions": defs["solutions"],
        "tools": defs["tools"],
        "prevention": defs["prevention"]
    })

for rule in CORRECTION_RULES:
    text = f"""异常【{rule['anomaly_id']}】修正策略
优先级：{rule['priority']}（{rule['priority_desc']}）
异常名称：{rule['anomaly_name']}
处理措施：
{chr(10).join([f'{i+1}. {a}' for i, a in enumerate(rule['actions'])])}
使用工具：{', '.join(rule['tools'])}
预防措施：{', '.join(rule['prevention'])}"""
    
    all_docs.append({
        "id": f"correction_{rule['anomaly_id']}",
        "text": text,
        "metadata": {"source": "correction_rules_v4", "category": "修正策略", "file": "correction_rules.json", "type": "strategy", "priority": rule["priority"]}
    })

print(f"  Added {len(CORRECTION_RULES)} correction rules", flush=True)

# ========== 3. 领域知识库 ==========
print("[4/8] Adding domain knowledge...", flush=True)

DOMAIN_KB = [
    ("电力系统基础知识", """电力系统由发电、输电、配电和用电组成。配电网是电力系统的重要组成部分，负责将电能配送到用户。

主要电压等级：
- 低压：0.4kV（民用）
- 中压：10kV、35kV（配电）
- 高压：110kV、220kV（输电）

关键设备：
- 母线(Bus)：汇集和分配电能
- 线路(Line)：输送电能，包括架空线和电缆
- 变压器(Transformer)：改变电压等级
- 断路器(Breaker)：切断或接通电路
- 负荷(Load)：电能消费设备
- 发电机(Generator)：电能生产设备
- 电容器组(Capacitor Bank)：无功补偿
- 电抗器(Reactor)：限制短路电流"""),
    
    ("状态估计原理", """状态估计是电力系统运行监控的核心技术，通过量测数据估计系统运行状态。

常用方法：
1. 加权最小二乘法(WLS)
   - 输入：遥测(功率、电压、电流)和遥信(开关状态)
   - 输出：节点电压幅值和相角
   
2. 卡尔曼滤波
   - 适用于动态系统
   - 可处理时变系统
   
3. 鲁棒估计
   - 对不良数据具有鲁棒性

关键步骤：
1. 网络拓扑分析
2. 量测配置优化
3. 不良数据检测
4. 状态计算

不良数据检测方法：
- 卡方检测：整体量测一致性
- 残差检测：标准化残差>3判定为不良数据
- 量测杂交检测：对比冗余量测"""),

    ("拓扑分析方法", """拓扑分析确定网络连接关系，是状态估计的基础。

基本概念：
- 节点(Bus)：母线、连接点
- 支路(Branch)：线路、变压器
- 开关(Switch)：断路器、刀闸

分析方法：
1. 连通性分析
   - 广度优先搜索(BFS)
   - 深度优先搜索(DFS)
   - 用于检测孤岛和连通分量

2. 拓扑识别
   - 从量测数据推断网络结构
   - 基于开关状态构建拓扑

3. 拓扑错误检测
   - 检测开关状态错误
   - 检测连接关系错误
   - 常用方法：残差分析、状态估计

4. 环网检测
   - 检测网络中的环
   - 分析环网对保护的影响"""),

    ("图神经网络应用", """图神经网络(GNN)在电力系统中有广泛应用。

主要应用场景：
1. 拓扑识别
   - 从量测数据学习网络结构
   - 识别虚假连接和孤岛
   
2. 状态估计
   - 学习非线性状态映射
   - 处理大规模系统
   
3. 负荷预测
   - 考虑空间相关性
   - 时空图神经网络

4. 故障检测
   - 识别异常模式
   - 快速故障定位

常用模型：
- GCN (图卷积网络)：卷积操作
- GAT (图注意力网络)：注意力机制
- GraphSAGE：归纳学习

输入特征：
- 节点特征：电压、功率、相角
- 边特征：阻抗、功率
- 拓扑：邻接矩阵"""),

    ("不良数据检测", """不良数据检测是状态估计的重要组成部分。

不良数据类型：
1. 随机误差：测量噪声
2. 坏数据：设备故障、人为错误
3. 系统误差：传感器漂移

检测方法：
1. 残差检测
   - 计算标准化残差
   - 阈值判断(通常3σ)
   
2. 卡方检测
   - 检验量测整体一致性
   - 用于检测多个不良数据
   
3. 量测杂交检测
   - 对比冗余量测
   - 识别矛盾量测
   
4. 递推检测
   - 逐步剔除不良数据
   - 重新估计状态

处理策略：
- 剔除法：直接删除
- 替换法：用估计值替代
- 加权法：降低权重"""),

    ("电压稳定分析", """电压稳定性是电力系统安全运行的关键。

电压崩溃过程：
1. 初始扰动导致电压下降
2. 负荷增加导致电压进一步下降
3. 无功功率不足
4. 电压崩溃

预防措施：
1. 无功补偿
   - 电容器组
   - 静止无功补偿器(SVC)
   - STATCOM
   
2. 减载方案
   - 自动低频减载
   - 自动低压减载
   
3. 网络重构
   - 调整运行方式
   - 优化潮流分布

电压稳定指标：
- PV曲线：电压-有功功率关系
- QV曲线：电压-无功功率关系
- 电压稳定裕度"""),

    ("配电网自动化", """配电网自动化实现远程监控和控制。

主要功能：
1. 数据采集与监控(SCADA)
   - 遥测、遥信、遥控、遥调
   - 实时数据监控
   - 历史数据存储

2. 故障检测与隔离(FA)
   - 故障检测
   - 故障隔离
   - 非故障区域恢复

3. 自动重合闸
   - 瞬时故障快速恢复
   - 永久故障闭锁

4. 电压无功控制(AVC)
   - 变压器分接头调节
   - 电容器组自动投切

通信方式：
- 光纤通信
- 数字微波
- 电力线载波(PLC)
- 无线公网"""),

    ("继电保护原理", """继电保护检测电力系统故障并快速隔离。

保护配置原则：
1. 选择性：只切除故障部分
2. 灵敏性：对故障有足够灵敏度
3. 快速性：尽快切除故障
4. 可靠性：不拒动、不误动

保护类型：
1. 过流保护
   - 电流超过定值动作
   - 时间级差配合
   
2. 距离保护
   - 基于测量阻抗
   - 不受运行方式影响
   
3. 差动保护
   - 基于电流差
   - 用于变压器、母线
   
4. 零序保护
   - 用于接地故障检测

定值整定：
- 躲过最大负荷电流
- 与下级保护配合
- 灵敏度校验"""),

    ("N-1安全准则", """N-1安全准则：任一元件退出运行后，系统仍能正常供电。

评估内容：
1. 元件N-1
   - 任一线路断开
   - 任一变压器断开
   
2. 安全指标
   - 支路过载检查
   - 节点电压限值
   - 系统频率稳定

3. 转供能力
   - 备用通道
   - 转供容量

评估方法：
1. 静态安全分析
   - 潮流计算
   - 安全约束检查
   
2. 动态安全分析
   - 暂态稳定
   - 电压稳定

N-1安全措施：
- 备用设备配置
- 转供方案准备
- 运行方式优化"""),

    ("电能质量", """电能质量包括电压质量、电流质量和供电可靠性。

主要指标：
1. 电压偏差
   - 允许范围：±7%（10kV）
   
2. 频率偏差
   - 允许范围：±0.2Hz
   
3. 谐波含量
   - THD限值根据电压等级
   - 各次谐波含有率
   
4. 电压波动和闪变
   - 短时闪变Pst
   - 长时闪变Plt
   
5. 三相不平衡
   - 不平衡度限值

改善措施：
1. 无功补偿
2. 谐波治理
3. 电压调节
4. 三相平衡化"""),

    ("配电网故障处理", """配电网故障处理流程：

1. 故障检测
   - 保护动作信号
   - 故障指示器告警
   - 自动化系统检测

2. 故障定位
   - 自动化系统定位
   - 人工巡检确认
   - 故障指示器查找

3. 故障隔离
   - 打开隔离开关
   - 隔离故障区段
   - 恢复非故障区供电

4. 故障修复
   - 现场故障处理
   - 设备更换
   - 绝缘修复

5. 恢复供电
   - 合闸恢复供电
   - 验证供电正常
   - 记录归档"""),

    ("分布式电源并网", """分布式电源(DG)并网对配电网产生影响。

主要影响：
1. 电压升高
   - 反向潮流导致电压升高
   - 需要限制渗透率
   
2. 保护配合复杂
   - 保护范围变化
   - 可能误动或拒动
   
3. 电能质量问题
   - 谐波
   - 电压波动
   
4. 孤岛效应
   - 电网断开后DG继续供电
   - 需防孤岛保护

并网要求：
1. 功率限制
   - 渗透率控制
   - 有功功率限制
   
2. 无功调节
   - 功率因数要求
   - 电压调节能力
   
3. 保护配置
   - 防孤岛保护
   - 低压/过压保护
   - 低压/过频保护

渗透率控制：
- 电压约束
- 热稳定约束
- 保护约束""")
]

for title, content in DOMAIN_KB:
    all_docs.append({
        "id": f"domain_{uuid.uuid4().hex[:8]}",
        "text": f"【{title}】{content}",
        "metadata": {"source": "domain_knowledge", "category": "领域知识", "file": "domain_knowledge.md", "type": "knowledge"}
    })

print(f"  Added {len(DOMAIN_KB)} domain knowledge articles", flush=True)

# ========== 4. Q&A对 ==========
print("[5/8] Adding Q&A pairs...", flush=True)

QAS = [
    ("配电网拓扑异常检测方法有哪些？", "主要方法：1)基于规则的检测-检查物理约束违反；2)状态估计残差检测-检测不良数据；3)图神经网络检测-学习拓扑模式；4)统计异常检测-识别偏离正常模式的节点；5)时序分析-检测渐变异常。"),
    ("什么是状态估计？", "状态估计通过量测数据估计电力系统运行状态。常用加权最小二乘法(WLS)，输入遥测遥信数据，输出节点电压幅值和相角。需进行不良数据检测和拓扑错误检测。"),
    ("如何检测拓扑错误？", "拓扑错误检测方法：1)网络连通性分析-检测孤岛；2)功率平衡检查-支路功率是否平衡；3)残差检测-拓扑错误会导致残差异常；4)量测一致性检验-对比冗余量测；5)GNN方法-学习正常拓扑模式检测异常。"),
    ("变压器分接头故障有什么表现？", "分接头故障表现：1)分接位置与SCADA显示不一致；2)电压调节失效-分接变化但电压不变；3)OLTC机构异常声音或振动；4)油温异常升高。需检查机构、电机和控制信号。"),
    ("如何处理遥测与拓扑不匹配？", "处理方法：1)对比线路两端功率是否平衡；2)检查开关状态是否正确上传；3)校验量测设备精度；4)分析残差定位不一致点；5)标记可疑数据进行人工核查。"),
    ("电压崩溃的征兆有哪些？", "电压崩溃征兆：1)多个节点电压持续下降；2)无功补偿设备已达极限；3)负荷中心电压低于0.9pu；4)发电机无功出力已达最大；5)电压-无功灵敏度异常。需紧急减载或增加补偿。"),
    ("什么是N-1安全准则？", "N-1安全准则：任一元件(线路或变压器)退出运行后，系统仍能正常供电。需评估：1)转供路径是否存在；2)转供后设备不过载；3)电压在允许范围内。"),
    ("配电网自动化的主要功能？", "配电网自动化功能：1)数据采集与监控(SCADA)；2)远程控制(遥控)；3)故障检测与隔离(FA)；4)自动重合闸；5)电压无功控制(AVC)；6)负荷管理。"),
    ("如何进行不良数据检测？", "不良数据检测方法：1)残差检测-计算标准化残差，大于阈值3判定为不良数据；2)卡方检测-检验量测整体一致性；3)量测杂交-对比冗余量测；4)递推检测-逐步剔除不良数据后重新估计。"),
    ("图神经网络在电力系统有哪些应用？", "GNN应用：1)拓扑识别-从量测推断网络结构；2)状态估计-学习非线性状态映射；3)负荷预测-考虑空间相关性；4)故障检测-识别异常模式；5)潮流计算-加速收敛。常用模型：GCN、GAT、GraphSAGE。"),
    ("分布式电源并网有什么影响？", "DG并网影响：1)电压升高-反向潮流导致；2)保护配合复杂-保护范围变化；3)电能质量问题-谐波和波动；4)孤岛效应-需防孤岛保护。需控制渗透率、配置保护、改善电能质量。"),
    ("如何处理接地故障？", "接地故障处理：1)根据零序电流定位故障区段；2)打开隔离开关隔离故障；3)恢复非故障区供电；4)排除故障后恢复。接地故障危害大，需快速隔离。"),
    ("谐波污染如何检测和处理？", "谐波检测：使用谐波分析仪测量各次谐波含量。处理方法：1)检测谐波源位置；2)安装谐波滤波器；3)限制谐波设备接入；4)改进设备设计减少谐波。"),
    ("时钟同步偏差会有什么影响？", "时钟偏差影响：1)事件时序错乱；2)数据融合困难；3)保护动作时序错误；4)故障分析困难。解决方法：同步NTP服务器、检查晶振状态、修复同步链路。"),
    ("旁路运行有什么风险？", "旁路运行风险：1)保护失效-选择性丧失；2)越级跳闸风险-故障扩大；3)无法快速隔离故障。必须尽快恢复旁路前状态，重新配置保护定值。"),
    ("负荷转移是怎么发生的？", "负荷转移原因：1)拓扑变化-线路或变压器断开；2)开关操作-转供操作；3)故障转移-自动隔离；4)负荷波动-自然迁移。需评估稳定性和设备承载能力。")
]

for i, (q, a) in enumerate(QAS):
    all_docs.append({
        "id": f"qa_{i}_{uuid.uuid4().hex[:8]}",
        "text": f"问：{q}\n答：{a}",
        "metadata": {"source": "qa_pairs", "category": "问答对", "file": "qa_pairs.json", "type": "qa"}
    })

print(f"  Added {len(QAS)} Q&A pairs", flush=True)

# ========== 5. 高质量案例 ==========
print("[6/8] Loading high-quality audit cases...", flush=True)

audit_dir = Path("output/llm_calls")
ig_count = 0
for jsonl in sorted(audit_dir.glob("2026-07-*.jsonl"))[:10]:
    try:
        with open(jsonl, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    ig = int(rec.get("industrial_grade_score", 0) or 0)
                    if ig >= 70:
                        raw = rec.get("raw", "") or rec.get("raw_preview", "")
                        payload = rec.get("payload", {})
                        if raw and len(raw) > 60 and payload:
                            text = f"工业案例(IG={ig}): {raw[:400]} | 分析结果: {json.dumps(payload, ensure_ascii=False)[:400]}"
                            all_docs.append({
                                "id": f"case_{uuid.uuid4().hex[:8]}",
                                "text": text,
                                "metadata": {"source": "llm_audit", "category": "工业案例", "file": jsonl.name, "ig_score": ig, "type": "case"}
                            })
                            ig_count += 1
                except:
                    continue
    except:
        continue

print(f"  Added {ig_count} industrial cases", flush=True)

# ========== 6. 生成嵌入 ==========
print(f"\n[7/8] Generating embeddings ({len(all_docs)} chunks)...", flush=True)

batch_size = 100
for i in range(0, len(all_docs), batch_size):
    batch = all_docs[i:i+batch_size]
    collection.add(
        ids=[d["id"] for d in batch],
        documents=[d["text"] for d in batch],
        metadatas=[d["metadata"] for d in batch]
    )
    if (i + batch_size) % 300 == 0:
        print(f"    {min(i+batch_size, len(all_docs))}/{len(all_docs)}", flush=True)

# ========== 7. 保存统计 ==========
print("[8/8] Saving stats...", flush=True)

categories = list(set(d["metadata"]["category"] for d in all_docs))
stats = {
    "total_chunks": len(all_docs),
    "db_path": DB_DIR,
    "version": "4.0",
    "embedding_model": "ONNXMiniLM_L6_V2",
    "categories": categories,
    "anomaly_types": len(ANOMALY_DEFS),
    "knowledge_articles": len(DOMAIN_KB),
    "qa_pairs": len(QAS),
    "industrial_cases": ig_count
}

with open(Path(DB_DIR) / "stats.json", "w", encoding="utf-8") as f:
    json.dump(stats, f, ensure_ascii=False, indent=2)

print(f"\n[OK] RAG v4.0 built!", flush=True)
print(f"    Total chunks: {len(all_docs)}", flush=True)
print(f"    Anomaly types: {len(ANOMALY_DEFS)}", flush=True)
print(f"    Domain knowledge: {len(DOMAIN_KB)} articles", flush=True)
print(f"    Q&A pairs: {len(QAS)}", flush=True)
print(f"    Industrial cases: {ig_count}", flush=True)
print(f"    Categories: {len(categories)}", flush=True)
print(f"    Path: {DB_DIR}", flush=True)