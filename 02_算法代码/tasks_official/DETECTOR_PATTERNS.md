# CP-202606 12 子任务 Detector 实施模式手册

> 本文件是 **本地大模型实现 detector 时的"算法 + 模板 + 边界"三合一参考**。
> 每一节对应 `tasks_official/catalog.py` 的一个 `TaskSpec`。
> 算法伪代码参考 `比赛要求/00_12个二级分类算法伪代码.md`。
> 测试用例参考 `比赛要求/00_12子任务单元测试清单.md`。

---

## 通用前置

每个 detector 都必须：

1. 仅依赖 `shared/`、`tasks_official/contracts.py`、`tasks_official/registry.py`。
2. 函数签名固定为 `detect(ctx: TaskContext) -> Sequence[ProblemRecord]`。
3. 在产出 `ProblemRecord` 前应用 `shared.exemption` 过滤器（详见每节）。
4. `correction_sql` 字段必须填非空字符串（占位用 `-- TODO` 也算违规，详见 JUDGE.md）。
5. `evidence` 至少包含 1 个 `EvidenceItem`，字段名 + observed 值取自原始表行。
6. 任何 `detect()` 抛异常会被 `OfficialRunner.run()` 捕获并整体拒绝执行，**不允许裸 except 吞错**。

---

## 任务 1.1 — 设备拓扑悬空检测（dangle）

### 算法核心

1. 合并 `JBS_PWTERMINAL` + `JBS_ZWTERMINAL`，统计每个 `EQUIP_ID` 的 `CONNECTIVITYNODE_ID` 集合大小。
2. 大小 ≤ 1 视为悬空。
3. 排除豁免：`shared.exemption.is_dangle_exempt(device_row)`。
4. 隔离开关单独处理：`shared.exemption.is_single_side_allowed(device_row)` 为 True 时**仅**豁免单端连接（不是豁免悬空本身）。

### 关键边界

| 边界 | 处理 |
|---|---|
| 设备没有任何 TERMINAL 行 | 视为悬空（集合大小 = 0） |
| 设备有 TERMINAL 但 `CONNECTIVITYNODE_ID` 为空串 | 不计入节点 |
| 同 `EQUIP_ID` 出现多次（如多个 ID 后缀） | 去重后再判断 |
| 主网设备（无 FEEDER_ID） | 仍要走豁免表，只是 `feeder_id` 字段留空 |
| `COMPOSITESWITCH` 非空 | 表示被组合开关吸收，不算独立悬空（额外判断） |

### 模板

```python
from shared.exemption import is_dangle_exempt, is_single_side_allowed
from shared.sql_emitter import insert_pw_terminal, insert_zw_terminal
from shared.graph_algos import adjacency_from_terminals
from tasks_official.evidence import EvidenceCollector

def detect(ctx):
    tables = ctx.tables
    equip_nodes = {}
    for t in tables.get("JBS_PWTERMINAL", ()) + tables.get("JBS_ZWTERMINAL", ()):
        eid = t.get("EQUIP_ID"); nid = t.get("CONNECTIVITYNODE_ID")
        if eid and nid:
            equip_nodes.setdefault(eid, set()).add(nid)
    for dev in tables.get("JBS_PWEQUIPINFO", ()) + tables.get("JBS_ZWEQUIPINFO", ()):
        if is_dangle_exempt(dev):
            continue
        eid = dev.get("EQUIP_ID")
        nodes = equip_nodes.get(eid, set())
        if len(nodes) > 1:
            continue
        if len(nodes) == 1 and is_single_side_allowed(dev):
            continue  # 隔离开关允许单端
        ev = EvidenceCollector("JBS_PWEQUIPINFO")
        ev.observe("EQUIP_ID", eid, record_id=eid)
        ev.observe("EQUIP_NAME", dev.get("EQUIP_NAME"))
        ev.observe("CONNECTIVITYNODE_COUNT", len(nodes))
        sql = insert_pw_terminal(eid, ":new_node_id") if dev.get("FEEDER_ID") else insert_zw_terminal(eid, ":new_node_id")
        yield ProblemRecord(
            task_code="1.1", device_id=eid, device_name=dev.get("EQUIP_NAME",""),
            feeder_id=dev.get("FEEDER_ID",""), station_id=dev.get("DSUBSTATION_ID","") or dev.get("ST_ID",""),
            description=f"设备 {dev.get('EQUIP_NAME', eid)} 仅 {len(nodes)} 个连通节点，需补足",
            correction="新增 CONNECTIVITYNODE 端子",
            correction_sql=sql, severity="critical", confidence=0.85, evidence=ev.finalize(),
        )
```

### 必杀测试样例

- `TMP00013138` → `TMP00047197` 路径上某设备单端悬空（来自必杀题 1.1）
- `XF*` 开头设备必须豁免
- 含 `TRANS` / `用户` / `配变` / `CUSTOMER` 设备必须豁免

---

## 任务 1.2 — 拓扑连通性异常诊断与断点定位

### 算法核心

1. `shared.graph_algos.adjacency_from_terminals(tables)` 得到 `CONNECTIVITYNODE` 邻接图。
2. `connected_components(adj)` 拿到所有连通分量。
3. 遍历每一对"应该连通"（同馈线、同变电站、同电压等级）的设备，若分属不同 CC，输出断点记录。

### 关键边界

| 边界 | 处理 |
|---|---|
| 应连通的判断依据 | 同 `FEEDER_ID` + 同 `VOLTAGE_TYPE`（不要用 EQUIP_ID 前缀猜） |
| 应连 vs 实际断 | 输出**本侧**（你这一半）和**对侧**（另一半）的设备 ID+名称 |
| 孤立单点 | 单设备孤立也算断点 |
| 主配接口断 | 主配间无共享节点时，单独标记 `task_code="4.1"`，不要混入 1.2 |

### 模板

```python
from shared.graph_algos import adjacency_from_terminals, connected_components, shortest_path
from shared.sql_emitter import insert_pw_terminal, multi_step
from tasks_official.evidence import EvidenceCollector

def detect(ctx):
    tables = ctx.tables
    adj = adjacency_from_terminals(tables)
    cc_list = connected_components(adj)
    equip_node_pairs = {}  # EQUIP_ID -> set of CONNECTIVITYNODE
    for t in tables.get("JBS_PWTERMINAL", ()) + tables.get("JBS_ZWTERMINAL", ()):
        eid = t.get("EQUIP_ID"); nid = t.get("CONNECTIVITYNODE_ID")
        if eid and nid:
            equip_node_pairs.setdefault(eid, set()).add(nid)
    equip_lookup = {d.get("EQUIP_ID"): d for d in tables.get("JBS_PWEQUIPINFO", ())}
    equip_lookup.update({d.get("EQUIP_ID"): d for d in tables.get("JBS_ZWEQUIPINFO", ())})
    seen_pairs = set()
    for dev in tables.get("JBS_PWEQUIPINFO", ()) + tables.get("JBS_ZWEQUIPINFO", ()):
        eid = dev.get("EQUIP_ID")
        feeder = dev.get("FEEDER_ID"); voltage = dev.get("VOLTAGE_TYPE")
        if not (eid and feeder): continue
        nodes = equip_node_pairs.get(eid, set())
        if not nodes: continue
        start_node = next(iter(nodes))
        # find sibling devices on same feeder+voltage but in different CC
        for other in tables.get("JBS_PWEQUIPINFO", ()):
            if other is dev: continue
            if other.get("FEEDER_ID") != feeder or other.get("VOLTAGE_TYPE") != voltage: continue
            other_nodes = equip_node_pairs.get(other.get("EQUIP_ID"), set())
            if not other_nodes: continue
            other_node = next(iter(other_nodes))
            if (eid, other.get("EQUIP_ID")) in seen_pairs or (other.get("EQUIP_ID"), eid) in seen_pairs: continue
            if not shortest_path(adj, start_node, other_node):
                seen_pairs.add((eid, other.get("EQUIP_ID")))
                ev = EvidenceCollector("JBS_PWEQUIPINFO")
                ev.observe("FEEDER_ID", feeder); ev.observe("VOLTAGE_TYPE", voltage)
                yield ProblemRecord(
                    task_code="1.2", device_id=eid, device_name=dev.get("EQUIP_NAME",""),
                    feeder_id=feeder, station_id=dev.get("DSUBSTATION_ID","") or dev.get("ST_ID",""),
                    description=f"与 {other.get('EQUIP_ID')} 不连通（应在同馈线 {feeder}）",
                    correction=f"在 {other.get('EQUIP_ID')} 端补 CONNECTIVITYNODE 共享 {start_node}",
                    correction_sql=insert_pw_terminal(other.get("EQUIP_ID"), start_node),
                    severity="high", confidence=0.8, evidence=ev.finalize(),
                    extra={"peer_device_id": other.get("EQUIP_ID")},
                )
```

---

## 任务 1.3 — 联络开关自动识别

### 算法核心

1. 取 `JBS_ZWEQUIPINFO` + `JBS_PWEQUIPINFO` 中 `EQUIP_TYPE in {"BREAKER","SWITCH","DISCONNECTOR"}` 且 `RUN_STATUS==1`（合位）。
2. 用 `CONNECTIVITYNODE` 邻接图扩散，得到该开关能到达的**变电站集合**。
3. 若 ≥ 2 个不同变电站，则为**联络开关**，标 `EQUIP_TYPE='TIE'`。
4. 排除站内开关：`shared.exemption.is_tie_switch_exempt(device_row, same_room=True)`。

### 关键边界

| 边界 | 处理 |
|---|---|
| 配电站 / 箱变内开关 | 必须豁免 |
| 一侧合位一侧分位 | 不是联络 |
| 同一变电站内不同母线 | 不是联络（即使物理上分属母线） |
| 隔离开关做联络 | 数据规范允许，但置信度降 0.1 |
| 同馈线内两台开关跨母线 | 通常不算联络（除非分属不同 STATION） |

### 模板

```python
from shared.graph_algos import adjacency_from_terminals, connected_components
from shared.exemption import is_tie_switch_exempt
from shared.sql_emitter import mark_tie_pw, mark_tie_zw

def detect(ctx):
    tables = ctx.tables
    adj = adjacency_from_terminals(tables)
    # station per node
    equip_station = {}
    for d in tables.get("JBS_ZWEQUIPINFO", ()) + tables.get("JBS_PWEQUIPINFO", ()):
        eid = d.get("EQUIP_ID"); st = d.get("ST_ID") or d.get("DSUBSTATION_ID") or d.get("SUBSTATION_ID")
        if eid and st:
            equip_station[eid] = st
    node_stations = {}
    for t in tables.get("JBS_PWTERMINAL", ()) + tables.get("JBS_ZWTERMINAL", ()):
        nid = t.get("CONNECTIVITYNODE_ID"); eid = t.get("EQUIP_ID")
        st = equip_station.get(eid)
        if nid and st:
            node_stations.setdefault(nid, set()).add(st)
    for dev in tables.get("JBS_ZWEQUIPINFO", ()) + tables.get("JBS_PWEQUIPINFO", ()):
        if dev.get("EQUIP_TYPE") not in ("BREAKER", "SWITCH", "DISCONNECTOR"): continue
        if dev.get("RUN_STATUS") != 1: continue
        eid = dev.get("EQUIP_ID")
        same_room = bool(dev.get("DSUBSTATION_ID"))
        if is_tie_switch_exempt(dev, same_room): continue
        my_nodes = [t.get("CONNECTIVITYNODE_ID") for t in tables.get("JBS_PWTERMINAL",())+tables.get("JBS_ZWTERMINAL",()) if t.get("EQUIP_ID")==eid and t.get("CONNECTIVITYNODE_ID")]
        subs = set()
        for n in my_nodes:
            subs |= node_stations.get(n, set())
        if len(subs) >= 2:
            sql = mark_tie_pw(eid) if dev.get("FEEDER_ID") else mark_tie_zw(eid)
            yield ProblemRecord(
                task_code="1.3", device_id=eid, device_name=dev.get("EQUIP_NAME",""),
                description=f"跨越 {len(subs)} 个变电站：{sorted(subs)}",
                correction="标记 EQUIP_TYPE='TIE'", correction_sql=sql,
                severity="medium", confidence=0.9, evidence=EvidenceCollector("JBS_PWEQUIPINFO").observe("EQUIP_TYPE","TIE",expected="SWITCH").finalize(),
                extra={"stations": sorted(subs)},
            )
```

---

## 任务 1.4 — 疑似联络开关智能识别与复核

### 算法核心

与 1.3 同骨架，但放宽判定条件：

- 隔离开关也算（置信度降 0.15）
- `RUN_STATUS` 缺失（None）也参与判定
- 仅 2 个端子**不严格**连到不同变电站，但邻接图经过 2 跳可达不同变电站 → 标记为"疑似"

### 关键边界

| 边界 | 处理 |
|---|---|
| `correction_sql` | **留空**（仅供复核） |
| 输出 | 比 1.3 多 1 个 `extra["confidence_reason"]` 字段说明依据 |
| 不要重复标 TIE | 与 1.3 同时跑时，用 `device_id` 去重 |

### 模板片段

```python
# 与 1.3 同框架，但：
sql = ""  # 仅标记，不修改
confidence = max(0.5, 0.85 - 0.15)
yield ProblemRecord(
    task_code="1.4", ..., correction_sql=sql, confidence=confidence,
    extra={"confidence_reason": "隔离开关 + RUN_STATUS 缺失 + 2 跳邻接"}
)
```

---

## 任务 1.5 — 非计划合环识别

### 算法核心

1. 用 `find_cycles(adj)` 找出所有简单环。
2. 对每个环，收集涉及的设备 → 馈线 → 变电站集合。
3. 若环涉及 ≥ 2 个不同馈线**且**不都是"正常并列运行"，标为非计划合环。
4. 应用 `shared.exemption.is_loop_exempt(candidate_devices)`：所有设备同一 `VOLTAGE_TYPE` → 豁免。

### 关键边界

| 边界 | 处理 |
|---|---|
| 同一馈线内的小环 | 通常是分段联络，正常 |
| 不同馈线跨同一变电站 | 正常并列运行，不算违规 |
| 不同馈线跨不同变电站 + 不同电压等级 | 几乎一定是违规 |
| 修正 SQL | 断开 RUN_STATUS=1 的某开关：`shared.sql_emitter.set_run_status_pw(device_id, 0)` |
| 选哪一台断开 | 选 RUN_STATUS=1 且置信度最低的那台 |

### 模板

```python
from shared.graph_algos import find_cycles, adjacency_from_terminals
from shared.exemption import is_loop_exempt
from shared.sql_emitter import set_run_status_pw, set_run_status_zw

def detect(ctx):
    tables = ctx.tables
    adj = adjacency_from_terminals(tables)
    cycles = find_cycles(adj, max_cycles=50)
    equip_lookup = {d.get("EQUIP_ID"): d for d in tables.get("JBS_PWEQUIPINFO",())}
    equip_lookup.update({d.get("EQUIP_ID"): d for d in tables.get("JBS_ZWEQUIPINFO",())})    
    for cycle in cycles:
        involved_devices = set()
        for node in cycle:
            for t in tables.get("JBS_PWTERMINAL",())+tables.get("JBS_ZWTERMINAL",()):
                if t.get("CONNECTIVITYNODE_ID") == node:
                    if t.get("EQUIP_ID"): involved_devices.add(t["EQUIP_ID"])
        dev_rows = [equip_lookup[d] for d in involved_devices if d in equip_lookup]
        if is_loop_exempt(dev_rows): continue
        feeders = {d.get("FEEDER_ID") for d in dev_rows if d.get("FEEDER_ID")}
        if len(feeders) < 2: continue
        # Pick the switch to open (lowest confidence)
        candidate = next((d for d in dev_rows if d.get("RUN_STATUS")==1), None)
        if not candidate: continue
        eid = candidate["EQUIP_ID"]
        sql = set_run_status_pw(eid, 0) if candidate.get("FEEDER_ID") else set_run_status_zw(eid, 0)
        yield ProblemRecord(
            task_code="1.5", device_id=eid, device_name=candidate.get("EQUIP_NAME",""),
            feeder_id=candidate.get("FEEDER_ID",""),
            description=f"非计划合环涉及 {len(feeders)} 个馈线: {sorted(feeders)}",
            correction=f"断开 {eid}", correction_sql=sql,
            severity="high", confidence=0.75, evidence=EvidenceCollector("JBS_PWEQUIPINFO").observe("RUN_STATUS",0,expected=1).finalize(),
            extra={"cycle_nodes": list(cycle), "feeders": sorted(feeders)},
        )
```

---

## 任务 2.1 — 仅图形无模型（SVG-only）

### 算法核心

1. 解析 SVG（外部数据），提取 `device_id` 集合。
2. 减去 `JBS_PWEQUIPINFO + JBS_ZWEQUIPINFO.EQUIP_ID` 集合 = 缺失集合。
3. 每个缺失设备产出一条记录 + INSERT SQL。

### 关键边界

| 边界 | 处理 |
|---|---|
| SVG 解析失败 | `detect()` 抛异常被 runner 整体拒绝（不要静默） |
| 设备已在模型中但字段缺失 | 不算 2.1（这属于数据完整性，不是图模一致性） |
| 同一 `EQUIP_ID` 多图层 | 去重 |
| 修正 SQL | `shared.sql_emitter.insert_pw_equip(...)` |

---

## 任务 2.2 — 仅模型无图形

### 算法核心

1. `JBS_PWEQUIPINFO + JBS_ZWEQUIPINFO.EQUIP_ID` 减去 SVG 集合 = 仅模型设备。
2. `correction_sql` 留空（不动数据库）。
3. `description` 写明"需补 SVG 图元"，`extra["svg_layer"]` 记录应放图层。

### 模板片段

```python
sql = ""  # 不动数据库
yield ProblemRecord(
    task_code="2.2", ..., correction_sql=sql,
    description=f"模型 {eid} 缺 SVG 图元，建议在 {layer} 图层补",
    extra={"svg_layer": "10kV馈线层" if voltage==10 else "35kV层"}
)
```

---

## 任务 2.3 — 物理连 / 逻辑断

### 算法核心

1. 取 `RUN_STATUS==1` 的开关集合。
2. 对每个开关，看其 `CONNECTIVITYNODE` 是否真在图中连通。
3. 不连通 → 物理连但逻辑断 → 补端子让图连通。

### 关键边界

| 边界 | 处理 |
|---|---|
| `RUN_STATUS` 缺失 | 视为分位，跳过 |
| 仅 1 个 `CONNECTIVITYNODE` 的开关 | 这是 1.1 的事，不要混入 2.3 |
| 修正 SQL | `shared.sql_emitter.insert_pw_terminal(...)` |

---

## 任务 2.4 — 物理断 / 逻辑连

### 算法核心

1. 取 `RUN_STATUS==0` 的开关集合。
2. 看其端子是否真在邻接图上连通。
3. 连通 → 物理断但逻辑连 → 删多余端子。

### 关键边界

| 边界 | 处理 |
|---|---|
| 哪些端子是"多余"的 | 删除后图论上不再连通的端子（删除必须保持设备至少 1 个端子） |
| 修正 SQL | `shared.sql_emitter.delete_pw_terminal(terminal_id)` |

---

## 任务 3.1 — 开关/电压基态匹配

### 算法核心

1. 对 `JBS_PWREAL`（配网）或 `JBS_ZWMEA`（主网）每个 `TRAN_ID`，统计电压均值 / 最大值。
2. 对 `JBS_PWEQUIPINFO / JBS_ZWEQUIPINFO` 中 `RUN_STATUS==0`（分位）但平均电压 > 0.1 pu → 异常（带电分位）。
3. 对 `RUN_STATUS==1`（合位）但平均电压 < 0.1 pu → 异常（合位无电）。

### 关键边界

| 边界 | 处理 |
|---|---|
| `TRAN_ID` 未配对到设备 | `shared.exemption.is_measurement_exempt(...)` 跳过 |
| 电压数据全空 | 视为 0 pu，警告 |
| 量测 96 点部分缺失 | 用现有数据均值，不要 raise |
| `RUN_STATUS` 缺失 | 跳过此设备 |
| 修正 SQL | `shared.sql_emitter.set_run_status_pw(expected_state)` |

### 模板

```python
from shared.exemption import is_measurement_exempt
from shared.sql_emitter import set_run_status_pw, set_run_status_zw

def detect(ctx):
    tables = ctx.tables
    equip_lookup = {d.get("EQUIP_ID"): d for d in tables.get("JBS_PWEQUIPINFO",()) + tables.get("JBS_ZWEQUIPINFO",())}
    # ZWMEA uses V0000-V2345 (96 points)
    tran_to_avg = {}
    for r in tables.get("JBS_ZWMEA", ()):
        if is_measurement_exempt(r, equip_lookup): continue
        vs = []
        for i in range(96):
            v = r.get(f"V{i:04d}")
            try: vs.append(float(v))
            except (TypeError, ValueError): pass
        if vs: tran_to_avg[r["TRAN_ID"]] = sum(vs) / len(vs)
    # PWREAL uses UA/UB/UC
    for r in tables.get("JBS_PWREAL", ()):
        if is_measurement_exempt(r, equip_lookup): continue
        phases = []
        for ph in ("UA","UB","UC"):
            try: phases.append(float(r.get(ph) or 0))
            except (TypeError, ValueError): pass
        if phases: tran_to_avg[r["TRAN_ID"]] = sum(phases) / len(phases) / 100.0  # V -> pu (rough)
    VOLTAGE_ON = 0.1  # pu
    VOLTAGE_OFF = 5.0  # V, below this is "no power"
    for eid, dev in equip_lookup.items():
        if dev.get("RUN_STATUS") is None: continue
        avg = tran_to_avg.get(eid, 0)
        point = dev["RUN_STATUS"]
        if point == 1 and avg < VOLTAGE_ON:
            yield ProblemRecord(task_code="3.1", device_id=eid, ..., description=f"合位但电压≈{avg:.2f}pu", correction="复核接线或分位", correction_sql=set_run_status_pw(eid, 0), severity="medium", confidence=0.75)
        elif point == 0 and avg > VOLTAGE_OFF:
            yield ProblemRecord(task_code="3.1", device_id=eid, ..., description=f"分位但带电≈{avg:.2f}V", correction="检查遥信配对", correction_sql=set_run_status_pw(eid, 1), severity="medium", confidence=0.7)
```

---

## 任务 4.1 — 主配接口漏拼接

### 算法核心

1. 取 `JBS_ZWTERMINAL` 的 `CONNECTIVITYNODE` 集合 Z。
2. 取 `JBS_PWTERMINAL` 的 `CONNECTIVITYNODE` 集合 P。
3. `Z ∩ P` 应该非空（主配通过共享节点联通）。
4. 某些 110kV 主网端子虽然 Z 内，但找不到对应的 10kV 配网端子 → 漏拼。

### 关键边界

| 边界 | 处理 |
|---|---|
| `Z ∩ P = ∅` 但所有主网设备都有配网对应 | 物理上不可能，不需要 4.1 |
| 主网设备无对应配网馈线 | 站房级问题，单独标"主配接口缺失" |
| 修正 SQL | `shared.sql_emitter.insert_zw_terminal_for_interface(...)` |

---

## 任务 4.2 — 主配接口错拼接

### 算法核心

1. 共享节点的两侧端子 `EQUIP_TYPE` 必须合理（如：主网母线 ≠ 配网母线）。
2. 类型不匹配 → 错拼 → 修改 CONNECTIVITYNODE。

### 关键边界

| 边界 | 处理 |
|---|---|
| `correction_sql` | `shared.sql_emitter.update_zw_terminal_node(terminal_id, correct_node)` |
| `extra["wrong_node"]` | 记录修正前的节点 ID |
| 同一共享节点两侧都是 BREAKER | 不一定错，看电压等级 |

---

## 反模式清单（务必避免）

1. **空 SQL 占位**：`correction_sql=""` 一旦 ≥ 1 条，SQL 可执行项扣分。
2. **yield 之后再改 record**：`ProblemRecord` 是 `@dataclass(frozen=True)`，不能改属性。
3. **detector 调其他 detector**：会破坏 selected_only 语义。
4. **静默吞错**：`try: ... except: pass` 在 detect() 内会让 runner 误以为成功。
5. **不附 evidence**：evidence=() 时评审无法复核，按 JUDGE.md 该 record 扣 0.05。
6. **用绝对路径**：所有设备 ID 必须是原值（如 `TMP00013138`），不要预填 `equipment/`。
7. **重复计数**：同一 `device_id` 在同一任务中输出多次只算 1 条覆盖率。
8. **越界 `correction_sql`**：必须用 `shared.sql_emitter.*`，手写容易缺分号/单引号。

---

## 性能与顺序

- 12 detector 顺序跑（按 `catalog.OFFICIAL_TASKS` 元组顺序）。
- 每 detector 不依赖前序结果（除 1.4 依赖 1.3 的 device_id 去重）。
- 单 detector 内：先建索引 dict（O(N)），再扫描（O(N)）。
- 大数据集（10k+ 设备）：用 `frozenset` / `dict` 而非 `list`，避免 `in` 操作 O(N)。
- 不要在 detect() 内 print；如需调试，用 `extra["debug_log"]` 收集，运行后看。

---

## 完整示例参考

见 `tasks_official/group_01_topology/task_1_1_dangle/detector.py` 当前骨架（含豁免逻辑）。
骨架填实后请保证 `from shared.exemption import is_dangle_exempt` 等三件套完整接入。
