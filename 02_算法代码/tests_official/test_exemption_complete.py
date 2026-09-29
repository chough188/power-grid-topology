import unittest

from shared.exemption import (
    is_dangle_exempt,
    is_internal_tie_switch_exempt,
    is_loop_exempt,
    is_measurement_exempt,
    is_single_side_allowed,
    is_tie_switch_exempt,
    normalize_room_type,
)


class ExemptionRuleTests(unittest.TestCase):
    """Verify all 8 exemption rules from JUDGE.md are covered."""

    def test_rule1_room_excludes_internal_tie(self):
        self.assertTrue(is_internal_tie_switch_exempt('配电站', same_room=True))
        self.assertFalse(is_internal_tie_switch_exempt('配电站', same_room=False))

    def test_rule2_xf_excludes_internal_tie(self):
        self.assertTrue(is_internal_tie_switch_exempt('箱变', same_room=True))
        self.assertTrue(is_tie_switch_exempt({'EQUIP_NAME': 'XF001 箱变'}, same_room=False))

    def test_rule3_trans_not_dangle(self):
        self.assertTrue(is_dangle_exempt({'EQUIP_NAME': '用户配变', 'EQUIP_TYPE': 'TRANS'}))
        self.assertTrue(is_dangle_exempt({'OBJ_CODE': 'TRANS'}))
        self.assertTrue(is_dangle_exempt({'EQUIP_NAME': '客户变压器'}))

    def test_rule4_cable_head_not_dangle(self):
        self.assertTrue(is_dangle_exempt({'EQUIP_NAME': '电缆终端头', 'EQUIP_TYPE': 'CABLE_HEAD'}))

    def test_rule5_spare_not_dangle(self):
        self.assertTrue(is_dangle_exempt({'EQUIP_NAME': '备用间隔', 'EQUIP_TYPE': 'SPARE_BAY'}))

    def test_rule6_disconnector_single_side_allowed(self):
        self.assertTrue(is_single_side_allowed({'EQUIP_TYPE': 'DISCONNECTOR'}))
        self.assertFalse(is_single_side_allowed({'EQUIP_TYPE': 'SWITCH'}))
        self.assertFalse(is_single_side_allowed({'EQUIP_TYPE': 'BREAKER'}))
        self.assertTrue(is_single_side_allowed({'EQUIP_NAME': '隔离开关002'}))

    def test_rule7_loop_same_voltage_exempt(self):
        devs = [{'VOLTAGE_TYPE': 10}, {'VOLTAGE_TYPE': 10}]
        self.assertTrue(is_loop_exempt(devs))
        devs = [{'VOLTAGE_TYPE': 10}, {'VOLTAGE_TYPE': 35}]
        self.assertFalse(is_loop_exempt(devs))

    def test_rule8_unpaired_measurement_exempt(self):
        self.assertTrue(is_measurement_exempt({'TRAN_ID': ''}, {}))
        self.assertTrue(is_measurement_exempt({'TRAN_ID': None}, {}))
        self.assertTrue(is_measurement_exempt({'TRAN_ID': 'UNKNOWN'}, {'D1': {}}))
        self.assertFalse(is_measurement_exempt({'TRAN_ID': 'D1'}, {'D1': {}}))

    def test_normalize_room_type(self):
        self.assertEqual(normalize_room_type('  配电站  '), '配电站')
        self.assertEqual(normalize_room_type('配 电 站'), '配电站')

    def test_xf_prefix_detection(self):
        """Verify XF prefix triggers tie exemption."""
        self.assertTrue(is_tie_switch_exempt({'OBJ_CODE': 'XF'}, same_room=False))


if __name__ == '__main__':
    unittest.main()
