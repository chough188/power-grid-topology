# -*- coding: utf-8 -*-
"""Tests for the CIM-aware T5/T6 official scenario runners (5.2).

Fixtures mirror the real CIM IEC 61970-301 export dialect observed in
``配网 svg/LINE215.svg``: namespaced device blocks
(``<ns0:g id="TMP_<uuid>">`` + ``<ns2:PSR_Ref>`` + ``<ns2:GLink_Ref>*``),
TXT label blocks (``ObjectID="TXT_<device>"``), nested layer groups, and
geometry lines that PRECEDE the metadata line.
"""
from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tasks_official.task5_svg.task_5_2_modify import scenarios as t56


T5_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<ns0:svg xmlns:ns0="http://www.w3.org/2000/svg" xmlns:ns1="urn:xlink" xmlns:ns2="urn:cim" width="800" height="600">
  <ns0:g id="ACLineSegment_Layer">
    <ns0:g id="TMP_aaaaaaaa-0000-0000-0000-000000000001">
      <ns0:use class="lkv10" ns1:href="#Breaker_x" width="4" height="4" x="100.0" y="200.0"/>
      <ns0:metadata>
        <ns2:PSR_Ref LineType="Trunk" ObjectID="TMP00000101" ObjectName="开关00104" PSRType="0115" TopType="02" businessType="3"/>
        <ns2:GLink_Ref ObjectID="TMP00000102"/>
        <ns2:Layer_Ref ObjectName="TMP00009999"/>
      </ns0:metadata>
    </ns0:g>
    <ns0:g id="TMP_bbbbbbbb-0000-0000-0000-000000000002">
      <ns0:use class="lkv10" ns1:href="#Breaker_y" width="4" height="4" x="300.0" y="200.0"/>
      <ns0:metadata>
        <ns2:PSR_Ref LineType="Trunk" ObjectID="TMP00000102" ObjectName="开关00102" PSRType="0115" TopType="02" businessType="3"/>
        <ns2:GLink_Ref ObjectID="TMP00000101"/>
        <ns2:Layer_Ref ObjectName="TMP00009999"/>
      </ns0:metadata>
    </ns0:g>
    <ns0:g id="TXT-TMP_cccccccc-0000-0000-0000-000000000003">
      <ns0:text x="100.0" y="180.0">开关00104</ns0:text>
      <ns0:metadata>
        <ns2:PSR_Ref LineType="Trunk" ObjectID="TXT_TMP00000101" PSRType="-1" TopType="02" businessType="5"/>
        <ns2:Layer_Ref ObjectName="TMP00009999"/>
      </ns0:metadata>
    </ns0:g>
  </ns0:g>
</ns0:svg>
"""

T6_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<ns0:svg xmlns:ns0="http://www.w3.org/2000/svg" xmlns:ns1="urn:xlink" xmlns:ns2="urn:cim" width="800" height="600">
  <ns0:g id="ACLineSegment_Layer">
    <ns0:g id="TMP_aaaaaaaa-0000-0000-0000-000000000101">
      <ns0:use class="lkv10" ns1:href="#Breaker_t" width="4" height="4" x="150.0" y="300.0"/>
      <ns0:metadata>
        <ns2:PSR_Ref LineType="Trunk" ObjectID="TMP00000201" ObjectName="开关00024" PSRType="0115" TopType="02" businessType="3"/>
        <ns2:GLink_Ref ObjectID="TMP00000202"/>
        <ns2:GLink_Ref ObjectID="TMP00000203"/>
        <ns2:Layer_Ref ObjectName="TMP00009999"/>
      </ns0:metadata>
    </ns0:g>
    <ns0:g id="TMP_bbbbbbbb-0000-0000-0000-000000000102">
      <ns0:use class="lkv10" ns1:href="#Fuse_t" width="4" height="4" x="80.0" y="300.0"/>
      <ns0:metadata>
        <ns2:PSR_Ref LineType="Trunk" ObjectID="TMP00000202" ObjectName="刀闸0023" PSRType="0115" TopType="02" businessType="5"/>
        <ns2:GLink_Ref ObjectID="TMP00000201"/>
        <ns2:Layer_Ref ObjectName="TMP00009999"/>
      </ns0:metadata>
    </ns0:g>
    <ns0:g id="TMP_cccccccc-0000-0000-0000-000000000103">
      <ns0:use class="lkv10" ns1:href="#Fuse_u" width="4" height="4" x="220.0" y="300.0"/>
      <ns0:metadata>
        <ns2:PSR_Ref LineType="Trunk" ObjectID="TMP00000203" ObjectName="刀闸0025" PSRType="0115" TopType="02" businessType="5"/>
        <ns2:GLink_Ref ObjectID="TMP00000201"/>
        <ns2:Layer_Ref ObjectName="TMP00009999"/>
      </ns0:metadata>
    </ns0:g>
    <ns0:g id="TXT-TMP_dddddddd-0000-0000-0000-000000000104">
      <ns0:text x="150.0" y="280.0">开关00024</ns0:text>
      <ns0:metadata>
        <ns2:PSR_Ref LineType="Trunk" ObjectID="TXT_TMP00000201" PSRType="-1" TopType="02" businessType="5"/>
        <ns2:Layer_Ref ObjectName="TMP00009999"/>
      </ns0:metadata>
    </ns0:g>
  </ns0:g>
</ns0:svg>
"""


def _assert_well_formed(svg_text: str) -> None:
    ET.fromstring(svg_text)   # raises on malformed XML / undeclared prefixes


class TestCIMParser(unittest.TestCase):
    def test_parse_devices_names_neighbors_positions(self):
        devices, labels = t56.parse_cim(T5_FIXTURE)
        self.assertEqual(set(devices), {"TMP00000101", "TMP00000102"})
        d1 = devices["TMP00000101"]
        self.assertEqual(d1.name, "开关00104")
        self.assertEqual(d1.psr_type, "0115")
        self.assertEqual(d1.neighbors, ["TMP00000102"])
        self.assertEqual((d1.x, d1.y), (100.0, 200.0))
        d2 = devices["TMP00000102"]
        self.assertEqual((d2.x, d2.y), (300.0, 200.0))
        # TXT label block is not a device but maps to the labelled device
        self.assertEqual(labels.get("开关00104"), "TMP00000101")

    def test_block_offsets_cover_metadata(self):
        devices, _ = t56.parse_cim(T5_FIXTURE)
        d1 = devices["TMP00000101"]
        block = T5_FIXTURE[d1.block_start:d1.block_end]
        self.assertIn('ObjectID="TMP00000101"', block)
        self.assertIn("</ns0:g>", block)
        self.assertNotIn("TMP00000102", block.split("PSR_Ref")[0])

    def test_find_anchor_exact_suffix_label_and_none(self):
        devices, labels = t56.parse_cim(T5_FIXTURE)
        self.assertIs(t56.find_anchor(devices, labels, "开关00104"),
                      devices["TMP00000101"])
        # suffix match (name ends with the query)
        self.assertIs(t56.find_anchor(devices, labels, "00102"),
                      devices["TMP00000102"])
        self.assertIsNone(t56.find_anchor(devices, labels, "开关99999"))
        self.assertIsNone(t56.find_anchor(devices, labels, ""))


class TestT5AddRoom(unittest.TestCase):
    def test_success_inserts_room_switches_and_glinks(self):
        res = t56.run_t5(T5_FIXTURE)
        self.assertTrue(res["ok"], res.get("error"))
        out = res["svg"]
        _assert_well_formed(out)
        self.assertIn('data-room-id="ROOM000300"', out)
        for sid in ("SW00301", "SW00302", "SW00303"):
            self.assertIn(f'data-equip-id="{sid}"', out)
        after, _ = t56.parse_cim(out)
        # anchors intact and gained the room entry switches as neighbours
        self.assertIn("TMP00000101", after)
        self.assertIn("TMP00000102", after)
        self.assertIn("SW00301", after["TMP00000101"].neighbors)
        self.assertIn("SW00303", after["TMP00000102"].neighbors)
        # inner wiring rules: 00301<->00104, 00302 spare, 00303<->00102
        self.assertEqual(after["SW00301"].neighbors, ["TMP00000101"])
        self.assertEqual(after["SW00302"].neighbors, [])
        self.assertEqual(after["SW00303"].neighbors, ["TMP00000102"])
        # original anchor link preserved
        self.assertIn("TMP00000102", after["TMP00000101"].neighbors)

    def test_missing_anchor_fails_gracefully(self):
        res = t56.run_t5(T5_FIXTURE, left_query="开关99999")
        self.assertFalse(res["ok"])
        self.assertIn("anchor not found", res["error"])
        self.assertIn("sample_names", res["diagnostics"])

    def test_same_anchor_rejected(self):
        res = t56.run_t5(T5_FIXTURE, left_query="开关00104", right_query="00104")
        self.assertFalse(res["ok"])
        self.assertIn("same device", res["error"])

    def test_duplicate_inner_id_rejected(self):
        # Rename ONLY the ObjectID (keep the name!) so the right anchor still
        # resolves via ObjectName — anchor resolution runs BEFORE the inner-id
        # collision check, and a missing anchor would mask the error under test.
        svg = T5_FIXTURE.replace(
            'ObjectID="TMP00000102" ObjectName="开关00102"',
            'ObjectID="SW00302" ObjectName="开关00102"',
            1,
        )
        res = t56.run_t5(svg)
        self.assertFalse(res["ok"])
        self.assertIn("already exists", res["error"])


class TestT6RemoveDevice(unittest.TestCase):
    def test_success_removes_device_label_and_direct_connects(self):
        res = t56.run_t6(T6_FIXTURE)
        self.assertTrue(res["ok"], res.get("error"))
        out = res["svg"]
        _assert_well_formed(out)
        after, labels_after = t56.parse_cim(out)
        self.assertNotIn("TMP00000201", after)
        self.assertNotIn("开关00024", list(labels_after))
        # no dangling refs to the removed device
        for d in after.values():
            self.assertNotIn("TMP00000201", d.neighbors)
        # direct neighbour<->neighbour connection added symmetrically
        self.assertIn("TMP00000203", after["TMP00000202"].neighbors)
        self.assertIn("TMP00000202", after["TMP00000203"].neighbors)
        self.assertEqual(res["diagnostics"]["direct_pair"],
                         ["TMP00000202", "TMP00000203"])
        # layer group survived
        self.assertIn("ACLineSegment_Layer", out)

    def test_missing_target_fails_gracefully(self):
        res = t56.run_t6(T6_FIXTURE, target_query="开关99999")
        self.assertFalse(res["ok"])
        self.assertIn("not found", res["error"])

    def test_single_neighbour_no_crash(self):
        svg = T6_FIXTURE.replace('<ns2:GLink_Ref ObjectID="TMP00000203"/>', "")
        svg = svg.replace('ObjectID="TMP00000203" ObjectName="刀闸0025"',
                          'ObjectID="TMP00000203X" ObjectName="刀闸0025X"')
        res = t56.run_t6(svg, target_query="开关00024")
        # target now has a single neighbour -> still removes cleanly
        self.assertTrue(res["ok"], res.get("error"))
        after, _ = t56.parse_cim(res["svg"])
        self.assertNotIn("TMP00000201", after)


class TestScenarioDispatch(unittest.TestCase):
    def test_dispatch_kinds(self):
        r5 = t56.run_scenario(T5_FIXTURE, kind="t5")
        self.assertTrue(r5["ok"])
        r6 = t56.run_scenario(T6_FIXTURE, kind="t6")
        self.assertTrue(r6["ok"])

    def test_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            t56.run_scenario(T5_FIXTURE, kind="t7")


if __name__ == "__main__":
    unittest.main()
