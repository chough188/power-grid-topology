# LLM模型目录

本目录存放LLM模型文件，用于诊断报告润色。

## 可用模型

| 模型 | 大小 | 说明 |
|------|------|------|
| Qwen3-0.6B-Instruct-Q4_K_M.gguf | ~400MB | 最轻量级，推荐 |
| Qwen3-1.7B-Instruct-Q4_K_M.gguf | ~1GB | 平衡性能 |
| Qwen3-4B-Instruct-Q4_K_M.gguf | ~2.5GB | 更强推理 |

## 下载方法

```bash
# 下载默认模型 (Qwen3-0.6B)
python download_model.py

# 下载指定模型
python download_model.py --model qwen3-1.7b
python download_model.py --model qwen3-4b

# 列出可用模型
python download_model.py --list
```

## 使用方法

```python
from llm_assistant.diagnostic_engine import DiagnosticEngine

# 无LLM模式（默认，100%可用）
engine = DiagnosticEngine()

# 有LLM模式（可选润色）
engine = DiagnosticEngine(
    use_llm=True,
    llm_model_path="models/Qwen3-0.6B-Instruct-Q4_K_M.gguf"
)

# 诊断
result = engine.diagnose(anomalies, network_context)
```

## 注意事项

1. 模型文件不纳入Git版本控制
2. 首次使用需运行下载脚本
3. 无模型时自动降级到规则引擎
4. CPU推理延迟约2-3秒
