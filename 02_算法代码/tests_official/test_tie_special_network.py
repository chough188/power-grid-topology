import json
import unittest
from pathlib import Path
from data_loader.loader import OfficialDataset
from tasks_official.execution import OfficialRunner
from tasks_official.registry import LazyTaskRegistry
from tasks_official.task5_svg.task_5_3_auto_draw.detector import render_5_3_2_tie_diagram

class TieSpecialNetworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).parents[2] / "03_数据集" / "official_special_networks"
        cls.runner = OfficialRunner(LazyTaskRegistry.with_module_resolver())
    def _run(self, name, task):
        tables = json.loads((self.root / name).read_text(encoding="utf-8"))["tables"]
        return self.runner.run([task], OfficialDataset(tables)).records_by_task[task]
    def test_clean_open_tie_is_task_1_3(self):
        self.assertEqual([r.device_id for r in self._run("tie_clean.json", "1.3")], ["TIE_AB"])
    def test_tie_svg_renders_same_open_tie(self):
        tables = json.loads((self.root / "tie_clean.json").read_text(encoding="utf-8"))["tables"]
        svg = render_5_3_2_tie_diagram(tables, "F_A")
        self.assertIn('data-equip-id="TIE_AB"', svg)
        self.assertNotIn("no tie switches", svg)
    def test_single_sided_tie_is_task_1_4(self):
        records = self._run("tie_suspect.json", "1.4")
        self.assertEqual([r.device_id for r in records], ["TIE_AB"])
        self.assertIn(records[0].extra["fail_reason"], {"contiguous_dangle", "svg_mismatch"})
        self.assertLess(records[0].confidence, 0.7)
if __name__ == "__main__": unittest.main()
