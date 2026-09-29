import unittest

from data_loader.synthetic_gen import make_empty_dataset
from shared.exemption import is_internal_tie_switch_exempt
from shared.id_prefix import ensure_temp_device_id, is_temp_device_id
from shared.kcl_kvl import check_kcl, check_kvl


class CommonContractTests(unittest.TestCase):
    def test_terminal_room_tie_switch_exemption(self):
        self.assertTrue(is_internal_tie_switch_exempt("配电站", same_room=True))
        self.assertTrue(is_internal_tie_switch_exempt("箱变", same_room=True))
        self.assertFalse(is_internal_tie_switch_exempt("配电站", same_room=False))

    def test_temp_device_prefix_is_tmp(self):
        self.assertEqual(ensure_temp_device_id("00034205"), "TMP00034205")
        self.assertTrue(is_temp_device_id("tmp00034205"))
        with self.assertRaises(ValueError):
            ensure_temp_device_id("")

    def test_kcl_and_kvl_residuals(self):
        self.assertTrue(check_kcl([10.0, 5.0], [14.95], tolerance=0.1).passed)
        self.assertTrue(check_kvl([10.0, -6.0, -4.0], tolerance=1e-9).passed)

    def test_empty_synthetic_dataset_satisfies_table_inventory(self):
        dataset = make_empty_dataset()
        self.assertEqual(dataset.missing_tables(), ())
        dataset.validate()


if __name__ == "__main__":
    unittest.main()
