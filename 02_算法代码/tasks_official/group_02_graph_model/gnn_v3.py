# -*- coding: utf-8 -*-
"""GNN v3: 综合异常分数 - 模块版."""
import sys, json, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

try:
    torch.manual_seed(42)
except (ValueError, RuntimeError):
    pass

FEATURE_TYPE_VOCAB = (
    "BREAKER", "SWITCH", "DISCONNECTOR", "LINE",
    "TRANSFORMER", "LOAD", "GENERATOR", "SOURCE",
    "BUS", "CABLE_HEAD", "TIE", "ROOM",
    "XF", "TRANS", "SPARE_BAY", "UNKNOWN",
)


class GraphSAGELayer(nn.Module):
    def __init__(self, in_dim, out_dim):
        super().__init__()
        self.linear_self = nn.Linear(in_dim, out_dim)
        self.linear_neigh = nn.Linear(in_dim, out_dim)
    
    def forward(self, x, edge_index):
        N = x.size(0)
        if edge_index.size(1) == 0:
            h_neigh = torch.zeros(N, x.size(1), device=x.device)
        else:
            src, dst = edge_index[0], edge_index[1]
            agg = torch.zeros(N, x.size(1), device=x.device)
            agg.index_add_(0, dst, x[src])
            deg = torch.zeros(N, dtype=torch.float, device=x.device)
            deg.index_add_(0, dst, torch.ones(dst.size(0), device=x.device))
            deg = deg.clamp(min=1.0).unsqueeze(1)
            h_neigh = agg / deg
        return F.relu(self.linear_self(x) + self.linear_neigh(h_neigh))


class GAE(nn.Module):
    def __init__(self, in_dim, hidden=32, num_layers=2):
        super().__init__()
        self.layers = nn.ModuleList([GraphSAGELayer(in_dim if i==0 else hidden, hidden) for i in range(num_layers)])
    
    def forward(self, x, edge_index):
        for layer in self.layers:
            x = layer(x, edge_index)
        return x


def build_graph_from_14tables_v3(tables, type_vocab=FEATURE_TYPE_VOCAB):
    pw_equip = tables.get('JBS_PWEQUIPINFO', [])
    zw_equip = tables.get('JBS_ZWEQUIPINFO', [])
    pw_term = tables.get('JBS_PWTERMINAL', [])
    zw_term = tables.get('JBS_ZWTERMINAL', [])
    pw_ids = {e.get('EQUIP_ID') for e in pw_equip if e.get('EQUIP_ID')}
    
    equip_list = []
    equip_meta = {}
    for e in pw_equip + zw_equip:
        eid = e.get('EQUIP_ID')
        if not eid: continue
        if eid not in equip_meta:
            equip_list.append(eid)
        equip_meta[eid] = {
            'type': e.get('EQUIP_TYPE', 'UNKNOWN'),
            'voltage': float(e.get('VOLTAGE_TYPE', 0) or 0),
            'feeder': e.get('FEEDER_ID') or e.get('ST_ID', ''),
            'run_status': e.get('RUN_STATUS', 1),
            'table': 'PW' if eid in pw_ids else 'ZW',
        }
    node_to_idx = {eid: i for i, eid in enumerate(equip_list)}
    node_to_terms = {}
    for t in pw_term + zw_term:
        eid = t.get('EQUIP_ID'); nid = t.get('CONNECTIVITYNODE_ID')
        if eid in node_to_idx and nid:
            node_to_terms.setdefault(eid, set()).add(nid)
    
    devices_by_node = {}
    for equipment_id, terminal_nodes in node_to_terms.items():
        for connectivity_node in terminal_nodes:
            devices_by_node.setdefault(connectivity_node, set()).add(equipment_id)
    edge_set = set()
    for device_ids in devices_by_node.values():
        for source_id in device_ids:
            for target_id in device_ids:
                if source_id == target_id:
                    continue
                edge_set.add((node_to_idx[source_id], node_to_idx[target_id]))
    edges = sorted(edge_set)
    
    vocab = tuple(type_vocab)
    type_to_idx = {t: i for i, t in enumerate(vocab)}
    unknown_idx = type_to_idx.get("UNKNOWN", len(vocab) - 1)
    num_types = len(vocab)
    
    degree_by_node = np.zeros(len(equip_list), dtype=np.int64)
    for _, destination in edges:
        degree_by_node[destination] += 1
    features = []
    for eid in equip_list:
        m = equip_meta[eid]
        f = [
            1.0 if m['table'] == 'PW' else 0.0,
            1.0 if m['table'] == 'ZW' else 0.0,
            float(m['voltage']) / 220.0,
        ]
        oh = [0.0] * num_types
        oh[type_to_idx.get(str(m['type']).upper(), unknown_idx)] = 1.0
        f.extend(oh)
        deg = int(degree_by_node[node_to_idx[eid]])
        f.append(min(deg, 10) / 10.0)
        f.append(min(len(node_to_terms.get(eid, set())), 5) / 5.0)
        f.append(1.0 if 'RM' in str(m['feeder']) or 'ST' in str(m['feeder']) else 0.0)
        f.append(float(m.get('run_status', 1) or 0))
        f.append(1.0 if m['feeder'] else 0.0)
        features.append(f)
    
    return {
        'node_ids': equip_list, 'node_to_idx': node_to_idx,
        'node_features': np.array(features, dtype=np.float32),
        'edge_index': np.array(edges, dtype=np.int64).T if edges else np.zeros((2, 0), dtype=np.int64),
        'equip_meta': equip_meta,
    }


def merge_graphs_v3(graphs):
    """Create a disjoint union for cross-network unsupervised training."""
    if not graphs:
        raise ValueError("At least one graph is required")
    feature_dims = {int(graph["node_features"].shape[1]) for graph in graphs}
    if len(feature_dims) != 1:
        raise ValueError("All graphs must use the same feature vocabulary")
    node_ids = []
    node_features = []
    edges = []
    equip_meta = {}
    offset = 0
    for graph in graphs:
        ids = list(graph["node_ids"])
        node_ids.extend(ids)
        node_features.append(graph["node_features"])
        edge_index = np.asarray(graph["edge_index"], dtype=np.int64)
        if edge_index.shape[1]:
            edges.append(edge_index + offset)
        equip_meta.update(graph.get("equip_meta", {}))
        offset += len(ids)
    return {
        "node_ids": node_ids,
        "node_to_idx": {node_id: i for i, node_id in enumerate(node_ids)},
        "node_features": np.concatenate(node_features, axis=0),
        "edge_index": np.concatenate(edges, axis=1) if edges else np.zeros((2, 0), dtype=np.int64),
        "equip_meta": equip_meta,
    }


def sample_negative_edges(edge_index, num_nodes, count, generator=None):
    """Sample directed non-edges without self loops or positive-edge leakage."""
    if num_nodes < 2 or count <= 0:
        return torch.zeros((2, 0), dtype=torch.long)
    positives = set(map(tuple, edge_index.t().tolist()))
    capacity = num_nodes * (num_nodes - 1) - len(positives)
    count = min(count, max(0, capacity))
    sampled = set()
    attempts = 0
    limit = max(100, count * 20)
    while len(sampled) < count and attempts < limit:
        src = int(torch.randint(0, num_nodes, (1,), generator=generator).item())
        dst = int(torch.randint(0, num_nodes, (1,), generator=generator).item())
        edge = (src, dst)
        if src != dst and edge not in positives:
            sampled.add(edge)
        attempts += 1
    if len(sampled) < count:
        for src in range(num_nodes):
            for dst in range(num_nodes):
                edge = (src, dst)
                if src != dst and edge not in positives:
                    sampled.add(edge)
                    if len(sampled) == count:
                        break
            if len(sampled) == count:
                break
    if not sampled:
        return torch.zeros((2, 0), dtype=torch.long)
    return torch.tensor(sorted(sampled), dtype=torch.long).t().contiguous()


def train_gae_v3(graph, epochs=80, lr=1e-2, seed=42):
    try:
        torch.manual_seed(seed)
    except (ValueError, RuntimeError):
        pass
    try:
        generator = torch.Generator().manual_seed(seed)
    except (ValueError, RuntimeError):
        generator = torch.Generator()
    in_dim = graph['node_features'].shape[1]
    model = GAE(in_dim, hidden=32).cpu()
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=5e-4)
    x = torch.tensor(graph['node_features'])
    edge_index = torch.tensor(graph['edge_index'])
    num_nodes = x.size(0)

    model.train()
    for _ in range(epochs):
        z = model(x, edge_index)
        if edge_index.size(1) > 0:
            pos_score = (z[edge_index[0]] * z[edge_index[1]]).sum(dim=-1)
        else:
            pos_score = torch.zeros(1)
        negative_edges = sample_negative_edges(
            edge_index, num_nodes, max(edge_index.size(1), 1), generator
        )
        if negative_edges.size(1) > 0:
            neg_score = (z[negative_edges[0]] * z[negative_edges[1]]).sum(dim=-1)
            negative_loss = -torch.log(1 - torch.sigmoid(neg_score) + 1e-8).mean()
        else:
            negative_loss = torch.zeros((), dtype=z.dtype)
        loss = -torch.log(torch.sigmoid(pos_score) + 1e-8).mean() + negative_loss
        opt.zero_grad(); loss.backward(); opt.step()
    return model


def anomaly_scores_v3(model, graph):
    model.eval()
    x = torch.tensor(graph['node_features'])
    edge_index = torch.tensor(graph['edge_index'])
    with torch.no_grad():
        z = model(x, edge_index)
    N = z.size(0)
    
    real_nbr = {i: set() for i in range(N)}
    degrees = np.zeros(N)
    if edge_index.size(1) > 0:
        for s, d in edge_index.t().tolist():
            real_nbr[s].add(d)
            degrees[d] += 1
    
    mean_deg = degrees.mean()
    std_deg = degrees.std() + 1e-6
    
    scores = []
    for i in range(N):
        sims = (z[i:i+1] * z).sum(dim=-1).squeeze()
        probs = torch.sigmoid(sims).numpy()
        recon_err = 0.0
        for j in range(N):
            if i == j: continue
            p = probs[j]
            if j in real_nbr[i]:
                recon_err += max(0, 1 - p) ** 2
            elif p > 0.7:
                recon_err += (p - 0.5) ** 2
        recon_err = math.sqrt(recon_err / max(1, N - 1))
        
        deg_pen = max(0, (mean_deg - degrees[i]) / max(1, mean_deg))
        z_deg = abs(degrees[i] - mean_deg) / std_deg
        deg_dev = min(1.0, z_deg / 3.0)
        
        combined = 0.5 * recon_err + 0.3 * deg_pen + 0.2 * deg_dev
        scores.append(combined)
    
    return scores


def rerank_rule_records_v3(model, graph, rule_records, alpha=0.0, enabled_tasks=('1.1',)):
    """Annotate rule records and apply GNN weighting only behind a calibrated task gate.

    Injection-v4 evidence showed that the unsupervised model improves ranking only for
    task 1.1; the default therefore preserves rule confidence and ordering. Callers may
    explicitly provide ``alpha`` after validating a model on a network-level holdout.
    """
    scores = anomaly_scores_v3(model, graph)
    id_to_score = {nid: s for nid, s in zip(graph['node_ids'], scores)}
    for record in rule_records:
        equipment_id = getattr(record, 'device_id', None) or (record.get('device_id', '') if isinstance(record, dict) else '')
        task_code = getattr(record, 'task_code', None) or (record.get('task_code', '') if isinstance(record, dict) else '')
        gnn_score = float(id_to_score.get(equipment_id, 0.5))
        rule_confidence = float(getattr(record, 'confidence', 0.7) or 0.7)
        effective_alpha = alpha if task_code in set(enabled_tasks) else 0.0
        adjusted = (1.0 - effective_alpha) * rule_confidence + effective_alpha * gnn_score
        if hasattr(record, 'extra') and record.extra is not None:
            record.extra['gnn_anomaly_score'] = round(gnn_score, 4)
            record.extra['gnn_weight_applied'] = round(effective_alpha, 4)
            record.extra['adjusted_confidence'] = round(adjusted, 4)
    rule_records.sort(key=lambda record: record.extra.get('adjusted_confidence', 0) if hasattr(record, 'extra') else 0, reverse=True)
    return rule_records