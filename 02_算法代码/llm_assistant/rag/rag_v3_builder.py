# -*- coding: utf-8 -*-
"""[v3.0] RAG Vector DB Builder - 电力拓扑工业知识库3000+ chunks"""
import os
import json
import uuid
from pathlib import Path
from typing import List, Dict, Any
import chromadb
from chromadb.utils import embedding_functions

DB_DIR = "output/rag_vector_db_v3"
KB_ROOT = Path(r"E:\项目大全\电力拓扑图修正\权威本地数据库")
CHUNK_SIZE = 350  # 更小chunk增加检索精度

print("[1/7] Initializing ChromaDB v3...", flush=True)
ef = embedding_functions.ONNXMiniLM_L6_V2()
client = chromadb.PersistentClient(path=DB_DIR)

try:
    client.delete_collection("power_topology_kb_v3")
except:
    pass

collection = client.create_collection(
    name="power_topology_kb_v3",
    metadata={"description": "电力拓扑异常检测工业知识库v3", "version": "3.0"},
    embedding_function=ef
)

# 28种异常类型详细定义
ANOMALY_TYPES = {
    "topology_interrupt": "拓扑中断 - 网络连接断开导致供电区域隔离",
    "virtual_faulty": "虚接/错接 - 设备连接错误或接触不良",
    "model_mismatch": "图模不符 - 图形表示与实际设备模型不一致",
    "ghost_topology": "幽灵拓扑 - 孤岛或虚假连接",
    "topo_obfuscation": "拓扑混淆 - 连接关系复杂难以解析",
    "telemetry_mismatch": "遥测与拓扑不匹配 - 量测数据与网络拓扑矛盾",
    "signal_mismatch": "遥信与遥测不匹配 - 开关状态与电气量测不一致",
    "measurement_outlier": "测量异常值 - 明显超出正常范围的量测",
    "stale_data": "数据过期 - 量测数据超时未更新",
    "measurement_bias": "测量偏差 - 系统性量测误差",
    "duplicate_measurement": "重复测量 - 同一量测点重复采集",
    "parameter_error": "参数错误 - 设备参数设置错误",
    "impedance_degradation": "阻抗退化 - 线路阻抗异常增大",
    "bypass_operation": "旁路运行 - 设备被旁路导致保护失效",
    "load_transfer_residual": "转供残差 - 转供操作未完全执行",
    "load_shift": "负荷转移 - 负荷在支路间异常迁移",
    "reverse_power_flow": "反向潮流 - 功率方向异常",
    "branch_contingency": "支路N-1 - 支路断开但系统仍可供电",
    "bus_section_mismatch": "母线分段不匹配 - 母线分段与实际不符",
    "voltage_collapse": "电压崩溃 - 电压急剧下降",
    "voltage_regulation": "电压调节异常 - 调压设备动作不当",
    "dg_intermittent": "分布式电源间歇 - DG出力波动",
    "communication_loss": "通信中断 - RTU或通信链路故障",
    "protection_misconfig": "保护误配置 - 保护定值或逻辑错误",
    "trafo_tap_fault": "变压器分接头故障 - 分接位置异常",
    "grounding_fault": "接地故障 - 单相接地或相间短路",
    "clock_drift": "时钟偏移 - 时间同步偏差",
    "harmonic_pollution": "谐波污染 - 谐波含量超标"
}

# 设备类型
DEVICE_TYPES = {
    "bus": "母线 - 汇集和分配电能的导体",
    "line": "线路 - 架空线或电缆输送电能",
    "transformer": "变压器 - 改变电压等级",
    "breaker": "断路器 - 切断或接通电路",
    "load": "负荷 - 电能消费设备",
    "generator": "发电机 - 电能生产设备",
    "capacitor": "电容器组 - 无功补偿",
    "reactor": "电抗器 - 限制短路电流",
    "switch": "开关 - 隔离或接通电路",
    "sectionalizer": "分段器 - 自动隔离故障",
    "recloser": "重合器 - 自动重合闸"
}

# 修正策略
CORRECTION_STRATEGIES = """
拓扑类异常修正策略:
1. topo_interrupt: 定位断开点，重新连接或切换供电路径
2. virtual_faulty: 检查设备连接关系，更新拓扑数据
3. model_mismatch: 同步图形和模型数据，确保一致
4. ghost_topology: 清除孤岛，更新拓扑结构
5. topo_obfuscation: 简化拓扑，标注关键节点

测量类异常修正策略:
1. telemetry_mismatch: 校验量测设备，对比相邻节点
2. signal_mismatch: 检查开关状态，核实量测逻辑
3. measurement_outlier: 剔除异常值或标记待检修
4. stale_data: 检查通信，标记数据过期
5. measurement_bias: 校准量测设备
6. duplicate_measurement: 合并重复点，保留有效数据

潮流类异常修正策略:
1. load_shift: 重新分配负荷，调整拓扑
2. reverse_power_flow: 检查DG出力方向，调整运行方式
3. branch_contingency: 评估N-1安全，准备转供方案
4. bus_section_mismatch: 调整分段开关状态

电压类异常修正策略:
1. voltage_collapse: 降低负荷，增加补偿
2. voltage_regulation: 调整变压器分接头或电容器组
3. dg_intermittent: 配置储能，平抑波动
"""

all_docs = []

def load_text_file(path: Path) -> str:
    encodings = ['utf-8', 'gbk', 'gb2312', 'utf-16']
    for enc in encodings:
        try:
            with open(path, 'r', encoding=enc) as f:
                return f.read()
        except:
            continue
    return ""

def chunk_text(text: str) -> List[str]:
    if len(text) < 80:
        return []
    paragraphs = text.replace('\r\n', '\n').split('\n\n')
    chunks = []
    current = ""
    for para in paragraphs:
        para = para.strip()
        if not para or len(para) < 30:
            continue
        if len(current) + len(para) < CHUNK_SIZE:
            current += " " + para if current else para
        else:
            if len(current) > 50:
                chunks.append(current.strip())
            current = para
    if current.strip() and len(current.strip()) > 50:
        chunks.append(current.strip())
    return chunks

def process_json_file(path: Path) -> List[Dict]:
    docs = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        text = json.dumps(data, ensure_ascii=False)
        if len(text) > 100:
            chunks = chunk_text(text)
            for i, chunk in enumerate(chunks):
                docs.append({
                    "id": f"{path.stem}_{i}_{uuid.uuid4().hex[:8]}",
                    "text": chunk[:1800],
                    "metadata": {"source": str(path), "category": "json_data", "file": path.name, "type": "json"}
                })
    except:
        pass
    return docs

print("[2/7] Adding anomaly type definitions...", flush=True)
for anom_id, desc in ANOMALY_TYPES.items():
    all_docs.append({
        "id": f"anomaly_{anom_id}",
        "text": f"异常类型: {desc}",
        "metadata": {"source": "anomaly_definitions", "category": "异常类型", "file": "28_anomaly_types.json", "type": "definition"}
    })
print(f"    Added {len(ANOMALY_TYPES)} anomaly definitions")

print("[3/7] Adding device types...", flush=True)
for dev_id, desc in DEVICE_TYPES.items():
    all_docs.append({
        "id": f"device_{dev_id}",
        "text": f"设备类型: {desc}",
        "metadata": {"source": "device_types", "category": "设备类型", "file": "device_types.json", "type": "definition"}
    })
print(f"    Added {len(DEVICE_TYPES)} device definitions")

print("[4/7] Adding correction strategies...", flush=True)
correction_chunks = chunk_text(CORRECTION_STRATEGIES)
for i, chunk in enumerate(correction_chunks):
    all_docs.append({
        "id": f"correction_{i}_{uuid.uuid4().hex[:8]}",
        "text": chunk,
        "metadata": {"source": "correction_strategies", "category": "修正策略", "file": "correction_strategies.md", "type": "strategy"}
    })
print(f"    Added {len(correction_chunks)} correction strategy chunks")

print("[5/7] Scanning authoritative database...", flush=True)
scan_count = 0
for ext in ['*.txt', '*.md', '*.json']:
    for file in KB_ROOT.rglob(ext):
        if any(x in str(file) for x in ['__pycache__', '.git', 'node_modules']):
            continue
        text = load_text_file(file)
        if len(text) > 100:
            chunks = chunk_text(text)
            for i, chunk in enumerate(chunks[:50]):  # 限制每个文件50个chunk
                all_docs.append({
                    "id": f"kb_{uuid.uuid4().hex[:8]}",
                    "text": chunk[:1500],
                    "metadata": {"source": str(file), "category": "knowledge_base", "file": file.name, "type": "text"}
                })
                scan_count += 1
                if scan_count % 500 == 0:
                    print(f"    Scanned {scan_count} chunks...", flush=True)
print(f"    Added {scan_count} knowledge base chunks")

print("[6/7] Loading high-quality audit cases...", flush=True)
audit_dir = Path("output/llm_calls")
ig_count = 0
for jsonl in sorted(audit_dir.glob("2026-07-*.jsonl"))[:5]:
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
                        if raw and len(raw) > 80 and payload:
                            text = f"工业案例分析: 网络拓扑分析。输入: {raw[:400]}。输出: {json.dumps(payload, ensure_ascii=False)[:400]}"
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
print(f"    Added {ig_count} industrial-grade cases")

print(f"\n[7/7] Total chunks: {len(all_docs)}", flush=True)
print("      Generating embeddings...", flush=True)

batch_size = 100
for i in range(0, len(all_docs), batch_size):
    batch = all_docs[i:i+batch_size]
    collection.add(
        ids=[d["id"] for d in batch],
        documents=[d["text"] for d in batch],
        metadatas=[d["metadata"] for d in batch]
    )
    if (i + batch_size) % 500 == 0:
        print(f"    {min(i+batch_size, len(all_docs))}/{len(all_docs)}", flush=True)

# Save stats
stats = {
    "total_chunks": len(all_docs),
    "db_path": DB_DIR,
    "embedding_model": "ONNXMiniLM_L6_V2",
    "version": "3.0",
    "anomaly_types": len(ANOMALY_TYPES),
    "device_types": len(DEVICE_TYPES)
}
with open(Path(DB_DIR) / "stats.json", "w", encoding="utf-8") as f:
    json.dump(stats, f, ensure_ascii=False, indent=2)

print(f"\n[OK] RAG v3 built! Chunks: {len(all_docs)}", flush=True)
print(f"    Path: {DB_DIR}", flush=True)