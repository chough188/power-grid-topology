# -*- coding: utf-8 -*-
"""GUI 入口：python run_full_gui.py 或 双击启动完整系统.bat

模块化拆分：
  - gui/theme.py       设计 token（配色/字号/间距/动效）
  - gui/motion.py      时间轴动效（GSAP 思路）
  - gui/auto_pipeline  一键 pipeline 逻辑（无 GUI 依赖）
  - gui/panels/        各功能面板
  - gui/main_window.py 主窗口
"""
from __future__ import annotations

import sys
from pathlib import Path

# 把当前目录加到 sys.path
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from gui.main_window import main


if __name__ == "__main__":
    main()
