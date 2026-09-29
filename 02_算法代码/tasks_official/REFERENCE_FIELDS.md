# CP-202606 14 官表字段详细参考

本文档详尽列出 14 张官表的字段、数据类型、约束、主键、用途,以及在 12 个 detector 中的使用位置。

## 主网(6 表)

### JBS_ZWSUBSTATION 主网站所

字段:
- SUBSTATION_ID - VARCHAR(主键) - 主网站所唯一标识
- SUBSTATION_NAME - VARCHAR - 站所名(用于显示)

用途:任务 1.3/1.4 联络开关跨站判定
关联:JBS_ZWEQUIPINFO.SUBSTATION_ID -> 本表

### JBS_ZWEQUIPINFO 主网设备

字段:
- EQUIP_ID - VARCHAR(主键) - 设备唯一 ID (前缀 TMP 或 OCR 代字)
- EQUIP_NAME - VARCHAR - 设备名(便于显示)
- EQUIP_TYPE - VARCHAR(外键 JBS_ZD_OBJECT) - 类型:
  - BREAKER 断路器
  - SWITCH 开关
  - DISCONNECTOR 隔离开关(可单端连接)
  - TRANSFORMER 变压器
  - TIE 联络开关
- VOLTAGE_TYPE - INT(外键 JBS_ZD_VOLTAGETYPE) - 电压等级
- RUN_STATUS - INT 0=分位 1=合位 - 实时运行状态
- SUBSTATION_ID - VARCHAR(外键 JBS_ZWSUBSTATION) - 所属站所

用途:任务 1.1/1.3/1.4/1.5/2.x/3.1 都涉及

### JBS_ZWLINEEND 主网线路端

字段:
- LINE_ID - VARCHAR - 线路 ID
- START_EQ_ID - VARCHAR - 起始设备 ID (外键 JBS_ZWEQUIPINFO)
- END_EQ_ID - VARCHAR - 终止设备 ID
- VOLTAGE_TYPE - INT - 电压等级

用途:任务 4.1 主配接口辅助匹配

### JBS_ZWTERMINAL 主网端点(拓扑节点)

字段:
- ID - VARCHAR(主键) - 端点 ID
- EQUIP_ID - VARCHAR(外键 JBS_ZWEQUIPINFO) - 所属设备
- CONNECTIVITYNODE_ID - VARCHAR - 拓扑连接点(共享即相连)

用途:任务 1.1/1.2/1.3/1.5/4.2 拓扑分析核心

### JBS_ZWMEA 主网量测

字段:
- TRAN_ID - VARCHAR - 测点设备 ID
- DATA_DATE - VARCHAR - 日期 YYYY-MM-DD
- V0000 ~ V2345 - 96 个 VARCHAR/VARCHAR2 - 96 个 15 分钟点电压值

用途:任务 3.1 电压匹配

### JBS_ZWSIGNAL 主网遥信

字段:
- ID - VARCHAR(主键) - 信号 ID
- POINT - INT 0=分位 1=合位 - 实时位置

用途:任务 1.3/1.4/2.3/2.4 实时分/合位对比

## 配网(5 表)

### JBS_PWFEEDERLINE 配网馈线

字段:
- LINE_ID - VARCHAR(主键) - 馈线 ID
- LINE_NAME - VARCHAR - 馈线全名
- START_ST_ID - VARCHAR(外键 JBS_ZWSUBSTATION) - 起始厂站
- VOLTAGE_TYPE - INT(外键 JBS_ZD_VOLTAGETYPE) - 电压等级

用途:任务 4.1 配网馈线入口判定

### JBS_PWROOM 配网站房(末端设备豁免)

字段:
- ROOM_ID - VARCHAR(主键) - 站房 ID
- ROOM_NAME - VARCHAR - 站房名
- TOP_VOLTAGE_TYPE - INT - 最高电压等级
- FEEDER_ID - VARCHAR(外键 JBS_PWFEEDERLINE) - 所属馈线

豁免:ROOM 类型设备的所有开关不纳入联络识别

### JBS_PWEQUIPINFO 配网设备

字段:
- EQUIP_ID - VARCHAR(主键) - 设备 ID
- EQUIP_NAME - VARCHAR - 设备名
- EQUIP_TYPE - VARCHAR(外键 JBS_ZD_OBJECT) - 类型
- VOLTAGE_TYPE - INT - 电压等级
- FEEDER_ID - VARCHAR - 所属馈线
- DSUBSTATION_ID - VARCHAR(外键 JBS_PWROOM) - 所属站房
- COMPOSITESWITCH - VARCHAR(外键 JBS_PWEQUIPINFO) - 所属组合开关

用途:任务 1.1/2.x/3.1/4.x 核心表

### JBS_PWTERMINAL 配网端点

字段:
- ID - VARCHAR(主键)
- EQUIP_ID - VARCHAR(外键 JBS_PWEQUIPINFO)
- CONNECTIVITYNODE_ID - VARCHAR - 拓扑连接点

用途:同 ZWTERMINAL,与 JBS_ZWTERMINAL 共享 CONNECTIVITYNODE_ID 联通主配

### JBS_PWREAL 配网设备遥测遥信

字段:
- NUM - VARCHAR - 序号
- TRAN_ID - VARCHAR - 设备 ID
- DATA_DATE - VARCHAR - 日期
- UA/UB/UC - VARCHAR - A/B/C 相电压
- IA/IB/IC - VARCHAR - A/B/C 相电流
- AP - VARCHAR - 有功功率 (kW)
- RP - VARCHAR - 无功功率 (kvar)
- POINT - VARCHAR - 0=分位 1=合位
- BDZ_ID - VARCHAR - 保护装置 ID
- FEEDER_ID - VARCHAR - 馈线 ID

注:PWREAL 用 UA/UB/UC 三相(每个设备 3 行);ZWMEA 用 V0000-V2345 96 点。任务 3.1 主用 PWREAL。

## 字典(3 表)

### JBS_ZD_OBJECT 对象类型

字段:
- OBJ_ID - VARCHAR(主键)
- OBJ_CODE - VARCHAR - 类型 code
- OBJ_CNNAME - VARCHAR - 中文名
- OBJ_ENNAME - VARCHAR - 英文名

关键 OBJ_CODE 值:
- BREAKER 断路器
- SWITCH 开关
- DISCONNECTOR 隔离开关
- TRANSFORMER 变压器
- TRANS 用户/配变
- CUSTOMER 用户
- XF 箱变
- ROOM 站房
- SPARE_BAY 备用间隔
- CABLE_HEAD 电缆终端头

### JBS_ZD_VOLTAGETYPE 电压等级

字段:
- VOLTAGE_ID - INTEGER(主键)
- VOLTAGE_NAME - VARCHAR - 等级名(10kV / 35kV / 110kV 等)

### JBS_ZD_MEASTYPE 量测类型

字段:
- CODE - INTEGER(主键)
- NAME_CHN - VARCHAR - 中文名(电流A / 电压A 等)

## 主键与外键汇总

主键与外键拓扑:
- 所有设备表主键 = EQUIP_ID
- 拓扑节点主键 = CONNECTIVITYNODE_ID (主配网共享)
- 所有字典主键 = OBJ_ID / VOLTAGE_ID / CODE

## 字段到任务的映射

| 任务 | 主要字段 |
|------|---------|
| 1.1 悬空 | EQUIP_ID, CONNECTIVITYNODE_ID, EQUIP_TYPE, EQUIP_NAME |
| 1.2 断点 | CONNECTIVITYNODE_ID (连通图) |
| 1.3 联络 | EQUIP_TYPE, RUN_STATUS, SUBSTATION_ID, CONNECTIVITYNODE_ID |
| 1.4 疑似 | 同 1.3 |
| 1.5 合环 | 同 1.3 |
| 2.1/2.2 图模 | EQUIP_ID, svg_devices (外部) |
| 2.3/2.4 连接 | EQUIP_ID, RUN_STATUS, CONNECTIVITYNODE_ID |
| 3.1 电压 | TRAN_ID, V0000~V2345 / UA/UB/UC, RUN_STATUS |
| 4.1 漏拼 | START_ST_ID, EQUIP_ID, FEEDER_ID, DSUBSTATION_ID |
| 4.2 错拼 | CONNECTIVITYNODE_ID, EQUIP_TYPE |

数据访问:
- 字典 (OBJ_CODE): tables.get(JBS_ZD_OBJECT, ())
- 设备: tables.get(JBS_PWEQUIPINFO, ()) + tables.get(JBS_ZWEQUIPINFO, ())
- 拓扑: tables.get(JBS_PWTERMINAL, ()) + tables.get(JBS_ZWTERMINAL, ())
- 量测: tables.get(JBS_PWREAL, ()) 或 tables.get(JBS_ZWMEA, ())
- 馈线: tables.get(JBS_PWFEEDERLINE, ())

---
文档结束 / End of document
