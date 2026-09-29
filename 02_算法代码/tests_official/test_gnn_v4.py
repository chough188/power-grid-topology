# -*- coding: utf-8 -*-
"""Smoke tests for the v4 HybridGNN graph construction + training."""
from __future__ import annotations

import unittest

import torch

from tasks_official.group_02_graph_model.gnn_v4 import (
    EDGE_TYPE_VOCAB,
    GATLayer,
    HybridGNN,
    RGCNLayer,
    TASK_HEADS,
    build_graph_from_14tables_v4,
    fine_tune_hybrid_gnn,
    hybrid_predict_with_confidence,
    merge_graphs_v4,
    rerank_rule_records_v4,
    train_hybrid_gnn,
)


def _make_graph():
    tables = {
        "JBS_PWEQUIPINFO": [
            {"EQUIP_ID": "A", "EQUIP_TYPE": "BREAKER", "VOLTAGE_TYPE": 10,
             "FEEDER_ID": "F1", "RUN_STATUS": 1, "DSUBSTATION_ID": "RM1"},
            {"EQUIP_ID": "B", "EQUIP_TYPE": "LINE", "VOLTAGE_TYPE": 10,
             "FEEDER_ID": "F1", "RUN_STATUS": 1, "DSUBSTATION_ID": "RM1"},
            {"EQUIP_ID": "C", "EQUIP_TYPE": "TRANSFORMER", "VOLTAGE_TYPE": 10,
             "FEEDER_ID": "F1", "RUN_STATUS": 1, "DSUBSTATION_ID": "RM1"},
            {"EQUIP_ID": "D", "EQUIP_TYPE": "LOAD", "VOLTAGE_TYPE": 0.4,
             "FEEDER_ID": "F1", "RUN_STATUS": 1, "DSUBSTATION_ID": "RM1"},
        ],
        "JBS_PWTERMINAL": [
            {"EQUIP_ID": "A", "CONNECTIVITYNODE_ID": "n1", "PORT_NO": 1,
             "ID": "t1", "VALID_FLAG": 1},
            {"EQUIP_ID": "B", "CONNECTIVITYNODE_ID": "n1", "PORT_NO": 1,
             "ID": "t2", "VALID_FLAG": 1},
            {"EQUIP_ID": "B", "CONNECTIVITYNODE_ID": "n2", "PORT_NO": 2,
             "ID": "t3", "VALID_FLAG": 1},
            {"EQUIP_ID": "C", "CONNECTIVITYNODE_ID": "n2", "PORT_NO": 1,
             "ID": "t4", "VALID_FLAG": 1},
            {"EQUIP_ID": "C", "CONNECTIVITYNODE_ID": "n3", "PORT_NO": 2,
             "ID": "t5", "VALID_FLAG": 1},
            {"EQUIP_ID": "D", "CONNECTIVITYNODE_ID": "n3", "PORT_NO": 1,
             "ID": "t6", "VALID_FLAG": 1},
        ],
        "JBS_ZWTERMINAL": [],
        "JBS_PWFEEDERLINE": [
            {"LINE_ID": "F1", "LINE_NAME": "F1", "START_ST_ID": "ST1",
             "VOLTAGE_TYPE": 10},
        ],
        "JBS_PWROOM": [
            {"ROOM_ID": "R1", "ROOM_NAME": "R1", "TOP_VOLTAGE_TYPE": 10,
             "FEEDER_ID": "F1"},
        ],
        "JBS_ZD_OBJECT": [
            {"OBJ_ID": "OBJ01", "OBJ_CODE": "BREAKER", "OBJ_CNNAME": "Breaker",
             "OBJ_ENNAME": "Breaker"},
        ],
    }
    return build_graph_from_14tables_v4(tables)


class GnnV4SmokeTests(unittest.TestCase):
    def test_build_graph_shapes_match_v3_contract(self):
        graph = _make_graph()
        self.assertEqual(set(graph.keys()), {
            "node_ids", "node_to_idx", "node_features", "edge_index",
            "edge_type", "edge_type_vocab", "equip_meta",
        })
        self.assertEqual(graph["node_features"].shape[1], 35)
        self.assertEqual(graph["edge_type"].shape[0], graph["edge_index"].shape[1])
        self.assertEqual(set(graph["edge_type_vocab"]), set(EDGE_TYPE_VOCAB))

    def test_gat_layer_handles_empty_graph(self):
        layer = GATLayer(in_dim=8, out_dim=4)
        x = torch.zeros(3, 8)
        empty_edges = torch.zeros((2, 0), dtype=torch.long)
        out = layer(x, empty_edges)
        self.assertEqual(out.shape, (3, 4))

    def test_rgcn_layer_handles_empty_graph(self):
        layer = RGCNLayer(in_dim=8, out_dim=4, num_relations=len(EDGE_TYPE_VOCAB))
        x = torch.zeros(3, 8)
        empty_edges = torch.zeros((2, 0), dtype=torch.long)
        empty_types = torch.zeros((0,), dtype=torch.long)
        out = layer(x, empty_edges, empty_types)
        self.assertEqual(out.shape, (3, 4))

    def test_training_loss_decreases(self):
        graph = _make_graph()
        try:
            torch.manual_seed(42)
        except (ValueError, RuntimeError):
            pass
        model = train_hybrid_gnn(graph, epochs=30, seed=42)
        x = torch.tensor(graph["node_features"])
        edge_index = torch.tensor(graph["edge_index"])
        edge_type = torch.tensor(graph["edge_type"])
        before = model(x, edge_index, edge_type)["1.1"].mean().item()
        for _ in range(30):
            pred = model(x, edge_index, edge_type)
            pos = pred["1.1"][edge_index[0]] * pred["1.1"][edge_index[1]]
            loss = -torch.log(torch.sigmoid(pos) + 1e-8).mean()
            loss.backward()
        self.assertTrue(torch.isfinite(torch.tensor(before)).item())

    def test_mc_dropout_returns_mean_and_std(self):
        graph = _make_graph()
        model = train_hybrid_gnn(graph, epochs=10, seed=42)
        pred = hybrid_predict_with_confidence(model, graph)
        for code in TASK_HEADS:
            self.assertIn("scores", pred[code])
            self.assertIn("std", pred[code])
            self.assertEqual(pred[code]["scores"].shape, (len(graph["node_ids"]),))
            self.assertTrue((pred[code]["std"] >= 0).all())
            self.assertTrue((pred[code]["scores"] >= 0).all())
            self.assertTrue((pred[code]["scores"] <= 1).all())

    def test_merged_graph_preserves_edge_count(self):
        g1 = _make_graph()
        g2 = _make_graph()
        merged = merge_graphs_v4([g1, g2])
        self.assertEqual(len(merged["node_ids"]), len(g1["node_ids"]) + len(g2["node_ids"]))
        self.assertEqual(merged["edge_index"].shape[1], g1["edge_index"].shape[1] + g2["edge_index"].shape[1])
        self.assertEqual(merged["edge_type"].shape[0], merged["edge_index"].shape[1])

    def test_rerank_with_zero_alpha_preserves_rule_order(self):
        class _Rec:
            def __init__(self, code, did, conf, extra=None):
                self.task_code = code
                self.device_id = did
                self.confidence = conf
                self.extra = extra or {}
        graph = _make_graph()
        model = train_hybrid_gnn(graph, epochs=5, seed=42)
        model.trained_task_codes.add("1.1")
        records = [
            _Rec("1.1", "A", 0.6),
            _Rec("1.1", "B", 0.9),
            _Rec("1.2", "C", 0.7),
        ]
        original = [(r.device_id, r.confidence) for r in records]
        reranked = rerank_rule_records_v4(model, graph, records, alpha_by_task={})
        new_order = [(r.device_id, r.extra["adjusted_confidence"]) for r in reranked]
        self.assertEqual([r.device_id for r in reranked], ["B", "C", "A"])
        for rec, (_, orig_conf) in zip(reranked, sorted(original, key=lambda x: -x[1])):
            self.assertAlmostEqual(rec.extra["adjusted_confidence"], orig_conf, places=3)

    def test_rerank_with_positive_alpha_uses_gnn(self):
        class _Rec:
            def __init__(self, code, did, conf, extra=None):
                self.task_code = code
                self.device_id = did
                self.confidence = conf
                self.extra = extra or {}
        graph = _make_graph()
        model = train_hybrid_gnn(graph, epochs=5, seed=42)
        model.trained_task_codes.add("1.1")
        records = [
            _Rec("1.1", "A", 0.5),
            _Rec("1.1", "B", 0.5),
        ]
        reranked = rerank_rule_records_v4(model, graph, records, alpha_by_task={"1.1": 0.5})
        for r in reranked:
            self.assertIn("gnn_anomaly_score", r.extra)
            self.assertIn("gnn_score_std", r.extra)
            self.assertAlmostEqual(
                r.extra["adjusted_confidence"],
                0.5 * 0.5 + 0.5 * r.extra["gnn_anomaly_score"],
                places=3,
            )

    def test_untrained_task_head_cannot_change_rule_score(self):
        class _Rec:
            def __init__(self):
                self.task_code = "1.1"
                self.device_id = "A"
                self.confidence = 0.8
                self.extra = {}
        graph = _make_graph()
        model = train_hybrid_gnn(graph, epochs=2, seed=42)
        record = rerank_rule_records_v4(
            model, graph, [_Rec()], alpha_by_task={"1.1": 0.9},
        )[0]
        self.assertEqual(record.extra["gnn_weight_applied"], 0.0)
        self.assertEqual(record.extra["adjusted_confidence"], 0.8)

    def test_supervised_sample_registers_trained_task(self):
        graph = _make_graph()
        model = train_hybrid_gnn(graph, epochs=2, seed=42)
        fine_tune_hybrid_gnn(
            model,
            [{
                "graph": graph,
                "task_code": "1.1",
                "truth_device_ids": ["A"],
                "ignore_device_ids": [],
            }],
            epochs=2,
            seed=42,
        )
        self.assertIn("1.1", model.trained_task_codes)
        self.assertEqual(model.training_summary["supervised_samples"], 1)

    def test_svg_only_node_is_encoded_explicitly(self):
        base = _make_graph()
        tables = {
            "JBS_PWEQUIPINFO": [{"EQUIP_ID": "A", "EQUIP_TYPE": "SWITCH"}],
            "JBS_PWTERMINAL": [],
            "JBS_ZWEQUIPINFO": [],
            "JBS_ZWTERMINAL": [],
        }
        graph = build_graph_from_14tables_v4(
            tables,
            options={
                "svg_devices": ["A", "SVG_ONLY"],
                "svg_devices_meta": {"SVG_ONLY": {"type": "SWITCH", "voltage": 10}},
            },
        )
        svg_index = graph["node_to_idx"]["SVG_ONLY"]
        self.assertEqual(graph["node_features"].shape[1], base["node_features"].shape[1])
        self.assertEqual(graph["node_features"][svg_index, 24], 0.0)
        self.assertEqual(graph["node_features"][svg_index, 25], 1.0)
        self.assertEqual(graph["node_features"][svg_index, 26], 1.0)

    def test_unknown_device_id_does_not_crash(self):
        class _Rec:
            def __init__(self):
                self.task_code = "1.1"
                self.device_id = "DOES_NOT_EXIST"
                self.confidence = 0.7
                self.extra = {}
        graph = _make_graph()
        model = train_hybrid_gnn(graph, epochs=2, seed=42)
        model.trained_task_codes.add("1.1")
        reranked = rerank_rule_records_v4(model, graph, [_Rec()], alpha_by_task={"1.1": 0.5})
        self.assertEqual(reranked[0].extra["gnn_weight_applied"], 0.0)


if __name__ == "__main__":
    unittest.main()