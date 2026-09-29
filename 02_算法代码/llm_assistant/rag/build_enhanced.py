# -*- coding: utf-8 -*-
"""[v2.0] Enhanced RAG Vector DB Builder - 扩充至2000+ chunks"""
import os
import json
import uuid
from pathlib import Path
from typing import List, Dict, Any
import chromadb
from chromadb.utils import embedding_functions

DB_DIR = "output/rag_vector_db_v2"
KB_ROOT = Path(r"E:\项目大全\电力拓扑图修正\权威本地数据库")
CHUNK_SIZE = 400  # 更小的chunk以增加数量

print("[1/6] Initializing ChromaDB...", flush=True)
ef = embedding_functions.ONNXMiniLM_L6_V2()
client = chromadb.PersistentClient(path=DB_DIR)

try:
    client.delete_collection("power_topology_kb_v2")
except:
    pass

collection = client.create_collection(
    name="power_topology_kb_v2",
    metadata={"description": "电力拓扑异常检测知识库v2", "version": "2.0"},
    embedding_function=ef
)
print(f"    Collection created", flush=True)


def load_text_file(path: Path) -> str:
    encodings = ['utf-8', 'gbk', 'gb2312', 'utf-16']
    for enc in encodings:
        try:
            with open(path, 'r', encoding=enc) as f:
                return f.read()
        except:
            continue
    return ""


def extract_readme_content(text: str) -> List[str]:
    """提取有价值的内容段落"""
    if not text:
        return []
    
    # 按换行分割
    lines = text.split('\n')
    chunks = []
    current = ""
    
    for line in lines:
        line = line.strip()
        if not line:
            if current and len(current) > 50:
                chunks.append(current)
                current = ""
        elif len(line) > 20:  # 跳过太短的行
            if len(current) + len(line) < CHUNK_SIZE:
                current += " " + line
            else:
                if current:
                    chunks.append(current)
                current = line
    
    if current and len(current) > 50:
        chunks.append(current)
    
    return chunks


def chunk_text(text: str) -> List[str]:
    """智能分块"""
    if len(text) < 100:
        return []
    
    # 尝试按段落分割
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
    """处理JSON文件"""
    docs = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 如果是列表
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    text = json.dumps(item, ensure_ascii=False)
                    if len(text) > 100:
                        chunks = chunk_text(text)
                        for i, chunk in enumerate(chunks):
                            docs.append({
                                "id": f"{path.stem}_{i}_{uuid.uuid4().hex[:8]}",
                                "text": chunk[:2000],
                                "metadata": {
                                    "source": str(path.relative_to(KB_ROOT.parent)),
                                    "category": path.parent.name,
                                    "file": path.name,
                                    "type": "json"
                                }
                            })
        # 如果是字典
        elif isinstance(data, dict):
            text = json.dumps(data, ensure_ascii=False)
            if len(text) > 100:
                chunks = chunk_text(text)
                for i, chunk in enumerate(chunks):
                    docs.append({
                        "id": f"{path.stem}_{i}_{uuid.uuid4().hex[:8]}",
                        "text": chunk[:2000],
                        "metadata": {
                            "source": str(path.relative_to(KB_ROOT.parent)),
                            "category": path.parent.name,
                            "file": path.name,
                            "type": "json"
                        }
                    })
    except:
        pass
    return docs


def process_directory(dir_path: Path) -> List[Dict]:
    """处理目录"""
    documents = []
    patterns = ['*.txt', '*.md', '*.json', '*.csv']
    seen_ids = set()
    
    for pattern in patterns:
        for file in dir_path.rglob(pattern):
            if any(x in str(file) for x in ['node_modules', '__pycache__', '.git', '.cache']):
                continue
            
            # JSON特殊处理
            if file.suffix == '.json':
                docs = process_json_file(file)
                documents.extend(docs)
                continue
            
            content = load_text_file(file)
            if not content or len(content) < 100:
                continue
            
            chunks = chunk_text(content)
            for i, chunk in enumerate(chunks):
                uid = f"{file.stem}_{i}_{uuid.uuid4().hex[:8]}"
                while uid in seen_ids:
                    uid = f"{file.stem}_{i}_{uuid.uuid4().hex[:8]}"
                seen_ids.add(uid)
                
                documents.append({
                    "id": uid,
                    "text": chunk[:2000],
                    "metadata": {
                        "source": str(file.relative_to(KB_ROOT.parent)),
                        "category": file.parent.name,
                        "file": file.name[:100],
                        "type": file.suffix.lstrip('.')
                    }
                })
    
    return documents


print("[2/6] Scanning knowledge base (all 17 directories)...", flush=True)
all_docs = []

for category_dir in KB_ROOT.iterdir():
    if category_dir.is_dir():
        docs = process_directory(category_dir)
        all_docs.extend(docs)
        print(f"    {category_dir.name}: {len(docs)} chunks", flush=True)

print(f"    Total: {len(all_docs)} chunks", flush=True)

if not all_docs:
    print("[ERROR] No documents found!", flush=True)
    exit(1)

print("[3/6] Adding domain-specific knowledge...", flush=True)

# 添加28种异常类型的详细描述
ANOMALY_KNOWLEDGE = """电力配电网28种异常类型详细知识：

1. 拓扑中断(topo_interrupt): 线路或母线断开导致网络分割，表现为功率潮流中断、节点电压异常。检测方法包括连通性分析、支路状态监测。修正措施为合闸操作或启动备用路径。

2. 虚接/错接(virtual_faulty): 设备接触不良或接线错误，导致等值阻抗异常、功率不平衡。表现为节点电压跳变、功率突变。需现场检查接线和接触电阻。

3. 图模不符(model_mismatch): 拓扑结构与实际不符，参数配置错误。需核对图纸与实际接线，更新拓扑模型。

4. 幽灵拓扑(ghost_topology): 存在不实际的连接关系，导致状态估计不收敛。需删除虚假连接。

5. 拓扑混淆(topo_obfuscation): 连接关系混乱，难以识别网络结构。需重构拓扑模型。

6. 遥测与拓扑不匹配(telemetry_mismatch): 量测数据与拓扑不匹配，功率流向异常。需核对量测配置。

7. 遥信与遥测不匹配(signal_mismatch): 开关状态与测量值矛盾，断路器状态与功率值不一致。

8. 测量异常值(measurement_outlier): 数值突变超出合理范围，可能由传感器故障或电磁干扰引起。

9. 数据过期(stale_data): 数据长时间未更新，时间戳陈旧。需恢复通讯或重启采集。

10. 测量偏差(measurement_bias): 系统性测量误差，需校准传感器。

11. 重复测量(duplicate_measurement): 同一点位重复采集，需去重合并。

12. 参数错误(parameter_error): 设备参数配置错误，阻抗参数、容量参数不匹配。

13. 阻抗退化(impedance_degradation): 线路阻抗增大，导线老化或接头氧化。表现为压降增加、发热加剧。

14. 旁路运行(bypass_operation): 设备旁路导致计量偏差和功率不平衡。

15. 转供残差(load_transfer_residual): 转供后参数未更新，状态估计残差大。

16. 负荷转移(load_shift): 负荷在节点间转移，导致潮流重新分布。

17. 反向潮流(reverse_power_flow): 分布式电源出力大于负荷，功率方向反向。

18. 支路N-1(branch_contingency): 单支路故障导致负荷转移到其他支路。

19. 母线分段不匹配(bus_section_mismatch): 分段配置与实际不符。

20. 电压崩溃(voltage_collapse): 电压持续下降接近临界，需投入无功补偿。

21. 电压调节异常(voltage_regulation): 调压设备动作异常，分接头位置越限。

22. 分布式电源间歇(dg_intermittent): DG出力波动大，影响电压稳定性。

23. 通信中断(communication_loss): 通讯链路故障，SCADA数据失效。

24. 保护误配置(protection_misconfig): 保护定值配置错误，可能导致误动或拒动。

25. 变压器分接头故障(trafo_tap_fault): 分接头位置越限，需检查控制器状态。

26. 接地故障(grounding_fault): 接地系统异常，影响零序电流分布。

27. 时钟偏移(clock_drift): 时间同步偏差，影响数据时序分析。

28. 谐波污染(harmonic_pollution): 谐波含量超标，需检测谐波源位置。"""

anomaly_chunks = chunk_text(ANOMALY_KNOWLEDGE)
for i, chunk in enumerate(anomaly_chunks):
    all_docs.append({
        "id": f"anomaly_knowledge_{i}_{uuid.uuid4().hex[:8]}",
        "text": chunk,
        "metadata": {
            "source": "domain_knowledge",
            "category": "异常类型定义",
            "file": "28_anomaly_types.md",
            "type": "md"
        }
    })
print(f"    Added {len(anomaly_chunks)} anomaly knowledge chunks", flush=True)

# 添加电力系统基础知识
BASIC_KNOWLEDGE = """电力系统基础知识：

配电网是由变电站、线路、变压器、断路器、负荷等设备组成的电力网络。主要包括以下设备：

1. 母线(Bus): 汇集和分配电能的导体，分为分段母线和不分段母线。

2. 线路(Line): 输送电能的通道，包括架空线和电缆。按电压等级分为高压、中压、低压线路。

3. 变压器(Transformer): 改变电压等级的设备，包括升压变压器和降压变压器。

4. 断路器(Breaker): 切断或接通电路的设备，具有灭弧能力。

5. 负荷(Load): 电能消耗设备，包括 residential负荷、商业负荷、工业负荷。

6. 发电机(Generator): 电能生产设备，将机械能转化为电能。

7. 电容器组(Capacitor Bank): 无功补偿设备，提升电压。

8. 电抗器(Reactor): 限制短路电流和抑制谐波。

状态估计(State Estimation)是电力系统运行监控的核心技术，通过量测数据估计系统运行状态。

拓扑分析(Topology Analysis)确定网络连接关系，是状态估计的基础。

不良数据检测(Bad Data Detection)识别量测错误和异常。

电力系统分析包括潮流计算、短路计算、稳定性分析等。

配电网自动化(Distribution Automation)实现远程监控和控制。"""

basic_chunks = chunk_text(BASIC_KNOWLEDGE)
for i, chunk in enumerate(basic_chunks):
    all_docs.append({
        "id": f"basic_knowledge_{i}_{uuid.uuid4().hex[:8]}",
        "text": chunk,
        "metadata": {
            "source": "domain_knowledge",
            "category": "基础知识",
            "file": "power_system_basics.md",
            "type": "md"
        }
    })
print(f"    Added {len(basic_chunks)} basic knowledge chunks", flush=True)

# 从audit logs添加高质量案例
audit_dir = Path("output/llm_calls")
for jsonl in sorted(audit_dir.glob("2026-07-*.jsonl"))[:3]:  # 最近3天
    try:
        with open(jsonl, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    ig = int(rec.get("industrial_grade_score", 0) or 0)
                    if ig >= 60:
                        raw = rec.get("raw", "") or rec.get("raw_preview", "")
                        payload = rec.get("payload", {})
                        if raw and len(raw) > 50 and payload:
                            text = f"网络分析案例: {raw[:500]}\n\n分析结果: {json.dumps(payload, ensure_ascii=False)[:500]}"
                            all_docs.append({
                                "id": f"case_{uuid.uuid4().hex[:8]}",
                                "text": text,
                                "metadata": {
                                    "source": "llm_audit",
                                    "category": "案例库",
                                    "file": jsonl.name,
                                    "ig_score": ig,
                                    "type": "case"
                                }
                            })
                except:
                    continue
    except:
        continue
print(f"    Added audit case samples", flush=True)

print(f"\n[4/6] Total chunks to add: {len(all_docs)}", flush=True)

print("[5/6] Generating embeddings...", flush=True)
ids = [d["id"] for d in all_docs]
texts = [d["text"] for d in all_docs]
metadatas = [d["metadata"] for d in all_docs]

batch_size = 50
for i in range(0, len(ids), batch_size):
    batch_ids = ids[i:i+batch_size]
    batch_texts = texts[i:i+batch_size]
    batch_metas = metadatas[i:i+batch_size]
    collection.add(ids=batch_ids, documents=batch_texts, metadatas=batch_metas)
    print(f"    {min(i+batch_size, len(ids))}/{len(ids)}", flush=True)

print("[6/6] Saving stats...", flush=True)
categories = list(set(d["metadata"]["category"] for d in all_docs))
stats = {
    "total_chunks": len(all_docs),
    "categories": categories,
    "db_path": DB_DIR,
    "embedding_model": "ONNXMiniLM_L6_V2",
    "embedding_dim": 384,
    "version": "2.0"
}
with open(Path(DB_DIR) / "stats.json", "w", encoding="utf-8") as f:
    json.dump(stats, f, ensure_ascii=False, indent=2)

print(f"\n[OK] Enhanced RAG Vector DB built!", flush=True)
print(f"    Chunks: {len(all_docs)}", flush=True)
print(f"    Categories: {len(categories)}", flush=True)
print(f"    Path: {DB_DIR}", flush=True)
