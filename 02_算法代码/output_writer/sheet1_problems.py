from .workbook_schema import SHEETS

SHEET = SHEETS[0]

# Official 12 sub-task names from 比赛要求/拓扑校验问题标准输出.xlsx Sheet 6
CATEGORY_MAP = {
    "1.1": ("1 拓扑结构完整性检测", "1.1 设备拓扑悬空检测任务"),
    "1.2": ("1 拓扑结构完整性检测", "1.2 拓扑连通性异常诊断与断点定位任务"),
    "1.3": ("1 拓扑结构完整性检测", "1.3 联络开关自动识别与可视化梳理任务"),
    "1.4": ("1 拓扑结构完整性检测", "1.4 疑似联络开关智能识别与复核研判任务"),
    "1.5": ("1 拓扑结构完整性检测", "1.5 非计划性合环拓扑识别任务"),
    "2.1": ("2 图模一致性校验", "2.1 图上有、模型无校验任务"),
    "2.2": ("2 图模一致性校验", "2.2 模型有、图上无校验任务"),
    "2.3": ("2 图模一致性校验", "2.3 图形物理连通、拓扑逻辑断开校验任务"),
    "2.4": ("2 图模一致性校验", "2.4 图形物理断开、拓扑逻辑误连通校验任务"),
    "3.1": ("3 电气逻辑校验", "3.1 开关 - 电压基础状态匹配校验任务"),
    "4.1": ("4 主配网接口拓扑完整性校验", "4.1 主配接口漏拼接校验任务"),
    "4.2": ("4 主配网接口拓扑完整性校验", "4.2 主配接口错拼接校验任务"),
}


def render(records, wb):
    """Sheet 1: 拓扑校验问题清单 — every ProblemRecord."""
    ws = wb.create_sheet(SHEET.name)
    ws.append(list(SHEET.columns))
    for idx, rec in enumerate(records, start=1):
        primary, secondary = CATEGORY_MAP.get(rec.task_code, ("", rec.task_code))
        ws.append([
            idx,
            primary,
            secondary,
            rec.device_id,
            rec.device_name,
            rec.feeder_id,
            rec.station_id,
            rec.description,
            rec.correction,
            rec.correction_sql,
        ])
    return ws
