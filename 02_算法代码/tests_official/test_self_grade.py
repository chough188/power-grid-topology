from tasks_official.registry import LazyTaskRegistry
import json
import tempfile
import unittest
from pathlib import Path

from tasks_official.self_grade import (
    ALL_TASKS,
    EXEMPT_KEYWORDS,
    KEY_TASKS,
    _has_sqlglot,
    _validate_sql_shape,
    parse_sql,
)


class SelfGradeUnitTests(unittest.TestCase):
    def test_all_tasks_count_matches_catalog(self):
        # 12 个二级子任务（任务组 1-4）+ 5.0 自评分 + 5.1/5.2/5.3 SVG 专项 = 16
        # ALL_TASKS 排除 5.0/5.1/5.2/5.3（评分和 SVG 不参与官方评分分母）
        # OFFICIAL_TASKS(16) - 5.0(1) - SVG(3) = 12 个评分任务
        self.assertEqual(len(ALL_TASKS), 12)

    def test_key_tasks_subset(self):
        for code in KEY_TASKS:
            self.assertIn(code, ALL_TASKS)

    def test_exempt_keywords_count(self):
        self.assertEqual(len(EXEMPT_KEYWORDS), 8)

    def test_sqlglot_detection(self):
        # Just check it does not raise
        self.assertIsInstance(_has_sqlglot(), bool)

    def test_parse_sql_empty(self):
        self.assertFalse(parse_sql(''))
        self.assertFalse(parse_sql('   '))

    def test_parse_sql_garbage(self):
        self.assertFalse(parse_sql('NOT VALID SQL AT ALL'))

    def test_parse_sql_select(self):
        self.assertTrue(parse_sql('SELECT 1 FROM DUAL'))
        self.assertTrue(parse_sql('SELECT * FROM T WHERE x = 1'))

    def test_parse_sql_insert(self):
        self.assertTrue(parse_sql('INSERT INTO T (a, b) VALUES (1, 2)'))
        self.assertTrue(parse_sql(
            'INSERT INTO JBS_PWTERMINAL (ID, EQUIP_ID, CONNECTIVITYNODE_ID) '
            'VALUES (SEQ_PWTERMINAL.NEXTVAL, :device_id, :new_node_id)'
        ))

    def test_parse_sql_update(self):
        self.assertTrue(parse_sql("UPDATE JBS_PWEQUIPINFO SET EQUIP_TYPE = 'TIE' WHERE EQUIP_ID = :device_id"))
        self.assertTrue(parse_sql('UPDATE T SET RUN_STATUS = 0 WHERE EQUIP_ID = :device_id'))

    def test_parse_sql_delete(self):
        self.assertTrue(parse_sql('DELETE FROM JBS_PWTERMINAL WHERE ID = :terminal_id'))

    def test_validate_sql_shape_balanced_parens(self):
        self.assertTrue(_validate_sql_shape('SELECT (1+2) FROM DUAL'))
        self.assertFalse(_validate_sql_shape('SELECT (1+2 FROM DUAL'))

    def test_validate_sql_shape_quoted_strings(self):
        # Strings can contain parens
        self.assertTrue(_validate_sql_shape("SELECT 'has ( inside' FROM DUAL"))

    def test_validate_sql_shape_invalid_keyword(self):
        self.assertFalse(_validate_sql_shape('FOOBAR 123'))
        self.assertFalse(_validate_sql_shape('GRANT SELECT ON T TO U'))


class SelfGradeEndToEndTests(unittest.TestCase):
    def test_self_grade_against_synthetic_dataset(self):
        from data_loader.synthetic_gen import make_synthetic_dataset
        from output_writer.writer import write_workbook
        from tasks_official.execution import OfficialRunner

        ds = make_synthetic_dataset(seed=42)
        runner = OfficialRunner(LazyTaskRegistry.with_module_resolver())
        result = runner.run(list(ALL_TASKS), ds)
        # Should run to completion (12 个评分任务 = 任务组 1-4 的二级子任务)
        self.assertEqual(len(result.executed_task_codes), 12)
        # xlsx should write without error
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as f:
            tmp_path = Path(f.name)
        try:
            records = [r for recs in result.records_by_task.values() for r in recs]
            out = write_workbook(records, tmp_path, dataset=ds)
            self.assertTrue(out.exists())
            self.assertGreater(out.stat().st_size, 0)
        finally:
            tmp_path.unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()