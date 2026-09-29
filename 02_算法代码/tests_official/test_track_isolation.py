import ast
import re
import unittest
from pathlib import Path

from data_loader.schema import REQUIRED_TABLES
from output_writer.workbook_schema import SHEETS
from tasks_official.catalog import OFFICIAL_TASKS


ALGORITHM_ROOT = Path(__file__).resolve().parents[1]
LEGACY_ROOT = ALGORITHM_ROOT / "_legacy_28anomaly"
OFFICIAL_ROOT = ALGORITHM_ROOT / "tasks_official"
COMMON_ROOTS = (
    ALGORITHM_ROOT / "shared",
    ALGORITHM_ROOT / "data_loader",
    ALGORITHM_ROOT / "output_writer",
)
LEGACY_IMPORTS = {
    "_legacy_28anomaly",
    "anomaly_detection",
    "api",
    "correction_engine",
    "data_preprocessing",
    "visualization",
    "workflow",
}


def imported_roots(path: Path) -> set[str]:
    source = path.read_text(encoding="utf-8-sig", errors="replace")
    roots: set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        pattern = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][A-Za-z0-9_.]*)", re.MULTILINE)
        return {match.group(1).split(".")[0] for match in pattern.finditer(source)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def python_files(root: Path):
    return root.rglob("*.py")


class TrackIsolationTests(unittest.TestCase):
    def test_catalog_contains_official_tasks(self):
        # 12 官方任务 + 5.0 自评分 + 5.1/5.2/5.3 SVG 图形任务 = 16
        self.assertEqual(len(OFFICIAL_TASKS), 16)
        required = {
            "1.1", "1.2", "1.3", "1.4", "1.5",
            "2.1", "2.2", "2.3", "2.4",
            "3.1", "4.1", "4.2",
            "5.0",
            "5.1", "5.2", "5.3",
        }
        self.assertEqual({task.code for task in OFFICIAL_TASKS}, required)
        for task in OFFICIAL_TASKS:
            self.assertTrue((OFFICIAL_ROOT / task.module_path).is_dir(), task.module_path)

    def test_module_5_outputs_correct_sheet_name(self):
        # Module 5 自评分 → Sheet 5
        module_5 = next(t for t in OFFICIAL_TASKS if t.code == "5.0")
        self.assertEqual(module_5.output_sheet, "Model correction quality scoring")
        # Sheet 5 必须仍叫 模型修正质量评分任务结果 (workbook_schema)
        from output_writer.workbook_schema import SHEETS_BY_NAME
        self.assertIn("模型修正质量评分任务结果", SHEETS_BY_NAME)
        self.assertEqual(len(SHEETS_BY_NAME["模型修正质量评分任务结果"].columns), 7)

    def test_official_track_does_not_import_legacy_packages(self):
        for path in python_files(OFFICIAL_ROOT):
            self.assertTrue(imported_roots(path).isdisjoint(LEGACY_IMPORTS), path)

    def test_legacy_track_does_not_import_official_track(self):
        for path in python_files(LEGACY_ROOT):
            self.assertNotIn("tasks_official", imported_roots(path), path)

    def test_common_layers_do_not_depend_on_either_track(self):
        forbidden = LEGACY_IMPORTS | {"tasks_official"}
        for root in COMMON_ROOTS:
            for path in python_files(root):
                self.assertTrue(imported_roots(path).isdisjoint(forbidden), path)

    def test_official_io_contract_counts_are_fixed(self):
        self.assertEqual(len(REQUIRED_TABLES), 14)
        self.assertEqual(len(SHEETS), 6)


if __name__ == "__main__":
    unittest.main()
