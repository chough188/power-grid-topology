# -*- coding: utf-8 -*-
"""
电力拓扑异常检测 LLM 推理 API
FastAPI + Qwen3.5-0.8B + LoRA
"""
import os
import sys
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

# 添加路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

# 配置
MODEL_CONFIG = {
    "base_model": os.environ.get("DIANLI_BASE_MODEL", "E:/llm_models/Qwen3.5-0.8B"),
    "lora_path": "output/lora/qwen3.5-0.8b-v4/lora_weights",
    "merged_path": "output/lora/qwen3.5-0.8b-merged",
    "max_length": 1024,
    "temperature": 0.1,
    "top_p": 0.9,
}

# 系统提示词
SYSTEM_PROMPT = """你是一个电力配电网拓扑异常检测专家助手。
遵循以下规则：
1. 只使用领域词汇：母线、线路、变压器、断路器、负荷、发电机、电压、电流
2. 禁止猜测数字，用"需现场确认"代替
3. 每项分析必须追溯数据来源
4. PII检测并脱敏

分析配电网数据，识别28种异常类型并给出修正建议。
输出格式必须为JSON。"""

# 全局变量
model = None
tokenizer = None
loaded = False

def load_model():
    """加载模型"""
    global model, tokenizer, loaded
    
    if loaded:
        return True
    
    print("[INFO] Loading model...", flush=True)
    
    try:
        # 优先使用合并后的模型
        merged_path = Path(MODEL_CONFIG["merged_path"])
        lora_path = Path(MODEL_CONFIG["lora_path"])
        
        print(f"[INFO] Base model: {MODEL_CONFIG['base_model']}", flush=True)
        print(f"[INFO] Merged path exists: {merged_path.exists()}", flush=True)
        print(f"[INFO] LoRA path exists: {lora_path.exists()}", flush=True)
        
        tokenizer = AutoTokenizer.from_pretrained(
            MODEL_CONFIG["base_model"], 
            trust_remote_code=True
        )
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        
        if merged_path.exists():
            print(f"[INFO] Loading merged model from {merged_path}", flush=True)
            model = AutoModelForCausalLM.from_pretrained(
                merged_path,
                trust_remote_code=True,
                torch_dtype=torch.float16,
                device_map="auto"
            )
        elif lora_path.exists():
            print(f"[INFO] Loading base + LoRA from {lora_path}", flush=True)
            base_model = AutoModelForCausalLM.from_pretrained(
                MODEL_CONFIG["base_model"],
                trust_remote_code=True,
                torch_dtype=torch.float16,
                device_map="auto"
            )
            model = PeftModel.from_pretrained(base_model, str(lora_path))
        else:
            print("[INFO] Using base model (no LoRA)", flush=True)
            model = AutoModelForCausalLM.from_pretrained(
                MODEL_CONFIG["base_model"],
                trust_remote_code=True,
                torch_dtype=torch.float16,
                device_map="auto"
            )
        
        model.eval()
        loaded = True
        print("[INFO] Model loaded successfully!", flush=True)
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to load model: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动和关闭时的处理"""
    # 启动时加载模型
    load_model()
    yield
    # 关闭时清理

# 创建 FastAPI 应用
app = FastAPI(
    title="电力拓扑异常检测 LLM API",
    description="基于Qwen3.5-0.8B + LoRA的电力配电网异常检测推理服务",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 请求模型
class AnalyzeRequest(BaseModel):
    network_data: str = Field(..., description="网络数据描述")
    network_id: Optional[str] = Field(None, description="网络ID")
    use_rag: bool = Field(False, description="是否使用RAG增强")

class GenerateRequest(BaseModel):
    prompt: str = Field(..., description="输入提示")
    max_tokens: int = Field(512, description="最大生成长度")
    temperature: float = Field(0.1, description="温度参数")

# 响应模型
class AnalyzeResponse(BaseModel):
    success: bool
    network_id: Optional[str]
    result: Optional[Dict[str, Any]]
    error: Optional[str]

class GenerateResponse(BaseModel):
    success: bool
    response: Optional[str]
    error: Optional[str]

class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    gpu_available: bool


@app.get("/", response_model=Dict)
async def root():
    """根路径"""
    return {
        "service": "电力拓扑异常检测 LLM API",
        "version": "1.0.0",
        "endpoints": ["/health", "/analyze", "/generate", "/docs"]
    }

@app.get("/health", response_model=HealthResponse)
async def health():
    """健康检查"""
    return HealthResponse(
        status="ok" if loaded else "loading",
        model_loaded=loaded,
        gpu_available=torch.cuda.is_available()
    )

@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    """分析网络数据"""
    if not loaded:
        raise HTTPException(status_code=503, detail="Model not loaded yet")
    
    try:
        # 构建提示词
        prompt = f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n"
        prompt += f"<|im_start|>user\n{request.network_data}<|im_end|>\n"
        prompt += "<|im_start|>assistant\n"
        
        # 生成
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=MODEL_CONFIG["max_length"],
                temperature=request.temperature if hasattr(request, 'temperature') else 0.1,
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id
            )
        
        response = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
        
        # 尝试解析JSON
        try:
            result = json.loads(response)
        except:
            result = {"raw_response": response}
        
        return AnalyzeResponse(
            success=True,
            network_id=request.network_id,
            result=result
        )
        
    except Exception as e:
        return AnalyzeResponse(
            success=False,
            network_id=request.network_id,
            result=None,
            error=str(e)
        )

@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest):
    """通用生成接口"""
    if not loaded:
        raise HTTPException(status_code=503, detail="Model not loaded yet")
    
    try:
        prompt = f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n"
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
        
        return GenerateResponse(success=True, response=response)
        
    except Exception as e:
        return GenerateResponse(success=False, response=None, error=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
