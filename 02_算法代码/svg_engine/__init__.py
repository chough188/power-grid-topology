#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SVG 拓扑图形处理引擎
===================
比赛任务二专用模块：
- 5.1 现有 SVG 图形标准化美化
- 5.2 SVG 图形交互式增删设备
- 5.3 自动生成 SVG 接线图

核心设计原则：
1. 5.1 美化任务：不读取数据库，仅依托 SVG 文件自身连接关系
2. 5.2 编辑任务：在美化后 SVG 上操作，保证图模一致
3. 5.3 生成任务：读取完整数据库，按国网规范自动出图
"""

__version__ = "0.1.0"

from . import svg_loader
from . import beautify
from . import edit_device
from . import auto_generate
