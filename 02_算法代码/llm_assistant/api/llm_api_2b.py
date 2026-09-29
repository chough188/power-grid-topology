# -*- coding: utf-8 -*-
"""Qwen3.5-2B LLM API - UTF-8 Fixed"""
import os
import sys
import json
import time
from pathlib import Path
from typing import Optional
import torch
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn
import chromadb
from chromadb.utils import embedding_functions

# 设置UTF-8
sys.stdout.reconfigure(encoding='utf-8')
os.chdir(r'E:\项目大全\电力拓扑图修正\02_算法代码')

MODEL_PATH = r'E:\llm_models\Qwen3.5-2B'
RAG_DB = 'output/rag_vector_db_v4'

_model = None
_tokenizer = None
_rag = None

def load_components():
    global _model, _tokenizer, _rag
    
    if _model is not None:
        return
    
    print('[Loading] Starting...', flush=True)
    
    from transformers import AutoModelForCausalLM, AutoTokenizer
    
    _tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
    if _tokenizer.pad_token is None:
        _tokenizer.pad_token = _tokenizer.eos_token
    
    print('[Loading] Model (2B)...', flush=True)
    _model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH,
        trust_remote_code=True,
        torch_dtype=torch.float16,
        device_map='auto'
    )
    _model.eval()
    print('[OK] Model loaded!', flush=True)
    
    try:
        ef = embedding_functions.ONNXMiniLM_L6_V2()
        client = chromadb.PersistentClient(path=RAG_DB)
        _rag = client.get_collection('power_topology_kb_v4')
        print(f'[OK] RAG: {_rag.count()} chunks', flush=True)
    except Exception as e:
        print(f'[WARN] RAG failed: {e}', flush=True)
        _rag = None

app = FastAPI(title='Qwen3.5-2B LLM API', version='2.0')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])

class QueryRequest(BaseModel):
    network_data: str = Field(..., description='Network data')
    question: str = Field('请分析拓扑异常并给出修正建议')
    use_rag: bool = Field(True)
    rag_top_k: int = Field(3)
    max_tokens: int = Field(512)
    temperature: float = Field(0.1)

class QueryResponse(BaseModel):
    success: bool
    answer: Optional[str] = None
    rag_sources: Optional[list] = None
    tokens: Optional[int] = None
    time_ms: Optional[float] = None
    error: Optional[str] = None

SYSTEM_PROMPT = '''你是电力系统拓扑异常分析专家。

规则：
1. 使用专业术语：母线、线路、变压器、断路器、负荷、发电机、电压、电流
2. 检测28种异常类型
3. 输出格式：总体评估、主要异常列表、修正建议

请分析以下配电网数据，识别异常并给出建议。'''

@app.post('/analyze', response_model=QueryResponse)
async def analyze(req: QueryRequest):
    load_components()
    start = time.time()
    
    # RAG
    rag_context = ''
    sources = []
    if req.use_rag and _rag:
        try:
            results = _rag.query(query_texts=[req.question], n_results=req.rag_top_k)
            if results and results.get('documents'):
                parts = []
                for i, (doc, meta) in enumerate(zip(results['documents'][0], results['metadatas'][0])):
                    parts.append(f'[{i+1}] {doc[:200]}')
                    sources.append({'text': doc[:150], 'source': meta.get('source', ''), 'category': meta.get('category', '')})
                rag_context = '【参考知识】\n' + '\n'.join(parts) + '\n\n'
        except Exception as e:
            pass
    
    full_input = f'{rag_context}【网络数据】\n{req.network_data}\n\n【分析要求】\n{req.question}'
    
    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': full_input}
    ]
    
    text = _tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = _tokenizer([text], return_tensors='pt').to(_model.device)
    
    try:
        with torch.no_grad():
            outputs = _model.generate(
                **inputs,
                max_new_tokens=req.max_tokens,
                temperature=req.temperature,
                do_sample=req.temperature > 0.01,
                repetition_penalty=1.1
            )
        
        response = _tokenizer.decode(outputs[0][inputs['input_ids'].shape[1]:], skip_special_tokens=True)
        elapsed = (time.time() - start) * 1000
        
        return QueryResponse(
            success=True,
            answer=response.strip(),
            rag_sources=sources if sources else None,
            tokens=len(outputs[0]) - inputs['input_ids'].shape[1],
            time_ms=round(elapsed, 1)
        )
    except Exception as e:
        return QueryResponse(success=False, error=str(e))

@app.get('/health')
async def health():
    load_components()
    return {
        'status': 'ok',
        'model': 'Qwen3.5-2B',
        'rag_chunks': _rag.count() if _rag else 0,
        'ready': _model is not None
    }

@app.get('/info')
async def info():
    return {
        'model': 'Qwen3.5-2B',
        'parameters': '2B',
        'rag_version': 'v4',
        'rag_chunks': 918,
        'anomaly_types': 28
    }

if __name__ == '__main__':
    print('='*50)
    print('Qwen3.5-2B LLM API')
    print('Model: Qwen3.5-2B')
    print('RAG: v4 (918 chunks)')
    print('='*50)
    uvicorn.run(app, host='0.0.0.0', port=8002, log_level='info')