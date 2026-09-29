# LOCAL_LLM_RUBRIC.md — 离线评测标准（PDF 4 维度权威）

> **来源**：CP-202606 比赛方案.pdf §一/§二 + 评审手册_10页.md §0
> **公式**：总分 = 电气规则符合性 20% + 技术性能 45% + 工程泛化 20% + 成果完整 15%
> **旧公式已废**：自评 self_grade.py 原先使用的 coverage+exempt+sql+key 四维度公式**仅作内部进度参考**，不是官方分数。

---

## 1. 总公式

```
score_total = 0.20 * E + 0.45 * T + 0.20 * G + 0.15 * C
```

| 维度 | 权重 | 说明 |
|------|------|------|
| **E** 电气规则符合性 | 20% | KCL/KVL 通过 + 修正三原则（合规+最小+可行） |
| **T** 技术性能 | 45% | 12 子任务全跑 + 必杀题 T1/T2 + 高 confidence + 可回溯 + 鲁棒 |
| **G** 工程泛化 | 20% | 跨平台（Win/Mac/Linux）+ 字段缺失处理 + 跨电压等级 + 雪崩测试 |
| **C** 成果完整 | 15% | 源码注释 + 6 Sheet 输出 + 垂测报告 + 文档 + API |

**评级**：
- ≥ 0.90 → 优
- ≥ 0.75 → 良
- ≥ 0.60 → 中
- <  0.60 → 差（建议不提交）

---

## 2. E — 电气规则符合性（20%）

### 2.1 子项

| 子项 | 满分 | 评分细则 |
|------|------|----------|
| KCL 节点守恒 | 8% | 修正前后对每个联通子图取一个内部节点，验证 ΣI_in = ΣI_out；容差 0.5A |
| KVL 回路守恒 | 7% | 对每个 cycle 取电压降之和，验证 ΣU = 0；容差 2.0V |
| 修正三原则 | 5% | 合规性 2% + 最小化 1.5% + 可行性 1.5% |

### 2.2 跑分脚本

```python
from shared.kcl_kvl import check_kcl, check_kvl
from tasks_official.execution import OfficialRunner

ds = load_json_snapshot("data/snapshot.json")
result = OfficialRunner().run(["1.1","1.2","1.3","1.4","1.5","2.1","2.2","2.3","2.4","3.1","4.1","4.2"], ds)
records = [r for recs in result.records_by_task.values() for r in recs]

# 简化评分：检查 records 的 correction_sql 是否含 KCL/KVL 引用
kcl_hits = sum(1 for r in records if "KCL" in (r.description + r.correction).upper())
kvl_hits = sum(1 for r in records if "KVL" in (r.description + r.correction).upper())

# 完整评分：实际跑 KCL/KVL（需要修正后的快照）
# E_score = (kcl_pass + kvl_pass + three_principle_pass) / total_checks
```

### 2.3 缺分原因（前三）
- detector 没调用 `check_kcl` / `check_kvl`
- 修正 SQL 改变了 RUN_STATUS 但没重新计算 KCL
- 修正三原则未在 description 中体现（合规/最小/可行）

---

## 3. T — 技术性能（45%）

### 3.1 子项

| 子项 | 满分 | 评分细则 |
|------|------|----------|
| 12 子任务覆盖 | 15% | 每任务 1.25%；按 emit records >0 计 |
| 必杀题 T1/T2 | 8% | 1.2 detector 输出含两端配对 |
| 高 confidence | 5% | records.confidence 均值 ≥ 0.75 |
| 可回溯（证据） | 7% | 每 record 的 evidence 长度 ≥ 3 |
| 鲁棒（字段缺失） | 5% | 缺 RUN_STATUS / CN / PORT_NO 时降级而非崩溃 |
| SVG 5.x 任务 | 5% | 5.1/5.2/5.3 至少完成 5.3.1（数据库出图） |

### 3.2 跑分脚本

```python
T_score = 0
T_score += coverage / 12 * 0.15             # 12 子任务
T_score += (1 if t1_t2_pass else 0) / 1 * 0.08  # T1/T2
T_score += mean(confidences) / 1 * 0.05     # confidence
T_score += mean(evidence_lengths >= 3) * 0.07  # 证据
T_score += robustness_pass * 0.05            # 字段缺失
T_score += svg_5x_done / 1 * 0.05            # SVG 5.3.1
```

### 3.3 必杀题验证命令

```powershell
python -X utf8 -m unittest tests_official.test_bisha_official_T1_T2 -v
# 期望: Ran 3 tests OK
# T1 命中: TMP00013138<->TMP00047197
# T2 命中: TMP00007913<->TMP00007907
# 1.5: 至少 1 record（合环桥存在）
```

### 3.4 缺分原因（前三）
- 12 子任务未全部 emit records
- T1/T2 必杀题未命中（1.2 输出不含配对端）
- evidence 长度 < 3（未挂证据或只挂 1 个字段）

---

## 4. G — 工程泛化（20%）

### 4.1 子项

| 子项 | 满分 | 评分细则 |
|------|------|----------|
| 跨平台 | 5% | Windows + Mac + Linux 均能跑（无硬编码路径） |
| 字段缺失处理 | 8% | RUN_STATUS 缺 / CN 缺 / VOLTAGE_TYPE 缺 → 降级而非崩溃 |
| 跨电压等级 | 4% | 10kV / 110kV / 35kV / 220V 多等级共存不冲突 |
| 雪崩测试 | 3% | 10 万级设备数据下内存 < 1GB + 时间 < 60s |

### 4.2 跑分脚本

```python
# 字段缺失：故意构造缺字段的 snapshot
broken = copy.deepcopy(ds.tables)
for row in broken["JBS_PWEQUIPINFO"][:100]:
    row.pop("RUN_STATUS", None)
broken_ds = OfficialDataset(broken)
broken_ds.validate()  # 必须不抛
result = OfficialRunner().run([...], broken_ds)  # 必须不抛
G_score += 0.08 if not crashed else 0

# 跨电压等级：4 种 VOLTAGE_TYPE 共存
multi_v = sum(1 for r in records if r.extra.get("voltage_type") in [10, 35, 110, 220])
G_score += min(multi_v / 4, 1) * 0.04
```

### 4.3 缺分原因（前三）
- 路径硬编码 `E:\\` 等 Windows 路径
- 字段缺失直接 KeyError 崩溃
- 单 voltage level 写死

---

## 5. C — 成果完整（15%）

### 5.1 子项

| 子项 | 满分 | 评分细则 |
|------|------|----------|
| 源码注释 | 3% | 每个 detector 顶部 docstring 含：模块 / 算法 / SQL 模板 / 豁免 / 证据 |
| 6 Sheet 输出 | 5% | Sheet 1-6 全有 + 列名匹配 + 中文 |
| 垂测报告 | 3% | 含 T1-T10 测试通过日志 |
| 文档齐全 | 2% | PROMPT_GUIDE + FIELD_MAPPING + DETECTOR_PATTERNS + JUDGE + RUNBOOK |
| API 友好 | 2% | OfficialRunner.run() 接口清晰 + 异常有提示 |

### 5.2 跑分脚本

```python
import openpyxl
wb = openpyxl.load_workbook("data/_result_official.xlsx")
sheets_ok = len(wb.sheetnames) == 6
sheet1_cols = [c.value for c in wb["拓扑校验问题清单"][1]]
cols_ok = sheet1_cols == ["序号","一级分类","二级分类","问题设备id","问题设备名称","所属馈线","所属厂站","问题说明","修正方案","修正sql"]
C_score = 0.05 if (sheets_ok and cols_ok) else 0
```

---

## 6. 综合跑分命令（一份脚本搞定）

```powershell
cd E:\dianli\xiangmu\src\dianli\电力拓扑图修正\02_算法代码
python -X utf8 -m tasks_official.self_grade_v2 data/snapshot.json
```

**注意**：必须用 `-m` 方式运行（直接 `python tasks_official/self_grade_v2.py` 会因包路径报 `ModuleNotFoundError: No module named 'tasks_official'`）。

**期望输出**（合成数据实测基准；真实数据下数字会变，抄实际输出）：
```
=== PDF 4 维度评分 ===
电气规则符合性 (E): 1.00 / 1.00  (权重 0.20 -> 0.200)
技术性能       (T): 0.83 / 1.00  (权重 0.45 -> 0.376)
工程泛化       (G): 0.95 / 1.00  (权重 0.20 -> 0.190)
成果完整       (C): 0.97 / 1.00  (权重 0.15 -> 0.146)
========================================
总分: 0.912
评级: 优
```

---

## 7. 与 self_grade.py 的关系

| 文件 | 作用 |
|------|------|
| self_grade.py | **简版进度仪表**（coverage+exempt+sql+key），不计入提交分数 |
| self_grade_v2.py | **PDF 4 维度正式评分**（E+T+G+C），用于终评 |
| LOCAL_LLM_RUBRIC.md | **本文档**，定义评分公式和子项 |

---

## 8. 自评触发改进清单

LLM 收到自评分数后，按以下顺序改进：

| 分数 | 行动 |
|------|------|
| E < 0.10 | 1.2 / 1.5 detector 加 KCL/KVL 调用 |
| T < 0.30 | 检查 12 子任务是否都有 records；T1/T2 是否命中 |
| G < 0.10 | 检查 KeyError 风险；加 try/except 降级 |
| C < 0.10 | 补 docstring + Sheet 列名 + 文档 |
| 总分 < 0.60 | 不建议提交；先跑 bisha 测试 + 修复 |

---

## 9. 离线 LLM 自检清单

跑完一次端到端后，LLM 应自检：

- [ ] 12 detector 全部成功返回 records（允许 2.1 因缺 svg_devices 输入返回 0）
- [ ] T1: TMP00013138 ↔ TMP00047197 出现在 1.2 输出
- [ ] T2: TMP00007913 ↔ TMP00007907 出现在 1.2 输出
- [ ] T3: TMP00012903 ↔ TMP00047124（0821 新增输入对/负对照）——真实数据中真正
      连通（148 节点全闭合路径、无分位开关），按 Q&A2/Q16 **正确不报告**；
      仅当数据中该对断开时才须出现在 1.2 输出（official_pairs 保障）
- [ ] 1.5 至少 1 record（如有合环桥）
- [ ] 4.1/4.2 至少各 1 record
- [ ] 6 Sheet 全部生成，列名匹配
- [ ] 修正 SQL 通过 stdlib shape validator
- [ ] KCL/KVL 校验可调用（不必每条都通过，但 import 不报错）
- [ ] 8 豁免关键字全出现在 records.description 中（TRANS/XF/CUSTOMER/ROOM/CABLE_HEAD/SPARE/DISCONNECTOR/MEASURE）
- [ ] 所有 record.correction_sql 非空（除 1.4/2.2）
- [ ] 所有 record.evidence 长度 ≥ 3
- [ ] 中文描述 / 修正方案（无英文乱码）

---

## 10. 附录：PDF 原文摘录

> **电气规则符合性 20%**：KCL/KVL 校验通过 + 修正三原则
> **技术性能 45%**：12 子任务全跑 + 高精/可回溯/抗扰
> **工程泛化 20%**：跨平台 + 字段缺失处理
> **成果完整 15%**：源码注释 + 垂测报告 + 可视化 + 文档

引用：CP-202606 比赛方案.pdf §一/§二 + 评审手册_10页.md 第 1 页。

