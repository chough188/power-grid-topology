# -*- coding: utf-8 -*-
"""Semantic SVG byte-diff helper.

Compares edge set, node set, and header. use: semantic_diff_svg.py a.svg b.svg
"""
from __future__ import annotations
import re
import sys
import json
from pathlib import Path

EDGE_RE = re.compile(r"<line [^/]+/>")
CIRCLE_RE = re.compile(r"<circle [^/]+/>")
TEXT_RE = re.compile(r"<text [^>]*>[^<]*</text>")

def normalize(path):
    text = Path(path).read_text(encoding="utf-8")
    head_end = text.find("<line")
    return {
        "edges": sorted(EDGE_RE.findall(text)),
        "circles": sorted(CIRCLE_RE.findall(text)),
        "texts": sorted(TEXT_RE.findall(text)),
        "head": text[:head_end] if head_end > 0 else text,
    }

def main(argv):
    if len(argv) != 3:
        print("usage: semantic_diff_svg.py ORIG.svg NEW.svg", file=sys.stderr)
        return 2
    sa = normalize(argv[1])
    sb = normalize(argv[2])
    report = {
        "ok": all([sa[k] == sb[k] for k in ("edges", "circles", "texts", "head")]),
        "edge_count": [len(sa["edges"]), len(sb["edges"])],
        "circle_count": [len(sa["circles"]), len(sb["circles"])],
        "text_count": [len(sa["texts"]), len(sb["texts"])],
        "head_match": sa["head"] == sb["head"],
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ok"] else 1

raise SystemExit(main(__import__("sys").argv))
