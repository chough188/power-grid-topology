# -*- coding: utf-8 -*-
"""
电力拓扑异常检测 LLM 推理 API - 完整版 v1.2
功能：RAG增强 + 历史记录 + 批量分析 + 导出
"""
import os
import sys
import json
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from contextlib import asynccontextmanager
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

# 导入RAG
from rag.rag_query import RAGQuerier

MODEL_CONFIG = {
    "base_model": os.environ.get("DIANLI_BASE_MODEL", "E:/llm_models/Qwen3.5-0.8B"),
    "lora_path": "output/lora/qwen3.5-0.8b-v4/lora_weights",
    "merged_path": "output/lora/qwen3.5-0.8b-merged",
    "max_length": 1024,
}

SYSTEM_PROMPT = """你是一个电力配电网拓扑异常检测专家助手。
遵循规则：
1. 只使用领域词汇：母线、线路、变压器、断路器、负荷、发电机、电压、电流
2. 禁止猜测数字，用"需现场确认"代替
3. 每项分析必须追溯数据来源
4. PII检测并脱敏

分析配电网数据，识别28种异常类型并给出修正建议。
输出格式必须为JSON。

异常类型包括：拓扑中断、虚接错接、图模不符、幽灵拓扑、拓扑混淆、遥测不匹配、遥信不匹配、测量异常、数据过期、测量偏差、重复测量、参数错误、阻抗退化、旁路运行、转供残差、负荷转移、反向潮流、支路N-1、母线分段不匹配、电压崩溃、电压调节异常、DG间歇、通信中断、保护误配置、分接头故障、接地故障、时钟偏移、谐波污染。"""

# 全局变量
model = None
tokenizer = None
rag_querier = None
loaded = False
history = defaultdict(list)  # 存储历史记录
MAX_HISTORY = 100

def load_model():
    global model, tokenizer, rag_querier, loaded
    if loaded:
        return True
    
    print("[INFO] Loading components...", flush=True)
    
    try:
        # 加载RAG
        print("[INFO] Loading RAG...", flush=True)
        rag_querier = RAGQuerier()
        
        # 加载LLM
        merged_path = Path(MODEL_CONFIG["merged_path"])
        lora_path = Path(MODEL_CONFIG["lora_path"])
        
        tokenizer = AutoTokenizer.from_pretrained(
            MODEL_CONFIG["base_model"], trust_remote_code=True
        )
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        
        if merged_path.exists():
            print("[INFO] Loading merged model...", flush=True)
            model = AutoModelForCausalLM.from_pretrained(
                merged_path, trust_remote_code=True,
                torch_dtype=torch.float16, device_map="auto"
            )
        elif lora_path.exists():
            print("[INFO] Loading base + LoRA...", flush=True)
            base = AutoModelForCausalLM.from_pretrained(
                MODEL_CONFIG["base_model"], trust_remote_code=True,
                torch_dtype=torch.float16, device_map="auto"
            )
            model = PeftModel.from_pretrained(base, str(lora_path))
        else:
            print("[INFO] Using base model...", flush=True)
            model = AutoModelForCausalLM.from_pretrained(
                MODEL_CONFIG["base_model"], trust_remote_code=True,
                torch_dtype=torch.float16, device_map="auto"
            )
        
        model.eval()
        loaded = True
        print("[INFO] All components loaded!", flush=True)
        return True
    except Exception as e:
        print(f"[ERROR] {e}", flush=True)
        import traceback; traceback.print_exc()
        return False


def build_prompt(question: str, rag_context: str = "") -> str:
    prompt = f"<|im_start|>system\n{SYSTEM_PROMPT}{rag_context}<|im_end|>\n"
    prompt += f"<|im_start|>user\n{question}<|im_end|>\n"
    prompt += "<|im_start|>assistant\n"
    return prompt


def generate_response(text: str, max_tokens: int = 512, temperature: float = 0.1) -> str:
    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_tokens,
            temperature=temperature,
            do_sample=temperature > 0,
            pad_token_id=tokenizer.eos_token_id
        )
    return tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)


def add_to_history(session_id: str, request: dict, response: dict):
    record = {
        "id": str(uuid.uuid4())[:8],
        "timestamp": datetime.now().isoformat(),
        "request": request,
        "response": response
    }
    history[session_id].append(record)
    # 限制历史记录数量
    if len(history[session_id]) > MAX_HISTORY:
        history[session_id] = history[session_id][-MAX_HISTORY:]


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_model()
    yield

app = FastAPI(
    title="电力拓扑异常检测 LLM API",
    description="基于Qwen3.5-0.8B + LoRA + RAG的智能分析服务",
    version="1.2.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 请求模型
class AnalyzeRequest(BaseModel):
    network_data: str
    network_id: Optional[str] = None
    session_id: Optional[str] = "default"
    use_rag: bool = True

class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: int = 512
    temperature: float = 0.1
    session_id: Optional[str] = "default"
    use_rag: bool = True

class BatchAnalyzeRequest(BaseModel):
    items: List[Dict[str, str]]  # [{"network_data": "...", "network_id": "..."}, ...]
    use_rag: bool = True

class RAGQueryRequest(BaseModel):
    query: str
    top_k: int = 3

# ============ 端点 ============

@app.get("/")
async def root():
    return {
        "service": "电力拓扑异常检测 LLM API",
        "version": "1.2.0",
        "endpoints": {
            "health": "GET /health",
            "analyze": "POST /analyze",
            "generate": "POST /generate",
            "batch_analyze": "POST /batch_analyze",
            "rag_query": "POST /rag_query",
            "history": "GET /history/{session_id}",
            "clear_history": "DELETE /history/{session_id}"
        }
    }

@app.get("/health")
async def health():
    rag_chunks = rag_querier.collection.count() if rag_querier else 0
    return {
        "status": "ok" if loaded else "loading",
        "model_loaded": loaded,
        "gpu_available": torch.cuda.is_available(),
        "rag_chunks": rag_chunks,
        "version": "1.2.0"
    }

@app.post("/rag_query")
async def rag_query(req: RAGQueryRequest):
    if not rag_querier:
        raise HTTPException(status_code=503, detail="RAG not loaded")
    docs = rag_querier.query(req.query, top_k=req.top_k)
    return {"success": True, "docs": docs}

@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    if not loaded:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    try:
        # RAG检索
        rag_context = ""
        if req.use_rag and rag_querier:
            docs = rag_querier.query(req.network_data, top_k=3)
            if docs:
                rag_context = "\n\n【参考知识】\n" + "\n".join([
                    f"- {d['category']}: {d['text'][:150]}..."
                    for d in docs
                ])
        
        # 构建提示词
        prompt = build_prompt(req.network_data, rag_context)
        
        # 生成回复
        response_text = generate_response(prompt, MODEL_CONFIG["max_length"])
        
        # 解析JSON
        try:
            result = json.loads(response_text)
        except:
            result = {"raw_response": response_text}
        
        # 保存历史
        add_to_history(req.session_id, {"network_data": req.network_data}, result)
        
        return {
            "success": True,
            "network_id": req.network_id,
            "result": result,
            "rag_used": bool(rag_context)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/generate")
async def generate(req: GenerateRequest):
    if not loaded:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    try:
        rag_context = ""
        if req.use_rag and rag_querier:
            docs = rag_querier.query(req.prompt, top_k=3)
            if docs:
                rag_context = "\n\n【参考知识】\n" + "\n".join([
                    f"- {d['category']}: {d['text'][:150]}..."
                    for d in docs
                ])
        
        prompt = build_prompt(req.prompt, rag_context)
        response_text = generate_response(prompt, req.max_tokens, req.temperature)
        
        add_to_history(req.session_id, {"prompt": req.prompt}, {"response": response_text})
        
        return {"success": True, "response": response_text}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/batch_analyze")
async def batch_analyze(req: BatchAnalyzeRequest):
    if not loaded:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    results = []
    for item in req.items:
        try:
            data = item.get("network_data", "")
            nid = item.get("network_id", "")
            docs = rag_querier.query(data, top_k=3) if req.use_rag and rag_querier else []
            rag_context = "\n\n【参考知识】\n" + "\n".join([f"- {d['category']}: {d['text'][:100]}..." for d in docs]) if docs else ""
            prompt = build_prompt(data, rag_context)
            response_text = generate_response(prompt, 512)
            try:
                result = json.loads(response_text)
            except:
                result = {"raw_response": response_text}
            results.append({"success": True, "network_id": nid, "result": result})
        except Exception as e:
            results.append({"success": False, "network_id": nid, "error": str(e)})
    
    return {"success": True, "results": results, "total": len(results)}

@app.get("/history/{session_id}")
async def get_history(session_id: str):
    return {"session_id": session_id, "records": history.get(session_id, [])}

@app.delete("/history/{session_id}")
async def clear_history(session_id: str):
    if session_id in history:
        history[session_id] = []
    return {"success": True, "message": f"History cleared for {session_id}"}

@app.get("/export/{session_id}")
async def export_history(session_id: str):
    records = history.get(session_id, [])
    if not records:
        raise HTTPException(status_code=404, detail="No records found")
    
    # 创建导出文件
    export_dir = Path("output/llm_exports")
    export_dir.mkdir(parents=True, exist_ok=True)
    filename = f"export_{session_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = export_dir / filename
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump({
            "session_id": session_id,
            "exported_at": datetime.now().isoformat(),
            "total_records": len(records),
            "records": records
        }, f, ensure_ascii=False, indent=2)
    
    return FileResponse(filepath, filename=filename, media_type="application/json")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
