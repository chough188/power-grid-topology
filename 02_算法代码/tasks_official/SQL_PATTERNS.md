# CP-202606 修正 SQL 模板与落库规范

本文档定义 12 个 detector 在产出 `ProblemRecord` 时，`correction_sql` 字段应填入的可执行 SQL 模板。评审时 `self_grade.py` 用 `sqlglot` 做纯语法解析（不连库），解析失败计入"SQL 不可执行"。

## 1. 总则

- **方言**：默认 Oracle（JBS_* 前缀来自泰豪方提供，标准为 Oracle 11g/19c）。若用户提供 PostgreSQL 快照，在 `TaskContext.options["dialect"]` 中声明，detector 按方言生成。
- **标识符**：表名、字段名全大写下划线 (`JBS_PWEQUIPINFO`, `CONNECTIVITYNODE_ID`)。不加反引号 / 双引号包裹。
- **字符串字面量**：用单引号 `'TMP00013138'`。
- **绑定变量**：设备 ID 用 `:device_id` 风格，不要直接拼字符串进 SQL。
- **自增主键**：终端表 (PWTERMINAL / ZWTERMINAL) 用 `SEQ_PWTERMINAL.NEXTVAL` / `SEQ_ZWTERMINAL.NEXTVAL`。

## 2. 12 任务 SQL 模板

### 2.1 任务 1.1 设备拓扑悬空

**异常**：设备在 `JBS_PWEQUIPINFO`/`JBS_ZWEQUIPINFO` 有记录，但 `*TERMINAL` 中对应的 `CONNECTIVITYNODE_ID` 数量 ≤ 1。

**修正**：补一条 TERMINAL 记录，新增共享 `CONNECTIVITYNODE_ID`。

```sql
INSERT INTO JBS_PWTERMINAL (ID, EQUIP_ID, CONNECTIVITYNODE_ID)
VALUES (SEQ_PWTERMINAL.NEXTVAL, :device_id, :new_node_id)
```

主网设备（无 FEEDER_ID）改用 `JBS_ZWTERMINAL`。

**豁免**：`EQUIP_NAME` / `EQUIP_TYPE` 含 `TRANS` / `XF` / `CUSTOMER` / `ROOM` / `CABLE_HEAD` / `SPARE` 不输出。

### 2.2 任务 1.2 拓扑连通断点

**异常**：连通图分析得出本应连通的设备 A 与 B 之间实际无共用 `CONNECTIVITYNODE`。

**修正二选一**：

(1) 追加端子让 B 复用 A 的节点：
```sql
INSERT INTO JBS_PWTERMINAL (ID, EQUIP_ID, CONNECTIVITYNODE_ID)
VALUES (SEQ_PWTERMINAL.NEXTVAL, :device_id_b, :shared_node_a)
```

(2) 把 B 现存端子的节点改为 A 的共享节点：
```sql
UPDATE JBS_PWTERMINAL SET CONNECTIVITYNODE_ID = :shared_node_a WHERE ID = :terminal_id_b
```

detector 可根据上下文选其一，`extra["strategy"]` 注明。

### 2.3 任务 1.3 联络开关自动识别

**异常**：开关两侧均合位且分属不同站所/馈线，被识别为联络但 `EQUIP_TYPE` 未标 `TIE`。

**修正**：标记为联络：
```sql
UPDATE JBS_PWEQUIPINFO SET EQUIP_TYPE = 'TIE' WHERE EQUIP_ID = :device_id
```

### 2.4 任务 1.4 疑似联络开关

**异常**：同 1.3 但置信度低（边界条件），需人工复核。

**修正**：`correction_sql` 留空。在 `description` 写明疑似依据，`extra["confidence_reason"]` 给出理由。

### 2.5 任务 1.5 非计划合环

**异常**：检测到非计划合环（两个并列运行馈线通过非联络开关短接）。

**修正**：断开一侧开关：
```sql
UPDATE JBS_PWEQUIPINFO SET RUN_STATUS = 0 WHERE EQUIP_ID = :device_id
```

`extra["opened_switch_id"]` 记录被断开的设备 ID。

### 2.6 任务 2.1 仅图形无模型

**异常**：SVG 中有设备图元但 `*EQUIPINFO` 无对应记录。

**修正**：补模型：
```sql
INSERT INTO JBS_PWEQUIPINFO (EQUIP_ID, EQUIP_NAME, EQUIP_TYPE, VOLTAGE_TYPE, FEEDER_ID, DSUBSTATION_ID)
VALUES (:device_id, :device_name, :equip_type, :voltage, :feeder_id, :substation_id)
```

### 2.7 任务 2.2 仅模型无图形

**异常**：模型中有设备但 SVG 无对应图元。

**修正**：`correction_sql` 留空。在 `description` 写明"需补 SVG 图元"，`extra["svg_layer"]` 记录应放图层。

### 2.8 任务 2.3 物理连/逻辑断

**异常**：实际连接 (`RUN_STATUS=1`) 但 `CONNECTIVITYNODE` 图论上不连通。

**修正**：补端子让逻辑连通：
```sql
INSERT INTO JBS_PWTERMINAL (ID, EQUIP_ID, CONNECTIVITYNODE_ID)
VALUES (SEQ_PWTERMINAL.NEXTVAL, :device_id, :expected_node)
```

### 2.9 任务 2.4 物理断/逻辑连

**异常**：实际断开 (`RUN_STATUS=0`) 但 `CONNECTIVITYNODE` 图论上连通。

**修正**：删除多余端子：
```sql
DELETE FROM JBS_PWTERMINAL WHERE ID = :terminal_id
```

### 2.10 任务 3.1 开关/电压状态匹配

**异常**：`RUN_STATUS=0`（分位）但 `JBS_PWREAL` 三相电压均 > 0.1 pu，或反之分位带电。

**修正**：以电压反推期望分/合位：
```sql
UPDATE JBS_PWEQUIPINFO SET RUN_STATUS = :expected_state WHERE EQUIP_ID = :device_id
```

`extra["expected_state"]` 取值 0 或 1。

### 2.11 任务 4.1 主配接口漏拼

**异常**：`JBS_ZWTERMINAL` 与 `JBS_PWTERMINAL` 应通过 `CONNECTIVITYNODE_ID` 共享联通主配网，但实际无共用节点。

**修正**：在主网端子表补一条：
```sql
INSERT INTO JBS_ZWTERMINAL (ID, EQUIP_ID, CONNECTIVITYNODE_ID)
VALUES (SEQ_ZWTERMINAL.NEXTVAL, :main_device_id, :shared_node)
```

`extra["dist_feeder_id"]` 记录对应的配网馈线 ID。

### 2.12 任务 4.2 主配接口错拼

**异常**：主配网端子通过错误的 `CONNECTIVITYNODE_ID` 连接，导致拓扑错位。

**修正**：
```sql
UPDATE JBS_ZWTERMINAL SET CONNECTIVITYNODE_ID = :correct_node WHERE ID = :terminal_id
```

`extra["wrong_node"]` 记录修正前的节点 ID。

## 3. 命名规范

- **表别名**：`T` for TERMINAL, `E` for EQUIPINFO, `F` for FEEDERLINE, `R` for ROOM, `S` for SUBSTATION。
- **CTE 风格**：子查询用 `WITH ... AS (...)`，嵌套不超过 3 层。
- **注释**：仅 `--` 单行注释，关键字段写注释（如 `-- 主网设备主键`）。

## 4. 落库顺序

涉及多表的修正按以下顺序，避免外键悬空：

1. `JBS_PWEQUIPINFO` / `JBS_ZWEQUIPINFO`（设备主表）
2. `JBS_PWTERMINAL` / `JBS_ZWTERMINAL`（拓扑端点）
3. `JBS_PWREAL` / `JBS_ZWMEA` / `JBS_PWSIGNAL`（量测/遥信）
4. `JBS_PWROOM` / `JBS_PWFEEDERLINE`（站房/馈线，最后）

## 5. Dry-run 检测

`self_grade.py` 调用：
```python
import sqlglot
try:
    sqlglot.parse(sql, read='oracle')
    ok += 1
except Exception:
    fail += 1
```

不发起任何数据库连接，纯本地解析。

## 6. 自检命令

提交前运行：
```powershell
$env:PYTHONPATH = "E:\dianli\xiangmu\dianli\电力拓扑图修正\02_算法代码"
python -X utf8 -c "from tasks_official.execution import OfficialRunner; from data_loader.loader import OfficialDataset; ds = OfficialDataset.load_snapshot('data/snapshot.json'); r = OfficialRunner().run(['1.1','1.2','1.3','1.5','3.1','4.1','4.2'], ds); sqls = [rec.correction_sql for recs in r.records_by_task.values() for rec in recs if rec.correction_sql]; print(f'非空 SQL: {len(sqls)} / 总记录: {sum(len(v) for v in r.records_by_task.values())}')"
```

期望：7 任务每任务 ≥ 1 条 SQL，SQL 数与记录数比 ≥ 0.6。

---
文档结束
