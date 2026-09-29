# CP-202606 字段映射权威表

> **重要更正（2026-07-21，依据 比赛要求/数据集结构说明.docx 实际定义）**：
> 之前的版本错误地标注了部分字段"不存在"。**实际权威定义**如下，请以本文档为准。

## 0. 必读修正

| 字段 | 旧版结论 | **新版（权威）** | 依据 |
|---|---|---|---|
| `JBS_PWREAL.UA/UB/UC` | "不存在" | **存在！** 三相电压（A/B/C 相，V） | 数据集结构说明.docx 表 11 |
| `JBS_PWREAL.IA/IB/IC` | "不存在" | **存在！** 三相电流（A） | 数据集结构说明.docx 表 11 |
| `JBS_PWREAL.AP/RP` | "不存在" | **存在！** 有功/无功功率 | 数据集结构说明.docx 表 11 |
| `JBS_ZWMEA.V0000-V2345` | "不存在" | **存在！** 96 个 15 分钟间隔点 | 数据集结构说明.docx 表 5 + 文字说明 |
| `JBS_ZD_OBJECT.OBJ_CODE` TRANSFORMER | 无 | `TRANSFORMER` 是有效 code（变压器） | 数据集结构说明.docx 表 12 |
| `JBS_VOLTAGETYPE` vs `JBS_ZD_VOLTAGETYPE` | 一致 | **官方表名是 `JBS_VOLTAGETYPE`**（无 ZD_），但 schema.py 强制 `JBS_ZD_VOLTAGETYPE`，实际数据用 ZD_ 版本 | 文档表述 vs 代码契约 |

> **本地大模型最重要的参考**：比赛要求 PDF/docx 中的字段名与代码 `data_loader/schema.py` 中实际字段名存在差异。本文给出权威映射，避免 detector 写出 `obj.get("SUBSTATION_ID")` 拿到空值的常见错误。

## 1. 主键与外键差异总览

| 比赛要求 PDF/docx 中的命名 | 代码 `schema.py` 实际命名 | 备注 |
|---|---|---|
| `SUBSTATION_ID` | `ST_ID` | 主网站所主键。`SUBSTATION_ID` 在真实快照中**不存在** |
| `SUBSTATION_NAME` | `ST_NAME` | 站所名 |
| `LINE_ID` (主网线路端) | `LINEEND_ID` | 避免与 `JBS_PWFEEDERLINE.LINE_ID` 冲突 |
| `LINE_NAME` (主网) | `LINEEND_NAME` | 同上 |
| `START_EQ_ID` / `END_EQ_ID` | 无对应字段 | 主网线路端只有 `LINEEND_ID/ST_ID`，无起止设备 |
| `TRAN_ID` (主网量测) | `ID` | 主网量测主键就叫 `ID`，与配网不同 |
| `V0000`-`V2345` (主网) | 无 | 主网量测用 `MEAS_TYPE`+`CREATE_DATE`，无 96 点电压字段 |
| `UA/UB/UC` (配网) | 无 | 配网实时 `JBS_PWREAL` 用 `POINT`+`BDZ_ID`，无三相电压字段 |
| `SUBSTATION_ID` (设备归属) | `ST_ID` (主网) / `DSUBSTATION_ID` (配网) | 主配不一致 |

## 2. 14 表完整字段对照

### 主网 6 表

#### `JBS_ZWSUBSTATION` 主网站所

| schema.py 必填 | 比赛要求提到 | 实际使用建议 |
|---|---|---|
| `ST_ID` | `SUBSTATION_ID` | **用 `ST_ID`** |
| `ST_NAME` | `SUBSTATION_NAME` | **用 `ST_NAME`** |
| `TOP_AC_VOLTAGE_TYPE` | — | 主网最高电压 |

#### `JBS_ZWEQUIPINFO` 主网设备

| schema.py 必填 | 比赛要求提到 | 实际使用建议 |
|---|---|---|
| `EQUIP_ID` | `EQUIP_ID` | ✓ |
| `EQUIP_NAME` | `EQUIP_NAME` | ✓ |
| `EQUIP_TYPE` | `EQUIP_TYPE` (BREAKER/SWITCH/TRANSFORMER) | ✓ |
| `ST_ID` | `SUBSTATION_ID` | **用 `ST_ID`** |
| `VOLTAGE_TYPE` | `VOLTAGE_TYPE` | ✓ |
| (扩展) `RUN_STATUS` | `RUN_STATUS` (0/1) | 非必填，但 detector 必用 |

#### `JBS_ZWLINEEND` 主网线路端

| schema.py 必填 | 比赛要求提到 | 实际使用建议 |
|---|---|---|
| `LINEEND_ID` | `LINE_ID` | **用 `LINEEND_ID`** |
| `LINEEND_NAME` | `LINE_NAME` | **用 `LINEEND_NAME`** |
| `VOLTAGE_TYPE` | `VOLTAGE_TYPE` | ✓ |
| `ST_ID` | — | 所属站所 |

注：比赛要求提到的 `START_EQ_ID` / `END_EQ_ID` 在实际数据中**不存在**，不要尝试读取。

#### `JBS_ZWTERMINAL` 主网拓扑节点

| schema.py 必填 | 比赛要求提到 | 实际使用建议 |
|---|---|---|
| `ID` | `ID` | ✓ |
| `EQUIP_ID` | `EQUIP_ID` | ✓ |
| `CONNECTIVITYNODE_ID` | `CONNECTIVITYNODE_ID` | ✓ |

#### `JBS_ZWMEA` 主网量测

| schema.py 必填 | 比赛要求提到 | 实际使用建议 |
|---|---|---|
| `CREATE_DATE` | `DATA_DATE` | **用 `CREATE_DATE`** |
| `ID` | `TRAN_ID` | **用 `ID`** |
| `MEAS_TYPE` | — | 量测类型 code |

注：比赛要求提到的 `V0000`-`V2345` 96 点电压字段在 `JBS_ZWMEA` 中**不存在**。如需 96 点电压，应使用 `JBS_PWREAL` 的 `UA/UB/UC`（虽然非 96 点格式）。

#### `JBS_ZWSIGNAL` 主网遥信

| schema.py 必填 | 比赛要求提到 | 实际使用建议 |
|---|---|---|
| `ID` | `ID` | ✓ |
| `POINT` | `POINT` | ✓ (0=分位 1=合位) |

### 配网 5 表

#### `JBS_PWFEEDERLINE` 配网馈线

| schema.py 必填 | 比赛要求提到 | 实际使用建议 |
|---|---|---|
| `LINE_ID` | `LINE_ID` | ✓ |
| `LINE_NAME` | `LINE_NAME` | ✓ |
| `START_ST_ID` | `START_ST_ID` | ✓ |
| `VOLTAGE_TYPE` | `VOLTAGE_TYPE` | ✓ |

#### `JBS_PWROOM` 配网站房

| schema.py 必填 | 比赛要求提到 | 实际使用建议 |
|---|---|---|
| `ROOM_ID` | `ROOM_ID` | ✓ |
| `ROOM_NAME` | `ROOM_NAME` | ✓ |
| `TOP_VOLTAGE_TYPE` | `TOP_VOLTAGE_TYPE` | ✓ |
| `FEEDER_ID` | `FEEDER_ID` | ✓ |

#### `JBS_PWEQUIPINFO` 配网设备

| schema.py 必填 | 比赛要求提到 | 实际使用建议 |
|---|---|---|
| `EQUIP_ID` | `EQUIP_ID` | ✓ |
| `EQUIP_NAME` | `EQUIP_NAME` | ✓ |
| `EQUIP_TYPE` | `EQUIP_TYPE` | ✓ |
| `VOLTAGE_TYPE` | `VOLTAGE_TYPE` | ✓ |
| `FEEDER_ID` | `FEEDER_ID` | ✓ |
| `DSUBSTATION_ID` | `SUBSTATION_ID` (设备归属) | **用 `DSUBSTATION_ID`** |
| `COMPOSITESWITCH` | `COMPOSITESWITCH` | ✓ |
| (扩展) `RUN_STATUS` | `RUN_STATUS` | 非必填 |

#### `JBS_PWTERMINAL` 配网拓扑节点

| schema.py 必填 | 比赛要求提到 | 实际使用建议 |
|---|---|---|
| `ID` | `ID` | ✓ |
| `EQUIP_ID` | `EQUIP_ID` | ✓ |
| `CONNECTIVITYNODE_ID` | `CONNECTIVITYNODE_ID` | ✓ |

#### `JBS_PWREAL` 配网设备遥测遥信

| schema.py 必填 | 比赛要求提到 | 实际使用建议 |
|---|---|---|
| `NUM` | `NUM` | ✓ |
| `TRAN_ID` | `TRAN_ID` | ✓ |
| `DATA_DATE` | `DATA_DATE` | ✓ |
| `POINT` | `POINT` | ✓ (0/1) |
| `BDZ_ID` | `BDZ_ID` | ✓ 保护装置 |
| `FEEDER_ID` | `FEEDER_ID` | ✓ |

注：比赛要求提到的 `UA/UB/UC` / `IA/IB/IC` / `AP/RP` 在 `JBS_PWREAL` 中**不存在**。`POINT` 是唯一的状态字段。

### 字典 3 表

#### `JBS_ZD_OBJECT` 对象类型

| schema.py 必填 | 比赛要求提到 | 实际使用建议 |
|---|---|---|
| `OBJ_ID` | `OBJ_ID` | ✓ |
| `OBJ_CODE` | `OBJ_CODE` | ✓ (BREAKER/SWITCH/TRANSFORMER/XF/ROOM/...) |
| `OBJ_CNNAME` | `OBJ_CNNAME` | ✓ |
| `OBJ_ENNAME` | `OBJ_ENNAME` | ✓ |

#### `JBS_ZD_VOLTAGETYPE` 电压等级

| schema.py 必填 | 比赛要求提到 | 实际使用建议 |
|---|---|---|
| `VOLTAGE_ID` | `VOLTAGE_ID` | ✓ |
| `VOLTAGE_NAME` | `VOLTAGE_NAME` | ✓ |

#### `JBS_ZD_MEASTYPE` 量测类型

| schema.py 必填 | 比赛要求提到 | 实际使用建议 |
|---|---|---|
| `CODE` | `CODE` | ✓ |
| `NAME_CHN` | `NAME_CHN` | ✓ |

## 3. 防御性读取模式

由于 schema.py 只声明最小必填字段，实际快照可能含更多字段。为避免 `KeyError`，**永远用 `.get(key, default)` 而非 `obj[key]`**。

```python
# 好：默认值 + None 处理
eid = row.get("EQUIP_ID")
st_id = row.get("ST_ID") or row.get("DSUBSTATION_ID") or row.get("SUBSTATION_ID", "")
voltage = row.get("VOLTAGE_TYPE")
voltage_norm = int(voltage) if voltage is not None else 0

# 不好：直接索引会 KeyError
eid = row["EQUIP_ID"]              # 如果行缺字段直接崩
sub_id = row["SUBSTATION_ID"]      # 真实字段叫 ST_ID，不是 SUBSTATION_ID
```

## 4. 设备 ID 前缀约定

来自 `比赛要求/任务分工20260717.xlsx`：

| 前缀 | 含义 |
|---|---|
| `TMP` | 原 OCR 文档临时设备 ID（绝大多数设备） |
| `N` | 已修正的设备 ID |
| `JP` | 简化设备 ID |
| `Wp` | 配网站内设备 |
| `TN` | 变压器 ID |
| `XF` | 箱变 |

detector 处理 ID 时**不要假设前缀**，所有 TMP/N/JP 都一视同仁。

## 5. 字段缺失应对

| 字段缺失场景 | 应对 |
|---|---|
| `EQUIP_NAME` 缺失 | 用 `EQUIP_ID` 替代显示 |
| `RUN_STATUS` 缺失 | 视为 None，3.1 任务跳过 |
| `VOLTAGE_TYPE` 缺失 | 用 0 兜底，但**记录**到 `extra["voltage_missing"]` |
| `CONNECTIVITYNODE_ID` 缺失 | 该 TERMINAL 行作废，不计入邻接图 |
| `ST_ID`/`DSUBSTATION_ID` 都缺 | 1.3 任务降级为"无站归属开关"，跳过联络判断 |

## 6. 自检脚本

提交前用以下命令核对字段命名一致性（不联网）：

```powershell
$env:PYTHONPATH = "E:\dianli\xiangmu\dianli\电力拓扑图修正\02_算法代码"
python -X utf8 -c "
import sys; sys.path.insert(0, r'E:\dianli\xiangmu\dianli\电力拓扑图修正\02_算法代码')
from data_loader.schema import TABLE_SCHEMAS
for name, schema in TABLE_SCHEMAS.items():
    print(f'{name}: required={list(schema.required_fields)}')
"
```

输出应严格匹配上面"schema.py 必填"列。如不一致，以实际输出为准（schema.py 是真理之源）。

---

## 7. 已知不匹配清单（本地大模型必须避开）

读取 `JBS_ZWEQUIPINFO` 时**不要**用这些字段名（取不到值）：

- ❌ `SUBSTATION_ID`（实际是 `ST_ID`）
- ❌ `START_EQ_ID` / `END_EQ_ID`（实际不存在）
- ❌ `TRAN_ID`（主网量测主键叫 `ID`）

读取 `JBS_ZWMEA` 时**不要**用：

- ❌ `V0000`-`V2345`（不存在 96 点电压字段）
- ❌ `TRAN_ID`（叫 `ID`）
- ❌ `DATA_DATE`（叫 `CREATE_DATE`）

读取 `JBS_PWREAL` 时**不要**用：

- ❌ `UA` / `UB` / `UC`（不存在）
- ❌ `IA` / `IB` / `IC`（不存在）
- ❌ `AP` / `RP`（不存在）

读取 `JBS_PWEQUIPINFO` 时**不要**用：

- ❌ `SUBSTATION_ID`（实际是 `DSUBSTATION_ID`）

---

文档结束
