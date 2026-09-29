import unittest

from data_loader.synthetic_gen import make_synthetic_dataset
from tasks_official.group_02_graph_model.hybrid_runner import HybridConfig, run_official_hybrid
from tasks_official.group_02_graph_model.gnn_v4 import (
    build_graph_from_14tables_v4,
    train_hybrid_gnn,
)
from tasks_official.execution import OfficialRunner
from tasks_official.registry import LazyTaskRegistry


class HybridRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = make_synthetic_dataset(seed=17)
        cls.registry = LazyTaskRegistry.with_module_resolver()

    def test_default_policy_is_exact_rule_path(self):
        expected = OfficialRunner(self.registry).run(["1.1"], self.dataset)
        actual = run_official_hybrid(["1.1"], self.dataset, registry=self.registry)
        self.assertEqual(actual.records_by_task, expected.records_by_task)

    def test_enabled_policy_preserves_candidates_and_annotates(self):
        expected = OfficialRunner(self.registry).run(["1.1", "2.2"], self.dataset)
        actual = run_official_hybrid(
            ["1.1", "2.2"],
            self.dataset,
            registry=self.registry,
            config=HybridConfig(enabled=True, alpha=0.25, epochs=2, enabled_tasks=("1.1",)),
        )
        for task_code in ("1.1", "2.2"):
            expected_ids = {record.device_id for record in expected.records_by_task[task_code]}
            actual_ids = {record.device_id for record in actual.records_by_task[task_code]}
            self.assertEqual(actual_ids, expected_ids)
            for record in actual.records_by_task[task_code]:
                self.assertIn("gnn_anomaly_score", record.extra)
                self.assertIn("adjusted_confidence", record.extra)
                expected_alpha = 0.25 if task_code == "1.1" else 0.0
                self.assertEqual(record.extra["gnn_weight_applied"], expected_alpha)

    def test_all_zero_task_alphas_preserve_exact_rule_order(self):
        expected = OfficialRunner(self.registry).run(["1.1"], self.dataset)
        actual = run_official_hybrid(
            ["1.1"],
            self.dataset,
            registry=self.registry,
            config=HybridConfig(enabled=True, alpha_by_task={"1.1": 0.0}, epochs=2),
        )
        self.assertEqual(actual.records_by_task, expected.records_by_task)

    def test_task_specific_alpha_can_be_calibrated_independently(self):
        actual = run_official_hybrid(
            ["1.1", "2.2"],
            self.dataset,
            registry=self.registry,
            config=HybridConfig(
                enabled=True,
                alpha_by_task={"1.1": 0.2},
                epochs=2,
            ),
        )
        for record in actual.records_by_task["1.1"]:
            self.assertEqual(record.extra["gnn_weight_applied"], 0.2)
        for record in actual.records_by_task["2.2"]:
            self.assertEqual(record.extra["gnn_weight_applied"], 0.0)

    def test_invalid_policy_rejected(self):
        with self.assertRaises(ValueError):
            run_official_hybrid(
                ["1.1"], self.dataset, config=HybridConfig(enabled=True, alpha=1.1)
            )

    def test_v4_branch_preserves_candidates_and_uses_trained_head_only(self):
        graph = build_graph_from_14tables_v4(self.dataset.normalized().tables)
        model = train_hybrid_gnn(graph, epochs=2, seed=42)
        model.trained_task_codes.add("1.1")
        expected = OfficialRunner(self.registry).run(["1.1"], self.dataset)
        actual = run_official_hybrid(
            ["1.1"],
            self.dataset,
            registry=self.registry,
            config=HybridConfig(
                enabled=True,
                alpha_by_task={"1.1": 0.2},
                model=model,
                model_version="v4",
            ),
        )
        self.assertEqual(
            {record.device_id for record in expected.records_by_task["1.1"]},
            {record.device_id for record in actual.records_by_task["1.1"]},
        )
        for record in actual.records_by_task["1.1"]:
            self.assertEqual(record.extra["hybrid_model_version"], "v4")
            self.assertEqual(record.extra["gnn_weight_applied"], 0.2)
            self.assertGreaterEqual(record.extra["gnn_anomaly_score"], 0.0)
            self.assertLessEqual(record.extra["gnn_anomaly_score"], 1.0)

    def test_invalid_model_version_rejected(self):
        with self.assertRaises(ValueError):
            run_official_hybrid(
                ["1.1"],
                self.dataset,
                config=HybridConfig(enabled=True, alpha=0.2, model_version="v5"),
            )


if __name__ == "__main__":
    unittest.main()
