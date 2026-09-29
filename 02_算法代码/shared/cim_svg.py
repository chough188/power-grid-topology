# -*- coding: utf-8 -*-
"""CIM / IEC 61970-301 style SVG parsing for official competition figures.

The released distribution-network SVGs do NOT use the simplified
``<g data-equip-id="...">`` markers that ``task_5_1_beautify`` targets.
Their structure (per figure element):

    <ns0:g id="TMP_<uuid>">
      ...shape elements (polyline / rect / circle / path)...
      <ns0:metadata>
        <ns2:PSR_Ref LineType="Trunk" ObjectID="TMP00xxxxxx"
                     ObjectName="..." PSRType="140000|zf01|..."/>
        <ns2:GLink_Ref ObjectID="TMPyyyyyyyy"/>   (zero or more)
        <ns2:Layer_Ref ObjectName="ConnLine_Layer|Substation_Layer|..."/>
      </ns0:metadata>
    </ns0:g>

Semantics used here (verified against the 2026-06-22 dataset):

* **device ids** = distinct ``PSR_Ref/@ObjectID`` values.  These are the
  physical resources drawn on the figure; they map 1:1 onto the
  ``EQUIP_ID`` vocabulary of JBS_PWEQUIPINFO / JBS_ZWEQUIPINFO when the
  model covers them (~27 % overlap in this dataset, per Q&A 50 the DB is
  authoritative and mismatches are reported, not silently merged).
* **graphical connectors** = PSR blocks whose ``PSRType`` is ``140000``
  (trunk/wire drawing artefacts with no model row) and that live on a
  connection-type layer (ConnLine_Layer / ACLineSegment_Layer).
* **text annotations** = ``<g id="TXT-...">`` blocks on Text_Layer holding a
  ``<text>`` name label.  Their PSR ObjectIDs carry a ``TXT_`` prefix mirroring
  the labelled device's ID (e.g. TXT_TMP00013138 labels 开关00133 = TMP00013138).
  They are NOT devices: verified corpus-wide (2026-06-22 data, 165 SVGs) every
  TXT_ label id maps onto a real device block, so excluding them removes ~19k
  phantom figure-only ids without hiding any genuine 2.1 finding.
* **edges** = for every ``GLink_Ref`` object id *g*, let S(g) be the set of
  PSR ids of the blocks referencing *g*.  After dropping graphical
  connectors, all pairs within S(g) are physically connected in the figure.
  (A wire between A and B shows up as S(g) = {A, wire, B} -> edge (A, B);
  a busbar junction with k devices yields the k-clique.)

The parser is regex-based (files are large and consistently namespaced);
it never raises on malformed input and degrades to an empty result.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Iterable

__all__ = ["parse_cim_blocks", "cim_device_ids", "cim_edges", "parse_cim_svg"]

# A figure-element block: <nsX:g id="..."> ... </nsX:g>.  The closing tag
# must use the same namespace prefix as the opening one.
_BLOCK_RE = re.compile(
    r'<(?P<prefix>[A-Za-z][\w.-]*):g\b[^>]*?\bid="(?P<block_id>[^"]*)"[^>]*>'
    r'(?P<inner>.*?)(?:</(?P=prefix):g>)',
    re.DOTALL,
)
# Full self-closed metadata tags (namespace prefix tolerated).
_PSR_TAG_RE = re.compile(r'<[A-Za-z][\w.-]*:PSR_Ref\b[^>]*/?>')
_GLINK_TAG_RE = re.compile(r'<[A-Za-z][\w.-]*:GLink_Ref\b[^>]*/?>')
_LAYER_TAG_RE = re.compile(r'<[A-Za-z][\w.-]*:Layer_Ref\b[^>]*/?>')
_ATTR_RE = re.compile(r'([A-Za-z_]\w*)="([^"]*)"')

#: PSRType marking pure drawing artefacts (wire / trunk segments).
WIRE_PSR_TYPE = "140000"
#: g-id prefix of text-annotation blocks (name labels, not devices).
TEXT_BLOCK_PREFIX = "TXT-"
#: PSR ObjectID prefix of text-annotation references.
TEXT_PSR_PREFIX = "TXT_"
#: Layers that hold connection geometry rather than equipment symbols.
CONNECTOR_LAYERS = frozenset({
    "connline_layer",
    "aclinesegment_layer",
})


def _attrs(tag_text: str) -> dict[str, str]:
    return dict(_ATTR_RE.findall(tag_text))


def parse_cim_blocks(svg_text: str) -> list[dict[str, Any]]:
    """Extract one record per figure element.

    Returns a list of dicts:
      {block_id, psr_id, psr_name, psr_type, layer, glinks: [str, ...]}
    Blocks without a PSR_Ref are omitted.
    """
    if not svg_text:
        return []
    out: list[dict[str, Any]] = []
    for m in _BLOCK_RE.finditer(svg_text):
        inner = m.group("inner")
        psr_tag = _PSR_TAG_RE.search(inner)
        if not psr_tag:
            continue
        psr_attrs = _attrs(psr_tag.group(0))
        psr_id = psr_attrs.get("ObjectID", "")
        if not psr_id:
            continue
        layer_tag = _LAYER_TAG_RE.search(inner)
        layer = ""
        if layer_tag:
            layer = _attrs(layer_tag.group(0)).get("ObjectName", "")
        block_id = m.group("block_id")
        out.append({
            "block_id": block_id,
            "psr_id": psr_id,
            "psr_name": psr_attrs.get("ObjectName", ""),
            "psr_type": psr_attrs.get("PSRType", ""),
            "layer": layer,
            "glinks": [
                _attrs(g.group(0)).get("ObjectID", "")
                for g in _GLINK_TAG_RE.finditer(inner)
            ],
            # Text_Layer name labels are annotations of other devices, not devices.
            "is_text": (
                block_id.startswith(TEXT_BLOCK_PREFIX)
                or psr_id.startswith(TEXT_PSR_PREFIX)
            ),
        })
    return out


def _is_connector(block: dict[str, Any]) -> bool:
    """True for wire/trunk drawing artefacts (no model row exists for them)."""
    layer = (block.get("layer") or "").lower()
    if block.get("psr_type") == WIRE_PSR_TYPE:
        return True
    # Empty PSRType counts as connector only on connection-geometry layers.
    if block.get("psr_type") == "" and layer in CONNECTOR_LAYERS:
        return True
    return False


def cim_device_ids(blocks: Iterable[dict[str, Any]]) -> set[str]:
    """Distinct PSR ObjectIDs across all device blocks (figure-side device set).

    Text-annotation blocks (TXT_* name labels) are excluded: they are not
    devices and would otherwise flood 2.1 with phantom fig-only records.
    """
    return {
        b["psr_id"]
        for b in blocks
        if b.get("psr_id") and not b.get("is_text")
    }


def cim_edges(blocks: Iterable[dict[str, Any]]) -> list[tuple[str, str]]:
    """Physically-connected device pairs derived from shared GLink refs.

    Graphical connector blocks (wire/trunk artefacts) are dropped from the
    endpoint sets before pair emission.  Pairs are emitted sorted and
    de-duplicated.
    """
    glink_members: dict[str, set[str]] = defaultdict(set)
    for b in blocks:
        pid = b.get("psr_id")
        if not pid or b.get("is_text"):
            continue
        for gl in b.get("glinks", ()):  # type: ignore[union-attr]
            if gl:
                glink_members[gl].add(pid)

    connector_ids = {
        b["psr_id"] for b in blocks if b.get("psr_id") and _is_connector(b)
    }
    edges: set[tuple[str, str]] = set()
    for members in glink_members.values():
        endpoints = sorted(members - connector_ids)
        if len(endpoints) < 2:
            continue
        for i in range(len(endpoints)):
            for j in range(i + 1, len(endpoints)):
                edges.add((endpoints[i], endpoints[j]))
    return sorted(edges)


def parse_cim_svg(svg_text: str) -> tuple[set[str], list[tuple[str, str]]]:
    """Convenience wrapper: (device_ids, edges) for one SVG document."""
    blocks = parse_cim_blocks(svg_text)
    return cim_device_ids(blocks), cim_edges(blocks)
