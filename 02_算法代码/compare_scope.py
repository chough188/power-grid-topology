"""Compare scope counts: feeder index vs original record filtering."""
import sys, json
sys.path.insert(0, ".")

from data_loader.loader import OfficialDataset
from tasks_official.contracts import TaskContext
from tasks_official.execution import OfficialRunner

with open("data/snapshot.json", "r", encoding="utf-8") as f:
    raw = json.load(f)

dataset = OfficialDataset(raw["tables"])
runner = OfficialRunner()
codes_pre = ["1.1","1.2","1.3","1.4","1.5","2.1","2.2","2.3","2.4","3.1","4.1","4.2"]
result = runner.run(codes_pre, dataset)
rbt = dict(result.records_by_task)

# Compare: feeder index vs original record filtering
from tasks_official.group_05_scoring.task_5_0_self_grade.detector import _station_feeder_pairs

pairs = _station_feeder_pairs(dataset.normalized().tables)

print("Comparing scope counts for each feeder:")
for st_id, st_name, line_id, line_name in pairs:
    # Original: record filtering (station="" means skip station check)
    orig_counts = {}
    for code, recs in rbt.items():
        filtered = [
            r for r in recs
            if (not st_id or str(r.station_id or "") == str(st_id))
            and (not line_id or str(r.feeder_id or "") == str(line_id))
        ]
        orig_counts[code] = len(filtered)
    
    # New: feeder index
    feeder_idx = {}
    for code, recs in rbt.items():
        for r in recs:
            fd = str(r.feeder_id or "")
            feeder_idx.setdefault(fd, {}).setdefault(code, 0)
            feeder_idx[fd][code] += 1
    
    new_counts = feeder_idx.get(str(line_id), {})
    
    # Compare
    all_codes = set(orig_counts.keys()) | set(new_counts.keys())
    diffs = {c: (orig_counts.get(c, 0), new_counts.get(c, 0)) for c in all_codes if orig_counts.get(c, 0) != new_counts.get(c, 0)}
    
    status = "MATCH" if not diffs else f"DIFF: {diffs}"
    print(f"  {line_id} ({line_name}): {status}")
    if diffs:
        print(f"    orig: {orig_counts}")
        print(f"    new:  {new_counts}")
