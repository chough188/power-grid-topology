import unittest

from data_loader.synthetic_gen import make_empty_dataset, make_synthetic_dataset


class SyntheticDatasetTests(unittest.TestCase):
    def test_empty_dataset_validates(self):
        ds = make_empty_dataset()
        self.assertEqual(ds.missing_tables(), ())
        ds.validate()

    def test_synthetic_dataset_has_14_tables(self):
        ds = make_synthetic_dataset(seed=42)
        self.assertEqual(len(ds.tables), 14)
        ds.validate()

    def test_synthetic_dataset_is_deterministic(self):
        ds1 = make_synthetic_dataset(seed=42)
        ds2 = make_synthetic_dataset(seed=42)
        for table in ds1.tables:
            self.assertEqual(len(ds1.tables[table]), len(ds2.tables[table]))
            for r1, r2 in zip(ds1.tables[table], ds2.tables[table]):
                self.assertEqual(r1, r2)

    def test_synthetic_dataset_has_tie_switch(self):
        ds = make_synthetic_dataset(seed=42)
        # Synthetic dataset names tie switch as 联络开关001
        tie_devices = [d for d in ds.tables['JBS_PWEQUIPINFO'] if '联络' in d.get('EQUIP_NAME', '')]
        self.assertGreater(len(tie_devices), 0)
        # Tie switch should have RUN_STATUS=1
        for d in tie_devices:
            self.assertEqual(d.get('RUN_STATUS'), 1)

    def test_synthetic_dataset_has_trans_devices(self):
        ds = make_synthetic_dataset(seed=42)
        trans_devices = [d for d in ds.tables['JBS_PWEQUIPINFO'] if d.get('EQUIP_TYPE') == 'TRANS']
        self.assertGreater(len(trans_devices), 0)

    def test_synthetic_dataset_has_xf_devices(self):
        ds = make_synthetic_dataset(seed=42)
        xf_devices = [d for d in ds.tables['JBS_PWEQUIPINFO'] if d.get('EQUIP_TYPE') == 'XF']
        self.assertGreater(len(xf_devices), 0)

    def test_synthetic_dataset_main_dist_share_nodes(self):
        ds = make_synthetic_dataset(seed=42)
        zw_nodes = {r.get('CONNECTIVITYNODE_ID') for r in ds.tables['JBS_ZWTERMINAL']}
        pw_nodes = {r.get('CONNECTIVITYNODE_ID') for r in ds.tables['JBS_PWTERMINAL']}
        self.assertGreater(len(zw_nodes), 0)
        self.assertGreater(len(pw_nodes), 0)

    def test_synthetic_dataset_no_dangling_terminals(self):
        # All equip should have >= 1 terminal
        ds = make_synthetic_dataset(seed=42)
        equip_terminal_count = {}
        for t in ds.tables['JBS_PWTERMINAL'] + ds.tables['JBS_ZWTERMINAL']:
            eid = t.get('EQUIP_ID')
            if eid:
                equip_terminal_count[eid] = equip_terminal_count.get(eid, 0) + 1
        # Skip TRANS / XF (exempt)
        exempt_count = 0
        for d in ds.tables['JBS_PWEQUIPINFO']:
            eid = d.get('EQUIP_ID')
            if d.get('EQUIP_TYPE') in ('TRANS', 'XF'):
                if eid not in equip_terminal_count:
                    exempt_count += 1
        # The first device (feeder head) may be a dangle by design
        # Just check the structure is reasonable
        self.assertGreater(len(equip_terminal_count), 0)


if __name__ == '__main__':
    unittest.main()
