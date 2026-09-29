# -*- coding: utf-8 -*-
"""CIM/XML 解析器（Phase 6.1，简化版）。"""
from __future__ import annotations
import xml.etree.ElementTree as ET
from typing import Dict, Any
import pandapower as pp


def parse_cim(xml_path: str) -> pp.auxiliary.pandapowerNet:
    """解析 CIM/E XML 并转换为 pandapower 网络。

    简化实现：解析 Substation/VoltageLevel/Equipment 元素，
    提取 Bus/Breaker/Line 等基本结构。
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    # CIM namespace
    ns = {"cim": "http://iec.ch/TC57/2013/CIM-schema-cim16#"}

    net = pp.create_empty_network()

    # 解析 Bus（用 ConnectivityNode/CIM16）
    bus_id_map = {}
    for i, cnode in enumerate(root.findall(".//cim:ConnectivityNode", ns)):
        # name: 优先 cim:name 子元素, 其次 name 属性, 最后默认
        nm_el = cnode.find("cim:name", ns)
        name = nm_el.text if nm_el is not None and nm_el.text else cnode.get("name", f"bus_{i}")
        # vn_kv from nested BaseVoltage/nominalVoltage
        vn = cnode.find("cim:ConnectivityNodeContainer/cim:VoltageLevel/cim:BaseVoltage/cim:nominalVoltage", ns)
        vn_kv = float(vn.text) / 1000.0 if vn is not None and vn.text else 20.0
        pp.create_bus(net, vn_kv=vn_kv, name=name)
        # id: 优先 rdf:ID 属性, 其次 id 属性
        cim_id = cnode.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}ID")
        if not cim_id:
            cim_id = cnode.get("id", str(i))
        bus_id_map[cim_id] = i

    # 解析线路（ACLineSegment）
    for i, line in enumerate(root.findall(".//cim:ACLineSegment", ns)):
        ends = line.findall("cim:Terminal", ns)
        if len(ends) >= 2:
            from_bus_id = ends[0].get("ConnectivityNode", "")
            to_bus_id = ends[1].get("ConnectivityNode", "")
            if from_bus_id in bus_id_map and to_bus_id in bus_id_map:
                pp.create_line(net,
                    from_bus=bus_id_map[from_bus_id],
                    to_bus=bus_id_map[to_bus_id],
                    length_km=1.0,
                    std_type="NAYY 4x50 SE",
                    name=line.get("name", f"line_{i}")
                )

    return net


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        net = parse_cim(sys.argv[1])
        print(f"Parsed: {len(net.bus)} buses, {len(net.line)} lines")
    else:
        print("Usage: python cim_parser.py <cim_xml_file>")