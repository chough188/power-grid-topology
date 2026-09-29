# -*- coding: utf-8 -*-
"""[v5] LLM API - RAG v3 + LoRA v4"""
import os
import sys
import json
import time
import torch
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

BASE_DIR = Path(__file__).parent.parent.parent
os.chdir(BASE_DIR)

MODEL_PATH = BASE_DIR / "output" / "lora" / "qwen3.5-0.8b-merged"
LORA_PATH = BASE_DIR / "output" / "lora" / "qwen3.5-0.8b-v4"
RAG_DB_V3 = BASE_DIR / "output" / "rag_vector_db_v3"

_model = None
_tokenizer = None
_rag_v3 = None

def load_all():
    global _model, _tokenizer, _rag_v3
    if _model is not None:
        return
    
    print("[Loading] Starting...", flush=True)
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import PeftModel
    import chromadb
    from chromadb.utils import embedding_functions
    
    _tokenizer = AutoTokenizer.from_pretrained(str(MODEL_PATH), trust_remote_code=True)
    base = AutoModelForCausalLM.from_pretrained(str(MODEL_PATH), trust_remote_code=True, torch_dtype=torch.float16, device_map="auto")
    
    if LORA_PATH.exists():
        try:
            _model = PeftModel.from_pretrained(base, str(LORA_PATH))
            print("[OK] LoRA v4 loaded", flush=True)
        except:
            _model = base
    else:
        _model = base
    
    _model.eval()
    
    # RAG v3
    try:
        ef = embedding_functions.ONNXMiniLM_L6_V2()
        client = chromadb.PersistentClient(path=str(RAG_DB_V3))
        _rag_v3 = client.get_collection("power_topology_kb_v3")
        print(f"[OK] RAG v3: {_rag_v3.count()} chunks", flush=True)
    except Exception as e:
        print(f"[WARN] RAG v3 failed: {e}", flush=True)
        _rag_v3 = None
    
    print("[OK] Ready!", flush=True)

app = FastAPI(title="Power Topology LLM API v5", version="5.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class AnalyzeRequest(BaseModel):
    network_data: str = Field(..., description="网络数据")
    question: str = Field("请分析拓扑异常并给出修正建议")
    use_rag: bool = Field(True)
    rag_top_k: int = Field(3, ge=1, le=10)
    max_tokens: int = Field(512, ge=100, le=2048)
    temperature: float = Field(0.1, ge=0.0, le=1.0)

class AnalyzeResponse(BaseModel):
    answer: str
    rag_sources: list = None
    tokens: int
    time_ms: float
    version: str

SYSTEM_PROMPT = """你是电力系统拓扑异常分析专家。

【规则】
1. 使用专业术语：母线、线路、变压器、断路器、负荷、发电机、电压、电流、有功功率、无功功率、阻抗
2. 检测28种异常：topology_interrupt, virtual_faulty, model_mismatch, ghost_topology, topo_obfuscation, telemetry_mismatch, signal_mismatch, measurement_outlier, stale_data, measurement_bias, duplicate_measurement, parameter_error, impedance_degradation, bypass_operation, load_transfer_residual, load_shift, reverse_power_flow, branch_contingency, bus_section_mismatch, voltage_collapse, voltage_regulation, dg_intermittent, communication_loss, protection_misconfig, trafo_tap_fault, grounding_fault, clock_drift, harmonic_pollution
3. 不确定时回答"未检测到异常"

【输出格式】
1. overall_assessment: 总体评估
2. top3_anomalies_explained: 主要异常说明
3. correction_priority_reasoning: 修正优先级分析
4. risk_forecast: 风险预测
5. recommendation_summary: 建议总结"""

@app.post("/v5/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    load_all()
    start = time.time()
    
    rag_context = ""
    sources = []
    if req.use_rag and _rag_v3:
        try:
            query = req.question or req.network_data[:200]
            results = _rag_v3.query(query_texts=[query], n_results=req.rag_top_k)
            if results and results.get("documents"):
                parts = []
                for i, (doc, meta) in enumerate(zip(results["documents"][0], results["metadatas"][0])):
                    parts.append(f"[参考{i+1}] {doc[:200]}")
                    sources.append({"text": doc[:150], "source": meta.get("source", ""), "category": meta.get("category", "")})
                rag_context = "\n".join(parts) + "\n\n"
        except Exception as e:
            print(f"[RAG] Error: {e}", flush=True)
    
    full_input = f"{rag_context}【网络数据】\n{req.network_data}\n\n【分析要求】\n{req.question}"
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": full_input}]
    text = _tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = _tokenizer([text], return_tensors="pt").to(_model.device)
    
    with torch.no_grad():
        outputs = _model.generate(**inputs, max_new_tokens=req.max_tokens, temperature=req.temperature, do_sample=req.temperature > 0.01, repetition_penalty=1.1)
    
    response = _tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    elapsed = (time.time() - start) * 1000
    
    return AnalyzeResponse(answer=response.strip(), rag_sources=sources if sources else None, tokens=len(outputs[0]) - inputs["input_ids"].shape[1], time_ms=round(elapsed, 1), version="v5")

@app.get("/health")
async def health():
    load_all()
    return {"status": "ok", "model": "qwen3.5-0.8b+v4", "rag_v3": _rag_v3.count() if _rag_v3 else 0, "ready": _model is not None}

@app.get("/v5/info")
async def info():
    return {"version": "5.0.0", "rag": "v3", "lora": "v4", "anomaly_types": 28}

if __name__ == "__main__":
    print("="*50)
    print("Power Topology LLM API v5")
    print("  Model: qwen3.5-0.8b + v4 LoRA")
    print("  RAG: v3 (1694 chunks)")
    print("="*50)
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")