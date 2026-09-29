"""Single source of truth for the official 12 second-level tasks + Module 5 self-grading."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TaskSpec:
    code: str
    name: str
    primary_category: str
    module_path: str
    output_sheet: str
    implementation_status: str = "needs_review"


OFFICIAL_TASKS = (
    TaskSpec("1.1", "设备拓扑悬空检测", "1 拓扑结构完整性检测", "group_01_topology/task_1_1_dangle", "Topology problem list", implementation_status="ready"),
    TaskSpec("1.2", "拓扑连通性异常诊断与断点定位", "1 拓扑结构完整性检测", "group_01_topology/task_1_2_break", "Topology connectivity result", implementation_status="ready"),
    TaskSpec("1.3", "联络开关自动识别与可视化梳理", "1 拓扑结构完整性检测", "group_01_topology/task_1_3_tie", "Tie switch result", implementation_status="ready"),
    TaskSpec("1.4", "疑似联络开关智能识别与复核研判", "1 拓扑结构完整性检测", "group_01_topology/task_1_4_suspect_tie", "Topology problem list", implementation_status="ready"),
    TaskSpec("1.5", "非计划性合环拓扑识别", "1 拓扑结构完整性检测", "group_01_topology/task_1_5_unplanned_loop", "Unplanned loop result", implementation_status="ready"),
    TaskSpec("2.1", "图上有、模型无校验", "2 图模一致性校验", "group_02_graph_model/task_2_1_svg_only", "Topology problem list", implementation_status="ready"),
    TaskSpec("2.2", "模型有、图上无校验", "2 图模一致性校验", "group_02_graph_model/task_2_2_model_only", "Topology problem list", implementation_status="ready"),
    TaskSpec("2.3", "图形物理连通、拓扑逻辑断开校验", "2 图模一致性校验", "group_02_graph_model/task_2_3_phys_connect_logi_break", "Topology problem list", implementation_status="ready"),
    TaskSpec("2.4", "图形物理断开、拓扑逻辑误连通校验", "2 图模一致性校验", "group_02_graph_model/task_2_4_phys_break_logi_connect", "Topology problem list", implementation_status="ready"),
    TaskSpec("3.1", "开关-电压状态匹配校验", "3 电气逻辑校验", "group_03_state_voltage/task_3_1_switch_voltage", "Topology problem list", implementation_status="ready"),
    TaskSpec("4.1", "主配接口漏拼接校验", "4 主配网接口校验", "group_04_main_dist_interface/task_4_1_missing", "Topology problem list", implementation_status="ready"),
    TaskSpec("4.2", "主配接口错拼接校验", "4 主配网接口校验", "group_04_main_dist_interface/task_4_2_wrong", "Topology problem list", implementation_status="ready"),
    TaskSpec("5.0", "模型修正质量自评分（4维度）", "5 质量自评分", "group_05_scoring/task_5_0_self_grade", "Model correction quality scoring", implementation_status="ready"),
    TaskSpec("5.1", "SVG 图形标准化美化排版", "6 SVG 图形专项", "task5_svg/task_5_1_beautify", "SVG beautification", implementation_status="ready"),
    TaskSpec("5.2", "SVG 图形交互式增删设备", "6 SVG 图形专项", "task5_svg/task_5_2_modify", "SVG modification", implementation_status="ready"),
    TaskSpec("5.3", "自动生成 SVG 接线图", "6 SVG 图形专项", "task5_svg/task_5_3_auto_draw", "SVG auto-draw", implementation_status="ready"),
)


TASKS_BY_CODE = {task.code: task for task in OFFICIAL_TASKS}


def get_task(code: str) -> TaskSpec:
    try:
        return TASKS_BY_CODE[code]
    except KeyError as error:
        raise ValueError(f"Unknown official task code: {code}") from error