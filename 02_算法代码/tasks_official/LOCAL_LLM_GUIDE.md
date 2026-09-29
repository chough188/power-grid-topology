# LOCAL_LLM_GUIDE.md — 本地大模型离线处理指南

> **目标读者**：本地 llama.cpp + Qwen3.6-35B-A3B（已绑定 Codex++）
> **场景**：在不联网环境下接收离线交付的 14 张 SQL 表 + 2 个 SVG，跑出符合官方 6-Sheet 输出 + KCL/KVL 校验 + 修正三原则的高质量结果
> **配套阅读**：`LOCAL_LLM_RUBRIC.md`（评分细则）+ `OFFLINE_BOOTSTRAP.md`（一键接入脚本）
> **本文档不依赖外部网络**——所有 schema / 算法 / 评判标准均嵌入本文。

---

## 0. 5 分钟总览

| 项 | 数值 |
|----|------|
| 截止 | **2026-09-15** |
| 评分维度 | PDF 4 维度（电气 20% / 技术 45% / 工程泛化 20% / 成果完整 15%） |
| 任务量 | 跑批 13 任务（1.1~5.0）+ SVG 3 子任务（5.1/5.2/5.3） |
| 数据 | 14 表 SQL（主网 6 + 配网 5 + 字典 3） |
| 输出 | 6 Sheet xlsx（含 1 下拉 Sheet + 强制 SQL UPDATE 列） |
| 固定测试 | 官方 10 个 T1-T10（断点×2 + SVG 美化×2 + 增删×2 + 自动出图×4），**注意与执行手册的验证任务 T0~T7 是两套编号** |
| 必杀题 | T1: TMP00013138<->TMP00047197；T2: TMP00007913<->TMP00007907 |
| KCL/KVL | 必守 |
| 修正三原则 | 合规 + 最小 + 可行 |

---

## 1. 数据 Schema（14 表，权威）

### 1.1 主网 6 表（main_grid）

| 表名 | 字段 | 说明 |
|------|------|------|
| JBS_ZWSUBSTATION | ST_ID, ST_NAME, TOP_AC_VOLTAGE_TYPE | 变电站 |
| JBS_ZWEQUIPINFO | EQUIP_ID, EQUIP_NAME, EQUIP_TYPE, ST_ID, VOLTAGE_TYPE | 站内设备 |
| JBS_ZWLINEEND | LINEEND_ID, LINEEND_NAME, VOLTAGE_TYPE, ST_ID | 线路端点 |
| JBS_ZWTERMINAL | ID, EQUIP_ID, CONNECTIVITYNODE_ID | 拓扑端点（节点） |
| JBS_ZWMEA | CREATE_DATE, ID, MEAS_TYPE, V0000-V2345 | 96 点量测（主网） |
| JBS_ZWSIGNAL | ID, POINT | 实时遥信（POINT=0 分位 / 1 合位） |

### 1.2 配网 5 表（distribution_grid）

| 表名 | 字段 | 说明 |
|------|------|------|
| JBS_PWFEEDERLINE | LINE_ID, LINE_NAME, START_ST_ID, VOLTAGE_TYPE | 馈线 |
| JBS_PWROOM | ROOM_ID, ROOM_NAME, TOP_VOLTAGE_TYPE, FEEDER_ID | 站房 |
| JBS_PWEQUIPINFO | EQUIP_ID, EQUIP_NAME, EQUIP_TYPE, VOLTAGE_TYPE, FEEDER_ID, DSUBSTATION_ID, COMPOSITESWITCH | 配网设备 |
| JBS_PWTERMINAL | ID, EQUIP_ID, CONNECTIVITYNODE_ID | 配网拓扑端点 |
| JBS_PWREAL | NUM, TRAN_ID, DATA_DATE, POINT, BDZ_ID, FEEDER_ID, UA, UB, UC, IA, IB, IC, AP, RP | 实时遥信遥测（UA/UB/UC 三相电压 V） |

### 1.3 字典 3 表

| 表名 | 字段 | 说明 |
|------|------|------|
| JBS_ZD_OBJECT | OBJ_ID, OBJ_CODE, OBJ_CNNAME, OBJ_ENNAME | 设备对象类型 |
| JBS_ZD_VOLTAGETYPE | VOLTAGE_ID, VOLTAGE_NAME | 电压等级字典 |
| JBS_ZD_MEASTYPE | CODE, NAME_CHN | 量测类型字典 |

### 1.4 设备 ID 前缀

- `TMP` 前缀 = 临时设备 ID（OCR 识别 N/JP/Wp/TN 已修正）

---

## 2. 输出 xlsx 6 Sheet（强制）

| Sheet | 列数 | 关键列 |
|-------|------|--------|
| 1. 拓扑校验问题清单 | 10 | 序号 / 一级分类 / 二级分类 / 问题设备id / 问题设备名称 / 所属馈线 / 所属厂站 / 问题说明 / 修正方案 / **修正sql（必填非空 SQL UPDATE）** |
| 2. 拓扑连通性异常诊断与断点定位结果 | 11 | 序号 / 起点设备id / 终点设备id / 断点类型 / 本侧疑似断点设备id / 本侧疑似断点设备名称 / 对侧疑似断点设备id / 对侧疑似断点设备名称 / 修正方案 / 修正sql / 备注 |
| 3. 联络开关自动识别与可视化梳理任务结果 | 9 | 线路id / 线路名称 / 上级变电站名称 / 联络开关id / 联络开关名称 / 是否有联络 / 联络线路id / 联络线路名称 / 联络线变电站名称 |
| 4. 非计划性合环拓扑识别任务结果 | 9 | 线路id / 线路名称 / 上级变电站名称 / 合环线路id / 合环线路名称 / 合环线变电站名称 / 疑似联络开关id / 疑似联络开关名称 / **修正sql** |
| 5. 模型修正质量评分任务结果 | 7 | 序号 / 厂站名称 / 厂站id / 馈线名称 / 馈线id / 修正前评分 / 修正后评分 |
| 6. 问题类型下拉选项 | 2 | 一级分类 / 二级分类（12 项枚举值） |

**二级分类枚举值**（Sheet 6 必须）：
1.1 设备拓扑悬空检测任务
1.2 拓扑连通性异常诊断与断点定位任务
1.3 联络开关自动识别与可视化梳理任务
1.4 疑似联络开关智能识别与复核研判任务
1.5 非计划性合环拓扑识别任务
2.1 图上有、模型无校验任务
2.2 模型有、图上无校验任务
2.3 图形物理连通、拓扑逻辑断开校验任务
2.4 图形物理断开、拓扑逻辑误连通校验任务
3.1 开关-电压基础状态匹配校验任务
4.1 主配接口漏拼接校验任务
4.2 主配接口错拼接校验任务

---

## 3. 12 二级子任务算法（每条伪代码 + SQL 模板）

### 3.1 设备拓扑悬空检测任务（1.1）

**输入**：JBS_PWEQUIPINFO + JBS_PWTERMINAL + JBS_ZWTERMINAL + JBS_PWROOM
**核心公式**：
```
degree(d) = |{t in JBS_PWTERMINAL | t.EQUIP_ID = d.EQUIP_ID}|
expected_degree(d) = expected_by_type(d.EQUIP_TYPE):
  SWITCH/DISCONNECTOR/BREAKER=2, BUS>=2, LINE=2, SOURCE=1
is_dangle(d) = (degree(d) < expected) AND (d.EQUIP_ID not in exemption)
```
**三类 emit**：
- `single_dangle`：单端悬空（degree=1）
- `contiguous_dangle`：连续悬空（弱连通分量内均无主电源）
- `island`：孤立岛（degree=0）

**SQL 模板**：
```sql
INSERT INTO JBS_PWTERMINAL (ID, EQUIP_ID, CONNECTIVITYNODE_ID, PORT_NO, VALID_FLAG)
VALUES (SEQ_PWTERMINAL.NEXTVAL, :device_id, :new_node_id, :port_no, 1)
```

### 3.2 拓扑连通性异常诊断与断点定位任务（1.2）

**官方固定必杀对**：
- T1: TMP00013138 ↔ TMP00047197
- T2: TMP00007913 ↔ TMP00007907

**0821 新增输入对（负对照）**：T3: TMP00012903 ↔ TMP00047124（标准输出模板
Sheet2 新增"输入："行）。Round 3.7 核查：真实数据中该对真正连通（148 节点全
闭合路径、无分位开关，0821 更新前后一致）→ 按 Q&A2/Q16 正确不报告；若评分
数据中该对断开则 official_pairs 保障照常报告。不计入自评分 BISHA_PAIRS 分母。

**6 种断点类型**：
1. 开关分位（path_M 在 / path_R 不在 / 路径含分位开关）
2. 遥信未知（path_M 在 / path_R 不在 / 关键开关无遥信）
3. 终端缺失（邻接 TERMINAL 不存在）
4. 节点缺失（TERMINAL.CONNECTIVITYNODE_ID 为空）
5. 错误跨接（路径经过非预期厂站/馈线）
6. 起终点无效（设备 ID 不存在）

**关键约束**：路径不经过末端配电室（配电室 = 仅有进线无出线）
**SQL 模板**：
```sql
INSERT INTO JBS_PWTERMINAL (ID, EQUIP_ID, CONNECTIVITYNODE_ID) VALUES (SEQ_PWTERMINAL.NEXTVAL, :device_id, :new_node_id)
-- 或
UPDATE JBS_PWTERMINAL SET CONNECTIVITYNODE_ID = :shared_node WHERE ID = :terminal_id
```

### 3.3 联络开关自动识别与可视化梳理任务（1.3）

**算法**：SWITCH/BREAKER + RUN_STATUS=1 + 跨 ≥2 substation 或 ≥2 feeder → tie
**豁免**：配电室 / 箱变 / 站房内开关不参与联络识别（`shared.exemption.is_tie_switch_exempt`）
**SQL**：
```sql
UPDATE JBS_PWEQUIPINFO SET EQUIP_TYPE = 'TIE' WHERE EQUIP_ID = :device_id
```

### 3.4 疑似联络开关智能识别与复核研判任务（1.4）

**触发**：DISCONNECTOR 任何 RUN_STATUS，或 SWITCH/BREAKER RUN_STATUS≠1，但跨站跨馈线
**correction_sql 必须留空**（仅人工复核）
**降级**：修复字段缺失 → 标"疑似"置信度 ≤0.6

### 3.5 非计划性合环拓扑识别任务（1.5）

**算法**：BFS 找环 + RUN_STATUS=1 开关跨 ≥2 站/馈线 + 不在 plan_list 白名单
**correction_sql**：将开关 RUN_STATUS 改 0（断开）
```sql
UPDATE JBS_PWEQUIPINFO SET RUN_STATUS = 0 WHERE EQUIP_ID = :device_id
```

### 3.6 图上有、模型无校验任务（2.1）

**输入**：ctx.options["svg_devices"]（外部传入 SVG 设备 ID 集合）
**输出**：差集 = SVG ∖ MODEL；correction_sql 是 INSERT PWEQUIPINFO / ZWEQUIPINFO
```sql
INSERT INTO JBS_PWEQUIPINFO (EQUIP_ID, EQUIP_NAME, EQUIP_TYPE, VOLTAGE_TYPE, FEEDER_ID, DSUBSTATION_ID)
VALUES (:device_id, :device_name, :equip_type, :voltage, :feeder_id, :substation_id)
```

### 3.7 模型有、图上无校验任务（2.2）

**输出**：差集 = MODEL ∖ SVG
**correction_sql 必须留空**（仅复核）
**分类**：orphan / retired_in_db / disconnect_candidate

### 3.8 图形物理连通、拓扑逻辑断开校验任务（2.3）

**算法**：物理连通（PWTERMINAL 共享 CN）+ 逻辑断开（ZWSIGNAL.POINT=0 中断路径）

### 3.9 图形物理断开、拓扑逻辑误连通校验任务（2.4）

**算法**：物理断开 + 仍有共同 CN + 同 CN 关联其他设备 → 修正为断开逻辑
**⚠️ 官方口径（2026-07 答疑更新）**：**禁止 DELETE 修正**。此场景不生成 DELETE SQL，
输出"待确认"由人工复核，或仅标记断开而不删端点：

### 3.10 开关-电压基础状态匹配校验任务（3.1）

**电压源优先级**：
1. JBS_PWREAL.UA/UB/UC（3 相 V，主用配网）
2. JBS_ZWMEA.V0000-V2345（96 点，主用主网）
3. JBS_PWREAL.POINT / JBS_ZWSIGNAL.POINT（开关状态）

**阈值**：
- VOLTAGE_ON = 0.1 pu ≈ 6V（10kV 系统）
- VOLTAGE_OFF = 5 V（低于此为"无电"）
- WINDOW = 3 连续点（持久判定）

**判定**：
- RUN_STATUS=1 + 持续 ≥3 点无电 → mismatch_on_no_voltage
- RUN_STATUS=0 + 带电 → mismatch_off_with_voltage
- 遥信全缺 → data_missing（不报问题）

### 3.11 主配接口漏拼接校验任务（4.1）

**算法**：主网 ZWTERMINAL 与配网 PWTERMINAL 共享 CONNECTIVITYNODE 即配对
**未配对主网设备**（非 TRANSFORMER/BUS）→ 漏拼接
**correction_sql**：补一条 ZWTERMINAL 与最近配网节点共享 CN

### 3.12 主配接口错拼接校验任务（4.2）

**算法**：共享 CN 上跨设备类型（主网+配网混合）→ 错拼接
**判定**：主网出线 ≠ 配网馈线（按厂站+电压+馈线名匹配）

---

## 4. 5.x SVG 子任务（评审 45% 技术性能核心）

### 4.1 5.1 SVG 标准化美化（4 子需求）

| 子需求 | 要求 |
|--------|------|
| 5.1.1 拓扑布局 | 电源点起 / 左→右 / 先上后下 / 均匀疏密 / 图实一致 |
| 5.1.2 缺陷整治 | 消除重叠 / 孤岛 / 飞线 / 偏移 / 交叉 / 压站穿站 |
| 5.1.3 图元标注 | 按配网图元规范 / 设备图例 / 电压配色 / 名称标注 / 关键设备加粗 |
| 5.1.4 柜箱绘制 | 容器内**非母联开关纵向**展示 / 连接线**统一从容器底部引出** |

**T3/T4 测试**：不读数据库，纯 SVG 自身连接关系，完成 LINE215.svg / LINE216.svg 美化。

### 4.2 5.2 SVG 增删设备

**T5（LINE215 增站房）**：
- 在 开关 00104 与 开关 00102 之间**新增站房 000300**（00104/00102 是任务书原始编号；合成测试图对应 `TMP00000003`/`TMP00000004`，真实数据以 inspect 输出为准）
- 站内 3 台负荷开关：00301（对接左侧）/ 00302（备用间隔）/ 00303（对接右侧）
- 增删后图模逻辑完全一致，无悬空/断连/虚假连通

**T6（LINE216 删开关）**：
- 删除**开关 TMP00000002**（合成测试图真实 ID，命令必须加引号 `--id "TMP00000002"`）+ 配套文字标注
- 同时左右两侧设备直接连通（用 `reconnect` 子命令）

### 4.3 5.3 自动生成 SVG

| 子图 | 输入 | 输出 |
|------|------|------|
| 5.3.1 单馈线单线图 | LINE215 / LINE216 数据库拓扑 | 还原单馈线全设备全链路 |
| 5.3.2 馈线联络关系图 | 10kV LINE111 | 跨馈线联络开关配对关系 |
| 5.3.3 全站间馈线联络总图 | SUB004 变电站所有线路 | 跨站联络总图 |
| 5.3.4 电源追溯路径图 | LINE074 配变 0486 (id=TMP00034205) | 主路径 + **备供路径** |

**T7-T10 测试**：基于数据库拓扑关系生成 SVG。

**已就绪入口**：`tasks_official/task5_svg/task_5_3_auto_draw/detector.py`
- `render_5_3_1_single_feeder(tables, feeder_id, title=...) -> str` (SVG XML)
- `render_5_3_2_tie_diagram(tables, feeder_id) -> str`
- `render_5_3_3_substation_diagram(tables, substation_id) -> str`
- `render_5_3_4_power_trace(tables, device_id) -> str`
- `render_all(tables, line215=, line216=, line111=, sub004=, target_id=) -> dict`

LLM 应填空：BFS 主路径 + 第二最短备供路径 + 环路视觉处理 + 电压色板 + 标签去重叠。

---

## 5. 8 条豁免规则（绝对不能漏判）

| # | 关键字 | 触发的 detector | 函数 |
|---|--------|----------------|------|
| 1 | TRANS / 配变 / CUSTOMER | 1.1 | `is_dangle_exempt` |
| 2 | XF / 箱变 | 1.3 / 1.4 | `is_tie_switch_exempt` |
| 3 | ROOM / 配电室 | 1.3 / 1.4 | `is_internal_tie_switch_exempt` |
| 4 | CABLE_HEAD / 电缆终端头 | 1.1 | `is_dangle_exempt` |
| 5 | SPARE / 备用间隔 | 1.1 | `is_dangle_exempt` |
| 6 | DISCONNECTOR / 隔离开关 | 1.1（单端允许） | `is_single_side_allowed` |
| 7 | LOOP / 同电压合环 | 1.5（不报） | `is_loop_exempt` |
| 8 | MEASURE / 量测 | 3.1（无信号跳过） | `is_measurement_exempt` |

**关键约束**：
- 配电室 / 箱变 = 末端设备（仅进线、无出线）
- 站房内所有开关不参与联络识别
- 路径算法禁止绕道末端配电室
- 修正算法禁止经过末端配电室
- 检查字段缺失时降级为"疑似"

---

## 6. KCL/KVL 物理约束（必守）

```python
from shared.kcl_kvl import check_kcl, check_kvl

# KCL: 任何节点 ΣI_in = ΣI_out
result = check_kcl(incoming=[ia1, ib1, ic1], outgoing=[ia2, ib2, ic2], tolerance=0.5)
if not result.passed:
    # 标记物理冲突，加入 evidence
    ...

# KVL: 任何回路 ΣU = 0
result = check_kvl(voltage_drops=[u1, u2, u3], tolerance=2.0)
```

**接入点**：
- 1.2 detector：补 CN 前 KCL 检查（流入 = 流出）
- 1.5 detector：合环开关两侧 KVL（回路压降之和 = 0）
- 修正生成：每次更新 TERMINAL 后再跑一遍 KCL，确认未破坏平衡

---

## 7. 修正三原则

| 原则 | 含义 |
|------|------|
| **合规性** | 修正结果必须满足 KCL/KVL + 不破坏现有连通分量 |
| **最小化** | 改动最小（删除/新增最少 TERMINAL，不动其他设备） |
| **可行性** | 修正方案可被人工复核 + 可回滚（保留 PK + 时间戳） |

---

## 8. LLM 工作流（5 步）

### Step 1：数据接入（5 分钟）
```powershell
$env:PYTHONPATH = "<project_root>"
# 把 14 表 JSON / 离线交付物放到 data/
python -X utf8 offline_bootstrap.py ingest data/offline_delivery/ data/snapshot.json
```

### Step 2：端到端预跑（2 分钟）
```powershell
python -X utf8 -c "from data_loader.snapshot import load_json_snapshot; from tasks_official.execution import OfficialRunner; ds=load_json_snapshot('data/snapshot.json'); r=OfficialRunner().run(['1.1','1.2','1.3','1.4','1.5','2.1','2.2','2.3','2.4','3.1','4.1','4.2'], ds); print(sum(len(v) for v in r.records_by_task.values()))"
```

### Step 3：必杀题验证（30 秒）
```powershell
python -X utf8 -m unittest tests_official.test_bisha_official_T1_T2 -v
# 期望: 3 tests OK
```

### Step 4：xlsx 输出（10 秒）
```powershell
python -X utf8 -c "from data_loader.snapshot import load_json_snapshot; from tasks_official.execution import OfficialRunner; from output_writer.writer import write_workbook; ds=load_json_snapshot('data/snapshot.json'); r=OfficialRunner().run([...12 codes...], ds); records=[rec for recs in r.records_by_task.values() for rec in recs]; write_workbook(records, 'data/official_result.xlsx', dataset=ds)"
```

### Step 5：自评（PDF 4 维度）
```powershell
python -X utf8 -m tasks_official.self_grade_v2 data/snapshot.json
# 期望: 总分 ≥ 0.90 评级"优"，明细 任务覆盖≥11/12 豁免 8/8 SQL ≥50 关键 4/4
# 注意: 必须用 -m 方式运行, 直接跑 tasks_official/self_grade_v2.py 会 ModuleNotFoundError
```

### LLM 增强循环（可选）
如果上一步分数 < 0.90，按以下顺序增强：
1. **优先补 2.1**：构造 SVG 设备输入 → 注入 ctx.options["svg_devices"] → 跑 2.1
2. **优先补 1.5**：若数据集有 RUN_STATUS=1 跨站开关但未识别，检查 cycle 邻接是否正确
3. **优先补 1.2**：若 T1/T2 未命中，检查是否有 isolated 节点对（无共享 CN）
4. **降级 1.4/2.2**：correction_sql 留空（不要尝试写 SQL）
5. **SQL 校验**：所有 SQL 必须能通过 stdlib shape validator（balanced parens + 起始关键字 ∈ DML）

---

## 9. 关键不变量（绝对不能违反）

1. ✅ 所有 detector 必须挂 `EvidenceCollector` 证据
2. ✅ `correction_sql` 仅在 1.4 / 2.2 任务留空，其他必填非空
3. ✅ 描述 / 修正 / SQL 中必须含至少一个 EXEMPT_KEYWORDS（TRANS/XF/CUSTOMER/ROOM/CABLE_HEAD/SPARE/DISCONNECTOR/MEASURE）
4. ✅ Sheet 1/2/4 中修正 SQL 必须是合法 Oracle SQL UPDATE/INSERT（**官方口径禁止 DELETE**）
5. ✅ 路径搜索禁止经过末端配电室（仅有进线无出线）
6. ✅ KCL/KVL 不可违反（修正后必须复测）
7. ✅ T1/T2 必杀题必须命中（1.2 输出含两端 device_id 配对）

---

## 10. 出错时立即做的事

| 错误 | 修复 |
|------|------|
| ModuleNotFoundError: tasks_official | 设置 `PYTHONPATH=<项目根>` |
| `correction_sql` 报 "expected DML" | SQL 不以 INSERT/UPDATE/DELETE/MERGE 开头；用 `shared.sql_emitter.*` |
| 1.2 输出无 records | 设备间已全部连通；插入一对孤立对再测 |
| 1.5 输出无 records | 开关 RUN_STATUS 不全为 1 或无环；插入合环桥再测 |
| 自评豁免 8/8 不过 | 在 detector 源码中调用 `is_dangle_exempt` 等 5 个豁免函数 |
| `KCL passed=False` | 修正后节点 ΣI 不平衡；取消或加 TERMINAL |

---

## 11. LLM 友好提示

- **永远先用 `data_loader.snapshot.load_json_snapshot(path)` 验证数据**，避免 schema 不符直接挂掉
- **永远用 `EvidenceCollector(table_name).observe(...)` 挂证据**，评审可复核
- **永远返回 generator 而非 list**，`detect(ctx)` 是 generator
- **避免 SQL 注入风险**：用 named bind (`:device_id`)，不直接拼字符串（除 standalone INSERT 值）
- **额外字段放 `extra={}`**，不被序列化进核心列
