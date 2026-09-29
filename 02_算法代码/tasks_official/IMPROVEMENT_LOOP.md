# CP-202606 自评驱动的迭代手册

> 本文件是 **本地大模型根据 `self_grade.py` 输出，反向优化 detector** 的闭环指南。
> 适用场景：自评分数低于预期（如 < 0.80），需要针对性提升。

## 1. 闭环流程

```
[数据送达] → [DATA_QA] → [跑 12 detector] → [self_grade 打分]
                                              ↓ (若 < 0.85)
                                       [查看明细]
                                              ↓
                                       [定位丢分子项]
                                              ↓
                                       [针对性补 detector]
                                              ↓
                                       [重跑 self_grade] → ...
```

每一轮迭代建议 ≤ 2 小时专注一个子项。

## 2. 子项得分解读

| 明细 | 丢分原因排查顺序 |
|---|---|
| 任务覆盖 < 12/12 | 1) 该 detector 是否实现？2) `return ()`？3) 数据集中无对应异常？ |
| 豁免 < 8/8 | grep detector 代码，看是否调用 `shared.exemption` 8 个函数 |
| SQL 可执行 < 1.0 | 1) `correction_sql=""`？2) 字段名写错？3) SQL 语法错？ |
| 关键 < 4/4 | 1.1/1.3/3.1/4.1 任一 task 0 输出 |

## 3. 迭代模式一：从 0 → 0.5（最低门槛）

目标：12 detector 都有 ≥ 1 条输出。

具体动作：

1. 跑 `self_grade.py` 看哪几个任务输出 = 0。
2. 对 0 输出任务，按 [DETECTOR_PATTERNS.md](./DETECTOR_PATTERNS.md) 对应章节填实骨架。
3. 每填一个，跑一次 `self_grade.py`。
4. 目标 = 12/12 任务覆盖 + 至少 4/4 关键任务命中。

最低分（12 任务覆盖 + 4 关键 + 0 SQL + 0 豁免）= 0.40 + 0.20 + 0 + 0 = 0.60，刚好"中"。

## 4. 迭代模式二：0.5 → 0.8（良）

目标：补 SQL 字段 + 4-6 条豁免规则。

具体动作：

1. 对每个 detector，从 `shared.sql_emitter` 选对应模板填入 `correction_sql`：
   - 1.1: `insert_pw_terminal` / `insert_zw_terminal`
   - 1.3: `mark_tie_pw` / `mark_tie_zw`
   - 1.5: `set_run_status_pw` / `set_run_status_zw`
   - 3.1: `set_run_status_pw` / `set_run_status_zw`
   - 4.1: `insert_zw_terminal_for_interface`
   - 4.2: `update_zw_terminal_node`
   - 2.1: `insert_pw_equip`
   - 2.3: `insert_pw_terminal`
   - 2.4: `delete_pw_terminal`
2. 验证 SQL 可执行（跑 `parse_sql`）：
   ```python
   from tasks_official.self_grade import parse_sql
   for sql in [r.correction_sql for r in records if r.correction_sql]:
       assert parse_sql(sql), sql
   ```
3. 调用 `shared.exemption` 8 个函数（至少 6 个）落实豁免规则。

目标分（12 + 6 豁免 + 80% SQL + 4 关键）= 0.40 + 0.15 + 0.16 + 0.20 = 0.91。

## 5. 迭代模式三：0.8 → 1.0（优）

目标：SQL 100% + 豁免 8/8 + 任务覆盖 12/12 + 关键 4/4。

具体动作：

1. **SQL 100%**：每个 detector 都填 `correction_sql`，无空串、无语法错。
2. **豁免 8/8**：每个 detector 都正确调用对应 exemption 函数。
3. **任务覆盖 12/12**：所有 detector 都至少 1 条输出（即使是占位 review）。
4. **关键 4/4**：1.1/1.3/3.1/4.1 都有实际检出记录。

目标分 = 0.40 + 0.20 + 0.20 + 0.20 = 1.00。

## 6. 调试技巧

### 6.1 找具体哪个任务 0 输出

```python
import sys; sys.path.insert(0, r'E:\dianli\xiangmu\dianli\电力拓扑图修正\02_算法代码')
from data_loader.snapshot import load_json_snapshot
from tasks_official.execution import OfficialRunner
ds = load_json_snapshot('data/snapshot.json')
result = OfficialRunner().run(['1.1','1.2','1.3','1.4','1.5','2.1','2.2','2.3','2.4','3.1','4.1','4.2'], ds)
for code, recs in result.records_by_task.items():
    print(f'{code}: {len(recs)} records')
```

### 6.2 看 SQL 字段都是什么

```python
import sys; sys.path.insert(0, r'E:\dianli\xiangmu\dianli\电力拓扑图修正\02_算法代码')
from data_loader.snapshot import load_json_snapshot
from tasks_official.execution import OfficialRunner
ds = load_json_snapshot('data/snapshot.json')
result = OfficialRunner().run(['1.1','1.3','3.1','4.1'], ds)
all_records = [r for recs in result.records_by_task.values() for r in recs]
print(f'total records: {len(all_records)}')
for r in all_records:
    print(f'  {r.task_code} {r.device_id}: SQL={"YES" if r.correction_sql else "EMPTY"}')
```

### 6.3 跑 shape validator 看 SQL

```python
from tasks_official.self_grade import parse_sql
bad = [(r.task_code, r.device_id, r.correction_sql) for r in all_records if r.correction_sql and not parse_sql(r.correction_sql)]
print(f'SQL syntax failures: {len(bad)}')
for code, eid, sql in bad[:5]:
    print(f'  {code} {eid}: {sql[:80]}...')
```

## 7. 常见瓶颈与对策

| 瓶颈 | 现象 | 对策 |
|---|---|---|
| 数据集本身极小 | 12/12 全 0 输出 | 与数据方确认规模；用 `make_synthetic_dataset()` 验证 detector 本身能产出 |
| 字段名写错 | detector 0 输出 | 参考 [FIELD_MAPPING.md](./FIELD_MAPPING.md) |
| 主配共享节点 = 0 | 4.1/4.2 无输出 | 检查 §2.8 主配联通性 |
| 量测未配对 | 3.1 无输出 | 检查 §2.9 配对率 |
| 设备 ID 全是 TRANS | 1.1/1.2/2.x 大量豁免 | 实际数据可能确实只有配变，需看是否需要放宽 |

## 8. 评分提升检查表（提交前过一遍）

- [ ] 12 detector 都有 ≥ 1 条输出（任务覆盖 12/12）
- [ ] 1.1 / 1.3 / 3.1 / 4.1 都有输出（关键 4/4）
- [ ] 所有 detector 的 `correction_sql` 非空（SQL ≥ 90%）
- [ ] 至少 6 个 detector 调用了 `shared.exemption` 函数（豁免 ≥ 6/8）
- [ ] 每个 record 都有 ≥ 1 个 `EvidenceItem`（评审可复核）
- [ ] 跑过 `tests_official/`（隔离门禁 + 契约）
- [ ] 跑过 `output_writer.writer` 生成 6 Sheet xlsx
- [ ] 跑过 `self_grade.py` 拿到 ≥ 0.85 总分
- [ ] 数据通过 [DATA_QA.md](./DATA_QA.md) 11 项校验

---

文档结束
