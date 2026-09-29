import json
import unittest
from pathlib import Path

from data_loader.loader import OfficialDataset
from tasks_official.execution import OfficialRunner
from tasks_official.registry import LazyTaskRegistry
from tasks_official.catalog import TASKS_BY_CODE
from training.official_anomaly_injection import INJECTORS


class OfficialAnomalyInjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).parents[1] / "data" / "snapshot.json"
        cls.tables = json.loads(path.read_text(encoding="utf-8-sig"))["tables"]
        cls.runner = OfficialRunner(LazyTaskRegistry.with_module_resolver())

    def _detect(self, task_code, tables, options=None):
        result = self.runner.run([task_code], OfficialDataset(tables), options=options or {})
        return list(result.records_by_task.get(task_code, []))

    def test_injections_are_deterministic_and_detectable(self):
        for task_code, injector in INJECTORS.items():
            with self.subTest(task_code=task_code):
                first = injector(self.tables, seed=7)
                second = injector(self.tables, seed=7)
                self.assertEqual(first, second)
                if len(first) == 3:
                    mutated, label, options = first
                else:
                    mutated, label = first
                    options = {}
                OfficialDataset(mutated).validate()
                # Stub tasks (e.g. 2.3) have injectors but no detector; skip detection
                if TASKS_BY_CODE[task_code].implementation_status == "stub":
                    continue
                records = self._detect(task_code, mutated, options)
                predicted = {str(record.device_id) for record in records}
                self.assertTrue(
                    any(any(device_id in prediction for prediction in predicted) for device_id in label.device_ids),
                    f"{task_code} did not detect injected devices {label.device_ids}; got {sorted(predicted)}",
                )


if __name__ == "__main__":
    unittest.main()
