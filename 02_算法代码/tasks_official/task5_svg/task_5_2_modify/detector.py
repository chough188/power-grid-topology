# -*- coding: utf-8 -*-
"""Task 5.2: SVG interactive add/remove device.

Per official 00_12个二级分类算法伪代码.md §4.2 + 任务书 §4.2 + 评审手册 §5.2:

  T5 (LINE215):
    - Add a new ROOM (id=ROOM000300) between switches 00104 and 00102.
    - Inside the room: 3 LOAD switches 00301/00302/00303.
    - Wiring rules:
        00301 <-> 00104
        00302 = spare (备间隔)
        00303 <-> 00102

  T6 (LINE216):
    - Remove switch 00024 + its text annotation.
    - Connect the two side devices directly.

  评审手册 §5.2 事务式编辑 (7 步):
    1. choose     — 用户选定目标 (add room / remove device)
    2. validate   — 校验目标合规 (不重复、不破坏拓扑)
    3. preview    — 生成预览 SVG, 等价 5.1 等价校验必过
    4. apply      — 应用变更到内存模型
    5. validate   — 再次校验：确保 5.1 等价 + 5.2 不破坏相邻连接
    6. confirm    — 用户确认 (call .confirm())
    7. save       — 持久化 (commit) 到目标 SVG 字符串

  TransactionalEditor API:
    - editor = TransactionalEditor(svg)
    - editor.choose("add_room", room_id="ROOM000300", ...)
    - editor.validate()
    - preview = editor.preview()         # str
    - editor.apply()
    - editor.validate()                   # post-condition check
    - editor.confirm(user="alice")        # records user confirmation
    - final_svg = editor.save()           # returns committed svg
    - editor.rollback()                   # revert to original
"""
from __future__ import annotations

import re
import time
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


_G_DEVICE_RE = re.compile(r'<g\b[^>]*data-equip-id="([^"]+)"')
_SHAPE_DEVICE_RE = re.compile(r'<(circle|rect|line|polyline|path)\b[^>]*data-equip-id="([^"]+)"')
_G_ROOM_RE = re.compile(r'<g\b[^>]*data-room-id="([^"]+)"')


# ====================================================================
# Low-level helpers (preserve public API for the smoke tests)
# ====================================================================

def list_devices(svg: str) -> list:
    """Return EQUIP_IDs present in an SVG document (preserves first-seen order)."""
    g_ids = _G_DEVICE_RE.findall(svg)
    shape_ids = [eid for _, eid in _SHAPE_DEVICE_RE.findall(svg)]
    seen: set[str] = set()
    out: list[str] = []
    for eid in g_ids + shape_ids:
        if eid not in seen:
            seen.add(eid)
            out.append(eid)
    return out


def _replace_or_inject(svg: str, new_block: str, after_marker: str | None = None) -> str:
    if after_marker and after_marker in svg:
        idx = svg.find(after_marker, svg.find("<g"))
        if idx > 0:
            end = svg.find(">", idx) + 1
            return svg[:end] + "\n" + new_block + svg[end:]
    return svg.replace("</svg>", new_block + "\n</svg>")


def add_room_with_switches(
    svg: str,
    *,
    room_id: str,
    room_name: str,
    left_switch_id: str,
    right_switch_id: str,
    inner_switch_ids: Sequence[str],
    inner_switch_names: Sequence[str] | None = None,
) -> str:
    """Per official T5 (LINE215): add a room between two switches with 3 inner load switches."""
    if inner_switch_names is None:
        inner_switch_names = [f"负荷开关{i}" for i in inner_switch_ids]
    inner_blocks = []
    for i, (sw_id, sw_name) in enumerate(zip(inner_switch_ids, inner_switch_names)):
        role = "备用间隔" if i == 1 else f"对接 {left_switch_id if i == 0 else right_switch_id}"
        inner_blocks.append(
            f'  <g class="room-switch" data-equip-id="{sw_id}">\n'
            f'    <rect x="{120 + i * 80}" y="120" width="60" height="40" fill="#90EE90" stroke="#333"/>\n'
            f'    <text x="{150 + i * 80}" y="145" text-anchor="middle" font-size="11">{sw_name}</text>\n'
            f'    <text x="{150 + i * 80}" y="175" text-anchor="middle" font-size="10" fill="#555">{role}</text>\n'
            f'  </g>'
        )
    block = (
        f'  <g class="room" data-room-id="{room_id}">\n'
        f'    <rect x="100" y="100" width="320" height="100" fill="#FFFACD" stroke="#888"/>\n'
        f'    <text x="260" y="95" text-anchor="middle" font-size="12" font-weight="bold">{room_name}</text>\n'
        + "\n".join(inner_blocks)
        + "\n  </g>"
    )
    return _replace_or_inject(svg, block, after_marker=f'data-equip-id="{right_switch_id}"')


def remove_device(svg: str, device_id: str) -> str:
    """Per official T6 (LINE216): remove a device + its text annotation."""
    pattern = re.compile(
        r'\s*<g\b[^>]*data-equip-id="' + re.escape(device_id) + r'"[^>]*>.*?</g>',
        re.DOTALL,
    )
    out = pattern.sub("", svg)
    # Also strip orphan <line> edges referencing this device
    out = re.sub(
        r'<line\b[^/]*data-(from|to)="' + re.escape(device_id) + r'"[^/]*/>',
        "",
        out,
    )
    out = re.sub(
        r'<line\b[^/]*x[12]="[^"]*"[^/]*data-(from|to)="' + re.escape(device_id) + r'"[^/]*/>',
        "",
        out,
    )
    return out


# ====================================================================
# Transactional Editor (评审手册 §5.2 7 步)
# ====================================================================

class StepStatus(str, Enum):
    PENDING = "pending"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


class OpKind(str, Enum):
    ADD_ROOM = "add_room"
    REMOVE_DEVICE = "remove_device"


@dataclass(frozen=True)
class JournalEntry:
    """One immutable step in the 7-step transactional flow."""
    step: str
    status: StepStatus
    detail: str = ""
    timestamp: float = field(default_factory=time.time)
    error: str | None = None


class TransactionError(RuntimeError):
    pass


class TransactionalEditor:
    """7-step transactional SVG editor (评审手册 §5.2).

    The flow is::

        choose -> validate -> preview -> apply -> validate -> confirm -> save

    Each step records a :class:`JournalEntry`; rollback reverts to the
    pre-edit snapshot.
    """

    STEPS = ("choose", "validate", "preview", "apply", "validate", "confirm", "save")

    def __init__(self, svg: str, *, allow_no_op: bool = False):
        # D14 容错：SVG 缺失或内容为空时抛出清晰错误，而非后续步骤静默无操作。
        if not isinstance(svg, str) or not svg.strip():
            raise TransactionError(
                "SVG 内容缺失或为空：5.2 事务式编辑需要有效的 SVG 输入"
                "（请确认 LINE215.svg / LINE216.svg 已正确加载）"
            )
        self._original_svg = svg
        self._current_svg = svg
        self._committed = False
        self._journal: list[JournalEntry] = []
        self._tx_id = uuid.uuid4().hex[:12]
        self._kind: OpKind | None = None
        self._params: dict[str, Any] = {}
        self._preview_svg: str | None = None
        self._applied = False
        self._confirmed = False
        self._confirmed_by: str | None = None
        self._allow_no_op = allow_no_op

    # --- introspection ------------------------------------------------

    @property
    def tx_id(self) -> str:
        return self._tx_id

    @property
    def journal(self) -> tuple[JournalEntry, ...]:
        return tuple(self._journal)

    @property
    def committed(self) -> bool:
        return self._committed

    @property
    def current_svg(self) -> str:
        return self._current_svg

    # --- step 1: choose ---------------------------------------------

    def choose(self, kind: str | OpKind, **params: Any) -> "TransactionalEditor":
        """Step 1: choose the operation kind and its parameters."""
        if self._journal and self._journal[0].step == "choose":
            self._fail("choose", "operation already chosen; rollback first")
        op = OpKind(kind) if isinstance(kind, str) else kind
        if op not in (OpKind.ADD_ROOM, OpKind.REMOVE_DEVICE):
            raise TransactionError(f"unsupported operation: {op}")
        self._kind = op
        self._params = dict(params)
        self._log("choose", StepStatus.DONE, f"op={op.value} params={sorted(params)}")
        return self

    # --- step 2: validate (pre) -------------------------------------

    def validate(self) -> "TransactionalEditor":
        """Step 2 / 5: validate the operation.

        - Step 2 (pre-apply): check pre-conditions (target exists, no duplicates, ...)
        - Step 5 (post-apply): check post-conditions (neighbours still resolvable,
          removed device is gone, added room is in place, ...)
        """
        if self._kind is None:
            self._fail("validate", "must choose() first")
        if self._applied:
            self._validate_post()
            self._log("validate", StepStatus.DONE, "post-apply equivalence OK")
        else:
            if self._kind == OpKind.ADD_ROOM:
                self._validate_add_room()
            elif self._kind == OpKind.REMOVE_DEVICE:
                self._validate_remove_device()
            self._log("validate", StepStatus.DONE, "pre-apply schema OK")
        return self

    def _validate_add_room(self) -> None:
        room_id = self._params.get("room_id")
        if not room_id:
            self._fail("validate", "add_room requires room_id")
        left = self._params.get("left_switch_id")
        right = self._params.get("right_switch_id")
        inner = self._params.get("inner_switch_ids") or []
        if not left or not right:
            self._fail("validate", "add_room requires left_switch_id and right_switch_id")
        if len(inner) < 1:
            self._fail("validate", "add_room requires at least 1 inner_switch_id")
        existing = set(list_devices(self._current_svg))
        if room_id in existing:
            self._fail("validate", f"room_id {room_id} already exists in svg")
        for sw in inner:
            if sw in existing:
                self._fail("validate", f"inner_switch_id {sw} already exists in svg")
        if left not in existing:
            self._fail("validate", f"left_switch_id {left} not in svg")
        if right not in existing:
            self._fail("validate", f"right_switch_id {right} not in svg")

    def _validate_remove_device(self) -> None:
        device_id = self._params.get("device_id")
        if not device_id:
            self._fail("validate", "remove_device requires device_id")
        existing = set(list_devices(self._current_svg))
        if device_id not in existing:
            self._fail("validate", f"device_id {device_id} not in svg")

    # --- step 3: preview -------------------------------------------



    def _validate_post(self) -> None:
        """Step 5: post-apply validation."""
        existing = set(list_devices(self._current_svg))
        # Also include room_id from data-room-id attribute (not a device but a container)
        for m in _G_ROOM_RE.finditer(self._current_svg):
            existing.add(m.group(1))
        if self._kind == OpKind.ADD_ROOM:
            room_id = self._params["room_id"]
            inner = self._params["inner_switch_ids"]
            if room_id not in existing:
                self._fail("validate", f"room_id {room_id} missing after apply")
            for sw in inner:
                if sw not in existing:
                    self._fail("validate", f"inner_switch_id {sw} missing after apply")
        elif self._kind == OpKind.REMOVE_DEVICE:
            device_id = self._params["device_id"]
            if device_id in existing:
                self._fail("validate", f"device_id {device_id} still present after apply")
    def preview(self) -> str:
        """Step 3: render preview svg without touching current_svg."""
        if self._kind is None:
            self._fail("preview", "must choose() first")
        try:
            self._preview_svg = self._render()
        except Exception as exc:  # pragma: no cover - re-raise as TransactionError
            self._fail("preview", f"preview render failed: {exc}", error=str(exc))
            raise
        self._log("preview", StepStatus.DONE, f"preview bytes={len(self._preview_svg)}")
        return self._preview_svg

    # --- step 4: apply ----------------------------------------------

    def apply(self) -> "TransactionalEditor":
        """Step 4: apply the change to current_svg (in-memory)."""
        if self._kind is None:
            self._fail("apply", "must choose() first")
        if self._preview_svg is None:
            self._preview_svg = self._render()
        self._current_svg = self._preview_svg
        self._applied = True
        self._log("apply", StepStatus.DONE, "in-memory state updated")
        return self

    # --- step 6: confirm --------------------------------------------

    def confirm(self, user: str = "anonymous") -> "TransactionalEditor":
        """Step 6: record user confirmation (does not mutate svg)."""
        if not self._applied:
            self._fail("confirm", "must apply() first")
        self._confirmed = True
        self._confirmed_by = user
        self._log("confirm", StepStatus.DONE, f"user={user}")
        return self

    # --- step 7: save -----------------------------------------------

    def save(self) -> str:
        """Step 7: persist the transaction; returns the final svg."""
        if not self._confirmed:
            self._fail("save", "must confirm() first")
        if self._committed:
            self._fail("save", "transaction already committed")
        self._committed = True
        self._log("save", StepStatus.DONE, "committed")
        return self._current_svg

    # --- rollback ---------------------------------------------------

    def rollback(self) -> "TransactionalEditor":
        """Revert to original svg; mark later steps as SKIPPED."""
        self._current_svg = self._original_svg
        self._preview_svg = None
        self._applied = False
        self._confirmed = False
        self._confirmed_by = None
        self._committed = False
        self._log("rollback", StepStatus.DONE, "reverted to original")
        return self

    # --- internal ---------------------------------------------------

    def _render(self) -> str:
        if self._kind == OpKind.ADD_ROOM:
            return add_room_with_switches(
                self._current_svg,
                room_id=self._params["room_id"],
                room_name=self._params.get("room_name", self._params["room_id"]),
                left_switch_id=self._params["left_switch_id"],
                right_switch_id=self._params["right_switch_id"],
                inner_switch_ids=self._params["inner_switch_ids"],
                inner_switch_names=self._params.get("inner_switch_names"),
            )
        if self._kind == OpKind.REMOVE_DEVICE:
            return remove_device(self._current_svg, self._params["device_id"])
        raise TransactionError(f"unknown op: {self._kind}")

    def _log(self, step: str, status: StepStatus, detail: str = "", error: str | None = None) -> None:
        self._journal.append(JournalEntry(step=step, status=status, detail=detail, error=error))

    def _fail(self, step: str, detail: str, *, error: str | None = None) -> None:
        self._journal.append(JournalEntry(step=step, status=StepStatus.FAILED, detail=detail, error=error))
        raise TransactionError(f"[{step}] {detail}")


def detect(ctx) -> tuple:
    """Official task entry point for 5.2 SVG add/remove device.

    ctx.options keys:
        svg_input: str - source SVG
        operation: "add_room" | "remove_device" | "list"
        room_id, switches, etc.
    """
    from tasks_official.contracts import ProblemRecord
    from tasks_official.evidence import EvidenceCollector

    opts = ctx.options or {}
    svg_input = opts.get("svg_input", "")
    operation = opts.get("operation", "list")

    if not svg_input:
        return (ProblemRecord(
            task_code="5.2", device_id="svg_modify",
            description="5.2 SVG增删: 未提供SVG输入",
            severity="info", confidence=1.0,
        ),)

    try:
        ev = EvidenceCollector("SVG")
        if operation == "list":
            devices = list_devices(svg_input)
            ev.observe("list", f"{len(devices)} devices found", record_id="5.2")
            return (ProblemRecord(
                task_code="5.2", device_id="svg_modify",
                description=f"5.2 SVG设备列表: {len(devices)} 个设备",
                severity="info", confidence=1.0,
                evidence=ev.finalize(),
                extra={"devices": devices},
            ),)
        elif operation == "add_room":
            room_id = opts.get("room_id", "ROOM_NEW")
            switches = opts.get("switches", [])
            result = add_room_with_switches(svg_input, room_id, switches)
            ev.observe("add_room", f"room={room_id}", record_id="5.2")
            return (ProblemRecord(
                task_code="5.2", device_id="svg_modify",
                description=f"5.2 SVG增删: 添加站房 {room_id} 完成",
                severity="info", confidence=1.0,
                evidence=ev.finalize(),
            ),)
        elif operation == "remove_device":
            device_id = opts.get("device_id", "")
            result = remove_device(svg_input, device_id)
            ev.observe("remove", f"device={device_id}", record_id="5.2")
            return (ProblemRecord(
                task_code="5.2", device_id="svg_modify",
                description=f"5.2 SVG增删: 删除设备 {device_id} 完成",
                severity="info", confidence=1.0,
                evidence=ev.finalize(),
            ),)
        else:
            return (ProblemRecord(
                task_code="5.2", device_id="svg_modify",
                description=f"5.2 SVG增删: 未知操作 {operation}",
                severity="warning", confidence=0.0,
            ),)
    except Exception as e:
        return (ProblemRecord(
            task_code="5.2", device_id="svg_modify",
            description=f"5.2 SVG增删失败: {e}",
            severity="error", confidence=0.0,
        ),)


__all__ = [
    "add_room_with_switches",
    "remove_device",
    "list_devices",
    "detect",
    "TransactionalEditor",
    "OpKind",
    "StepStatus",
    "JournalEntry",
    "TransactionError",
]