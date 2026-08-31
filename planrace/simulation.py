"""Multi-epoch incentive simulation used by tests and the live demo."""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from typing import Any

from planrace.miners import REFERENCE_MINERS, MinerStrategy
from planrace.scoring import evaluate_artifact
from planrace.taskgen import generate_workload


def simulate(
    epochs: int = 5,
    miners: Sequence[MinerStrategy] = REFERENCE_MINERS,
) -> dict[str, Any]:
    if epochs < 1:
        raise ValueError("epochs must be positive")
    scores: dict[str, list[float]] = {}
    records = []
    for epoch in range(epochs):
        workload = generate_workload(epoch)
        evaluations = []
        for miner in miners:
            artifact = miner(workload.task)
            evaluation = evaluate_artifact(workload, artifact)
            scores.setdefault(artifact.miner_id, []).append(evaluation.score)
            evaluations.append(evaluation.model_dump(mode="json"))
        records.append(
            {
                "epoch": epoch,
                "task_id": workload.task.task_id,
                "seed_commitment": workload.task.seed_commitment,
                "seed_reveal_verified": True,
                "evaluations": evaluations,
            }
        )
    means = {miner_id: statistics.mean(values) for miner_id, values in scores.items()}
    return {
        "protocol_version": "planrace/1",
        "epochs": records,
        "mean_scores": means,
        "winner": max(means, key=lambda miner_id: means[miner_id]),
    }
