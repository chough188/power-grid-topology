"""Minimal SVG contract checks for offline-only tests."""
from __future__ import annotations

from collections.abc import Iterable
from xml.etree import ElementTree


def validate_svg_document(svg_text: str) -> list[str]:
    if not isinstance(svg_text, str) or not svg_text.strip():
        return ["SVG_EMPTY"]
    try:
        root = ElementTree.fromstring(svg_text)
    except ElementTree.ParseError:
        return ["SVG_XML_INVALID"]
    if not root.tag.lower().endswith("svg"):
        return ["SVG_ROOT_INVALID"]
    ids: set[str] = set()
    issues: list[str] = []
    for element in root.iter():
        element_id = element.attrib.get("id")
        if not element_id:
            continue
        if element_id in ids:
            issues.append(f"SVG_DUPLICATE_ID:{element_id}")
        ids.add(element_id)
    return issues


def synthetic_svg() -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 120">'
        '<g id="LINE001"><rect id="SW001" x="80" y="50" width="20" height="20"/>'
        '<line id="EDGE001" x1="20" y1="60" x2="80" y2="60"/></g></svg>'
    )