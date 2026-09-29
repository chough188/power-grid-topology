# -*- coding: utf-8 -*-
"""构建 GNN+规则混合异常检测器.

设计: 无监督 (不需要标注)
  - 节点特征: 度数/中心性/电压/类型OH/端子数
  - 模型: GraphSAGE 编码器 + 内积解码器 (Graph Auto-Encoder)
  - 异常分数: 节点embedding 与邻居内积 → 与真实边的偏差
  - 用法: 与rule detector串联, 对candidate记录重新打分
"""
import sys, json, math, random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

# 1. 14-table -> 图数据
def build_graph_from_14tables(tables):
    """从14-table数据构建异构图.
    
    Nodes: 设备 (PW + ZW)
    Edges: 通过 shared CONNECTIVITYNODE 连接
    
    Returns:
      node_ids: list of EQUIP_ID (含PW+ZW)
      node_types: list of (type_str, voltage, is_substation_end)
      edge_index: (2, E) tensor of (src, dst) indices
      node_features: (N, F) numpy array
    """
    pw_equip = tables.get('JBS_PWEQUIPINFO', [])
    zw_equip = tables.get('JBS_ZWEQUIPINFO', [])
    pw_term = tables.get('JBS_PWTERMINAL', [])
    zw_term = tables.get('JBS_ZWTERMINAL', [])
    
    equip_list = []
    equip_meta = {}
    
    for e in pw_equip + zw_equip:
        eid = e.get('EQUIP_ID')
        if not eid:
            continue
        equip_list.append(eid)
        equip_meta[eid] = {
            'type': e.get('EQUIP_TYPE', 'UNKNOWN'),
            'voltage': e.get('VOLTAGE_TYPE', 0) or 0,
            'name': e.get('EQUIP_NAME', ''),
            'feeder': e.get('FEEDER_ID') or e.get('ST_ID', ''),
            'run_status': e.get('RUN_STATUS', 1),
            'table': 'PW' if eid in {x.get('EQUIP_ID') for x in pw_equip} else 'ZW',
        }
    
    # node idx map
    node_to_idx = {eid: i for i, eid in enumerate(equip_list)}
    
    # 边: 通过 shared CONNECTIVITYNODE 连接
    node_to_terms = {}
    for t in pw_term + zw_term:
        eid = t.get('EQUIP_ID')
        nid = t.get('CONNECTIVITYNODE_ID')
        if eid in node_to_idx and nid:
            node_to_terms.setdefault(eid, set()).add(nid)
    
    edges = []
    edge_attr = []  # 电压类型 / 边类型
    for t in pw_term + zw_term:
        eid = t.get('EQUIP_ID')
        nid = t.get('CONNECTIVITYNODE_ID')
        if not (eid in node_to_idx and nid):
            continue
        # 找共享同一 node 的其他设备
        for other_eid, term_set in node_to_terms.items():
            if other_eid == eid:
                continue
            if nid in term_set:
                src, dst = node_to_idx[eid], node_to_idx[other_eid]
                if src < dst:
                    edges.append((src, dst))
                    edges.append((dst, src))
                    v = equip_meta[eid]['voltage']
                    edge_attr.append([v, 0])  # voltage, is_switch
                    edge_attr.append([v, 0])
    
    # 构建节点特征
    # 特征: [is_PW, is_ZW, voltage_norm, type_oh_8, degree, num_terms, is_substation_end, run_status, has_feeder]
    type_set = sorted({m['type'] for m in equip_meta.values()})
    type_to_idx = {t: i for i, t in enumerate(type_set)}
    num_types = max(8, len(type_set))
    
    node_features = []
    for eid in equip_list:
        m = equip_meta[eid]
        f = [
            1.0 if m['table'] == 'PW' else 0.0,
            1.0 if m['table'] == 'ZW' else 0.0,
            float(m['voltage']) / 220.0,  # 归一化
        ]
        # type OH
        oh = [0.0] * num_types
        oh[type_to_idx.get(m['type'], 0)] = 1.0
        f.extend(oh)
        # degree
        deg = sum(1 for s, d in edges if d == node_to_idx[eid])
        f.append(min(deg, 10) / 10.0)
        # num terminals
        f.append(min(len(node_to_terms.get(eid, set())), 5) / 5.0)
        # is end / substation
        f.append(1.0 if 'RM' in str(m['feeder']) or 'ST' in str(m['feeder']) else 0.0)
        # run status
        f.append(float(m.get('run_status', 1) or 0))
        # has feeder
        f.append(1.0 if m['feeder'] else 0.0)
        node_features.append(f)
    
    return {
        'node_ids': equip_list,
        'node_to_idx': node_to_idx,
        'node_features': np.array(node_features, dtype=np.float32),
        'edge_index': np.array(edges, dtype=np.int64).T if edges else np.zeros((2, 0), dtype=np.int64),
        'edge_attr': np.array(edge_attr, dtype=np.float32) if edge_attr else np.zeros((0, 2), dtype=np.float32),
        'equip_meta': equip_meta,
    }


# 2. GNN 模型
class GraphSAGELayer(nn.Module):
    def __init__(self, in_dim, out_dim):
        super().__init__()
        self.linear_self = nn.Linear(in_dim, out_dim)
        self.linear_neigh = nn.Linear(in_dim, out_dim)
        nn.init.xavier_uniform_(self.linear_self.weight)
        nn.init.xavier_uniform_(self.linear_neigh.weight)
    
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
    """Graph Auto-Encoder: GraphSAGE encoder + inner-product decoder.
    
    Anomaly score = reconstruction error of edges
    """
    def __init__(self, in_dim, hidden=32, num_layers=2, dropout=0.1):
        super().__init__()
        self.layers = nn.ModuleList()
        prev = in_dim
        for i in range(num_layers):
            h = hidden
            self.layers.append(GraphSAGELayer(prev, h))
            prev = h
        self.dropout = nn.Dropout(dropout)
    
    def encode(self, x, edge_index):
        for layer in self.layers:
            x = layer(x, edge_index)
            x = self.dropout(x)
        return x
    
    def decode(self, z, edge_pairs):
        """内积解码"""
        src = edge_pairs[0]
        dst = edge_pairs[1]
        return (z[src] * z[dst]).sum(dim=-1)
    
    def forward(self, x, edge_index):
        return self.encode(x, edge_index)


# 3. 训练 + 推理
def train_gae(graph_data, hidden=32, epochs=80, lr=1e-2, device='cpu'):
    """训练 GAE: 重建存在的边, 不重建不存在的边."""
    in_dim = graph_data['node_features'].shape[1]
    model = GAE(in_dim, hidden=hidden).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=5e-4)
    
    x = torch.tensor(graph_data['node_features'], device=device)
    edge_index = torch.tensor(graph_data['edge_index'], device=device)
    
    # 负采样: 不存在的边
    N = x.size(0)
    pos_edges = edge_index  # (2, E)
    num_pos = pos_edges.size(1)
    num_neg = num_pos
    
    # 训练
    model.train()
    for epoch in range(epochs):
        z = model(x, edge_index)
        # 正样本分数 (应该高)
        pos_score = model.decode(z, pos_edges)
        # 负采样
        neg_src = torch.randint(0, N, (num_neg,), device=device)
        neg_dst = torch.randint(0, N, (num_neg,), device=device)
        neg_score = model.decode(z, (neg_src, neg_dst))
        # 损失: 正样本1 - sigmoid(score), 负样本 sigmoid(score)
        pos_loss = -torch.log(torch.sigmoid(pos_score) + 1e-8).mean()
        neg_loss = -torch.log(1 - torch.sigmoid(neg_score) + 1e-8).mean()
        loss = pos_loss + neg_loss
        opt.zero_grad()
        loss.backward()
        opt.step()
        if (epoch + 1) % 20 == 0:
            print(f'  Epoch {epoch+1}: loss={loss.item():.4f} (pos={pos_loss.item():.4f}, neg={neg_loss.item():.4f})')
    
    return model


def anomaly_scores(model, graph_data, device='cpu'):
    """计算每个节点的异常分数.
    
    对每个节点, 计算它与所有其他节点的内积, 与真实边集的偏差.
    """
    model.eval()
    x = torch.tensor(graph_data['node_features'], device=device)
    edge_index = torch.tensor(graph_data['edge_index'], device=device)
    
    with torch.no_grad():
        z = model(x, edge_index)  # (N, hidden)
    
    N = z.size(0)
    
    # 1. 邻居预测误差: 对每个节点, 看它应该连但没连的边 (高分) 或不该连但连了的边 (低分)
    # 简化: 对每个节点, 用 z[i] @ z[j] 计算与所有 j 的"应该连"概率, 与实际邻接比较
    scores = []
    real_neighbors = {i: set() for i in range(N)}
    if edge_index.size(1) > 0:
        for s, d in edge_index.t().tolist():
            real_neighbors[s].add(d)
    
    for i in range(N):
        # 与所有 j 的相似度
        sims = (z[i:i+1] * z).sum(dim=-1).squeeze()  # (N,)
        probs = torch.sigmoid(sims)
        # 邻居应该有高分, 非邻居应该有低分
        real_nbr = real_neighbors[i]
        score = 0.0
        for j in range(N):
            if i == j:
                continue
            p = probs[j].item()
            if j in real_nbr:
                # 应连: 期望高分, 1 - p
                score += max(0, 1 - p) ** 2
            else:
                # 不应连: 期望低分, 但允许小值
                if p > 0.7:  # 高分则惩罚
                    score += (p - 0.5) ** 2
        scores.append(math.sqrt(score / max(1, N - 1)))
    
    return scores


# 4. 集成到 rule detector
def rerank_rule_records(model, graph_data, rule_records, alpha=0.4):
    """用 GNN 异常分数对 rule detector 输出重排序.
    
    final_score = (1-alpha) * rule_score + alpha * gnn_anomaly_score
    
    Args:
      rule_records: list of dict-like, 至少有 device_id / score / task_code
    Returns:
      同 list, 但带 gnn_score 字段和 adjusted_score
    """
    scores = anomaly_scores(model, graph_data)
    node_ids = graph_data['node_ids']
    id_to_score = {nid: s for nid, s in zip(node_ids, scores)}
    
    for r in rule_records:
        eid = getattr(r, 'device_id', None) or r.get('device_id', '')
        gnn_s = id_to_score.get(eid, 0.5)
        rule_s = getattr(r, 'confidence', None) or r.get('confidence', 0.5) or 0.7
        adj = (1 - alpha) * rule_s + alpha * gnn_s
        if hasattr(r, 'extra'):
            r.extra['gnn_anomaly_score'] = round(gnn_s, 4)
            r.extra['adjusted_confidence'] = round(adj, 4)
        else:
            r['gnn_anomaly_score'] = round(gnn_s, 4)
            r['adjusted_confidence'] = round(adj, 4)
    
    # 按 adjusted_confidence 降序
    key = lambda r: (getattr(r, 'extra', {}) or r).get('adjusted_confidence', 0) if isinstance(r, dict) else r.extra.get('adjusted_confidence', 0)
    rule_records.sort(key=lambda r: r.extra.get('adjusted_confidence', 0) if hasattr(r, 'extra') else r.get('adjusted_confidence', 0), reverse=True)
    return rule_records


# 5. 演示入口
if __name__ == '__main__':
    from data_loader.sql_importer import import_sql
    
    print('=' * 60)
    print('GNN+规则混合异常检测演示')
    print('=' * 60)
    
    # 1. 加载 date_real.sql
    tables = import_sql('temp/date_real.sql')
    print(f'加载数据: {sum(len(v) for v in tables.values())} 行')
    
    # 2. 构建图
    graph = build_graph_from_14tables(tables)
    print(f'图: {len(graph["node_ids"])} 节点, {graph["edge_index"].shape[1]} 边')
    print(f'节点特征维度: {graph["node_features"].shape[1]}')
    
    # 3. 训练 GAE
    print()
    print('训练 GAE (Graph Auto-Encoder)...')
    try:
        torch.manual_seed(42)
    except (ValueError, RuntimeError):
        pass
    model = train_gae(graph, hidden=32, epochs=60)
    
    # 4. 计算异常分数
    print()
    print('=== GNN 异常分数 (top 10) ===')
    scores = anomaly_scores(model, graph)
    ranked = sorted(zip(graph['node_ids'], scores), key=lambda x: -x[1])[:10]
    for nid, s in ranked:
        meta = graph['equip_meta'][nid]
        print(f'  {nid:18s} score={s:.4f}  type={meta["type"]:14s} feeder={meta["feeder"]}')
    
    # 5. 集成: 用 rule detector
    from tasks_official.execution import OfficialRunner
    from tasks_official.registry import LazyTaskRegistry
    
    print()
    print('=== 规则 detector 输出 ===')
    from data_loader.loader import OfficialDataset
    ds = OfficialDataset(tables)
    ds.validate()
    
    runner = OfficialRunner(LazyTaskRegistry.with_module_resolver())
    all_tasks = ['1.1', '1.2', '1.5', '2.2', '2.4', '3.1']
    result = runner.run(all_tasks, ds)
    rule_records = [r for recs in result.records_by_task.values() for r in recs]
    print(f'共 {len(rule_records)} 条')
    
    # 6. 用 GNN 重排序
    rerank_rule_records(model, graph, rule_records, alpha=0.4)
    
    print()
    print('=== 重排序后 top 10 ===')
    for r in rule_records[:10]:
        eid = r.device_id
        gs = r.extra.get('gnn_anomaly_score', 0)
        adj = r.extra.get('adjusted_confidence', 0)
        print(f'  {r.task_code} {eid:18s} adj={adj:.4f}  gnn={gs:.4f}  | {r.description[:60]}')
    
    # 7. 保存模型
    out_dir = Path('output/gnn_hybrid')
    out_dir.mkdir(parents=True, exist_ok=True)
    torch.save({
        'model_state': model.state_dict(),
        'in_dim': graph['node_features'].shape[1],
        'hidden': 32,
        'num_layers': 2,
        'node_ids': graph['node_ids'],
        'X_mean': graph['node_features'].mean(0).tolist(),
        'X_std': (graph['node_features'].std(0) + 1e-6).tolist(),
    }, out_dir / 'gae_v1.pt')
    
    info = {
        'model_class': 'GAE_GraphSAGE',
        'in_dim': graph['node_features'].shape[1],
        'hidden': 32,
        'num_layers': 2,
        'n_nodes': len(graph['node_ids']),
        'n_edges': graph['edge_index'].shape[1],
        'alpha': 0.4,
        'anomaly_top10': [(n, round(s, 4)) for n, s in ranked],
    }
    (out_dir / 'gae_v1_info.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf-8')
    print()
    print(f'模型已保存: {out_dir}/gae_v1.pt')
    print(f'元信息: {out_dir}/gae_v1_info.json')