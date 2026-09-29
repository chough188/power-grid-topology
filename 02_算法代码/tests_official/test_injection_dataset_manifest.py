import hashlib
import json
import unittest
from pathlib import Path


class InjectionDatasetManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).parents[2] / "03_数据集" / "official_injection_v4"
        cls.manifest = json.loads((cls.root / "manifest.json").read_text(encoding="utf-8-sig"))

    def _resolve(self, raw: str) -> Path:
        p = Path(raw)
        return self.root / p.name if not p.exists() else p

    def test_valid_samples_have_matching_hashes_and_group_ids(self):
        valid = [sample for sample in self.manifest["samples"] if sample.get("status") == "ok"]
        self.assertGreaterEqual(len(valid), 50)
        for sample in valid:
            path = self._resolve(sample["path"])
            self.assertTrue(path.is_file())
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), sample["sha256"])
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["metadata"]["network_id"], sample["network_id"])
            self.assertEqual(payload["metadata"]["split_group"], sample["network_id"])
            self.assertEqual(payload["label"]["task_code"], sample["task_code"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), sample["sha256"])
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["metadata"]["network_id"], sample["network_id"])
            self.assertEqual(payload["metadata"]["split_group"], sample["network_id"])
            self.assertEqual(payload["label"]["task_code"], sample["task_code"])

    def test_manifest_requires_network_level_split(self):
        self.assertIn("same network_id", self.manifest["leakage_rule"])
        self.assertIn("counterfactual", self.manifest["quality_gate"])

    def test_no_invalid_counterfactual_is_scored(self):
        invalid = [sample for sample in self.manifest["samples"] if sample.get("status") == "invalid_counterfactual"]
        self.assertGreater(len(invalid), 0)
        self.assertTrue(all("metrics" not in sample for sample in invalid))


if __name__ == "__main__":
    unittest.main()
