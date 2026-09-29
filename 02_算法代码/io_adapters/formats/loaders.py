# -*- coding: utf-8 -*-
"""多种数据格式导入（Phase 7.1）。"""
from __future__ import annotations
import json
import csv
from typing import Dict, Any, List


def load_from_json(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_from_csv(path: str) -> List[Dict[str, Any]]:
    out = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            out.append(dict(row))
    return out


def load_from_excel(path: str) -> Dict[str, Any]:
    try:
        import openpyxl
        wb = openpyxl.load_workbook(path)
        ws = wb.active
        out = {"sheets": [], "data": []}
        for row in ws.iter_rows(values_only=True):
            out["data"].append(list(row))
        return out
    except ImportError:
        return {"error": "openpyxl未安装"}


if __name__ == "__main__":
    print("formats module loaded")