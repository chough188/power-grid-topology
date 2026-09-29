"""Optional GNN second-pass integration for the official rule detectors.

The official detector path remains dependency-free and unchanged by default.
This module is opt-in: it builds an unsupervised graph from the same 14-table
snapshot, annotates existing rule candidates, and never creates or removes a
candidate on its own.
"""
from __future__ import annotations

from pathlib import Path

from dataclasses import dataclass, replace
from typing import Any, Mapping, Sequence

from tasks_official.contracts import ProblemRecord
from tasks_official.execution import OfficialRunResult, OfficialRunner
from tasks_official.registry import LazyTaskRegistry


@dataclass(frozen=True)
class HybridConfig:
    """Explicit policy for enabling the experimental GNN second pass."""

    enabled: bool = False
    alpha: float = 0.0
    enabled_tasks: tuple[str, ...] = ("1.1",)
    epochs: int = 80
    seed: int = 42
    model: Any | None = None
    alpha_by_task: Mapping[str, float] | None = None
    model_version: str = "v3"

    def validate(self) -> None:
        if not 0.0 <= self.alpha <= 1.0:
            raise ValueError("Hybrid alpha must be between 0 and 1")
        if self.epochs < 1:
            raise ValueError("Hybrid epochs must be positive")
        if self.model_version not in {"v3", "v4"}:
            raise ValueError("Hybrid model_version must be 'v3' or 'v4'")
        for task_code, alpha in (self.alpha_by_task or {}).items():
            if not 0.0 <= float(alpha) <= 1.0:
                raise ValueError(f"Hybrid alpha for {task_code} must be between 0 and 1")

    def alpha_for(self, task_code: str) -> float:
        if self.alpha_by_task is not None:
            return float(self.alpha_by_task.get(task_code, 0.0))
        return self.alpha if task_code in set(self.enabled_tasks) else 0.0


def _annotate_records(
    records: Sequence[ProblemRecord],
    graph: Mapping[str, Any],
    model: Any,
    config: HybridConfig,
) -> tuple[ProblemRecord, ...]:
    """Return records with GNN evidence while preserving detector semantics."""

    from .gnn_v3 import anomaly_scores_v3

    scores = anomaly_scores_v3(model, graph)
    score_by_device = {
        device_id: float(score)
        for device_id, score in zip(graph["node_ids"], scores)
    }
    annotated: list[ProblemRecord] = []
    for record in records:
        gnn_score = score_by_device.get(record.device_id, 0.5)
        effective_alpha = config.alpha_for(record.task_code)
        rule_confidence = float(record.confidence if record.confidence is not None else 0.5)
        adjusted = (1.0 - effective_alpha) * rule_confidence + effective_alpha * gnn_score
        extra = dict(record.extra)
        extra.update(
            {
                "gnn_anomaly_score": round(gnn_score, 6),
                "gnn_weight_applied": round(effective_alpha, 6),
                "adjusted_confidence": round(adjusted, 6),
                "hybrid_policy": "rule_candidate_preserved_gnn_rerank",
            }
        )
        annotated.append(replace(record, confidence=adjusted, extra=extra))
    return tuple(
        sorted(
            annotated,
            key=lambda record: (
                float(record.extra.get("adjusted_confidence", 0.0)),
                record.device_id,
            ),
            reverse=True,
        )
    )


def _annotate_records_v4(
    records: Sequence[ProblemRecord],
    graph: Mapping[str, Any],
    model: Any,
    config: HybridConfig,
) -> tuple[ProblemRecord, ...]:
    from .gnn_v4 import hybrid_predict_with_confidence

    predictions = hybrid_predict_with_confidence(model, graph)
    index_by_device = {
        str(device_id): index for index, device_id in enumerate(graph["node_ids"])
    }
    trained_tasks = set(getattr(model, "trained_task_codes", ()))
    annotated: list[ProblemRecord] = []
    for record in records:
        indices = []
        if record.device_id in index_by_device:
            indices.append(index_by_device[record.device_id])
        else:
            indices.extend(
                index_by_device[component]
                for component in str(record.device_id).replace("->", "|").split("|")
                if component in index_by_device
            )
        head_trained = record.task_code in trained_tasks
        if indices and record.task_code in predictions:
            scores = predictions[record.task_code]["scores"]
            deviations = predictions[record.task_code]["std"]
            gnn_score = sum(float(scores[index]) for index in indices) / len(indices)
            gnn_std = sum(float(deviations[index]) for index in indices) / len(indices)
        else:
            gnn_score = 0.5
            gnn_std = 0.0
        effective_alpha = config.alpha_for(record.task_code) if head_trained and indices else 0.0
        rule_confidence = float(record.confidence if record.confidence is not None else 0.5)
        adjusted = (1.0 - effective_alpha) * rule_confidence + effective_alpha * gnn_score
        extra = dict(record.extra)
        extra.update({
            "gnn_anomaly_score": round(gnn_score, 6),
            "gnn_score_std": round(gnn_std, 6),
            "gnn_weight_applied": round(effective_alpha, 6),
            "gnn_task_head_trained": head_trained,
            "adjusted_confidence": round(adjusted, 6),
            "hybrid_model_version": "v4",
            "hybrid_policy": "rule_candidate_preserved_gnn_rerank",
        })
        annotated.append(replace(record, confidence=adjusted, extra=extra))
    return tuple(
        sorted(
            annotated,
            key=lambda record: (
                float(record.extra.get("adjusted_confidence", 0.0)),
                record.device_id,
            ),
            reverse=True,
        )
    )


def run_official_hybrid(
    task_codes: Sequence[str],
    dataset: Any,
    *,
    config: HybridConfig | None = None,
    options: Mapping[str, Any] | None = None,
    registry: LazyTaskRegistry | None = None,
) -> OfficialRunResult:
    """Run official rules, optionally applying the GNN second-pass ranking.

    With the default configuration this is exactly the normal ``OfficialRunner``
    behavior and does not import PyTorch. When enabled, the GNN only annotates
    and re-ranks candidates already emitted by rules; it cannot manufacture a
    positive result or silently filter one out.
    """

    policy = config or HybridConfig()
    policy.validate()
    runner = OfficialRunner(registry)
    result = runner.run(task_codes, dataset, options=options)
    has_task_alpha = any(float(value) > 0.0 for value in (policy.alpha_by_task or {}).values())
    if not policy.enabled or (policy.alpha == 0.0 and not has_task_alpha):
        return result

    use_v4 = policy.model_version == "v4" or (
        policy.model is not None and policy.model.__class__.__name__ == "HybridGNN"
    )
    if use_v4:
        from .gnn_v4 import build_graph_from_14tables_v4, train_hybrid_gnn

        graph = build_graph_from_14tables_v4(
            dataset.normalized().tables,
            options=options,
        )
        if not graph["node_ids"]:
            return result
        model = policy.model or train_hybrid_gnn(
            graph,
            epochs=policy.epochs,
            seed=policy.seed,
        )
        records_by_task = {
            task_code: _annotate_records_v4(records, graph, model, policy)
            for task_code, records in result.records_by_task.items()
        }
    else:
        from .gnn_v3 import build_graph_from_14tables_v3, train_gae_v3

        graph = build_graph_from_14tables_v3(dataset.normalized().tables)
        if not graph["node_ids"]:
            return result
        model = policy.model or train_gae_v3(graph, epochs=policy.epochs, seed=policy.seed)
        records_by_task = {
            task_code: _annotate_records(records, graph, model, policy)
            for task_code, records in result.records_by_task.items()
        }
    return OfficialRunResult(
        plan=result.plan,
        executed_task_codes=result.executed_task_codes,
        records_by_task=records_by_task,
    )




# ----------------------------------------------------------------------
# v5 default config (production)
# Loaded lazily: pass to run_official_hybrid() via config=production_v5_config()
# ----------------------------------------------------------------------
V5_CHECKPOINT = (Path(__file__).parent / ".." / ".." / ".." / "03_数据集" / "gnn_hybrid_v1" / "gae_hybrid_v5.pt").resolve()
V2_CHECKPOINT = (Path(__file__).parent / ".." / ".." / ".." / "output" / "gnn_hybrid_v2_checkpoint.pt").resolve()

V5_ALPHA: dict[str, float] = {
    "1.1": 0.05,
    "1.2": 0.0,
    "2.4": 0.05,
    "4.1": 0.0,
    "4.2": 0.0,
}


def production_v5_config() -> HybridConfig:
    """Return the v5 production HybridConfig: GNN enabled, task-specific alphas."""
    return HybridConfig(
        enabled=True,
        model_version="v4",
        alpha_by_task=V5_ALPHA,
    )


def load_production_v5_model():
    """Lazily load the v5 checkpoint into a HybridGNN model.

    Returns:
        tuple[HybridGNN, str]: (model, model_version)
    """
    import torch
    from .gnn_v4 import EDGE_TYPE_VOCAB, HybridGNN

    checkpoint = torch.load(V5_CHECKPOINT, map_location="cpu", weights_only=False)
    model = HybridGNN(
        checkpoint["feature_dim"],
        hidden=checkpoint["hidden"],
        num_layers=checkpoint["num_layers"],
        num_relations=len(checkpoint.get("edge_type_vocab", EDGE_TYPE_VOCAB)),
        task_heads=checkpoint["task_codes"],
        num_mc_samples=checkpoint.get("num_mc_samples", 5),
    )
    model.load_state_dict(checkpoint["model_state"])
    model.trained_task_codes.update(checkpoint.get("trained_task_codes", ()))
    model.eval()
    return model, "v4"


def load_production_v2_model():
    """Lazily load the v2 checkpoint (12-task) into a HybridGNN model.

    Returns:
        tuple[HybridGNN, str]: (model, model_version)
    """
    import torch
    from .gnn_v4 import EDGE_TYPE_VOCAB, HybridGNN

    checkpoint = torch.load(V2_CHECKPOINT, map_location="cpu", weights_only=True)
    model = HybridGNN(
        checkpoint["feature_dim"],
        hidden=checkpoint.get("hidden", 32),
        num_layers=checkpoint.get("num_layers", 2),
        num_relations=len(checkpoint.get("edge_type_vocab", EDGE_TYPE_VOCAB)),
        task_heads=checkpoint["task_codes"],
        num_mc_samples=checkpoint.get("num_mc_samples", 10),
    )
    model.load_state_dict(checkpoint["model_state"])
    model.trained_task_codes.update(checkpoint.get("trained_task_codes", ()))
    model.eval()
    return model, "v2"


__all__ = ["HybridConfig", "run_official_hybrid", "production_v5_config", "load_production_v5_model", "load_production_v2_model", "V5_ALPHA"]


