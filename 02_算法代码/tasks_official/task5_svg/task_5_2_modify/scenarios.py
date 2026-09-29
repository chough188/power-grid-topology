# -*- coding: utf-8 -*-
"""Official T5/T6 scenarios executed on REAL CIM SVG files.

Background
----------
The generic :mod:`detector` in this package speaks the synthetic
``data-equip-id`` dialect; the official dataset ships CIM IEC 61970-301
exports where device instances look like::

    <ns0:g id="TMP_<uuid>">
      <ns0:use class="lkv10" ns1:href="#Fuse_..." x="484.08" y="558.22" .../>
      <ns0:metadata>
        <ns2:PSR_Ref LineType="Trunk" ObjectID="TMP00044412"
                     ObjectName="刀闸0035" PSRType="0115" TopType="02" businessType="3"/>
        <ns2:GLink_Ref ObjectID="TMP00311328"/>
        <ns2:GLink_Ref ObjectID="TMP00311547"/>
        <ns2:Layer_Ref ObjectName="TMP00132371"/>
      </ns0:metadata>
    </ns0:g>

i.e. there is **no** ``data-equip-id`` attribute, so
``detector.list_devices`` returns ``[]`` and ``TransactionalEditor``
cannot validate anchors. This module adds a CIM-aware parser plus the two
official scenario runners:

* **T5 (LINE215)** — insert room ``ROOM000300`` between switches
  ``开关00104`` and ``开关00102`` carrying three inner load switches
  ``00301/00302/00303`` (wiring rules: 00301<->00104, 00302 spare bay,
  00303<->00102).
* **T6 (LINE216)** — remove switch ``开关00024`` + its text annotation
  and connect its two neighbours directly.

Both runners follow the 评审手册 §5.2 transactional discipline
(choose -> validate -> preview -> apply -> validate -> confirm -> save)
with an in-memory journal, and both verify topological consistency of the
resulting GLink graph before reporting success.

Anchor resolution is name-driven and deterministic:
  1. exact ``PSR_Ref@ObjectName`` match on a device block;
  2. unique suffix match on ``ObjectName``;
  3. exact / unique-suffix match on TXT label content mapped through
     ``ObjectID="TXT_<device>"`` to the labelled device.
If no unique anchor is found the runner fails gracefully with a
diagnostics payload instead of guessing.
"""
from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# CIM parsing
# ---------------------------------------------------------------------------

_OPEN_G_RE = re.compile(r'<([\w.-]+:)?g\b([^>]*)>')
_CLOSE_G_RE = re.compile(r'</([\w.-]+:)?g\s*>')
_PSR_RE = re.compile(r'([\w.-]+:)?PSR_Ref\b([^/>]*)/?>')
_GLINK_RE = re.compile(r'([\w.-]+:)?GLink_Ref\b[^>]*?ObjectID="([^"]+)"')
_TEXT_RE = re.compile(r'<([\w.-]+:)?text\b[^>]*>(.*?)</(?:[\w.-]+:)?text\s*>', re.DOTALL)
_USE_RE = re.compile(r'<([\w.-]+:)?use\b([^>]*)/?>')
_POLY_RE = re.compile(r'<([\w.-]+:)?polyline\b([^>]*)/?>')


def _attr(tag_attrs: str, name: str) -> str | None:
    m = re.search(name + r'="([^"]*)"', tag_attrs or "")
    return m.group(1) if m else None


@dataclass
class CIMDevice:
    """One CIM device instance parsed from an SVG document."""

    block_id: str                      # <g id="...">
    object_id: str                     # PSR_Ref@ObjectID
    name: str | None = None            # PSR_Ref@ObjectName (may be missing)
    psr_type: str | None = None        # PSR_Ref@PSRType
    neighbors: list[str] = field(default_factory=list)   # GLink_Ref order
    x: float | None = None
    y: float | None = None
    block_start: int = -1              # char offset of the opening <g ...>
    block_end: int = -1                # char offset just past </g>

    @property
    def pos(self) -> tuple[float, float]:
        return (self.x or 0.0, self.y or 0.0)


def parse_cim(svg_text: str) -> tuple[dict[str, CIMDevice], dict[str, str]]:
    """Parse device instances and text labels out of a CIM SVG document.

    Returns ``(devices, labels)``:
      * ``devices``: ObjectID -> :class:`CIMDevice` (TXT label blocks are
        not devices);
      * ``labels``: visible label text -> labelled device ObjectID
        (via ``ObjectID="TXT_<device>"``).

    Namespace prefixes (``ns0:`` / ``ns2:`` ...) are tolerated; nested
    layer groups are handled by tracking the innermost open ``<g>``.
    """
    devices: dict[str, CIMDevice] = {}
    labels: dict[str, str] = {}
    stack: list[dict[str, Any]] = []
    offset = 0
    for line in svg_text.splitlines(keepends=True):
        s = line.strip()
        if s.startswith('<'):
            m_close = _CLOSE_G_RE.search(s)
            m_open = _OPEN_G_RE.search(s)
            if m_open:
                gid = _attr(m_open.group(2), "id") or ""
                stack.append({"id": gid, "txt": gid.startswith("TXT-"),
                              "obj": None, "text_content": None, "geo": None,
                              "start": offset})
                if s.endswith('/>'):
                    stack.pop()
            elif m_close:
                if stack:
                    frame = stack.pop()
                    oid = frame.get("obj")
                    if oid and oid in devices:
                        devices[oid].block_end = offset + len(line)
                    if frame["txt"] and frame.get("text_content") and oid is None:
                        pass  # TXT without PSR_Ref: ignore
            else:
                if stack:
                    frame = stack[-1]
                    # NOTE: single if/elif chain — no `continue` here, so the
                    # per-line offset bookkeeping below runs for EVERY line
                    # (a previous revision's bare `continue`s skipped it and
                    # corrupted block_start/block_end char offsets).
                    m_psr = _PSR_RE.search(s)
                    m_gl = _GLINK_RE.search(s)
                    if m_psr:
                        attrs = m_psr.group(2) or ""
                        oid = _attr(attrs, "ObjectID")
                        name = _attr(attrs, "ObjectName")
                        psr_type = _attr(attrs, "PSRType")
                        if frame["txt"]:
                            if oid and oid.startswith("TXT_"):
                                target = oid[len("TXT_"):]
                                content = frame.get("text_content")
                                if content:
                                    labels.setdefault(content, target)
                        else:
                            if oid:
                                dev = devices.get(oid)
                                if dev is None:
                                    dev = CIMDevice(block_id=frame["id"], object_id=oid,
                                                     block_start=frame["start"])
                                    devices[oid] = dev
                                if name and not dev.name:
                                    dev.name = name
                                if psr_type and not dev.psr_type:
                                    dev.psr_type = psr_type
                                # geometry line precedes metadata in real CIM files:
                                # attach the buffered position now
                                if dev.x is None and frame.get("geo"):
                                    dev.x, dev.y = frame["geo"]
                                frame["obj"] = oid
                    elif m_gl and frame.get("obj"):
                        nb = m_gl.group(2)
                        dev = devices.get(frame["obj"])
                        if dev is not None and nb not in dev.neighbors:
                            dev.neighbors.append(nb)
                    else:
                        m_tx = _TEXT_RE.search(s)
                        if m_tx and frame["txt"]:
                            content = (m_tx.group(2) or "").strip()
                            if content:
                                frame["text_content"] = content
                        else:
                            m_use = _USE_RE.search(s)
                            if m_use:
                                if frame.get("geo") is None:
                                    ux = _attr(m_use.group(2), "x")
                                    uy = _attr(m_use.group(2), "y")
                                    if ux and uy:
                                        try:
                                            frame["geo"] = (float(ux), float(uy))
                                        except ValueError:
                                            pass
                            else:
                                m_poly = _POLY_RE.search(s)
                                if m_poly:
                                    if frame.get("geo") is None:
                                        pts = _attr(m_poly.group(2), "points") or ""
                                        coords = re.findall(r"([-\d.]+)[,\s]+([-\d.]+)", pts)
                                        if coords:
                                            xs = [float(a) for a, _ in coords]
                                            ys = [float(b) for _, b in coords]
                                            frame["geo"] = (sum(xs) / len(xs), sum(ys) / len(ys))
        offset += len(line)
    return devices, labels


def find_anchor(devices: dict[str, CIMDevice], labels: dict[str, str],
                query: str) -> CIMDevice | None:
    """Deterministic anchor lookup by device name / label text.

    Order: exact ObjectName, unique ObjectName suffix, exact label,
    unique label suffix. Returns ``None`` when no unique candidate exists.
    """
    q = (query or "").strip()
    if not q:
        return None
    for oid in sorted(devices):
        d = devices[oid]
        if d.name and d.name.strip() == q:
            return d
    cands = [devices[o] for o in sorted(devices)
             if devices[o].name and devices[o].name.strip().endswith(q)]
    if len(cands) == 1:
        return cands[0]
    for txt in sorted(labels):
        if txt.strip() == q and labels[txt] in devices:
            return devices[labels[txt]]
    cands = [devices[labels[t]] for t in sorted(labels)
             if t.strip().endswith(q) and labels[t] in devices]
    if len(cands) == 1:
        return cands[0]
    return None


# ---------------------------------------------------------------------------
# GLink surgery helpers
# ---------------------------------------------------------------------------

def _glink_line(prefix_ns: str, object_id: str) -> str:
    # tolerate callers that pass the prefix with or without the colon
    p = prefix_ns or ""
    ns = p if p.endswith(":") else (f"{p}:" if p else "")
    return f'<{ns}GLink_Ref ObjectID="{object_id}"/>'


def _block_glink_lines(block_text: str) -> list[str]:
    return _GLINK_RE.findall(block_text)


def _rewrite_block_glinks(block_text: str, new_neighbors: list[str]) -> str:
    """Replace the GLink_Ref run of one block with ``new_neighbors``.

    Old GLink lines are dropped entirely; the new run is inserted right
    before ``Layer_Ref`` (or the metadata close), matching the real CIM
    ordering PSR_Ref, GLink_Ref*, Layer_Ref.
    """
    lines = block_text.splitlines(keepends=True)
    ns = ""
    first_gl = next((ln for ln in lines if _GLINK_RE.search(ln)), None)
    if first_gl is not None:
        m = re.match(r'<([\w.-]+:)?', first_gl.strip())
        ns = (m.group(1) or "") if m else ""
    gl_pat = re.compile(r'^\s*<([\w.-]+:)?GLink_Ref\b[^>]*/>\s*$')
    kept = [ln for ln in lines if not gl_pat.match(ln)]
    insert_at = None
    for i, ln in enumerate(kept):
        if "Layer_Ref" in ln:
            insert_at = i
            break
    if insert_at is None:
        for i in range(len(kept) - 1, -1, -1):
            if "</metadata>" in kept[i]:
                insert_at = i
                break
    if insert_at is None:
        insert_at = len(kept)
    new_lines = [_glink_line(ns, nb) + "\n" for nb in new_neighbors]
    return "".join(kept[:insert_at] + new_lines + kept[insert_at:])


def _strip_glinks_to(svg_text: str, target_id: str) -> str:
    """Remove every GLink_Ref line pointing at ``target_id``."""
    pat = re.compile(
        r'^\s*<([\w.-]+:)?GLink_Ref\b[^>]*?ObjectID="' + re.escape(target_id) + r'"[^>]*/>\s*\n?',
        re.MULTILINE,
    )
    return pat.sub("", svg_text)


# ---------------------------------------------------------------------------
# T5: add room between two switches
# ---------------------------------------------------------------------------

T5_INNER_DEFAULTS = (
    ("SW00301", "负荷开关00301"),
    ("SW00302", "备用间隔00302"),
    ("SW00303", "负荷开关00303"),
)


def run_t5(svg_text: str, *,
           room_id: str = "ROOM000300",
           room_name: str = "新增站房000300",
           left_query: str = "开关00104",
           right_query: str = "开关00102",
           inner_switches: tuple[tuple[str, str], ...] = T5_INNER_DEFAULTS,
           ) -> dict[str, Any]:
    """Execute official T5 on a CIM SVG document.

    Returns a result dict: ``ok``, ``svg`` (modified document),
    ``report`` (human-readable steps), ``diagnostics`` (anchor ids).
    Fails gracefully when anchors are missing or ambiguous.
    """
    report: list[str] = []
    # step 1 choose
    devices, labels = parse_cim(svg_text)
    report.append(f"choose: parsed {len(devices)} CIM device blocks, {len(labels)} labels")
    left = find_anchor(devices, labels, left_query)
    right = find_anchor(devices, labels, right_query)
    if left is None or right is None:
        diag = {
            "left_query": left_query, "right_query": right_query,
            "left_found": left.object_id if left else None,
            "right_found": right.object_id if right else None,
            "sample_names": sorted({d.name for d in devices.values() if d.name})[:40],
        }
        report.append("choose FAILED: anchor not found (see diagnostics)")
        return {"ok": False, "error": "anchor not found", "report": report,
                "diagnostics": diag}
    if left is right:
        return {"ok": False, "error": "left and right anchors resolve to the same device",
                "report": report,
                "diagnostics": {"left": left.object_id, "right": right.object_id}}

    # step 2 validate
    inner_ids = [sid for sid, _ in inner_switches]
    for sid in inner_ids:
        if sid in devices:
            return {"ok": False, "error": f"inner switch id {sid} already exists",
                    "report": report, "diagnostics": {}}
    lx, ly = left.pos
    rx, ry = right.pos
    mx, my = ((lx + rx) / 2.0, (ly + ry) / 2.0 - 90.0)   # room above the line
    box_w, box_h = 330.0, 110.0
    sw_pos = [(mx - 110.0, my + 55.0), (mx, my + 55.0), (mx + 110.0, my + 55.0)]
    report.append(f"validate ok: left={left.object_id} ({left.name}) "
                  f"right={right.object_id} ({right.name})")

    # step 3 preview: build the new document in memory
    ns_g = "ns0" if "<ns0:g" in svg_text else ""
    ns_m = "ns2" if "<ns2:PSR_Ref" in svg_text else ""
    g_pre = f"{ns_g}:" if ns_g else ""
    m_pre = f"{ns_m}:" if ns_m else ""

    def _meta(oid: str, name: str, neighbors: list[str]) -> str:
        # NOTE: real CIM files use ns0:metadata as the container while the
        # reference elements inside it are ns2:* — keep both prefixes distinct.
        safe_name = _html.escape(name, quote=True)
        parts = [f'      <{g_pre}metadata>',
                 f'        <{m_pre}PSR_Ref ObjectID="{oid}" ObjectName="{safe_name}" PSRType="0115" TopType="02" businessType="3"/>']
        for nb in neighbors:
            parts.append(f'        <{m_pre}GLink_Ref ObjectID="{nb}"/>')
        parts.append(f'      </{g_pre}metadata>')
        return "\n".join(parts)

    inner_xml: list[str] = []
    for i, (sid, sname) in enumerate(inner_switches):
        sx, sy = sw_pos[i]
        if i == 0:
            nbs = [left.object_id]
        elif i == len(inner_switches) - 1 and len(inner_switches) > 1:
            nbs = [right.object_id]
        else:
            nbs = []   # spare bay (备间隔): no wiring
        safe_sname = _html.escape(sname)
        inner_xml.append(
            f'    <{g_pre}g id="TMP_T5_{sid}" data-equip-id="{sid}">\n'
            f'      <{g_pre}rect x="{sx - 26:.1f}" y="{sy - 16:.1f}" width="52" height="32" '
            f'fill="#90EE90" stroke="#333"/>\n'
            f'      <{g_pre}text x="{sx:.1f}" y="{sy + 4:.1f}" text-anchor="middle" font-size="11">{safe_sname}</{g_pre}text>\n'
            + _meta(sid, sname, nbs) + "\n"
            f'    </{g_pre}g>'
        )
    connectors = (
        f'    <{g_pre}polyline points="{lx:.1f},{ly:.1f} {sw_pos[0][0]:.1f},{sw_pos[0][1]:.1f}" '
        f'fill="none" stroke="#C00000" stroke-width="1.2"/>\n'
        f'    <{g_pre}polyline points="{sw_pos[-1][0]:.1f},{sw_pos[-1][1]:.1f} {rx:.1f},{ry:.1f}" '
        f'fill="none" stroke="#C00000" stroke-width="1.2"/>'
    )
    safe_room_name = _html.escape(room_name, quote=True)
    # 站房容器自身必须是 CIM 对象（QC 终检 5.2：房间容器缺 PSR_Ref）。
    # 真实 CIM 中站房类对象的约定为 PSRType="zf07"（见 LINE215.svg 站房块）。
    room_meta = (
        f'    <{g_pre}metadata>\n'
        f'      <{m_pre}PSR_Ref LineType="Trunk" ObjectID="{room_id}" '
        f'ObjectName="{safe_room_name}" PSRType="zf07" TopType="02" businessType="3"/>\n'
        f'    </{g_pre}metadata>\n'
    )
    room_block = (
        f'  <{g_pre}g class="room" id="TMP_T5_{room_id}" data-room-id="{room_id}">\n'
        f'    <{g_pre}rect x="{mx - box_w / 2:.1f}" y="{my - 20:.1f}" width="{box_w:.1f}" height="{box_h:.1f}" '
        f'fill="#FFFACD" stroke="#888" stroke-dasharray="5,3"/>\n'
        f'    <{g_pre}text x="{mx:.1f}" y="{my - 28:.1f}" text-anchor="middle" font-size="12" '
        f'font-weight="bold">{_html.escape(room_name)} ({room_id})</{g_pre}text>\n'
        + room_meta
        + connectors + "\n"
        + "\n".join(inner_xml) + "\n"
        f'  </{g_pre}g>\n'
    )
    # splice before the document's closing svg tag (namespace may vary)
    m_svg_close = re.search(r'</(?:[\w.-]+:)?svg\s*>', svg_text)
    if m_svg_close is None:
        return {"ok": False, "error": "no closing svg tag found",
                "report": report, "diagnostics": {}}
    preview_svg = (svg_text[:m_svg_close.start()] + room_block
                   + svg_text[m_svg_close.start():])

    # GLink surgery: anchors gain the room's entry switches as neighbours.
    left_dev, right_dev = devices[left.object_id], devices[right.object_id]
    new_left_nbs = list(left_dev.neighbors) + [inner_ids[0]]
    new_right_nbs = list(right_dev.neighbors) + [inner_ids[-1]]
    for dev, nbs in ((left_dev, new_left_nbs), (right_dev, new_right_nbs)):
        block = svg_text[dev.block_start:dev.block_end]
        rewritten = _rewrite_block_glinks(block, nbs)
        preview_svg = preview_svg.replace(block, rewritten, 1)

    # step 4 apply + step 5 validate (topological consistency of result)
    after_devices, _ = parse_cim(preview_svg)
    problems = []
    if not any(f'data-room-id="{room_id}"' in ln for ln in preview_svg.splitlines()):
        problems.append("room container missing after apply")
    for sid in inner_ids:
        if sid not in after_devices and f'data-equip-id="{sid}"' not in preview_svg:
            problems.append(f"inner switch {sid} missing after apply")
    for anchor in (left, right):
        if anchor.object_id not in after_devices:
            problems.append(f"anchor {anchor.object_id} lost after apply")
    dangling_new = set()
    for d in after_devices.values():
        for nb in d.neighbors:
            if nb not in after_devices and nb not in svg_text:
                dangling_new.add(nb)
    if problems:
        return {"ok": False, "error": "; ".join(problems), "report": report,
                "diagnostics": {"left": left.object_id, "right": right.object_id}}
    report.append("apply+validate ok: room inserted, anchors intact, "
                  f"GLink updated ({left.object_id}+={inner_ids[0]}, "
                  f"{right.object_id}+={inner_ids[-1]})")
    # steps 6-7 confirm+save are implicit in the returned committed document
    report.append("confirm(user=pipeline) + save: committed")
    return {
        "ok": True,
        "svg": preview_svg,
        "report": report,
        "diagnostics": {
            "left": left.object_id, "right": right.object_id,
            "room": room_id, "inner": list(inner_ids),
            "dangling_refs_not_in_source": sorted(dangling_new)[:10],
        },
    }


# ---------------------------------------------------------------------------
# T6: remove a switch and direct-connect its neighbours
# ---------------------------------------------------------------------------

_HSEG_RE = re.compile(
    r'<(?:[\w.-]+:)?(?:polyline|line)\b([^>]*)points="([^"]+)"[^>]*>',
    re.DOTALL)


def _bridge_deleted_gap(svg_after: str, dev: CIMDevice) -> tuple[str, str | None]:
    """Bridge the busbar gap that the removed device's symbol used to cover.

    Real CIM busbars are drawn as a chain of tiny per-device stub segments; a
    switch ``<use>`` symbol sits visually on top of the stub gap it spans.
    Removing the switch exposes that sub-pixel gap (QC 终检 5.2: ≈2.76 SVG
    units ≈ 0.17 px at the deletion point). This restores visual continuity
    by drawing one plain line across the gap on the device's own y-line whose
    span contains the device anchor x (fallback: nearest gap ≤5 units away).
    Returns ``(new_svg, description_or_None)``; a no-op when no qualifying
    gap exists (e.g. fixtures without stub chains).
    """
    if dev.x is None or dev.y is None:
        return svg_after, None
    y_star = dev.y
    tol = 0.05

    def hsegs(text: str):
        segs = []
        for m in _HSEG_RE.finditer(text):
            attrs, pts_raw = m.group(1), m.group(2)
            pts = []
            for p in pts_raw.split():
                parts = p.split(",")
                if len(parts) == 2:
                    try:
                        pts.append((float(parts[0]), float(parts[1])))
                    except ValueError:
                        continue
            for (x1, y1), (x2, y2) in zip(pts[:-1], pts[1:]):
                if abs(y1 - y_star) <= tol and abs(y2 - y_star) <= tol \
                        and abs(x1 - x2) > 1e-9:
                    segs.append((min(x1, x2), max(x1, x2), attrs))
        return segs

    merged: list[list] = []
    for lo, hi, attrs in sorted(hsegs(svg_after)):
        if merged and lo <= merged[-1][1] + 1e-6:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi, attrs])
    target = None
    best = None
    for i in range(len(merged) - 1):
        gap_lo, gap_hi = merged[i][1], merged[i + 1][0]
        size = gap_hi - gap_lo
        if not (0.2 <= size <= 20.0):
            continue
        if gap_lo <= dev.x <= gap_hi:
            target = (i, size)
            break
        mid = (gap_lo + gap_hi) / 2.0
        d = abs(mid - dev.x)
        if d <= 5.0 and (best is None or d < best[0]):
            best = (d, i, size)
    if target is None and best is not None:
        target = (best[1], best[2])
    if target is None:
        return svg_after, None
    i, size = target
    left, right = merged[i], merged[i + 1]
    stroke_m = re.search(r'stroke="([^"]+)"', left[2])
    width_m = re.search(r'stroke-width="([^"]+)"', left[2])
    stroke = stroke_m.group(1) if stroke_m else "rgb(128,128,128)"
    width = width_m.group(1) if width_m else "1"
    ns_prefix = "ns0:" if "<ns0:g" in svg_after else ""
    bridge = (
        f'    <{ns_prefix}line x1="{left[1]:.6f}" y1="{y_star:.6f}" '
        f'x2="{right[0]:.6f}" y2="{y_star:.6f}" '
        f'stroke="{stroke}" stroke-width="{width}"/>'
    )
    m_close = re.search(r'</(?:[\w.-]+:)?svg\s*>', svg_after)
    if m_close is None:
        return svg_after, None
    new_svg = (svg_after[:m_close.start()] + bridge + "\n"
               + svg_after[m_close.start():])
    return new_svg, (f"({left[1]:.4f},{y_star:.4f})->({right[0]:.4f},"
                     f"{y_star:.4f}) size={size:.4f}")


def run_t6(svg_text: str, *, target_query: str = "开关00024") -> dict[str, Any]:
    """Execute official T6 on a CIM SVG document.

    Removes the target device block, its TXT label block(s), every
    GLink_Ref pointing at it, and — when exactly two neighbours exist —
    adds the direct neighbour<->neighbour link. Returns the same result
    shape as :func:`run_t5`.
    """
    report: list[str] = []
    devices, labels = parse_cim(svg_text)
    report.append(f"choose: parsed {len(devices)} CIM device blocks, {len(labels)} labels")
    dev = find_anchor(devices, labels, target_query)
    if dev is None:
        diag = {
            "target_query": target_query,
            "sample_names": sorted({d.name for d in devices.values() if d.name})[:40],
        }
        report.append("choose FAILED: target not found (see diagnostics)")
        return {"ok": False, "error": "target device not found",
                "report": report, "diagnostics": diag}
    nbs = list(dev.neighbors)
    if len(nbs) >= 2:
        a, b = sorted(nbs)[:2]
    elif len(nbs) == 1:
        a = b = nbs[0]
    else:
        a = b = None
    report.append(f"validate ok: target={dev.object_id} ({dev.name}) neighbours={nbs}")

    # step 3 preview: splice out the blocks (largest offset first)
    removed_blocks: list[tuple[int, int]] = [(dev.block_start, dev.block_end)]
    # TXT label block(s) whose PSR ObjectID is "TXT_<device>". Scanned
    # line-wise so an enclosing layer group can never be swallowed: a TXT
    # block is flat (no nested <g>), so its close is the next </...g> line.
    lines = svg_text.splitlines(keepends=True)
    offsets: list[int] = []
    acc = 0
    for ln in lines:
        offsets.append(acc)
        acc += len(ln)
    txt_open_re = re.compile(r'^\s*<([\w.-]+:)?g id="(TXT-[^"]+)"[^>]*/?>')
    g_close_re = re.compile(r'</(?:[\w.-]+:)?g\s*>')
    want = f'ObjectID="TXT_{dev.object_id}"'
    for i, ln in enumerate(lines):
        m = txt_open_re.match(ln)
        if not m:
            continue
        j = i
        while j < len(lines) and not g_close_re.search(lines[j]):
            j += 1
        if j >= len(lines):
            continue
        block = "".join(lines[i:j + 1])
        if want in block:
            removed_blocks.append((offsets[i], offsets[j + 1]))
    # any other block that merely references the device keeps living; only
    # its GLink lines are stripped below.
    preview_svg = svg_text
    for start, end in sorted(removed_blocks, key=lambda t: -t[0]):
        preview_svg = preview_svg[:start] + preview_svg[end:]

    # strip dangling GLink refs everywhere
    preview_svg = _strip_glinks_to(preview_svg, dev.object_id)

    # direct-connect the two neighbours. Re-parse before EACH rewrite:
    # rewriting one block changes document offsets, so stored offsets of
    # the other side would go stale.
    if a and b and a != b:
        for side, other in ((a, b), (b, a)):
            cur_devices, _ = parse_cim(preview_svg)
            if side not in cur_devices:
                continue
            sd = cur_devices[side]
            new_nbs = [n for n in sd.neighbors if n != dev.object_id]
            if other not in new_nbs:
                new_nbs.append(other)
            block = preview_svg[sd.block_start:sd.block_end]
            rewritten = _rewrite_block_glinks(block, new_nbs)
            preview_svg = preview_svg.replace(block, rewritten, 1)
        report.append(f"direct connect added: {a} <-> {b}")
    elif a:
        report.append(f"single neighbour {a}: no direct pair to add")

    # step 3b: restore visual busbar continuity across the gap the removed
    # device's symbol used to cover (QC 终检 5.2 sub-pixel gap).
    preview_svg, bridge_desc = _bridge_deleted_gap(preview_svg, dev)
    if bridge_desc:
        report.append(f"busbar bridge added: {bridge_desc}")

    # step 4 apply + step 5 validate
    after_devices, after_labels = parse_cim(preview_svg)
    problems = []
    if dev.object_id in after_devices:
        problems.append("target device still present after apply")
    leftover_refs = {nb for d in after_devices.values() for nb in d.neighbors
                     if nb == dev.object_id}
    if leftover_refs:
        problems.append("dangling GLink_Ref to removed device remains")
    if problems:
        return {"ok": False, "error": "; ".join(problems), "report": report,
                "diagnostics": {"target": dev.object_id}}
    report.append("apply+validate ok: device + label removed, no dangling refs")
    report.append("confirm(user=pipeline) + save: committed")
    return {
        "ok": True,
        "svg": preview_svg,
        "report": report,
        "diagnostics": {
            "target": dev.object_id,
            "direct_pair": [a, b] if a and b and a != b else None,
            "blocks_removed": len(removed_blocks),
        },
    }


# ---------------------------------------------------------------------------
# Unified entry point
# ---------------------------------------------------------------------------

def run_scenario(svg_text: str, *, kind: str, **kwargs: Any) -> dict[str, Any]:
    """Dispatch to :func:`run_t5` / :func:`run_t6` by scenario kind."""
    if kind == "t5":
        return run_t5(svg_text, **kwargs)
    if kind == "t6":
        return run_t6(svg_text, **kwargs)
    raise ValueError(f"unknown scenario kind: {kind!r} (expected 't5' or 't6')")


__all__ = [
    "CIMDevice",
    "T5_INNER_DEFAULTS",
    "find_anchor",
    "parse_cim",
    "run_scenario",
    "run_t5",
    "run_t6",
]
