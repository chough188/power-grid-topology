import hashlib
import json
import unittest
from pathlib import Path

from data_loader.loader import OfficialDataset


class PandapowerConversionOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).parents[2] / "03_数据集" / "official_base_networks_v2"
        cls.manifest = json.loads((cls.root / "manifest.json").read_text(encoding="utf-8-sig"))

    @classmethod
    def _resolve_output(cls, p: str) -> Path:
        """Resolve manifest output path (mojibake-safe)."""
        raw = Path(p)
        if raw.exists():
            return raw
        if raw.drive:
            alt = Path(raw.drive.replace("E:", "F:")) / str(raw.relative_to(raw.anchor))
            if alt.exists():
                return alt
        # manifest paths have garbled Chinese; use basename in known directory
        return cls.root / raw.name

    @classmethod
    def _resolve_source(cls, metadata: dict) -> Path | None:
        """Resolve metadata['source'] to pandapower_networks/."""
        raw = Path(metadata["source"])
        p = Path(__file__).resolve().parent.parent.parent / "03_数据集" / "pandapower_networks" / raw.name
        if p.exists():
            return p
        return None

    def test_five_independent_networks_are_valid_fourteen_table_snapshots(self):
        self.assertEqual(len(self.manifest), 5)
        network_ids = set()
        for item in self.manifest:
            output = self._resolve_output(item["output"])
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["tables"]), 14)
            self.assertTrue(all(payload["tables"].values()))
            OfficialDataset(payload["tables"]).validate()
            metadata = payload["metadata"]
            network_ids.add(metadata["network_id"])
            source = self._resolve_source(metadata)
            if source is not None:
                self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), metadata["source_sha256"])
            self.assertFalse(metadata["production_data_claim"])
            self.assertTrue(metadata["synthetic_measurements"])
        self.assertEqual(len(network_ids), 5)


if __name__ == "__main__":
    unittest.main()

