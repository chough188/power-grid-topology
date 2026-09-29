import sys
import unittest

import numpy as np
import torch

from tasks_official.group_02_graph_model.gnn_v3 import (
    build_graph_from_14tables_v3,
    sample_negative_edges,
    rerank_rule_records_v3,
    train_gae_v3,
)


class GnnV3Tests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        for module_name in list(sys.modules):
            if module_name == "torch" or module_name.startswith("torch."):
                sys.modules.pop(module_name, None)

    def test_negative_samples_are_true_non_edges(self):
        positive = torch.tensor([[0, 1, 1, 2], [1, 0, 2, 1]], dtype=torch.long)
        sampled = sample_negative_edges(
            positive, 4, 6, torch.Generator().manual_seed(7)
        )
        positive_set = set(map(tuple, positive.t().tolist()))
        negative_set = set(map(tuple, sampled.t().tolist()))
        self.assertEqual(sampled.size(1), 6)
        self.assertFalse(positive_set & negative_set)
        self.assertTrue(all(src != dst for src, dst in negative_set))

    def test_duplicate_equipment_ids_are_collapsed(self):
        tables = {
            "JBS_PWEQUIPINFO": [{"EQUIP_ID": "E1", "EQUIP_TYPE": "LINE"}],
            "JBS_ZWEQUIPINFO": [{"EQUIP_ID": "E1", "EQUIP_TYPE": "BREAKER"}],
        }
        graph = build_graph_from_14tables_v3(tables)
        self.assertEqual(graph["node_ids"], ["E1"])
        self.assertEqual(graph["node_features"].shape[0], 1)

    def test_default_rerank_preserves_rule_confidence(self):
        class Record:
            def __init__(self):
                self.device_id = "E1"
                self.task_code = "1.1"
                self.confidence = 0.83
                self.extra = {}

        graph = {
            "node_ids": ["E1", "E2"],
            "node_features": np.eye(2, dtype=np.float32),
            "edge_index": np.array([[0, 1], [1, 0]], dtype=np.int64),
        }
        model = train_gae_v3(graph, epochs=1, seed=3)
        records = rerank_rule_records_v3(model, graph, [Record()])
        self.assertEqual(records[0].extra["gnn_weight_applied"], 0.0)
        self.assertEqual(records[0].extra["adjusted_confidence"], 0.83)

    def test_training_is_reproducible_for_same_seed(self):
        graph = {
            "node_features": np.eye(3, dtype=np.float32),
            "edge_index": np.array([[0, 1, 1, 2], [1, 0, 2, 1]], dtype=np.int64),
        }
        first = train_gae_v3(graph, epochs=3, seed=11)
        second = train_gae_v3(graph, epochs=3, seed=11)
        for left, right in zip(first.parameters(), second.parameters()):
            self.assertTrue(torch.equal(left, right))


if __name__ == "__main__":
    unittest.main()
