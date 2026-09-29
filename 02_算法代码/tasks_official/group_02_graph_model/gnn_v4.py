# -*- coding: utf-8 -*-
"""GNN v4: A 级 GNN+规则混合 - 注意力 + 边类型 + 任务头 + 置信度."""
from __future__ import annotations
import math
import sys
from typing import Any, Mapping, Sequence

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

FEATURE_TYPE_VOCAB = (
    "BREAKER", "SWITCH", "DISCONNECTOR", "LINE",
    "TRANSFORMER", "LOAD", "GENERATOR", "SOURCE",
    "BUS", "CABLE_HEAD", "TIE", "ROOM",
    "XF", "TRANS", "SPARE_BAY", "UNKNOWN",
)
EDGE_TYPE_VOCAB = (
    "POWER_LINE", "SWITCH_LINK", "TRANSFORMER_LINK", "GENERATOR_LINK",
    "LOAD_LINK", "SOURCE_LINK", "BUS_LINK", "ROOM_LINK", "UNKNOWN",
)
TASK_HEADS = (
    "1.1", "1.2", "1.3", "1.4", "1.5",
    "2.1", "2.2", "2.3", "2.4",
    "3.1", "4.1", "4.2",
)
try:
    torch.manual_seed(42)
except (ValueError, RuntimeError):
    pass

class GATLayer(nn.Module):
    def __init__(self, in_dim, out_dim, dropout=0.1):
        super().__init__()
        self.W = nn.Linear(in_dim, out_dim, bias=False)
        self.a_src = nn.Linear(out_dim, 1, bias=False)
        self.a_dst = nn.Linear(out_dim, 1, bias=False)
        self.leaky = nn.LeakyReLU(0.2)
        self.dropout = nn.Dropout(dropout)
        self.norm = nn.LayerNorm(out_dim)
    def forward(self, x, edge_index):
        h = self.W(x)
        N = h.size(0)
        if edge_index.size(1) == 0:
            return self.norm(h)
        src = edge_index[0]
        dst = edge_index[1]
        attn_src = self.a_src(h)[src].squeeze(-1)
        attn_dst = self.a_dst(h)[dst].squeeze(-1)
        attn = self.leaky(attn_src + attn_dst)
        attn = torch.exp(attn - attn.max())
        attn = self.dropout(attn)
        agg = torch.zeros(N, h.size(1), device=h.device, dtype=h.dtype)
        agg.index_add_(0, dst, (attn.unsqueeze(-1) * h[src]))
        deg = torch.zeros(N, device=h.device, dtype=h.dtype)
        deg.index_add_(0, dst, attn)
        deg = deg.clamp(min=1e-6).unsqueeze(-1)
        h_out = agg / deg
        if h_out.size(-1) == h.size(-1):
            h_out = self.norm(h_out + h)
        else:
            h_out = self.norm(h_out)
        return F.elu(h_out)

class RGCNLayer(nn.Module):
    def __init__(self, in_dim, out_dim, num_relations, dropout=0.1):
        super().__init__()
        self.W_self = nn.Linear(in_dim, out_dim)
        self.W_rel = nn.Linear(in_dim, out_dim, bias=False)
        self.rel_emb = nn.Embedding(num_relations, in_dim)
        self.norm = nn.LayerNorm(out_dim)
        self.dropout = nn.Dropout(dropout)
    def forward(self, x, edge_index, edge_type):
        h = self.W_self(x)
        if edge_index.size(1) == 0:
            return self.norm(h)
        src = edge_index[0]
        dst = edge_index[1]
        rel = self.rel_emb(edge_type)
        msg = self.W_rel(x[src] + rel)
        agg = torch.zeros_like(h)
        agg.index_add_(0, dst, msg)
        deg = torch.zeros(h.size(0), device=h.device, dtype=h.dtype)
        deg.index_add_(0, dst, torch.ones_like(dst, dtype=h.dtype))
        deg = deg.clamp(min=1.0).unsqueeze(-1)
        h_out = self.norm(h + self.dropout(agg / deg))
        return F.relu(h_out)

class HybridGNN(nn.Module):
    def __init__(self, in_dim, hidden=32, num_layers=2, num_relations=len(EDGE_TYPE_VOCAB), task_heads=TASK_HEADS, num_mc_samples=5):
        super().__init__()
        self.gat_layers = nn.ModuleList([GATLayer(in_dim if i == 0 else hidden, hidden) for i in range(num_layers)])
        self.rgcn_layers = nn.ModuleList([RGCNLayer(in_dim if i == 0 else hidden, hidden, num_relations) for i in range(num_layers)])
        self.fuse = nn.Linear(hidden * 2, hidden)
        self.task_codes = list(task_heads)
        self.task_heads = nn.ModuleList([nn.Sequential(nn.Linear(hidden, hidden), nn.ReLU(), nn.Dropout(0.1), nn.Linear(hidden, 1)) for _ in task_heads])
        self.confidence_head = nn.Sequential(nn.Linear(hidden, hidden), nn.ReLU(), nn.Linear(hidden, 1))
        self.num_mc_samples = num_mc_samples
        self.trained_task_codes: set[str] = set()
    def encode(self, x, edge_index, edge_type):
        h = x
        for gat, rgcn in zip(self.gat_layers, self.rgcn_layers):
            h_gat = gat(h, edge_index)
            h_rgcn = rgcn(h, edge_index, edge_type)
            h = self.fuse(torch.cat([h_gat, h_rgcn], dim=-1))
        return h
    def forward(self, x, edge_index, edge_type):
        z = self.encode(x, edge_index, edge_type)
        out = {code: head(z).squeeze(-1) for code, head in zip(self.task_codes, self.task_heads)}
        out["confidence"] = torch.sigmoid(self.confidence_head(z).squeeze(-1))
        return out
    def mc_dropout_forward(self, x, edge_index, edge_type):
        was_training = self.training
        self.train()
        samples = {code: [] for code in self.task_codes}
        for _ in range(self.num_mc_samples):
            pred = self.forward(x, edge_index, edge_type)
            for code in self.task_codes:
                samples[code].append(torch.sigmoid(pred[code]).detach())
        result = {}
        for code in self.task_codes:
            stacked = torch.stack(samples[code], dim=0)
            result[code] = (stacked.mean(dim=0), stacked.std(dim=0, unbiased=False))
        self.train(was_training)
        return result

def _edge_type_for_pair(src_meta, dst_meta):
    rules = {
        "POWER_LINE": ("LINE",),
        "SWITCH_LINK": ("BREAKER", "SWITCH", "DISCONNECTOR"),
        "TRANSFORMER_LINK": ("TRANSFORMER", "XF", "TRANS"),
        "GENERATOR_LINK": ("GENERATOR",),
        "LOAD_LINK": ("LOAD",),
        "SOURCE_LINK": ("SOURCE",),
        "BUS_LINK": ("BUS",),
        "ROOM_LINK": ("ROOM",),
    }
    s_type = str(src_meta.get("type", "UNKNOWN")).upper()
    d_type = str(dst_meta.get("type", "UNKNOWN")).upper()
    for key in ["SOURCE_LINK", "TRANSFORMER_LINK", "GENERATOR_LINK", "LOAD_LINK", "SWITCH_LINK", "BUS_LINK", "ROOM_LINK", "POWER_LINE"]:
        if s_type in rules[key] or d_type in rules[key]:
            return key
    return "UNKNOWN"

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_graph_from_14tables_v4(
    tables,
    type_vocab=FEATURE_TYPE_VOCAB,
    edge_vocab=EDGE_TYPE_VOCAB,
    options: Mapping[str, Any] | None = None,
):
    options = dict(options or {})
    pw_equip = tables.get("JBS_PWEQUIPINFO", [])
    zw_equip = tables.get("JBS_ZWEQUIPINFO", [])
    pw_term = tables.get("JBS_PWTERMINAL", [])
    zw_term = tables.get("JBS_ZWTERMINAL", [])
    pw_ids = {e.get("EQUIP_ID") for e in pw_equip if e.get("EQUIP_ID")}
    model_ids = {
        str(e.get("EQUIP_ID"))
        for e in pw_equip + zw_equip
        if e.get("EQUIP_ID")
    }
    svg_devices_raw = options.get("svg_devices")
    if svg_devices_raw is None:
        svg_devices_raw = list(model_ids)
    svg_known = True
    svg_ids = {str(value) for value in svg_devices_raw if value}
    svg_meta = options.get("svg_devices_meta", {}) or {}
    equip_list = []
    equip_meta = {}
    for e in pw_equip + zw_equip:
        eid = e.get("EQUIP_ID")
        if not eid:
            continue
        if eid not in equip_meta:
            equip_list.append(eid)
        equip_meta[eid] = {
            "type": e.get("EQUIP_TYPE", "UNKNOWN"),
            "voltage": _safe_float(e.get("VOLTAGE_TYPE")),
            "feeder": e.get("FEEDER_ID") or e.get("ST_ID", ""),
            "run_status": e.get("RUN_STATUS", 1),
            "table": "PW" if eid in pw_ids else "ZW",
            "model_present": True,
        }
    for eid in sorted(svg_ids - model_ids):
        meta = svg_meta.get(eid, {}) if isinstance(svg_meta, Mapping) else {}
        equip_list.append(eid)
        equip_meta[eid] = {
            "type": meta.get("type", "UNKNOWN"),
            "voltage": _safe_float(meta.get("voltage")),
            "feeder": meta.get("feeder_id", ""),
            "run_status": meta.get("run_status", 1),
            "table": "SVG",
            "model_present": False,
        }
    node_to_idx = {eid: i for i, eid in enumerate(equip_list)}
    node_to_terms = {}
    terminal_rows = {}
    empty_terminal_rows = {}
    for t in pw_term + zw_term:
        eid = t.get("EQUIP_ID")
        nid = t.get("CONNECTIVITYNODE_ID")
        if eid not in node_to_idx:
            continue
        terminal_rows[eid] = terminal_rows.get(eid, 0) + 1
        if nid:
            node_to_terms.setdefault(eid, set()).add(nid)
        else:
            empty_terminal_rows[eid] = empty_terminal_rows.get(eid, 0) + 1
    signal_point = {}
    voltage_observed = {}
    for row in tables.get("JBS_PWREAL", ()):
        eid = str(row.get("TRAN_ID") or row.get("EQUIP_ID") or "")
        if not eid:
            continue
        if row.get("POINT") not in (None, ""):
            signal_point[eid] = _safe_float(row.get("POINT"))
        phases = [
            abs(_safe_float(row.get(key), float("nan")))
            for key in ("UA", "UB", "UC")
            if row.get(key) not in (None, "")
        ]
        phases = [value for value in phases if not math.isnan(value)]
        if phases:
            voltage_observed[eid] = max(phases)
    for row in tables.get("JBS_ZWSIGNAL", ()):
        eid = str(row.get("ID") or row.get("EQUIP_ID") or "")
        if eid and row.get("POINT") not in (None, ""):
            signal_point[eid] = _safe_float(row.get("POINT"))
    for row in tables.get("JBS_ZWMEA", ()):
        eid = str(row.get("ID") or row.get("EQUIP_ID") or "")
        if eid and row.get("V2000") not in (None, ""):
            voltage_observed[eid] = abs(_safe_float(row.get("V2000")))
    devices_by_node = {}
    for eid, term_nodes in node_to_terms.items():
        for cn in term_nodes:
            devices_by_node.setdefault(cn, set()).add(eid)
    edge_dict = {}
    for devices in devices_by_node.values():
        for src in devices:
            for dst in devices:
                if src == dst:
                    continue
                src_idx = node_to_idx[src]
                dst_idx = node_to_idx[dst]
                if src_idx == dst_idx:
                    continue
                rel = _edge_type_for_pair(equip_meta[src], equip_meta[dst])
                if (src_idx, dst_idx) not in edge_dict:
                    edge_dict[(src_idx, dst_idx)] = rel
    edges = sorted(edge_dict.keys())
    edge_types = [edge_dict[(s, d)] for s, d in edges]
    edge_type_to_idx = {t: i for i, t in enumerate(edge_vocab)}
    edge_type_idx = [edge_type_to_idx.get(t, len(edge_vocab) - 1) for t in edge_types]
    type_to_idx = {t: i for i, t in enumerate(type_vocab)}
    unknown_idx = type_to_idx.get("UNKNOWN", len(type_vocab) - 1)
    num_types = len(type_vocab)

    # ── 拓扑感知特征预计算（方案1 StructFeat）───────────────
    # 构造邻接表（无向），用于 BFS-2 拓扑特征
    adj: dict[int, set[int]] = {i: set() for i in range(len(equip_list))}
    for (s, d) in edges:
        adj[s].add(d)
        adj[d].add(s)

    # 预取每节点的 feeder（前缀作为站所标识）
    def _feeder_prefix(eid: str) -> str:
        f = equip_meta[eid].get("feeder", "")
        return f[:4] if f else ""

    topo_feats: dict[int, tuple[float, float, float]] = {}
    for i, eid in enumerate(equip_list):
        # BFS-2（两层可达节点，不含自身）
        visited = set()
        current_level = adj[i]
        visited.update(current_level)
        if current_level:
            next_level: set[int] = set()
            for nb in current_level:
                next_level.update(adj[nb])
            visited.update(next_level)

        # 特征1：2跳内邻居数（归一化）
        num_dist2 = len(visited)
        f1 = min(num_dist2, 10) / 10.0

        # 特征2：是否存在跨 feeder 路径（同站所内跨供电方向）
        my_feeder = _feeder_prefix(eid)
        f2 = 0.0
        if my_feeder:
            for nb_eid in visited:
                nb_feeder = _feeder_prefix(equip_list[nb_eid])
                if nb_feeder and nb_feeder != my_feeder:
                    f2 = 1.0
                    break
        else:
            # 无 feeder 标识时，看 voltage 是否不同（跨电压等级也算跨供电源）
            my_v = equip_meta[eid].get("voltage", 0)
            for nb_eid in visited:
                nb_v = equip_meta[equip_list[nb_eid]].get("voltage", 0)
                if nb_v != my_v:
                    f2 = 1.0
                    break

        # 特征3：端子所在连通节点的站所多样性（不同 feeder 前缀数）
        term_nodes = node_to_terms.get(eid, set())
        station_set: set[str] = set()
        for cn in term_nodes:
            for dev_at_cn in devices_by_node.get(cn, []):
                sf = _feeder_prefix(dev_at_cn)
                if sf:
                    station_set.add(sf)
        f3 = min(len(station_set), 5) / 5.0

        topo_feats[i] = (f1, f2, f3)

    degree_by_node = np.zeros(len(equip_list), dtype=np.int64)
    for _, dst in edges:
        degree_by_node[dst] += 1
    features = []
    for eid in equip_list:
        m = equip_meta[eid]
        f = [1.0 if m["table"] == "PW" else 0.0, 1.0 if m["table"] == "ZW" else 0.0, float(m["voltage"]) / 220.0]
        oh = [0.0] * num_types
        oh[type_to_idx.get(str(m["type"]).upper(), unknown_idx)] = 1.0
        f.extend(oh)
        deg = int(degree_by_node[node_to_idx[eid]])
        f.append(min(deg, 10) / 10.0)
        f.append(min(len(node_to_terms.get(eid, set())), 5) / 5.0)
        f.append(1.0 if "RM" in str(m["feeder"]) or "ST" in str(m["feeder"]) else 0.0)
        f.append(float(m.get("run_status", 1) or 0))
        f.append(1.0 if m["feeder"] else 0.0)
        row_count = terminal_rows.get(eid, 0)
        measured_voltage = voltage_observed.get(eid)
        nominal_voltage = max(float(m["voltage"]) * 1000.0, 1.0)
        f.extend([
            1.0 if m.get("model_present") else 0.0,
            1.0,
            1.0 if eid in svg_ids else 0.0,
            min(row_count, 5) / 5.0,
            empty_terminal_rows.get(eid, 0) / max(row_count, 1),
            1.0 if measured_voltage is not None else 0.0,
            min((measured_voltage or 0.0) / nominal_voltage, 2.0) / 2.0,
            min(max(signal_point.get(eid, _safe_float(m.get("run_status", 1))), 0.0), 1.0),
            *topo_feats[node_to_idx[eid]],   # StructFeat: dist2_neighbours, cross_feeder, station_diversity
        ])
        features.append(f)
    return {"node_ids": equip_list, "node_to_idx": node_to_idx, "node_features": np.array(features, dtype=np.float32), "edge_index": np.array(edges, dtype=np.int64).T if edges else np.zeros((2, 0), dtype=np.int64), "edge_type": np.array(edge_type_idx, dtype=np.int64) if edges else np.zeros((0,), dtype=np.int64), "edge_type_vocab": list(edge_vocab), "equip_meta": equip_meta}

def merge_graphs_v4(graphs):
    if not graphs:
        raise ValueError("at least one graph required")
    node_ids = []
    feats = []
    edges = []
    edge_types = []
    offset = 0
    for g in graphs:
        n = len(g["node_ids"])
        node_ids.extend(g["node_ids"])
        feats.append(g["node_features"])
        if g["edge_index"].size > 0:
            for s, d in g["edge_index"].T:
                edges.append((int(s) + offset, int(d) + offset))
            edge_types.extend(int(x) for x in g["edge_type"])
        offset += n
    feat = np.concatenate(feats, axis=0) if feats else np.zeros((0, 0), dtype=np.float32)
    return {"node_ids": node_ids, "node_features": feat, "edge_index": np.array(edges, dtype=np.int64).T if edges else np.zeros((2, 0), dtype=np.int64), "edge_type": np.array(edge_types, dtype=np.int64) if edge_types else np.zeros((0,), dtype=np.int64)}

def sample_negative_edges(edge_index, num_nodes, count, generator):
    if num_nodes <= 1:
        return torch.zeros((2, 0), dtype=torch.long)
    positives = {(int(s), int(d)) for s, d in edge_index.t().tolist()}
    sampled = set()
    attempts = 0
    while len(sampled) < count and attempts < count * 20:
        src = int(torch.randint(0, num_nodes, (1,), generator=generator).item())
        dst = int(torch.randint(0, num_nodes, (1,), generator=generator).item())
        edge = (src, dst)
        if src != dst and edge not in positives:
            sampled.add(edge)
        attempts += 1
    if not sampled:
        return torch.zeros((2, 0), dtype=torch.long)
    return torch.tensor(sorted(sampled), dtype=torch.long).t().contiguous()

def _device_indices(device_ids: Sequence[str], node_to_idx: Mapping[str, int]) -> set[int]:
    indices: set[int] = set()
    for raw_id in device_ids:
        device_id = str(raw_id)
        if device_id in node_to_idx:
            indices.add(node_to_idx[device_id])
            continue
        for component in device_id.replace("->", "|").split("|"):
            if component in node_to_idx:
                indices.add(node_to_idx[component])
    return indices


def fine_tune_hybrid_gnn(
    model,
    supervised_samples: Sequence[Mapping[str, Any]],
    *,
    epochs=20,
    lr=2e-3,
    seed=42,
    device="cpu",
    negative_ratio=4,
):
    generator = _safe_manual_seed(seed)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=5e-4)
    usable_samples = []
    trained_tasks: set[str] = set()
    for sample in supervised_samples:
        graph = sample["graph"]
        task_code = str(sample["task_code"])
        if task_code not in model.task_codes:
            continue
        positive = _device_indices(sample.get("truth_device_ids", ()), graph["node_to_idx"])
        ignored = _device_indices(sample.get("ignore_device_ids", ()), graph["node_to_idx"])
        if not positive:
            continue
        usable_samples.append((graph, task_code, positive, ignored))
        trained_tasks.add(task_code)
    losses = []
    model.to(device)
    for _ in range(epochs):
        order = torch.randperm(len(usable_samples), generator=generator).tolist()
        for sample_index in order:
            graph, task_code, positive, ignored = usable_samples[sample_index]
            node_count = len(graph["node_ids"])
            available_negative = sorted(set(range(node_count)) - positive - ignored)
            negative_count = min(
                len(available_negative),
                max(len(positive) * int(negative_ratio), len(positive)),
            )
            if negative_count:
                permutation = torch.randperm(len(available_negative), generator=generator)
                negative = [available_negative[index] for index in permutation[:negative_count].tolist()]
            else:
                negative = []
            selected = sorted(positive) + negative
            labels = torch.tensor(
                [1.0] * len(positive) + [0.0] * len(negative),
                dtype=torch.float32,
                device=device,
            )
            x = torch.tensor(graph["node_features"], dtype=torch.float32, device=device)
            edge_index = torch.tensor(graph["edge_index"], dtype=torch.long, device=device)
            edge_type = torch.tensor(graph["edge_type"], dtype=torch.long, device=device)
            prediction = model(x, edge_index, edge_type)
            logits = prediction[task_code][torch.tensor(selected, dtype=torch.long, device=device)]
            positive_weight = torch.tensor(
                max(len(negative), 1) / max(len(positive), 1),
                dtype=torch.float32,
                device=device,
            )
            task_loss = F.binary_cross_entropy_with_logits(
                logits,
                labels,
                pos_weight=positive_weight,
            )
            confidence_target = (1.0 - (torch.sigmoid(logits) - labels).abs()).detach()
            confidence = prediction["confidence"][torch.tensor(selected, dtype=torch.long, device=device)]
            confidence_loss = F.mse_loss(confidence, confidence_target)
            loss = task_loss + 0.05 * confidence_loss
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
    model.trained_task_codes.update(trained_tasks)
    model.training_summary = {
        **getattr(model, "training_summary", {}),
        "supervised_samples": len(usable_samples),
        "supervised_epochs": int(epochs),
        "supervised_final_loss": losses[-1] if losses else None,
        "trained_task_codes": sorted(model.trained_task_codes),
    }
    model.eval()
    return model


def _safe_manual_seed(seed: int) -> torch.Generator | None:
    """Workaround for Windows DLL conflict when importing torch.cuda.

    When many modules are loaded in bulk (e.g. unittest discover), ``torch.manual_seed``
    triggers a late import of ``torch.cuda`` that may fail with:
      ``ValueError: module functions cannot set METH_CLASS or METH_STATIC``
    This is a known PyTorch-on-Windows issue with no upstream fix as of 2.13.
    We degrade gracefully: skip manual seed, still return a seeded generator.
    """
    try:
        torch.manual_seed(seed)
    except (ValueError, RuntimeError):
        # Windows DLL conflict — proceed without seed
        pass
    try:
        return torch.Generator().manual_seed(seed)
    except (ValueError, RuntimeError):
        return None


def train_hybrid_gnn(
    graph,
    epochs=80,
    lr=1e-2,
    seed=42,
    device="cpu",
    supervised_samples: Sequence[Mapping[str, Any]] | None = None,
    supervised_epochs=20,
):
    generator = _safe_manual_seed(seed)
    in_dim = graph["node_features"].shape[1]
    num_relations = len(graph.get("edge_type_vocab", EDGE_TYPE_VOCAB))
    model = HybridGNN(in_dim, hidden=32, num_relations=num_relations).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=5e-4)
    x = torch.tensor(graph["node_features"], dtype=torch.float32, device=device)
    edge_index = torch.tensor(graph["edge_index"], dtype=torch.long, device=device)
    edge_type = torch.tensor(graph["edge_type"], dtype=torch.long, device=device)
    num_nodes = x.size(0)
    if num_nodes == 0:
        raise ValueError("GNN training requires at least one equipment node")
    negative_edges = sample_negative_edges(
        edge_index.cpu(), num_nodes, max(edge_index.size(1), 1), generator
    ).to(device)
    losses = []
    model.train()
    for _ in range(epochs):
        embedding = model.encode(x, edge_index, edge_type)
        if edge_index.size(1) > 0:
            pos_score = (
                embedding[edge_index[0]] * embedding[edge_index[1]]
            ).sum(dim=-1)
        else:
            pos_score = torch.zeros(1, device=device)
        if negative_edges.size(1) > 0:
            neg_score = (
                embedding[negative_edges[0]] * embedding[negative_edges[1]]
            ).sum(dim=-1)
            neg_loss = -torch.log(1 - torch.sigmoid(neg_score) + 1e-8).mean()
        else:
            neg_loss = torch.zeros((), device=device)
        link_loss = -torch.log(torch.sigmoid(pos_score) + 1e-8).mean() + neg_loss
        degrees = torch.zeros(num_nodes, device=device)
        if edge_index.size(1) > 0:
            degrees.index_add_(0, edge_index[1], torch.ones_like(edge_index[1], dtype=torch.float))
        mean_deg = degrees.mean()
        std_deg = degrees.std(unbiased=False) + 1e-6
        z_deg = (degrees - mean_deg) / std_deg
        target_conf = torch.exp(-z_deg.abs()).detach()
        confidence = torch.sigmoid(model.confidence_head(embedding).squeeze(-1))
        conf_loss = F.mse_loss(confidence, target_conf)
        loss = link_loss + 0.1 * conf_loss
        opt.zero_grad(); loss.backward(); opt.step()
        losses.append(float(loss.detach().cpu()))
    model.training_summary = {
        "pretrain_epochs": int(epochs),
        "pretrain_final_loss": losses[-1] if losses else None,
    }
    if supervised_samples:
        return fine_tune_hybrid_gnn(
            model,
            supervised_samples,
            epochs=supervised_epochs,
            seed=seed,
            device=device,
        )
    model.eval()
    return model

def hybrid_predict_with_confidence(model, graph, device="cpu"):
    x = torch.tensor(graph["node_features"], dtype=torch.float32, device=device)
    edge_index = torch.tensor(graph["edge_index"], dtype=torch.long, device=device)
    edge_type = torch.tensor(graph["edge_type"], dtype=torch.long, device=device)
    model.to(device)
    with torch.no_grad():
        mc = model.mc_dropout_forward(x, edge_index, edge_type)
    result = {}
    for code, (mean, std) in mc.items():
        result[code] = {"scores": mean.cpu().numpy(), "std": std.cpu().numpy()}
    return result

def rerank_rule_records_v4(model, graph, rule_records, alpha_by_task=None):
    alpha_by_task = dict(alpha_by_task or {})
    mc = hybrid_predict_with_confidence(model, graph)
    id_to_idx = {nid: i for i, nid in enumerate(graph["node_ids"])}
    trained_tasks = set(getattr(model, "trained_task_codes", ()))
    for record in rule_records:
        eid = getattr(record, "device_id", None) or (record.get("device_id") if isinstance(record, dict) else None)
        code = getattr(record, "task_code", None) or (record.get("task_code") if isinstance(record, dict) else None)
        indices = sorted(_device_indices((str(eid),), id_to_idx)) if eid else []
        head_trained = code in trained_tasks
        if not indices or code not in mc:
            effective_alpha = 0.0; gnn_score = 0.5; gnn_std = 0.0
        else:
            gnn_score = float(np.mean(mc[code]["scores"][indices]))
            gnn_std = float(np.mean(mc[code]["std"][indices]))
            effective_alpha = float(alpha_by_task.get(code, 0.0)) if head_trained else 0.0
        rule_conf = float(getattr(record, "confidence", 0.7) or 0.7)
        adjusted = (1.0 - effective_alpha) * rule_conf + effective_alpha * gnn_score
        if hasattr(record, "extra") and record.extra is not None:
            record.extra["gnn_anomaly_score"] = round(gnn_score, 4)
            record.extra["gnn_score_std"] = round(gnn_std, 4)
            record.extra["gnn_weight_applied"] = round(effective_alpha, 4)
            record.extra["adjusted_confidence"] = round(adjusted, 4)
            record.extra["gnn_task_head_trained"] = head_trained
    rule_records = sorted(rule_records, key=lambda r: r.extra.get("adjusted_confidence", 0) if hasattr(r, "extra") else 0, reverse=True)
    return list(rule_records)

def smoke_test():
    tables = {
        "JBS_PWEQUIPINFO": [{"EQUIP_ID": "A", "EQUIP_TYPE": "BREAKER", "VOLTAGE_TYPE": 10, "FEEDER_ID": "F1", "RUN_STATUS": 1}, {"EQUIP_ID": "B", "EQUIP_TYPE": "LINE", "VOLTAGE_TYPE": 10, "FEEDER_ID": "F1", "RUN_STATUS": 1}, {"EQUIP_ID": "C", "EQUIP_TYPE": "TRANSFORMER", "VOLTAGE_TYPE": 10, "FEEDER_ID": "F1", "RUN_STATUS": 1}, {"EQUIP_ID": "D", "EQUIP_TYPE": "LOAD", "VOLTAGE_TYPE": 0.4, "FEEDER_ID": "F1", "RUN_STATUS": 1}],
        "JBS_PWTERMINAL": [{"EQUIP_ID": "A", "CONNECTIVITYNODE_ID": "n1", "PORT_NO": 1, "ID": "t1", "VALID_FLAG": 1}, {"EQUIP_ID": "B", "CONNECTIVITYNODE_ID": "n1", "PORT_NO": 1, "ID": "t2", "VALID_FLAG": 1}, {"EQUIP_ID": "B", "CONNECTIVITYNODE_ID": "n2", "PORT_NO": 2, "ID": "t3", "VALID_FLAG": 1}, {"EQUIP_ID": "C", "CONNECTIVITYNODE_ID": "n2", "PORT_NO": 1, "ID": "t4", "VALID_FLAG": 1}, {"EQUIP_ID": "C", "CONNECTIVITYNODE_ID": "n3", "PORT_NO": 2, "ID": "t5", "VALID_FLAG": 1}, {"EQUIP_ID": "D", "CONNECTIVITYNODE_ID": "n3", "PORT_NO": 1, "ID": "t6", "VALID_FLAG": 1}],
        "JBS_ZWTERMINAL": [{"ID": "z", "EQUIP_ID": "", "CONNECTIVITYNODE_ID": ""}],
        "JBS_PWFEEDERLINE": [{"LINE_ID": "F1", "LINE_NAME": "F1", "START_ST_ID": "ST1", "VOLTAGE_TYPE": 10}],
        "JBS_PWROOM": [{"ROOM_ID": "R1", "ROOM_NAME": "R1", "TOP_VOLTAGE_TYPE": 10, "FEEDER_ID": "F1"}],
        "JBS_ZD_OBJECT": [{"OBJ_ID": "OBJ01", "OBJ_CODE": "BREAKER", "OBJ_CNNAME": "Breaker", "OBJ_ENNAME": "Breaker"}],
    }
    graph = build_graph_from_14tables_v4(tables)
    model = train_hybrid_gnn(graph, epochs=20, seed=42)
    pred = hybrid_predict_with_confidence(model, graph)
    return {"nodes": graph["node_ids"], "edges": graph["edge_index"].shape[1], "edge_types": graph["edge_type"].tolist(), "task_summaries": {code: {"mean": float(pred[code]["scores"].mean()), "std": float(pred[code]["std"].mean())} for code in TASK_HEADS}}

if __name__ == "__main__":
    print(smoke_test())
