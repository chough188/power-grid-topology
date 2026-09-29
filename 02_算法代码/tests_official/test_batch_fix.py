# -*- coding: utf-8 -*-
"""batch_fix 单元测试：完整检测 + 首末端自动豁免 + 孤岛 PENDING/候选 + view 标记。"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINE215 = ROOT.parent / "03_数据集" / "svg_input" / "LINE215.svg"


def _run_batch_fix(in_dir: str) -> str:
    r = subprocess.run([sys.executable, "-X", "utf8", "scripts/llm_svg_tools.py", "batch_fix", in_dir],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=str(ROOT))
    return (r.stdout or "") + (r.stderr or "")


class BatchFixTests(unittest.TestCase):
    def _make_issue_svg(self, td: str, extra_block: str) -> Path:
        """复制 LINE215 并在 </svg> 前插入孤岛设备。"""
        text = LINE215.read_text(encoding="utf-8")
        text = text.rstrip()
        self.assertTrue(text.endswith("</svg>"))
        text = text[: -len("</svg>")] + extra_block + "\n</svg>"
        p = Path(td) / "issue.svg"
        p.write_text(text, encoding="utf-8")
        return p

    def test_clean_svg_is_ok_no_view(self):
        with tempfile.TemporaryDirectory() as td:
            Path(td, "a.svg").write_text(LINE215.read_text(encoding="utf-8"), encoding="utf-8")
            out = _run_batch_fix(td)
            self.assertIn("BATCHFIX a.svg = OK", out)
            self.assertIn("verify_ok=True view=N", out)
            self.assertIn("BATCHFIX_OK = 1", out)
            self.assertIn("BATCHFIX_NEED_VIEW = 0", out)

    def test_island_device_is_pending_with_candidates(self):
        with tempfile.TemporaryDirectory() as td:
            self._make_issue_svg(td, '<g class="device" data-equip-id="TMP00000099">'
                                     '<rect x="700" y="460" width="30" height="30" fill="#333"/></g>')
            out = _run_batch_fix(td)
            self.assertIn("BATCHFIX issue.svg = PENDING", out)
            self.assertIn("islands=1", out)
            self.assertIn("view=Y", out)
            self.assertIn("CAND TMP00000099 ->", out)
            self.assertIn("BATCHFIX_PENDING = 1", out)
            self.assertIn("BATCHFIX_NEED_VIEW_LIST = issue.svg", out)

    def test_line_end_switch_auto_exempt(self):
        """LINE215 首端/末端开关 deg=1 且 x 极值 → 自动豁免，verify_ok=True。"""
        with tempfile.TemporaryDirectory() as td:
            Path(td, "a.svg").write_text(LINE215.read_text(encoding="utf-8"), encoding="utf-8")
            out = _run_batch_fix(td)
            self.assertIn("dangling=2", out)
            self.assertIn("exempt=TMP00000001,TMP00000012", out)
            self.assertIn("verify_ok=True", out)


if __name__ == "__main__":
    unittest.main()
