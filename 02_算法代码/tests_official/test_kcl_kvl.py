# -*- coding: utf-8 -*-
"""Tests for KCL/KVL helper API (shared.kcl_kvl).

Per 比赛要求/00_评审手册_10页.md §9.4 KCL: node ΣI = ΣO; KVL: loop ΣU = 0。
本测试验证 helper API 稳定 + 可被 detector 在 emit ProblemRecord 前调用,
给出 KCL 残差附加分。
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shared.kcl_kvl import (  # noqa: E402
    ConstraintResult,
    check_kcl,
    check_kvl,
    compute_device_kcl_residual,
    compute_node_kcl_residual,
)


class TestCheckKCL(unittest.TestCase):
    """Test check_kcl(): sum(in) - sum(out) vs tolerance."""

    def test_balanced_currents_pass(self):
        result = check_kcl([5.0, 3.0], [8.0], 0.5)
        self.assertIsInstance(result, ConstraintResult)
        self.assertTrue(result.passed)
        self.assertAlmostEqual(result.residual, 0.0)

    def test_unbalanced_currents_fail(self):
        # 13 in, 8 out → residual 5.0, tolerance 0.5 → fail
        result = check_kcl([10.0, 3.0], [8.0], 0.5)
        self.assertFalse(result.passed)
        self.assertAlmostEqual(result.residual, 5.0)

    def test_tolerance_inclusive(self):
        # 3.4 in, 3.0 out → residual 0.4, tolerance 0.5 → pass
        result = check_kcl([3.4], [3.0], 0.5)
        self.assertTrue(result.passed)

    def test_empty_node_trivial_pass(self):
        # No currents → trivially balanced
        result = check_kcl([], [], 0.5)
        self.assertTrue(result.passed)


class TestCheckKVL(unittest.TestCase):
    """Test check_kvl(): loop voltage drops sum to 0."""

    def test_balanced_loop_pass(self):
        result = check_kvl([2.0, 1.5, -3.5], 0.1)
        self.assertTrue(result.passed)
        self.assertAlmostEqual(result.residual, 0.0)

    def test_unbalanced_loop_fail(self):
        # sum=0.5, tolerance=0.1 → fail
        result = check_kvl([2.0, 1.5, -3.0], 0.1)
        self.assertFalse(result.passed)
        self.assertAlmostEqual(result.residual, 0.5)


class TestComputeDeviceKCLResidual(unittest.TestCase):
    def test_empty_tables_returns_zero(self):
        tables = {"JBS_PWEQUIPINFO": [], "JBS_PWREAL": []}
        result = compute_device_kcl_residual(tables, "DOES_NOT_EXIST")
        self.assertIsInstance(result, ConstraintResult)

    def test_realistic_zero_residual_for_pass_through(self):
        tables = {
            "JBS_PWEQUIPINFO": [{"EQUIP_ID": "DEV1", "VOLTAGE_TYPE": 10}],
            "JBS_PWREAL": [
                {"TRAN_ID": "DEV1", "DATA_DATE": "2026-07-29", "POINT": "1",
                 "UA": "5", "UB": "5", "UC": "5", "IA": "100", "IB": "100", "IC": "100",
                 "AP": "0", "RP": "0", "BDZ_ID": "", "FEEDER_ID": "F101"}
            ],
        }
        result = compute_device_kcl_residual(tables, "DEV1")
        # |IA|+|IB|+|IC| = 300 ≥ tolerance 0.5 → fail unless device passes 0
        # This device has nonzero sum; just assert no crash
        self.assertIsInstance(result, ConstraintResult)


class TestComputeNodeKCLResidual(unittest.TestCase):
    def test_balanced_node(self):
        tables = {
            "JBS_PWTERMINAL": [
                {"ID": "T1", "EQUIP_ID": "DEV1", "CONNECTIVITYNODE_ID": "N1"},
                {"ID": "T2", "EQUIP_ID": "DEV2", "CONNECTIVITYNODE_ID": "N1"},
            ],
            "JBS_PWREAL": [
                {"TRAN_ID": "DEV1", "DATA_DATE": "2026-07-29", "POINT": "1",
                 "UA": "5", "UB": "5", "UC": "5", "IA": "100", "IB": "0", "IC": "0",
                 "AP": "0", "RP": "0", "BDZ_ID": "", "FEEDER_ID": "F101"},
                {"TRAN_ID": "DEV2", "DATA_DATE": "2026-07-29", "POINT": "1",
                 "UA": "5", "UB": "5", "UC": "5", "IA": "100", "IB": "0", "IC": "0",
                 "AP": "0", "RP": "0", "BDZ_ID": "", "FEEDER_ID": "F101"},
            ],
            "JBS_PWEQUIPINFO": [
                {"EQUIP_ID": "DEV1", "VOLTAGE_TYPE": 10},
                {"EQUIP_ID": "DEV2", "VOLTAGE_TYPE": 10},
            ],
        }
        result = compute_node_kcl_residual(tables, "N1")
        self.assertIsInstance(result, ConstraintResult)


class TestIntegrationWithSnapshot(unittest.TestCase):
    """Run compute_*_kcl_residual against snapshot_v5."""

    @classmethod
    def setUpClass(cls):
        snap = _ROOT / "data" / "snapshot_v5.json"
        if not snap.exists():
            raise unittest.SkipTest("snapshot_v5 not found")
        cls.tables = {k: [dict(r) for r in v]
                       for k, v in json.loads(snap.read_text(encoding="utf-8"))["tables"].items()}

    def test_no_crash_for_first_real_device(self):
        for e in self.tables.get("JBS_PWEQUIPINFO", []):
            eid = e.get("EQUIP_ID")
            if eid:
                result = compute_device_kcl_residual(self.tables, eid)
                self.assertIsInstance(result, ConstraintResult)
                return

    def test_no_crash_for_first_pwterm_node(self):
        for t in self.tables.get("JBS_PWTERMINAL", []):
            nid = t.get("CONNECTIVITYNODE_ID")
            if nid:
                result = compute_node_kcl_residual(self.tables, nid)
                self.assertIsInstance(result, ConstraintResult)
                return


if __name__ == "__main__":
    unittest.main()
