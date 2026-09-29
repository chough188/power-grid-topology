# -*- coding: utf-8 -*-
"""
电力拓扑异常检测 LLM 推理 API - RAG增强版
"""
import os
import sys
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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

# 系统提示词
SYSTEM_PROMPT = """你是一个电力配电网拓扑异常检测专家助手。
遵循以下规则：
1. 只使用领域词汇：母线、线路、变压器、断路器、负荷、发电机
2. 禁止猜测数字，用"需现场确认"代替
3. 每项分析必须追溯数据来源
4. PII检测并脱敏

分析配电网数据，识别28种异常类型并给出修正建议。
输出格式必须为JSON。"""

# 全局变量
model = None
tokenizer = None
rag_querier = None
loaded = False

def load_model():
    global model, tokenizer, rag_querier, loaded
    
    if loaded:
        return True
    
    print("[INFO] Loading model...", flush=True)
    
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
            print(f"[INFO] Loading merged model", flush=True)
            model = AutoModelForCausalLM.from_pretrained(
                merged_path, trust_remote_code=True,
                torch_dtype=torch.float16, device_map="auto"
            )
        elif lora_path.exists():
            print(f"[INFO] Loading base + LoRA", flush=True)
            base_model = AutoModelForCausalLM.from_pretrained(
                MODEL_CONFIG["base_model"], trust_remote_code=True,
                torch_dtype=torch.float16, device_map="auto"
            )
            model = PeftModel.from_pretrained(base_model, str(lora_path))
        else:
            print(f"[INFO] Using base model", flush=True)
            model = AutoModelForCausalLM.from_pretrained(
                MODEL_CONFIG["base_model"], trust_remote_code=True,
                torch_dtype=torch.float16, device_map="auto"
            )
        
        model.eval()
        loaded = True
        print("[INFO] Model loaded successfully!", flush=True)
        return True
        
    except Exception as e:
        print(f"[ERROR] {e}", flush=True)
        import traceback; traceback.print_exc()
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_model()
    yield

app = FastAPI(
    title="电力拓扑异常检测 LLM API (RAG增强)",
    version="1.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AnalyzeRequest(BaseModel):
    network_data: str = Field(..., description="网络数据描述")
    network_id: Optional[str] = Field(None, description="网络ID")
    use_rag: bool = Field(True, description="是否使用RAG增强")

class GenerateRequest(BaseModel):
    prompt: str = Field(..., description="输入提示")
    max_tokens: int = Field(512, description="最大生成长度")
    temperature: float = Field(0.1, description="温度参数")
    use_rag: bool = Field(True, description="是否使用RAG增强")

class RAGQueryRequest(BaseModel):
    query: str = Field(..., description="查询内容")
    top_k: int = Field(3, description="返回结果数量")

class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    gpu_available: bool
    rag_chunks: int

@app.get("/", response_model=Dict)
async def root():
    return {
        "service": "电力拓扑异常检测 LLM API (RAG增强)",
        "version": "1.1.0",
        "endpoints": ["/health", "/analyze", "/generate", "/rag_query", "/docs"]
    }

@app.get("/health", response_model=HealthResponse)
async def health():
    rag_chunks = 0
    if rag_querier:
        try:
            rag_chunks = rag_querier.collection.count()
        except:
            pass
    return HealthResponse(
        status="ok" if loaded else "loading",
        model_loaded=loaded,
        gpu_available=torch.cuda.is_available(),
        rag_chunks=rag_chunks
    )

@app.post("/rag_query")
async def rag_query(request: RAGQueryRequest):
    """RAG知识库检索"""
    if not rag_querier:
        raise HTTPException(status_code=503, detail="RAG not loaded")
    
    docs = rag_querier.query(request.query, top_k=request.top_k)
    return {"success": True, "docs": docs}

@app.post("/analyze", response_model=Dict)
async def analyze(request: AnalyzeRequest):
    if not loaded:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    try:
        # RAG检索
        rag_context = ""
        if request.use_rag and rag_querier:
            docs = rag_querier.query(request.network_data, top_k=3)
            if docs:
                rag_context = "\n\n【相关知识】\n" + "\n".join([
                    f"- {d['category']}: {d['text'][:200]}"
                    for d in docs
                ])
        
        # 构建提示词
        prompt = f"<|im_start|>system\n{SYSTEM_PROMPT}{rag_context}<|im_end|>\n"
        prompt += f"<|im_start|>user\n{request.network_data}<|im_end|>\n"
        prompt += "<|im_start|>assistant\n"
        
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=MODEL_CONFIG["max_length"],
                temperature=0.1,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id
            )
        
        response = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
        
        try:
            result = json.loads(response)
        except:
            result = {"raw_response": response}
        
        return {"success": True, "network_id": request.network_id, "result": result}
        
    except Exception as e:
        return {"success": False, "network_id": request.network_id, "error": str(e)}

@app.post("/generate", response_model=Dict)
async def generate(request: GenerateRequest):
    if not loaded:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    try:
        # RAG检索
        rag_context = ""
        if request.use_rag and rag_querier:
            docs = rag_querier.query(request.prompt, top_k=3)
            if docs:
                rag_context = "\n\n【相关知识】\n" + "\n".join([
                    f"- {d['category']}: {d['text'][:200]}"
                    for d in docs
                ])
        
        prompt = f"<|im_start|>system\n{SYSTEM_PROMPT}{rag_context}<|im_end|>\n"
        prompt += f"<|im_start|>user\n{request.prompt}<|im_end|>\n"
        prompt += "<|im_start|>assistant\n"
        
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=request.max_tokens,
                temperature=request.temperature,
                do_sample=request.temperature > 0,
                pad_token_id=tokenizer.eos_token_id
            )
        
        response = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
        
        return {"success": True, "response": response}
        
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
