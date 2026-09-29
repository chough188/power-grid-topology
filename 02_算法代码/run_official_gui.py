"""Entry point that launches the CP-202606 official task GUI.

This script deliberately stays inside the official track. It does NOT
import legacy_28_anomaly, legacy_api, llm_assistant or gnn_classifier
modules; isolation is enforced by tasks_official.execution.ISOLATED_COMPONENTS
and by starting a fresh Python interpreter with PYTHONPATH pointed only at
02_算法代码.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from tasks_official.gui import main

if __name__ == "__main__":
    main()
