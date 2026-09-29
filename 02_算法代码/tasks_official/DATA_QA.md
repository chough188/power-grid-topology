# CP-202606 数据送达后校验协议（DATA_QA）

> 本文件是数据落到 `data/snapshot.json` 后、12 detector 跑之前的**必经检查清单**。
> 目的是避免脏数据导致 detector 输出垃圾，进而拉低 JUDGE.md 评分。

## 1. 校验入口

```powershell
$env:PYTHONPATH = "E:\dianli\xiangmu\dianli\电力拓扑图修正\02_算法代码"
python -X utf8 -c "
import sys; sys.path.insert(0, r'E:\dianli\xiangmu\dianli\电力拓扑图修正\02_算法代码')
from data_loader.snapshot import load_json_snapshot
from data_loader.synthetic_gen import make_synthetic_dataset
ds = load_json_snapshot('data/snapshot.json')
ds.validate()
print('Schema check: OK')
print('Tables:', sorted(ds.tables.keys()))
print('Rows per table:')
for name in sorted(ds.tables.keys()):
    print(f'  {name}: {len(ds.tables[name])} rows')
"
```

期望：14 张表全在，无 `missing_tables` / `field_errors` 报错。

## 2. 必须通过的数据质量检查（11 项）

### 2.1 主键唯一性

```python
from collections import Counter
for table, key_field in [
    ("JBS_ZWSUBSTATION", "ST_ID"),
    ("JBS_ZWEQUIPINFO", "EQUIP_ID"),
    ("JBS_ZWTERMINAL", "ID"),
    ("JBS_PWFEEDERLINE", "LINE_ID"),
    ("JBS_PWROOM", "ROOM_ID"),
    ("JBS_PWEQUIPINFO", "EQUIP_ID"),
    ("JBS_PWTERMINAL", "ID"),
    ("JBS_PWREAL", "NUM"),  # 复合主键 NUM+TRAN_ID+DATA_DATE
    ("JBS_ZD_OBJECT", "OBJ_ID"),
    ("JBS_ZD_VOLTAGETYPE", "VOLTAGE_ID"),
    ("JBS_ZD_MEASTYPE", "CODE"),
]:
    rows = ds.tables.get(table, ())
    keys = [r.get(key_field) for r in rows]
    dup = [k for k, c in Counter(keys).items() if c > 1 and k]
    if dup:
        print(f'WARN {table}: 主键 {key_field} 重复: {dup[:5]}')
```

期望：除空值外，所有主键出现次数 = 1。

### 2.2 外键完整性

检查关键外键是否有悬挂引用：

```python
equip_ids = {r.get("EQUIP_ID") for r in ds.tables.get("JBS_PWEQUIPINFO", ()) + ds.tables.get("JBS_ZWEQUIPINFO", ())}
feeder_ids = {r.get("LINE_ID") for r in ds.tables.get("JBS_PWFEEDERLINE", ())}
sub_ids = {r.get("ST_ID") for r in ds.tables.get("JBS_ZWSUBSTATION", ())}
room_ids = {r.get("ROOM_ID") for r in ds.tables.get("JBS_PWROOM", ())}

# TERMINAL.EQUIP_ID 必须 ∈ equip_ids
dangling_term = [r.get("EQUIP_ID") for r in ds.tables.get("JBS_PWTERMINAL", ()) if r.get("EQUIP_ID") not in equip_ids]
print(f'PWTERMINAL.EQUIP_ID 悬挂引用: {len(dangling_term)}')

# PWEQUIPINFO.FEEDER_ID 必须 ∈ feeder_ids
dangling_fd = [r.get("FEEDER_ID") for r in ds.tables.get("JBS_PWEQUIPINFO", ()) if r.get("FEEDER_ID") and r.get("FEEDER_ID") not in feeder_ids]
print(f'PWEQUIPINFO.FEEDER_ID 悬挂引用: {len(dangling_fd)}')
```

期望：所有悬挂数 = 0。如有，需告知数据提供方清洗。

### 2.3 字段命名一致性

参见 [FIELD_MAPPING.md](./FIELD_MAPPING.md)。重点：

- `SUBSTATION_ID` 不应出现（应用 `ST_ID`）
- `TRAN_ID` 在 `JBS_ZWMEA` 中不应出现（应用 `ID`）

### 2.4 设备 ID 前缀

抽样 10 个 `EQUIP_ID`，确认前缀匹配预期：

```python
samples = [r.get("EQUIP_ID") for r in ds.tables.get("JBS_PWEQUIPINFO", ())[:10]]
print(samples)
# 期望：TMP/N/JP/Wp/TN/XF 前缀之一
```

### 2.5 EQUIP_TYPE 字典合法性

```python
valid_types = {r.get("OBJ_CODE") for r in ds.tables.get("JBS_ZD_OBJECT", ())}
equip_types = {r.get("EQUIP_TYPE") for r in ds.tables.get("JBS_PWEQUIPINFO", ()) + ds.tables.get("JBS_ZWEQUIPINFO", ())}
unknown = equip_types - valid_types - {None, ""}
print(f'未知 EQUIP_TYPE: {unknown}')
```

期望：`unknown == set()`。如有，需补 OBJ_CODE。

### 2.6 VOLTAGE_TYPE 字典合法性

类似 §2.5，对 `JBS_ZD_VOLTAGETYPE`。

### 2.7 RUN_STATUS 取值合法性

```python
rs_values = {r.get("RUN_STATUS") for r in ds.tables.get("JBS_PWEQUIPINFO", ()) + ds.tables.get("JBS_ZWEQUIPINFO", ())}
print(f'RUN_STATUS 取值: {rs_values}')
# 期望：{0, 1, None} 三种之一
```

### 2.8 CONNECTIVITYNODE 共享度

主配接口联通的基础：至少存在 1 个 `CONNECTIVITYNODE_ID` 同时出现在 `JBS_ZWTERMINAL` 和 `JBS_PWTERMINAL`：

```python
zw_nodes = {r.get("CONNECTIVITYNODE_ID") for r in ds.tables.get("JBS_ZWTERMINAL", ())}
pw_nodes = {r.get("CONNECTIVITYNODE_ID") for r in ds.tables.get("JBS_PWTERMINAL", ())}
shared = zw_nodes & pw_nodes
print(f'主配共享节点数: {len(shared)}')
# 期望：≥ 1
```

如为 0，任务 4.1 无意义，需先确认数据完整性。

### 2.9 量测配对率

```python
equip_ids = {r.get("EQUIP_ID") for r in ds.tables.get("JBS_PWEQUIPINFO", ()) + ds.tables.get("JBS_ZWEQUIPINFO", ())}
tran_ids = {r.get("TRAN_ID") for r in ds.tables.get("JBS_PWREAL", ()) + ds.tables.get("JBS_ZWMEA", ())}
unpaired = tran_ids - equip_ids - {None, ""}
print(f'未配对量测 TRAN_ID: {len(unpaired)}')
# 期望：占比 < 30%
```

如未配对比例 > 50%，任务 3.1 输出可能全空。

### 2.10 字段缺失率

```python
for table in REQUIRED_TABLES:
    rows = ds.tables.get(table, ())
    if not rows:
        continue
    total = len(rows) * len(rows[0])
    missing = sum(1 for r in rows for v in r.values() if v is None or v == "")
    rate = missing / total if total else 0
    if rate > 0.3:
        print(f'WARN {table}: 字段缺失率 {rate:.1%}')
```

期望：每张表缺失率 < 30%。

### 2.11 拓扑连通性 sanity

```python
from shared.graph_algos import adjacency_from_terminals, connected_components
adj = adjacency_from_terminals(ds.tables)
cc = connected_components(adj)
big = sum(1 for c in cc if len(c) >= 10)
small = sum(1 for c in cc if 1 <= len(c) < 10)
print(f'大连通分量 (≥10): {big}, 小孤立分量 (<10): {small}')
# 期望：大分量 ≥ 1，小孤立分量 < 大分量 / 5
```

如小孤立分量过多，可能是数据集本身就有大量拓扑问题（好事，detector 会出记录），也可能是数据缺失（坏事）。

## 3. 数据问题登记表

发现问题时记录到 `data/_data_issues.md`（新建）：

```markdown
# 数据问题登记

| 时间 | 检查项 | 严重度 | 问题描述 | 处理 |
|---|---|---|---|---|
| 2026-07-22 14:00 | §2.8 共享节点 | 高 | 主配共享节点 = 0 | 待数据方确认 |
| 2026-07-22 14:00 | §2.5 OBJ_CODE | 中 | "CABLE_HEAD" 不在字典中 | 已加白名单 |
```

## 4. 通过/拒绝标准

| 检查项 | 通过条件 |
|---|---|
| 1. 主键唯一性 | 全部唯一 |
| 2. 外键完整性 | 悬挂 ≤ 0.5% |
| 3. 字段命名 | 无 SUBSTATION_ID/TRAN_ID 误用 |
| 4. 设备 ID 前缀 | 至少 90% 匹配 TMP/N/JP/Wp/TN/XF |
| 5-6. 字典合法性 | 全部命中 |
| 7. RUN_STATUS | 只取 {0, 1, None} |
| 8. 主配共享节点 | ≥ 1 |
| 9. 量测配对率 | ≥ 50% |
| 10. 字段缺失率 | 每表 < 30% |
| 11. 拓扑连通性 | 大分量 ≥ 1 |

任意高严重度项不通过：**拒绝运行 detector**，先反馈数据提供方。

## 5. 数据快照保存规范

通过 §2 后，将快照保存为：

```
data/snapshot.json          # 当前活跃数据（每次跑覆盖前备份）
data/_history/snap_YYYYMMDD_HHMM.json  # 历史归档
```

历史归档便于回滚对比。

---

文档结束
