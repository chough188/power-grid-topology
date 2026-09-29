/* CP-202606 配电网图模拓扑智能识别与修正 — 比赛数据契约层 (api_competition.js)
 * 作用: 前端所有页面经此层取数, 严格对齐《拓扑校验问题标准输出.xlsx》6 张表 schema + 比赛 taxonomy。
 * 策略: 当前后端(tasks_official)未就绪, 先以「符合标准 schema 的样本数据」打通演示剧本。
 *       后端就绪后, 仅需修改此文件内部的 _fetch() 适配层(同一 schema, 零成本替换), 页面无需改动。
 * 调用示例:
 *   const r = await compApi.getProblems({ l1: '1', l2: '1.2' });   // sheet1 问题清单
 *   const bp = await compApi.getBreakpoints();                    // sheet2 断点定位
 *   const q  = await compApi.getQuality();                        // sheet5 质量评分
 */
(function (global) {
  "use strict";

  /* ============================================================
   * 0. 元信息
   * ========================================================== */
  var META = {
    project: "CP-202606 面向新型电力系统的配电网图模拓扑智能识别与修正",
    vendor: "泰豪软件股份有限公司",
    sample: true, // 当前模式标记; 唯一切换点见下方 BACKEND.useSample (改 false 即走真实接口, 页面零改动)
    schemaVersion: "标准输出 v1",
  };

  /* ============================================================
   * 1. 问题类型 Taxonomy (标准输出 sheet6: 一级/二级分类全量)
   * ========================================================== */
  var TAXONOMY = [
    { code: "1", name: "拓扑结构完整性检测", items: [
      { code: "1.1", name: "设备拓扑悬空检测任务" },
      { code: "1.2", name: "拓扑连通性异常诊断与断点定位任务" },
      { code: "1.3", name: "联络开关自动识别与可视化梳理任务" },
      { code: "1.4", name: "疑似联络开关智能识别与复核研判任务" },
      { code: "1.5", name: "非计划性合环拓扑识别任务" },
    ]},
    { code: "2", name: "图模一致性校验", items: [
      { code: "2.1", name: "图上有、模型无校验任务" },
      { code: "2.2", name: "模型有、图上无校验任务" },
      { code: "2.3", name: "图形物理连通、拓扑逻辑断开校验任务" },
      { code: "2.4", name: "图形物理断开、拓扑逻辑误连通校验任务" },
    ]},
    { code: "3", name: "电气逻辑校验", items: [
      { code: "3.1", name: "开关-电压基础状态匹配校验任务" },
    ]},
    { code: "4", name: "主配网接口拓扑完整性校验", items: [
      { code: "4.1", name: "主配接口漏拼接校验任务" },
      { code: "4.2", name: "主配接口错拼接校验任务" },
    ]},
  ];

  function l1Name(code) { var t = TAXONOMY.find(function (x) { return x.code === code; }); return t ? (t.code + " " + t.name) : code; }
  function l2Name(code) {
    for (var i = 0; i < TAXONOMY.length; i++) {
      var it = TAXONOMY[i].items.find(function (x) { return x.code === code; });
      if (it) return it.name;
    }
    return code;
  }

  /* ============================================================
   * 2. 样本数据 — 严格对齐各 sheet 列
   * ========================================================== */

  // sheet1: 序号/一级分类/二级分类/问题设备id/问题设备名称/所属馈线/所属厂站/问题说明/修正方案/修正sql
  var PROBLEM_LIST = [
    { seq: 1, l1: "1", l2: "1.1", devId: "TMP00013138", devName: "10kV分段开关", feeder: "LINE215 215线", station: "SUB004 兴港变电站",
      desc: "10kV分段开关(TMP00013138)一侧拓扑悬空, 仅与母线单端连接, 对侧联络缺失。", fix: "依据接线图示意, 该分段开关应与TMP00047197建立联络连线。",
      sql: "UPDATE topo_connectivity SET to_device_id='TMP00047197', status='connected' WHERE device_id='TMP00013138' AND end='B';", suspType: "单端悬空" },
    { seq: 2, l1: "1", l2: "1.1", devId: "TMP00007913", devName: "10kV负荷开关", feeder: "LINE074 074线", station: "SUB004 兴港变电站",
      desc: "10kV负荷开关(TMP00007913)为单端悬空端点, 另一侧未与任何设备连通。", fix: "按图纸将其与TMP00007907进线侧相连。",
      sql: "UPDATE topo_connectivity SET to_device_id='TMP00007907' WHERE device_id='TMP00007913' AND end='B';", suspType: "单端悬空" },
    { seq: 3, l1: "1", l2: "1.2", devId: "TMP00013138", devName: "10kV分段开关", feeder: "LINE215 215线", station: "SUB004 兴港变电站",
      desc: "拓扑检索 TMP00013138→TMP00047197 路径中断, 存在开关分断/拓扑断连。", fix: "定位断点为TMP00047197本侧, 补接联络连线并核对开关分合位。",
      sql: "UPDATE topo_device SET connect_state='1' WHERE device_id='TMP00047197';" },
    { seq: 4, l1: "1", l2: "1.2", devId: "TMP00007913", devName: "10kV负荷开关", feeder: "LINE074 074线", station: "SUB004 兴港变电站",
      desc: "拓扑检索 TMP00007913→TMP00007907 路径中断, 疑似断点位于TMP00007907对侧。", fix: "补接TMP00007907出线侧连线, 恢复拓扑通道。",
      sql: "INSERT INTO topo_connectivity(device_id, end, to_device_id, status) VALUES('TMP00007907','A','TMP00007913','connected');" },
    { seq: 5, l1: "1", l2: "1.3", devId: "LKS00021516", devName: "联络开关", feeder: "LINE215 215线", station: "SUB004 兴港变电站",
      desc: "215线与216线之间存在合规联络开关(分位, 两侧均连通变电站母线)。", fix: "纳入全网联络台账, 配对馈线LINE215↔LINE216。",
      sql: "UPDATE tie_switch SET pair_feeder='LINE216' WHERE switch_id='LKS00021516';" },
    { seq: 6, l1: "1", l2: "1.4", devId: "LKS00007403", devName: "疑似联络开关(分闸非检修)", feeder: "LINE074 074线", station: "SUB004 兴港变电站",
      desc: "分闸非检修状态开关, 单侧连通变电站母线, 另一侧拓扑异常, 疑似联络开关。", fix: "复核对侧拓扑缺失诱因, 输出标准化整改建议后转人工研判。",
      sql: "UPDATE tie_switch SET suspect='1', review='pending' WHERE switch_id='LKS00007403';" },
    { seq: 7, l1: "1", l2: "1.5", devId: "TMP00022081", devName: "10kV环网柜开关", feeder: "LINE216 216线", station: "SUB004 兴港变电站",
      desc: "216线内设备私自搭建闭环, 形成不合规拓扑结构(违规合环)。", fix: "断开私自合环点TMP00022081, 恢复单辐射运行方式。",
      sql: "UPDATE topo_device SET connect_state='0' WHERE device_id='TMP00022081';" },
    { seq: 8, l1: "2", l2: "2.1", devId: "TMP00034205", devName: "10kV配变0486", feeder: "LINE074 074线", station: "SUB004 兴港变电站",
      desc: "图纸上有配变0486(TMP00034205), 但后台模型无该设备记录(图存模无)。", fix: "将配变0486补录至模型, 建立物理-模型一致台账。",
      sql: "INSERT INTO topo_device(device_id, name, type, feeder_id) VALUES('TMP00034205','10kV配变0486','transformer','LINE074');" },
    { seq: 9, l1: "2", l2: "2.2", devId: "TMP00090012", devName: "10kV刀闸", feeder: "LINE215 215线", station: "SUB004 兴港变电站",
      desc: "模型中存在刀闸TMP00090012, 但图纸上无对应图元(模存图无)。", fix: "在图纸补绘该刀闸图元或核实模型冗余后清理。",
      sql: "INSERT INTO drawing_symbol(device_id, symbol, status) VALUES('TMP00090012','disconnector','pending');" },
    { seq: 10, l1: "2", l2: "2.3", devId: "TMP00047197", devName: "10kV分段开关", feeder: "LINE215 215线", station: "SUB004 兴港变电站",
      desc: "图形物理连通, 但拓扑逻辑断开(模型未生成关联链路)。", fix: "重建TMP00047197与下游设备的逻辑关联, 消除虚假断开。",
      sql: "INSERT INTO topo_connectivity(device_id, end, to_device_id, status) VALUES('TMP00047197','B','TMP00013138','connected');" },
    { seq: 11, l1: "2", l2: "2.4", devId: "TMP00022081", devName: "10kV环网柜开关", feeder: "LINE216 216线", station: "SUB004 兴港变电站",
      desc: "图形物理断开, 但模型误生成关联链路, 形成虚假拓扑连通。", fix: "断开模型错误链路, 还原物理断开真实状态。",
      sql: "DELETE FROM topo_connectivity WHERE device_id='TMP00022081' AND to_device_id='TMP00022082';" },
    { seq: 12, l1: "3", l2: "3.1", devId: "TMP00013138", devName: "10kV分段开关", feeder: "LINE215 215线", station: "SUB004 兴港变电站",
      desc: "开关处于分位, 但其电压量测显示带电(10.2kV), 开关-电压基础状态不匹配。", fix: "核实开关实际分合位与遥测一致性, 修正状态或量测异常。",
      sql: "UPDATE topo_device SET voltage_state='live', state_match='0' WHERE device_id='TMP00013138';" },
    { seq: 13, l1: "3", l2: "3.1", devId: "TMP00090012", devName: "10kV刀闸", feeder: "LINE215 215线", station: "SUB004 兴港变电站",
      desc: "刀闸显示合位但两侧电压不一致, 状态匹配异常。", fix: "复核刀闸两侧电压量测, 修正遥信遥测不一致。",
      sql: "UPDATE topo_device SET state_match='0' WHERE device_id='TMP00090012';" },
    { seq: 14, l1: "4", l2: "4.1", devId: "BUS10KVA", devName: "10kV I段母线出线间隔", feeder: "10kVLINE111", station: "SUB004 兴港变电站",
      desc: "主网10kV I段母线出线间隔与配网进线设备未建立对接关联(主配接口漏拼接)。", fix: "补全主配网接口对接台账, 建立出线间隔↔配网进线关联。",
      sql: "INSERT INTO main_dist_join(main_device, dist_device, status) VALUES('BUS10KVA','LINE111','linked');" },
    { seq: 15, l1: "4", l2: "4.2", devId: "BUS10KVB", devName: "10kV II段母线出线间隔", feeder: "10kVLINE111", station: "SUB004 兴港变电站",
      desc: "主网出线间隔BUS10KVB错误对接到非本段母线配网进线(主配接口错拼接)。", fix: "更正对接关系至正确配网进线, 消除跨层级错拼接。",
      sql: "UPDATE main_dist_join SET dist_device='LINE111_B' WHERE main_device='BUS10KVB';" },
    { seq: 16, l1: "1", l2: "1.1", devId: "TMP00030001", devName: "配电站房进线开关", feeder: "LINE216 216线", station: "000300 新建站房",
      desc: "新建站房000300进线开关单端悬空(仅进线无出线, 末端配置)。", fix: "核实末端设备豁免规则, 站房内部开关不纳入悬空判定。",
      sql: "-- 末端设备豁免: 无需修正", suspType: "末端设备·豁免" },
    { seq: 17, l1: "2", l2: "2.1", devId: "TMP00030002", devName: "10kV负荷开关", feeder: "LINE216 216线", station: "000300 新建站房",
      desc: "站房000300新增负荷开关图纸存在, 模型未同步(图存模无)。", fix: "同步站房000300新增的3台负荷开关至模型。",
      sql: "INSERT INTO topo_device(device_id, name, type, feeder_id) VALUES('TMP00030002','负荷开关','switch','LINE216');" },
    { seq: 18, l1: "2", l2: "2.2", devId: "TMP00000024", devName: "10kV开关00024", feeder: "LINE215 215线", station: "SUB004 兴港变电站",
      desc: "模型中存在开关00024, 图纸已删除该设备(模存图无)。", fix: "图纸删除开关00024并自动连通两侧, 清理模型冗余记录。",
      sql: "DELETE FROM topo_device WHERE device_id='TMP00000024';" },
    { seq: 19, l1: "1", l2: "1.3", devId: "LKS00011105", devName: "联络开关", feeder: "10kVLINE111", station: "SUB004 兴港变电站",
      desc: "111线与215线间联络开关识别合规, 纳入联络台账。", fix: "配对馈线10kVLINE111↔LINE215。",
      sql: "UPDATE tie_switch SET pair_feeder='LINE215' WHERE switch_id='LKS00011105';" },
    { seq: 20, l1: "1", l2: "1.5", devId: "TMP00022082", devName: "10kV环网柜开关", feeder: "LINE216 216线", station: "SUB004 兴港变电站",
      desc: "216线分支存在隐蔽性违规合环(TMP00022081↔TMP00022082)。", fix: "断开违规合环支路, 恢复辐射状供电。",
      sql: "UPDATE topo_device SET connect_state='0' WHERE device_id='TMP00022082';" },
    { seq: 21, l1: "3", l2: "3.1", devId: "TMP00034205", devName: "10kV配变0486", feeder: "LINE074 074线", station: "SUB004 兴港变电站",
      desc: "配变0486(TMP00034205)电压量测缺失, 开关-电压状态无法校验。", fix: "补采配变0486电压遥测, 完善电气逻辑校验输入。",
      sql: "UPDATE topo_device SET voltage_state='unknown', state_match='null' WHERE device_id='TMP00034205';" },
    { seq: 22, l1: "4", l2: "4.1", devId: "BUS35KVA", devName: "35kV母线出线间隔", feeder: "LINE215 215线", station: "SUB004 兴港变电站",
      desc: "35kV主网出线与10kV配网进线接口未拼接(跨电压等级对接缺失)。", fix: "建立35kV出线间隔与对应10kV配变主配接口关联。",
      sql: "INSERT INTO main_dist_join(main_device, dist_device, status) VALUES('BUS35KVA','TMP00034205','linked');" },
    { seq: 23, l1: "2", l2: "2.4", devId: "TMP00047197", devName: "10kV分段开关", feeder: "LINE215 215线", station: "SUB004 兴港变电站",
      desc: "模型误将TMP00047197与TMP00007907连通, 物理上二者不属于同一通道(误连通)。", fix: "删除跨通道错误逻辑链路。",
      sql: "DELETE FROM topo_connectivity WHERE device_id='TMP00047197' AND to_device_id='TMP00007907';" },
    { seq: 24, l1: "1", l2: "1.4", devId: "LKS00021507", devName: "疑似联络开关(分闸非检修)", feeder: "LINE215 215线", station: "SUB004 兴港变电站",
      desc: "分闸非检修开关, 单侧连通母线, 另一侧线路断连, 疑似联络开关。", fix: "区分线路断连诱因, 输出整改建议后人工复核。",
      sql: "UPDATE tie_switch SET suspect='1', review='pending' WHERE switch_id='LKS00021507';" },
  ];

  // sheet2: 序号/起点设备id/终点设备id/断点类型/本侧疑似断点设备id/本侧疑似断点设备名称/对侧疑似断点设备id/对侧疑似断点设备名称/修正方案/修正sql
  // (注: 标准表头无"名称"列于本侧/对侧, 此处按任务书对齐保留名称便于展示; 导出时提供标准10列)
  var BREAKPOINTS = [
    { seq: 1, startId: "TMP00013138", endId: "TMP00047197", breakType: "开关分断/拓扑断连",
      thisSideId: "TMP00047197", thisSideName: "10kV分段开关", otherSideId: "TMP00013138", otherSideName: "10kV分段开关",
      note: "注意不经过末端配电站房, 即站房内仅有进线无出线。",
      fix: "补接TMP00047197本侧联络连线, 核对开关分合位后恢复通道。",
      sql: "UPDATE topo_connectivity SET to_device_id='TMP00013138', status='connected' WHERE device_id='TMP00047197' AND end='B';" },
    { seq: 2, startId: "TMP00007913", endId: "TMP00007907", breakType: "线路断连/拓扑断连",
      thisSideId: "TMP00007907", thisSideName: "10kV进线开关", otherSideId: "TMP00007913", otherSideName: "10kV负荷开关",
      note: "路径内存在物理断连, 未经过末端配电站房。",
      fix: "补接TMP00007907出线侧连线至TMP00007913, 恢复拓扑通道。",
      sql: "INSERT INTO topo_connectivity(device_id, end, to_device_id, status) VALUES('TMP00007907','A','TMP00007913','connected');" },
  ];

  // sheet3: 线路id/线路名称/上级变电站名称/联络开关id/联络开关名称/是否有联络/联络线路id/联络线路名称/联络线变电站名称
  var TIE_SWITCHES = [
    { lineId: "LINE215", lineName: "215线", substation: "SUB004 兴港变电站", swId: "LKS00021516", swName: "联络开关", hasTie: "是", tieLineId: "LINE216", tieLineName: "216线", tieSub: "SUB004 兴港变电站" },
    { lineId: "10kVLINE111", lineName: "111线", substation: "SUB004 兴港变电站", swId: "LKS00011105", swName: "联络开关", hasTie: "是", tieLineId: "LINE215", tieLineName: "215线", tieSub: "SUB004 兴港变电站" },
    { lineId: "LINE216", lineName: "216线", substation: "SUB004 兴港变电站", swId: "LKS00021516", swName: "联络开关", hasTie: "是", tieLineId: "LINE215", tieLineName: "215线", tieSub: "SUB004 兴港变电站" },
    { lineId: "LINE074", lineName: "074线", substation: "SUB004 兴港变电站", swId: "—", swName: "—", hasTie: "否", tieLineId: "—", tieLineName: "—", tieSub: "—" },
  ];

  // sheet4: 线路id/线路名称/上级变电站名称/合环线路id/合环线路名称/合环线变电站名称/疑似联络开关id/疑似联络开关名称/修正sql
  var LOOPS = [
    { lineId: "LINE216", lineName: "216线", substation: "SUB004 兴港变电站", loopLineId: "LINE216", loopLineName: "216线(支)", loopSub: "SUB004 兴港变电站",
      suspectSwId: "TMP00022081", suspectSwName: "10kV环网柜开关", sql: "UPDATE topo_device SET connect_state='0' WHERE device_id='TMP00022081';" },
    { lineId: "LINE216", lineName: "216线", substation: "SUB004 兴港变电站", loopLineId: "LINE216", loopLineName: "216线(支)", loopSub: "SUB004 兴港变电站",
      suspectSwId: "TMP00022082", suspectSwName: "10kV环网柜开关", sql: "UPDATE topo_device SET connect_state='0' WHERE device_id='TMP00022082';" },
  ];

  // sheet5: 序号/厂站名称/厂站id/馈线名称/馈线id/修正前评分/修正后评分
  var QUALITY = [
    { seq: 1, station: "SUB004 兴港变电站", stationId: "SUB004", feeder: "LINE215 215线", feederId: "LINE215", before: 80, after: 93 },
    { seq: 2, station: "SUB004 兴港变电站", stationId: "SUB004", feeder: "LINE216 216线", feederId: "LINE216", before: 78, after: 91 },
    { seq: 3, station: "SUB004 兴港变电站", stationId: "SUB004", feeder: "LINE074 074线", feederId: "LINE074", before: 72, after: 88 },
    { seq: 4, station: "SUB004 兴港变电站", stationId: "SUB004", feeder: "10kVLINE111 111线", feederId: "10kVLINE111", before: 85, after: 95 },
    { seq: 5, station: "000300 新建站房", stationId: "000300", feeder: "LINE216 216线", feederId: "LINE216", before: 65, after: 90 },
  ];

  // 模块五 4 维度评分(雷达): 拓扑完整性 / 图模一致性 / 电气逻辑 / 主配网规范 (before/after, 0-100)
  var QUALITY_DIM = {
    SUB004: { before: [80, 76, 82, 74], after: [94, 92, 95, 90] },
    "000300": { before: [60, 70, 68, 55], after: [92, 88, 90, 86] },
  };
  var QUALITY_DIM_AXES = ["拓扑完整性", "图模一致性", "电气逻辑", "主配网规范"];

  /* ============================================================
   * 3. SVG 任务二 数据 (5.1 美化 + 5.3 自动出图)
   * ========================================================== */
  // 3.1 原始(未美化)SVG 样本 — LINE215 / LINE216 (用于 5.1 标准化美化对比)
  var RAW_SVG = {
    LINE215: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 420" width="760" height="420" font-family="sans-serif">\n' +
      '  <rect width="760" height="420" fill="#ffffff"/>\n' +
      '  <text x="20" y="30" font-size="18" font-weight="bold">LINE215 单线图(原始)</text>\n' +
      '  <rect x="40" y="80" width="120" height="40" fill="#cccccc" stroke="#333"/><text x="60" y="105" font-size="12">10kV母线</text>\n' +
      '  <line x1="160" y1="100" x2="260" y2="100" stroke="#333" stroke-width="2"/>\n' +
      '  <circle cx="260" cy="100" r="14" fill="#fff" stroke="#333" stroke-width="2"/><text x="240" y="80" font-size="11">分段</text>\n' +
      '  <line x1="274" y1="100" x2="420" y2="100" stroke="#333" stroke-width="2"/>\n' +
      '  <rect x="420" y="84" width="40" height="32" fill="#fff" stroke="#333"/><text x="424" y="105" font-size="10">变0486</text>\n' +
      '  <line x1="460" y1="100" x2="600" y2="100" stroke="#333" stroke-width="2"/>\n' +
      '  <circle cx="600" cy="100" r="14" fill="#fff" stroke="#333" stroke-width="2"/><text x="582" y="80" font-size="10">联络</text>\n' +
      '  <line x1="614" y1="100" x2="700" y2="100" stroke="#999" stroke-width="2" stroke-dasharray="4 3"/>\n' +
      '  <text x="700" y="105" font-size="10">216线</text>\n' +
      '</svg>',
    LINE216: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 420" width="760" height="420" font-family="sans-serif">\n' +
      '  <rect width="760" height="420" fill="#ffffff"/>\n' +
      '  <text x="20" y="30" font-size="18" font-weight="bold">LINE216 单线图(原始)</text>\n' +
      '  <rect x="40" y="120" width="120" height="40" fill="#cccccc" stroke="#333"/><text x="60" y="145" font-size="12">10kV母线</text>\n' +
      '  <line x1="160" y1="140" x2="300" y2="140" stroke="#333" stroke-width="2"/>\n' +
      '  <rect x="300" y="124" width="40" height="32" fill="#fff" stroke="#333"/><text x="304" y="145" font-size="10">环网</text>\n' +
      '  <line x1="340" y1="140" x2="480" y2="200" stroke="#f00" stroke-width="2"/><text x="400" y="170" font-size="10">合环!</text>\n' +
      '  <line x1="340" y1="140" x2="480" y2="80" stroke="#333" stroke-width="2"/>\n' +
      '  <circle cx="480" cy="200" r="14" fill="#fff" stroke="#333" stroke-width="2"/><text x="460" y="225" font-size="10">负荷</text>\n' +
      '  <circle cx="480" cy="80" r="14" fill="#fff" stroke="#333" stroke-width="2"/><text x="460" y="60" font-size="10">联络</text>\n' +
      '</svg>',
  };

  // 3.2 拓扑模型(用于 5.3 自动出图) — 以节点/边描述, 渲染时计算布局
  // type: bus(母线)/source(电源点)/switch(开关)/transformer(配变)/load(负荷)/station(站房容器)
  var GRAPHS = {
    LINE215: {
      name: "LINE215 215线", voltage: "10kV", substation: "SUB004 兴港变电站",
      nodes: [
        { id: "BUS", name: "10kV I段母线", type: "bus", feederSource: true },
        { id: "TMP00013138", name: "分段开关", type: "switch" },
        { id: "TMP00047197", name: "分段开关", type: "switch" },
        { id: "TMP00034205", name: "配变0486", type: "transformer" },
        { id: "TMP00090012", name: "刀闸", type: "switch" },
        { id: "LKS00021516", name: "联络开关", type: "switch", tie: true },
        { id: "LOAD215A", name: "负荷A", type: "load" },
      ],
      edges: [
        { from: "BUS", to: "TMP00013138" },
        { from: "TMP00013138", to: "TMP00047197" },
        { from: "TMP00047197", to: "TMP00034205" },
        { from: "TMP00034205", to: "TMP00090012" },
        { from: "TMP00090012", to: "LOAD215A" },
        { from: "TMP00047197", to: "LKS00021516" },
      ],
    },
    LINE216: {
      name: "LINE216 216线", voltage: "10kV", substation: "SUB004 兴港变电站",
      nodes: [
        { id: "BUS2", name: "10kV II段母线", type: "bus", feederSource: true },
        { id: "TMP00022081", name: "环网柜开关", type: "switch", loop: true },
        { id: "TMP00022082", name: "环网柜开关", type: "switch", loop: true },
        { id: "LOAD216A", name: "负荷B", type: "load" },
        { id: "LKS00021516", name: "联络开关", type: "switch", tie: true },
        { id: "LOAD216B", name: "负荷C", type: "load" },
      ],
      edges: [
        { from: "BUS2", to: "TMP00022081" },
        { from: "TMP00022081", to: "TMP00022082" },
        { from: "TMP00022082", to: "LOAD216A" },
        { from: "TMP00022081", to: "LKS00021516" },
        { from: "BUS2", to: "LOAD216B" },
      ],
    },
    LINE310: {
      name: "LINE310 310线", voltage: "10kV", substation: "SUB007 临港变电站",
      nodes: [
        { id: "BUS310", name: "10kV母线", type: "bus", feederSource: true },
        { id: "SW310", name: "开关", type: "switch" },
        { id: "LKS00031015", name: "联络开关", type: "switch", tie: true },
        { id: "LOAD310", name: "负荷", type: "load" },
      ],
      edges: [ { from: "BUS310", to: "SW310" }, { from: "SW310", to: "LKS00031015" }, { from: "SW310", to: "LOAD310" } ],
    },
    LINE311: {
      name: "LINE311 311线", voltage: "10kV", substation: "SUB007 临港变电站",
      nodes: [
        { id: "BUS311", name: "10kV母线", type: "bus", feederSource: true },
        { id: "SW311", name: "开关", type: "switch" },
        { id: "LOAD311", name: "负荷", type: "load" },
      ],
      edges: [ { from: "BUS311", to: "SW311" }, { from: "SW311", to: "LOAD311" } ],
    },
  };

  // 3.3 电源追溯演示图(5.3.4): LINE074 配变0486 的主供路径 + 备供路径(经联络开关接入对侧 LINE215 电源)
  var TRACE_GRAPH = {
    name: "LINE074 电源追溯(含备供)", voltage: "10kV", substation: "SUB004 兴港变电站",
    nodes: [
      { id: "BUS074", name: "10kV母线(074主供)", type: "bus", feederSource: true },
      { id: "SW074", name: "开关00104", type: "switch" },
      { id: "TMP00034205", name: "配变0486", type: "transformer" },
      { id: "LKS074", name: "联络开关", type: "switch", tie: true },
      { id: "SW215", name: "分段开关", type: "switch" },
      { id: "BUS215", name: "10kV母线(215备供)", type: "bus", feederSource: true },
    ],
    edges: [
      { from: "BUS074", to: "SW074" },
      { from: "SW074", to: "TMP00034205" },
      { from: "SW074", to: "LKS074" },
      { from: "LKS074", to: "SW215" },
      { from: "SW215", to: "BUS215" },
    ],
  };

  // 跨站联络(用于 5.3.3 全站间馈线联络总图): SUB007 经联络开关与 SUB004 互联
  var TIE_CROSS = [
    { from: "LINE310", to: "LINE215", viaTie: "LKS00031015", cross: true },
  ];

  /* ============================================================
   * 4. 适配层 — 全站唯一数据出入口 (后端就绪后仅改 BACKEND 区块)
   *    - 单一开关: BACKEND.useSample = true  → 内存样本 (_sampleStore)
   *                BACKEND.useSample = false → 真实 HTTP 接口 (_realFetch)
   *    - 真实接口约定: BASE + '/' + kind (方法见 BACKEND.method), 返回与样本同 schema 的 JSON
   *    - 各 pages/*.html 完全不感知取数来源, 零改动即可切换后端
   * ========================================================== */
  var BACKEND = {
    useSample: true,        // ← 后端就绪改为 false (全站唯一切换点)
    fallbackToSampleOnError: true, // 真实接口异常(超时/HTTP/网络)时降级到样本, 保证演示不白屏; 后端稳定后改 false
    base: "/api/comp",      // 真实接口前缀, 按部署环境修改
    method: "POST",         // 真实接口默认方法; 后端若用 GET, 改为 "GET"
    timeoutMs: 15000,       // 超时保护, 避免页面在网络异常时永久挂起
  };
  // 保持 META.sample 展示标记与单一开关同步
  META.sample = BACKEND.useSample;

  // 真实数据源: 走标准 fetch, 入参/出参 schema 与 _sampleStore 完全一致
  function _realFetch(kind, params) {
    var url = BACKEND.base.replace(/\/+$/, "") + "/" + kind;
    var opts = {
      method: BACKEND.method,
      headers: { "Accept": "application/json", "Content-Type": "application/json" },
      credentials: "same-origin",
    };
    if (BACKEND.method === "GET" && params) {
      var q = Object.keys(params).map(function (k) {
        return encodeURIComponent(k) + "=" + encodeURIComponent(params[k]);
      }).join("&");
      if (q) url += "?" + q;
    } else if (params) {
      opts.body = JSON.stringify(params);
    }
    return new Promise(function (resolve, reject) {
      var settled = false;
      var timer = setTimeout(function () {
        if (!settled) { settled = true; reject(new Error("[compApi] 请求超时: " + url)); }
      }, BACKEND.timeoutMs);
      fetch(url, opts)
        .then(function (r) { if (!r.ok) throw new Error("[compApi] HTTP " + r.status + " " + url); return r.json(); })
        .then(function (data) { if (!settled) { settled = true; clearTimeout(timer); resolve(data); } })
        .catch(function (err) { if (!settled) { settled = true; clearTimeout(timer); reject(err); } });
    });
  }

  // 统一出口: 全部 compApi.get* 经此函数取数
  function _fetch(kind, params) {
    if (BACKEND.useSample) return Promise.resolve(_sampleStore(kind, params));
    // 后端就绪后走真实接口; 若开启 fallbackToSampleOnError, 真实接口异常时优雅降级到样本,
    // 避免答辩演示因后端偶发抖动而白屏(数据 schema 与样本一致, 仅来源不同)。
    if (!BACKEND.fallbackToSampleOnError) return _realFetch(kind, params);
    return _realFetch(kind, params).catch(function (err) {
      console.warn("[compApi] 真实接口失败, 降级到样本数据:", err && err.message, "(kind=" + kind + ")");
      return _sampleStore(kind, params);
    });
  }
  function _sampleStore(kind, params) {
    switch (kind) {
      case "problems": return filterProblems(PROBLEM_LIST, params || {});
      case "taxonomy": return TAXONOMY;
      case "breakpoints": return BREAKPOINTS;
      case "tieSwitches": return TIE_SWITCHES;
      case "loops": return LOOPS;
      case "quality": return QUALITY;
      case "qualityDim": return QUALITY_DIM;
      case "rawSvg": return RAW_SVG[(params && params.line) || "LINE215"] || "";
      case "graph": return GRAPHS[(params && params.line) || "LINE215"] || null;
      case "graphs": return GRAPHS;
      case "traceGraph": return TRACE_GRAPH;
      default: return [];
    }
  }
  function filterProblems(list, p) {
    return list.filter(function (x) {
      if (p.l1 && x.l1 !== p.l1) return false;
      if (p.l2 && x.l2 !== p.l2) return false;
      if (p.feeder && x.feeder.indexOf(p.feeder) < 0) return false;
      if (p.station && x.station.indexOf(p.station) < 0) return false;
      if (p.q) {
        var hay = (x.devId + x.devName + x.desc + x.fix).toLowerCase();
        if (hay.indexOf(String(p.q).toLowerCase()) < 0) return false;
      }
      return true;
    });
  }

  /* ============================================================
   * 5. 公共 API
   * ========================================================== */
  var compApi = {
    META: META,
    TAXONOMY: TAXONOMY,
    l1Name: l1Name,
    l2Name: l2Name,
    QUALITY_DIM_AXES: QUALITY_DIM_AXES,

    getMeta: function () { return Promise.resolve(META); },
    getTaxonomy: function () { return _fetch("taxonomy"); },
    getProblems: function (params) { return _fetch("problems", params); },
    getBreakpoints: function () { return _fetch("breakpoints"); },
    getTieSwitches: function () { return _fetch("tieSwitches"); },
    getLoops: function () { return _fetch("loops"); },
    getQuality: function () { return _fetch("quality"); },
    getQualityDim: function (stationId) {
      return _fetch("qualityDim").then(function (d) { return stationId ? (d[stationId] || null) : d; });
    },
    getRawSvg: function (line) { return _fetch("rawSvg", { line: line }); },
    getGraph: function (line) { return _fetch("graph", { line: line }); },
    getGraphs: function () { return _fetch("graphs"); },
    getTraceGraph: function () { return _fetch("traceGraph"); },
    // 联络关系(含跨站): 由 sheet3 派生的同站配对 + TIE_CROSS 跨站配对
    getStationTies: function () {
      var intra = TIE_SWITCHES.filter(function (t) { return t.tieLineId !== "—"; }).map(function (t) { return { from: t.lineId, to: t.tieLineId, viaTie: t.swId, cross: false }; });
      return intra.concat(TIE_CROSS);
    },

    // 仪表盘汇总(运营总览)
    getDashboard: function () {
      var by = {}; TAXONOMY.forEach(function (t) { t.items.forEach(function (it) { by[it.code] = 0; }); });
      PROBLEM_LIST.forEach(function (p) { if (by[p.l2] !== undefined) by[p.l2]++; });
      var counts = TAXONOMY.map(function (t) {
        return { code: t.code, name: t.name, total: t.items.reduce(function (s, it) { return s + by[it.code]; }, 0), items: t.items.map(function (it) { return { code: it.code, name: it.name, count: by[it.code] }; }) };
      });
      var total = PROBLEM_LIST.length;
      var avgBefore = (QUALITY.reduce(function (s, q) { return s + q.before; }, 0) / QUALITY.length).toFixed(1);
      var avgAfter = (QUALITY.reduce(function (s, q) { return s + q.after; }, 0) / QUALITY.length).toFixed(1);
      return Promise.resolve({
        total: total,
        byCategory: counts,
        breakpoints: BREAKPOINTS.length,
        tieSwitches: TIE_SWITCHES.filter(function (x) { return x.hasTie === "是"; }).length,
        loops: LOOPS.length,
        qualityAvgBefore: avgBefore,
        qualityAvgAfter: avgAfter,
        qualityImprove: (avgAfter - avgBefore).toFixed(1),
      });
    },

    // 导出《拓扑校验问题标准输出.xlsx》标准 6 表头(供 reports 页使用)
    STANDARD_HEADERS: {
      problems: ["序号", "一级分类", "二级分类", "问题设备id", "问题设备名称", "所属馈线", "所属厂站", "问题说明", "修正方案", "修正sql"],
      breakpoints: ["序号", "起点设备id", "终点设备id", "断点类型", "本侧疑似断点设备id", "本侧疑似断点设备名称", "对侧疑似断点设备id", "对侧疑似断点设备名称", "修正方案", "修正sql", "备注"],
      tieSwitches: ["线路id", "线路名称", "上级变电站名称", "联络开关id", "联络开关名称", "是否有联络", "联络线路id", "联络线路名称", "联络线变电站名称"],
      loops: ["线路id", "线路名称", "上级变电站名称", "合环线路id", "合环线路名称", "合环线变电站名称", "疑似联络开关id", "疑似联络开关名称", "修正sql"],
      quality: ["序号", "厂站名称", "厂站id", "馈线名称", "馈线id", "修正前评分", "修正后评分"],
      taxonomy: ["一级分类", "二级分类"],
    },
  };

  global.compApi = compApi;
})(typeof window !== "undefined" ? window : globalThis);
