# -*- coding: utf-8 -*-
"""启动 LLM API 服务"""
import sys
import subprocess
from pathlib import Path

def main():
    script_dir = Path(__file__).parent
    api_script = script_dir / "llm_assistant" / "api" / "llm_api.py"
    
    print("=" * 60)
    print("电力拓扑异常检测 LLM API 服务")
    print("=" * 60)
    print(f"API脚本: {api_script}")
    print(f"启动命令: py {api_script}")
    print()
    print("API端点:")
    print("  GET  /          - 服务信息")
    print("  GET  /health    - 健康检查")
    print("  POST /analyze   - 分析网络数据")
    print("  POST /generate  - 通用生成")
    print("  GET  /docs      - API文档")
    print()
    print("=" * 60)
    print("启动服务...")
    print("=" * 60)
    
    # 启动服务
    cmd = [sys.executable, str(api_script)]
    subprocess.run(cmd)

if __name__ == "__main__":
    main()