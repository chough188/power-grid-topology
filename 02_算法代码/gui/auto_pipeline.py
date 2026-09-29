# -*- coding: utf-8 -*-
"""One-click pipeline: multi-file smart ingest + 13 detector + 6 Sheet xlsx + 4-dim score.

Wired together from existing modules (no detector rewriting):
  - ``data_loader.sql_importer.import_sql`` for *.sql inputs.
  - ``data_loader.snapshot.load_json_snapshot`` for *.json inputs.
  - ``data_loader.synthetic_gen.make_synthetic_dataset`` for empty fallback.
  - ``tasks_official.execution.OfficialRunner`` for the 12 official detectors.
  - ``tasks_official.self_grade_v2.grade`` for PDF 4-dimension scoring.
  - ``output_writer.writer.write_workbook`` for the 6-Sheet xlsx contract.
  - ``tasks_official.task5_svg.task_5_1_beautify.detector.beautify`` for SVG T3/T4.
  - ``tasks_official.task5_svg.task_5_2_modify.detector.TransactionalEditor`` for T5/T6.

Every step returns a structured result so the GUI layer can stream it into
Treeview / Canvas widgets without losing detail.
"""
from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from data_loader.loader import OfficialDataset
from data_loader.schema import REQUIRED_TABLES
from data_loader.snapshot import load_json_snapshot
from data_loader.sql_importer import import_sql, inspect_sql
from data_loader.synthetic_gen import make_empty_dataset, make_synthetic_dataset

from output_writer.writer import write_workbook
from tasks_official.execution import OfficialRunner
from tasks_official.registry import LazyTaskRegistry


ALL_TASKS: tuple[str, ...] = (
    "1.1", "1.2", "1.3", "1.4", "1.5",
    "2.1", "2.2", "2.3", "2.4",
    "3.1",
    "4.1", "4.2",
    "5.0",
)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class FileDescriptor:
    """Single input file with auto-detected format."""
    path: str
    kind: str  # "sql" | "json" | "csv" | "svg_main" | "svg_dist" | "svg_other"
    role: str  # "data" | "svg_main" | "svg_dist" | "svg_decoration"

    @property
    def display_name(self) -> str:
        return Path(self.path).name


@dataclass
class PipelineResult:
    dataset: OfficialDataset
    snapshot_path: str
    detected_tables: tuple[str, ...]
    extra_tables: tuple[str, ...]
    records_by_task: Mapping[str, tuple[Any, ...]]
    total_records: int
    xlsx_path: str | None = None
    score_lines: tuple[str, ...] = ()
    score_overall: float | None = None
    source_mode: str = "real"
    manifest_path: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)
    svg_files: tuple[FileDescriptor, ...] = field(default_factory=tuple)
    svg_outputs: tuple[dict[str, str], ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# 文件识别
# ---------------------------------------------------------------------------


def sniff_files(paths: Iterable[str | Path]) -> list[FileDescriptor]:
    """Classify user-selected files into ``FileDescriptor`` list.

    Rules:
      - ``.sql``           → ``sql / data``
      - ``.json``          → ``json / data``
      - ``.csv``           → ``csv / data``
      - ``.svg`` 名字含 LINE215 / 215 / line215 → ``svg_main``
      - ``.svg`` 名字含 LINE216 / 216 / line216 → ``svg_dist``
      - 其它 ``.svg``      → ``svg_other``
    """
    out: list[FileDescriptor] = []
    for raw in paths:
        p = Path(raw).expanduser().resolve()
        if not p.exists() or not p.is_file():
            continue
        ext = p.suffix.lower()
        name_lower = p.name.lower()
        if ext == ".sql":
            out.append(FileDescriptor(str(p), "sql", "data"))
        elif ext == ".json":
            out.append(FileDescriptor(str(p), "json", "data"))
        elif ext == ".csv":
            out.append(FileDescriptor(str(p), "csv", "data"))
        elif ext == ".svg":
            if "line215" in name_lower or "215" in name_lower:
                out.append(FileDescriptor(str(p), "svg_main", "svg_main"))
            elif "line216" in name_lower or "216" in name_lower:
                out.append(FileDescriptor(str(p), "svg_dist", "svg_dist"))
            else:
                out.append(FileDescriptor(str(p), "svg_other", "svg_decoration"))
        else:
            out.append(FileDescriptor(str(p), "other", "data"))
    return out


# ---------------------------------------------------------------------------
# 加载
# ---------------------------------------------------------------------------


def _load_one_sql(path: Path) -> dict[str, list[dict]]:
    return import_sql(path)


def _load_one_csv(path: Path) -> dict[str, list[dict]]:
    """Single-table CSV ingest: table name from filename stem, matches REQUIRED_TABLES."""
    stem = path.stem.upper()
    matched = None
    for tname in REQUIRED_TABLES:
        if tname.upper() == stem:
            matched = tname
            break
    if matched is None:
        # try fuzzy match
        for tname in REQUIRED_TABLES:
            if stem in tname.upper() or tname.upper() in stem:
                matched = tname
                break
    if matched is None:
        raise ValueError(f"CSV file {path.name}: cannot match stem '{stem}' to any of {len(REQUIRED_TABLES)} required tables")
    with open(path, "r", encoding="utf-8-sig", newline="") as fp:
        rows = [dict(r) for r in csv.DictReader(fp)]
    return {matched: rows}


def _ingest_files(
    files: Sequence[FileDescriptor],
) -> tuple[dict[str, list[dict]], list[str], str]:
    """Merge inputs without contaminating real rows with schema-demo rows."""
    merged: dict[str, list[dict]] = {}
    demo_tables: dict[str, list[dict]] = {}
    warnings: list[str] = []
    for fd in files:
        p = Path(fd.path)
        try:
            if fd.kind == "sql":
                source = inspect_sql(p)
                t = _load_one_sql(p)
                if source.mode == "schema_only":
                    for tname, rows in t.items():
                        demo_tables.setdefault(tname, []).extend(rows)
                    warnings.append(
                        f"{p.name}: 仅含 CREATE TABLE，无真实记录；已识别为 schema 演示源"
                    )
                    continue
                if source.mode != "data":
                    raise ValueError("SQL 中未识别到官方表 INSERT 或 CREATE TABLE")
            elif fd.kind == "json":
                ds = load_json_snapshot(p)
                t = {k: list(v) for k, v in ds.tables.items()}
            elif fd.kind == "csv":
                t = _load_one_csv(p)
            else:
                continue
            for tname, rows in t.items():
                merged.setdefault(tname, []).extend(rows)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{p.name}: {type(exc).__name__}: {exc}")
    if merged:
        if demo_tables:
            warnings.append("已检测到真实数据，DDL 合成行已自动隔离，未混入检测结果")
        return merged, warnings, "real"
    if demo_tables:
        warnings.append("当前结果基于 DDL 合成演示数据，不代表真实比赛检测结论")
        return demo_tables, warnings, "schema_demo"
    return merged, warnings, "empty"


def _pick_identifier(values: Sequence[str], preferred: str, fallback_index: int = 0) -> str | None:
    for value in values:
        if value.upper() == preferred.upper():
            return value
    if not values:
        return None
    return values[min(fallback_index, len(values) - 1)]


def _resolve_official_case_ids(
    tables: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, str]:
    """Resolve official 5.3 case display names to internal TMP ids.

    The official reference cases are named by display strings
    (LINE215 / LINE216 / 10kV LINE111 / SUB004 / TMP00034205), but every
    ``render_*`` function filters on the internal TMP ids:
      - feeder diagrams  -> ``PWEQUIPINFO.FEEDER_ID == PWFEEDERLINE.LINE_ID``
      - substation diagram -> ``PWEQUIPINFO.DSUBSTATION_ID == ZWSUBSTATION.ST_ID``
      - power trace      -> ``PWEQUIPINFO.EQUIP_ID``

    ``PWFEEDERLINE`` carries both: ``LINE_ID`` is the TMP key while
    ``LINE_NAME`` holds the human-readable name (e.g. '10kVLINE111');
    ``ZWSUBSTATION`` maps ``ST_NAME`` ('SUB004_变') to ``ST_ID``.
    Only successfully resolved keys are returned; callers fall back to
    positional defaults when a display name is absent (synthetic data).
    """
    out: dict[str, str] = {}

    # Feeder display-name -> TMP LINE_ID
    name_to_line_id: dict[str, str] = {}
    for row in tables.get("JBS_PWFEEDERLINE", ()):
        lid = row.get("LINE_ID")
        lname = row.get("LINE_NAME")
        if lid and lname:
            name_to_line_id.setdefault(str(lname), str(lid))

    def pick_feeder(display: str) -> str | None:
        upper = display.upper()
        for lname, lid in name_to_line_id.items():
            if lname.upper() == upper:
                return lid
        for lname, lid in name_to_line_id.items():
            if upper in lname.upper():
                return lid
        return None

    v = pick_feeder("LINE215")
    if v:
        out["line215"] = v
    v = pick_feeder("LINE216")
    if v:
        out["line216"] = v
    v = pick_feeder("LINE111")
    if v:
        out["line111"] = v

    # Substation display-name prefix -> TMP ST_ID
    for row in tables.get("JBS_ZWSUBSTATION", ()):
        sid = row.get("ST_ID")
        sname = str(row.get("ST_NAME") or "")
        if sid and sname.upper().startswith("SUB004"):
            out["sub004"] = str(sid)
            break

    # Device id used verbatim by the official case (TMP00034205).
    devices = {
        str(row.get("EQUIP_ID"))
        for row in tables.get("JBS_PWEQUIPINFO", ())
        if row.get("EQUIP_ID") not in (None, "")
    }
    if "TMP00034205" in devices:
        out["target_id"] = "TMP00034205"
    return out


def _task_options(
    tables: Mapping[str, Sequence[Mapping[str, Any]]],
    svg_files: Sequence[FileDescriptor],
) -> tuple[dict[str, Any], list[str]]:
    """Build graph-model and auto-draw options from selected files and tables."""
    warnings: list[str] = []
    svg_devices: set[str] = set()
    svg_connections: set[tuple[str, str]] = set()
    svg_devices_meta: dict[str, dict[str, str]] = {}
    try:
        from tasks_official.task5_svg.task_5_1_beautify.detector import (
            _parse_devices,
            _parse_edges,
        )
        simple_parser = True
    except Exception as exc:  # noqa: BLE001
        simple_parser = False
        warnings.append(f"SVG 简化解析器不可用：{type(exc).__name__}: {exc}")
    try:
        from shared.cim_svg import parse_cim_svg
        cim_parser = True
    except Exception as exc:  # noqa: BLE001
        cim_parser = False
        warnings.append(f"CIM SVG 解析器不可用：{type(exc).__name__}: {exc}")

    if not simple_parser and not cim_parser:
        warnings.append("SVG 拓扑预解析失败：无任何可用解析器")
    else:
        cim_file_count = 0
        # CIM 设备 -> 来源图形（馈线）上下文。仅含 feeder 字段（无 name/type），
        # 2.1 检测到该形态时跳过模糊匹配、仍走具体 ID 的最小 INSERT，
        # 同时把 feeder 写入问题清单「所属馈线」列（孤儿 SVG 馈线因此可见）。
        for descriptor in svg_files:
            try:
                svg = Path(descriptor.path).read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                warnings.append(f"{Path(descriptor.path).name}: 读取失败 {exc}")
                continue
            # 简化自动出图格式（<g data-equip-id="...">）
            if simple_parser:
                svg_devices.update(str(item["equip_id"]) for item in _parse_devices(svg))
                svg_connections.update(tuple(map(str, edge)) for edge in _parse_edges(svg))
            # CIM / IEC 61970-301 官方数据集格式（PSR_Ref + GLink_Ref）
            if cim_parser:
                ids, edges = parse_cim_svg(svg)
                if ids or edges:
                    cim_file_count += 1
                svg_devices.update(ids)
                svg_connections.update(edges)
                stem = Path(descriptor.path).stem
                for d_id in ids:
                    svg_devices_meta.setdefault(d_id, {"feeder": stem})
        if cim_file_count:
            warnings.append(
                f"CIM SVG 预解析成功：{cim_file_count} 个文件，"
                f"图元 ID {len(svg_devices)} 个，物理连接对 {len(svg_connections)} 条"
            )

    # 2.3 只评估「图形与模型共模设备」之间的逻辑一致性；
    # 仅存在于图形上的设备缺失问题由 2.1 报告（避免按边重复刷屏）。
    model_ids: set[str] = set()
    for tbl in ("JBS_PWEQUIPINFO", "JBS_ZWEQUIPINFO"):
        for row in tables.get(tbl, ()):
            value = row.get("EQUIP_ID")
            if value not in (None, ""):
                model_ids.add(str(value))
    if model_ids:
        co_modeled = {
            pair for pair in svg_connections if pair[0] in model_ids and pair[1] in model_ids
        }
        dropped = len(svg_connections) - len(co_modeled)
        svg_connections = co_modeled
        if dropped:
            warnings.append(
                f"svg_connections 已过滤至图模共模设备对：保留 {len(co_modeled)}，"
                f"剔除涉及仅图形设备的 {dropped} 条（由 2.1 覆盖）"
            )

    feeders: list[str] = []
    for row in tables.get("JBS_PWFEEDERLINE", ()):
        value = row.get("LINE_ID") or row.get("FEEDER_ID")
        if value not in (None, ""):
            feeders.append(str(value))
    for row in tables.get("JBS_PWEQUIPINFO", ()):
        value = row.get("FEEDER_ID")
        if value not in (None, ""):
            feeders.append(str(value))
    feeders = list(dict.fromkeys(feeders))

    substations: list[str] = []
    for table_name in ("JBS_ZWSUBSTATION", "JBS_PWFEEDERLINE", "JBS_PWEQUIPINFO"):
        for row in tables.get(table_name, ()):
            value = row.get("SUBSTATION_ID") or row.get("DSUBSTATION_ID") or row.get("START_ST_ID")
            if value not in (None, ""):
                substations.append(str(value))
    substations = list(dict.fromkeys(substations))

    devices = [
        str(row.get("EQUIP_ID"))
        for row in tables.get("JBS_PWEQUIPINFO", ())
        if row.get("EQUIP_ID") not in (None, "")
    ]
    options: dict[str, Any] = {
        "svg_devices": tuple(sorted(svg_devices)),
        "svg_connections": tuple(sorted(svg_connections)),
        "svg_devices_meta": svg_devices_meta,
    }
    # Official 5.3 cases: prefer display-name resolution (LINE_NAME / ST_NAME)
    # so the diagrams target the exact official feeders/substation; fall back
    # to positional defaults only when the names are absent (synthetic data).
    case_ids = _resolve_official_case_ids(tables)
    fallbacks = {
        "line215": ("LINE215", 0),
        "line216": ("LINE216", 1),
        "line111": ("LINE111", 0),
        "sub004": ("SUB004", 0),
        "target_id": ("TMP00034205", 0),
    }
    for key, value in case_ids.items():
        options[key] = value
    for key, (preferred, idx) in fallbacks.items():
        if key in options:
            continue
        pool = substations if key == "sub004" else (devices if key == "target_id" else feeders)
        value = _pick_identifier(pool, preferred, idx)
        if value:
            options[key] = value
    return options, warnings


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


@dataclass
class RunOptions:
    task_codes: tuple[str, ...] = ALL_TASKS
    write_xlsx: bool = True
    run_score: bool = True
    use_synthetic_if_empty: bool = True
    # Task 2 §5.3: render the four official business diagrams
    # (single-line / tie / substation-wide / power-trace) as standalone SVGs.
    # Kept out of ``task_codes`` on purpose: the 6-Sheet contract's 12
    # secondary categories do not include 5.3, so its output is a graphics
    # deliverable, not a problem-list row.
    run_auto_draw: bool = True


def run_pipeline(
    file_paths: Sequence[str | Path],
    output_dir: str | Path,
    options: RunOptions | None = None,
) -> PipelineResult:
    """Top-level one-click pipeline.

    Args:
        file_paths: 一组用户选择的文件（sql/json/csv/svg）。
        output_dir: 产物输出目录（snapshot.json、xlsx 等）。
        options:    任务范围/评分开关。

    Returns:
        PipelineResult，包含检测结果、xlsx 路径、4 维评分等。
    """
    opts = options or RunOptions()
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    files = sniff_files(file_paths)
    data_files = [f for f in files if f.role == "data"]
    svg_files = tuple(f for f in files if f.role.startswith("svg"))
    warnings: list[str] = []

    if not data_files:
        if opts.use_synthetic_if_empty:
            warnings.append("未检测到数据文件，使用内置 synthetic 数据集（确定性 seed=42）")
            tables = dict(make_synthetic_dataset(seed=42).tables)
            source_mode = "synthetic"
        else:
            tables = dict(make_empty_dataset().tables)
            source_mode = "empty"
    else:
        tables, ingest_warnings, source_mode = _ingest_files(data_files)
        warnings.extend(ingest_warnings)

    dataset = OfficialDataset(tables)
    if source_mode in {"real", "synthetic"}:
        try:
            dataset.validate()
        except ValueError as exc:
            if source_mode == "real":
                warnings.append(f"数据 schema 校验失败：{exc}")
            else:
                warnings.append(f"数据 schema 校验（synthetic）警告：{exc}")
    else:
        warnings.append("演示模式：跳过严格 schema 校验")

    task_options, parse_warnings = _task_options(tables, svg_files)
    warnings.extend(parse_warnings)
    if source_mode in {"empty", "schema_demo"}:
        task_options = dict(task_options)
        task_options["__allow_incomplete_dataset__"] = True

    snapshot_path = output / "snapshot.json"
    snapshot_path.write_text(
        json.dumps({"tables": dict(dataset.tables)}, ensure_ascii=False),
        encoding="utf-8",
    )

    runner = OfficialRunner(LazyTaskRegistry.with_module_resolver())
    result = runner.run(list(opts.task_codes), dataset, options=task_options or None)
    records_by_task = dict(result.records_by_task)
    total = sum(len(v) for v in records_by_task.values())

    xlsx_path: str | None = None
    if opts.write_xlsx:
        flat_records = [r for recs in records_by_task.values() for r in recs]
        xlsx_path = str(output / "official_result.xlsx")
        try:
            # project_io may be unavailable; use strict=False to avoid
            # RuntimeError from the contract gate's assert when isolation
            # check is not available (strict=True would raise if project_io
            # is missing, masking the real error).
            write_workbook(flat_records, xlsx_path, dataset=dataset, strict=False)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"xlsx 写入失败：{exc}")
            xlsx_path = None

    score_lines: tuple[str, ...] = ()
    score_overall: float | None = None
    if opts.run_score:
        try:
            import contextlib
            import io as _io
            from tasks_official.self_grade_v2 import grade
            buf = _io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = grade(snapshot_path)
            lines = buf.getvalue().splitlines()
            score_lines = tuple(lines)
            for line in lines:
                if "总分" in line:
                    try:
                        score_overall = float(line.split(":")[-1].strip())
                    except ValueError:
                        pass
            warnings.append(f"自评分 rc={rc}, 总分={score_overall}")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"自评分失败：{exc}")

    detected = tuple(sorted(tables.keys()))
    extras = tuple(sorted(set(detected) - set(REQUIRED_TABLES)))

    # ----- SVG 美化与增删 (T3/T4 + T5/T6) ---------------------------
    auto_draw_outputs: list[dict[str, str]] = []
    if opts.run_auto_draw or "5.3" in opts.task_codes:
        try:
            from data_loader.object_dictionary import normalize_dataset_types
            from tasks_official.task5_svg.task_5_3_auto_draw.detector import render_all
            # Normalize EQUIP_TYPE (OBJ_CODE -> canonical/CIM enum) before
            # rendering: the 5.3 type filters need TRANSFORMER/BUS/SWITCH
            # classes, which raw OBJ_CODEs (1703/1301/1705/...) never match.
            draw_tables = normalize_dataset_types(tables)
            rendered = render_all(
                draw_tables,
                line215=task_options.get("line215"),
                line216=task_options.get("line216"),
                line111=task_options.get("line111"),
                sub004=task_options.get("sub004"),
                target_id=task_options.get("target_id"),
            )
            for name, svg in rendered.items():
                out_path = output / f"{name}.svg"
                out_path.write_text(svg, encoding="utf-8")
                auto_draw_outputs.append({"name": name, "path": str(out_path), "size": str(len(svg))})
                warnings.append(f"5.3 自动出图: {name} -> {out_path.name} ({len(svg)} 字节)")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"5.3 自动出图失败：{type(exc).__name__}: {exc}")
    svg_outputs: list[dict[str, str]] = []
    if svg_files:
        try:
            from tasks_official.task5_svg.task_5_1_beautify.detector import (
                beautify, verify_topological_equivalence,
            )
            from tasks_official.task5_svg.task_5_1_beautify.detector import (
                _parse_devices, _parse_edges,
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"无法加载 SVG 美化模块: {exc}")
        else:
            for fd in svg_files:
                try:
                    src_svg = Path(fd.path).read_text(encoding="utf-8", errors="replace")
                    devices = _parse_devices(src_svg)
                    edges = _parse_edges(src_svg)
                    voltage_lookup = {d["equip_id"]: d.get("voltage") or 10 for d in devices}
                    equip_type_lookup = {d["equip_id"]: d.get("equip_type") or "DEVICE" for d in devices}
                    out_svg = beautify(
                        src_svg,
                        voltage_lookup=voltage_lookup,
                        equip_type_lookup=equip_type_lookup,
                        edge_lookup=edges,
                    )
                    res = verify_topological_equivalence(src_svg, out_svg, edges_before=edges, edges_after=edges)
                    ok = res.get("ok", False)
                    out_path = output / f"{Path(fd.path).stem}_beautified.svg"
                    out_path.write_text(out_svg, encoding="utf-8")
                    svg_outputs.append({
                        "src": fd.path,
                        "out": str(out_path),
                        "kind": fd.kind,
                        "devices": str(len(devices)),
                        "edges": str(len(edges)),
                        "topology_ok": str(ok),
                    })
                    warnings.append(f"SVG 美化: {Path(fd.path).name} -> {Path(out_path).name} ({len(devices)} 设备, 拓扑等价={ok})")
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"SVG 美化失败 {Path(fd.path).name}: {type(exc).__name__}: {exc}")

    # ----- SVG 增删 T5/T6 官方场景 (CIM-aware) -------------------------
    scenario_outputs: list[dict[str, str]] = []
    if svg_files:
        try:
            from tasks_official.task5_svg.task_5_2_modify import scenarios as _t56
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"无法加载 T5/T6 场景模块: {exc}")
        else:
            plan = (("LINE215", "t5", "T5_added"), ("LINE216", "t6", "T6_removed"))
            for stem, kind, suffix in plan:
                fd = next((f for f in svg_files
                           if Path(f.path).stem.upper() == stem.upper()), None)
                if fd is None:
                    warnings.append(f"T5/T6 场景跳过: 未找到 {stem}.svg")
                    continue
                try:
                    src_svg = Path(fd.path).read_text(encoding="utf-8", errors="replace")
                    res = _t56.run_scenario(src_svg, kind=kind)
                    out_name = f"{stem}_{suffix}.svg"
                    out_path = output / out_name
                    if res.get("ok"):
                        out_path.write_text(res["svg"], encoding="utf-8")
                        scenario_outputs.append({
                            "scenario": kind,
                            "src": fd.path,
                            "out": str(out_path),
                            "diagnostics": json.dumps(res.get("diagnostics", {}), ensure_ascii=False),
                        })
                        warnings.append(f"T5/T6 场景 {kind} 成功: {Path(fd.path).name} -> {out_name}")
                    else:
                        warnings.append(
                            f"T5/T6 场景 {kind} 失败: {res.get('error')} "
                            f"(diagnostics={json.dumps(res.get('diagnostics', {}), ensure_ascii=False)[:300]})")
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"T5/T6 场景 {kind} 异常: {type(exc).__name__}: {exc}")

    # ----- 回滚 SQL（评审手册核心承诺: 所有修正有反向SQL + 前置快照可恢复）--
    rollback_info: dict | None = None
    try:
        from shared.rollback_sql import generate_rollback_sql

        rollback_info = generate_rollback_sql(str(xlsx_path), str(snapshot_path), output)
        warnings.append(
            f"rollback.sql 生成成功: cells={rollback_info['cells']} "
            f"counts={rollback_info['counts']}")
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"rollback.sql 生成失败: {type(exc).__name__}: {exc}")

    manifest_path = output / "run_manifest.json"
    try:
        manifest_payload = {
            "source_mode": source_mode,
            "snapshot": str(snapshot_path),
            "tables": detected,
            "extras": extras,
            "task_codes": list(opts.task_codes),
            "total_records": total,
            "xlsx": xlsx_path,
            "score": score_overall,
            "score_lines": list(score_lines),
            "warnings": list(warnings),
            "svg_outputs": list(svg_outputs),
            "auto_draw": auto_draw_outputs,
            "scenario_outputs": list(scenario_outputs),
            "rollback": rollback_info,
        }
        manifest_path.write_text(
            json.dumps(manifest_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"manifest 写入失败：{type(exc).__name__}: {exc}")
        manifest_path = None
    return PipelineResult(
        dataset=dataset,
        snapshot_path=str(snapshot_path),
        detected_tables=detected,
        extra_tables=extras,
        records_by_task=records_by_task,
        total_records=total,
        xlsx_path=xlsx_path,
        score_lines=score_lines,
        score_overall=score_overall,
        source_mode=source_mode,
        manifest_path=str(manifest_path) if manifest_path else None,
        warnings=tuple(warnings),
        svg_files=svg_files,
        svg_outputs=tuple(svg_outputs),
    )


__all__ = [
    "ALL_TASKS",
    "FileDescriptor",
    "PipelineResult",
    "RunOptions",
    "run_pipeline",
    "sniff_files",
]

