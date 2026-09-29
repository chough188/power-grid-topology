# -*- coding: utf-8 -*-
"""
LLM模型下载脚本

下载Qwen3-0.6B-Instruct GGUF量化模型
模型大小: ~400MB
用途: 诊断报告润色

使用方法:
    python download_model.py                    # 下载默认模型
    python download_model.py --model qwen3-1.7b  # 下载指定模型
    python download_model.py --list             # 列出可用模型
"""
import os
import sys
import argparse
import subprocess
from pathlib import Path

# 模型配置
AVAILABLE_MODELS = {
    "qwen3-0.6b": {
        "repo": "Qwen/Qwen3-0.6B-Instruct-GGUF",
        "file": "Qwen3-0.6B-Instruct-Q4_K_M.gguf",
        "size": "~400MB",
        "description": "最轻量级，适合CPU推理",
    },
    "qwen3-1.7b": {
        "repo": "Qwen/Qwen3-1.7B-Instruct-GGUF",
        "file": "Qwen3-1.7B-Instruct-Q4_K_M.gguf",
        "size": "~1GB",
        "description": "平衡性能和大小",
    },
    "qwen35-4b-claude": {
        "repo": "Jackrong/Qwen3.5-4B-Claude-4.6-Opus-Reasoning-Distilled-GGUF",
        "file": "Qwen3.5-4B.Q4_K_M.gguf",
        "size": "~2.5GB",
        "description": "Claude Opus蒸馏推理模型(推荐)",
    },
    "qwen3-4b": {
        "repo": "Qwen/Qwen3-4B-Instruct-GGUF",
        "file": "Qwen3-4B-Instruct-Q4_K_M.gguf",
        "size": "~2.5GB",
        "description": "更强推理能力",
    },
}

DEFAULT_MODEL = "qwen35-4b-claude"
TARGET_DIR = Path(r"E:\llm_models\Qwen3.5-4B-Claude-Opus")


def list_models():
    """列出可用模型"""
    print("\n可用模型:")
    print("-" * 60)
    for name, info in AVAILABLE_MODELS.items():
        print(f"  {name:15} | {info['size']:8} | {info['description']}")
    print("-" * 60)
    print(f"\n默认模型: {DEFAULT_MODEL}")


def download_model(model_name: str):
    """下载模型"""
    if model_name not in AVAILABLE_MODELS:
        print(f"错误: 未知模型 '{model_name}'")
        list_models()
        return False
    
    model_info = AVAILABLE_MODELS[model_name]
    repo = model_info["repo"]
    filename = model_info["file"]
    target_path = TARGET_DIR / filename
    
    # 检查是否已存在
    if target_path.exists():
        print(f"模型已存在: {target_path}")
        print(f"文件大小: {target_path.stat().st_size / 1024 / 1024:.1f} MB")
        return True
    
    print(f"\n下载模型: {model_name}")
    print(f"  仓库: {repo}")
    print(f"  文件: {filename}")
    print(f"  大小: {model_info['size']}")
    print(f"  目标: {target_path}")
    print()
    
    # 检查huggingface-cli
    try:
        subprocess.run(["huggingface-cli", "--version"], 
                      capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("错误: 未安装huggingface-cli")
        print("请运行: pip install huggingface_hub")
        return False
    
    # 下载
    try:
        cmd = [
            "huggingface-cli", "download",
            repo,
            filename,
            "--local-dir", str(TARGET_DIR),
        ]
        print(f"执行命令: {' '.join(cmd)}")
        print("下载中...")
        
        result = subprocess.run(cmd, check=True)
        
        if target_path.exists():
            print(f"\n下载成功!")
            print(f"文件大小: {target_path.stat().st_size / 1024 / 1024:.1f} MB")
            return True
        else:
            print("\n下载失败: 文件不存在")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"\n下载失败: {e}")
        return False



def download_from_modelscope(model_name: str):
    """从ModelScope下载模型（国内镜像，无需翻墙）"""
    try:
        from modelscope import snapshot_download
    except ImportError:
        print("modelscope未安装，请运行: pip install modelscope")
        return False
    
    ms_map = {
        "qwen2.5-0.5b": "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
        "qwen2.5-1.5b": "Qwen/Qwen2.5-1.5B-Instruct-GGUF",
    }
    
    repo = ms_map.get(model_name, model_name)
    print(f"从ModelScope下载: {repo}")
    
    try:
        model_dir = snapshot_download(repo, local_dir=str(TARGET_DIR), allow_file_pattern="*Q4_K*")
        print(f"下载完成: {model_dir}")
        return True
    except Exception as e:
        print(f"ModelScope下载失败: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="下载LLM模型")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL,
                       help=f"模型名称 (默认: {DEFAULT_MODEL})")
    parser.add_argument("--list", action="store_true",
                       help="列出可用模型")
    
    args = parser.parse_args()
    
    if args.list:
        list_models()
        return
    
    success = download_model(args.model)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
