"""Reference miner strategies; real miners are free to implement better search."""

from __future__ import annotations

from collections.abc import Callable

from planrace.models import OptimizationArtifact, QueryTask

MinerStrategy = Callable[[QueryTask], OptimizationArtifact]


def indexed_miner(task: QueryTask) -> OptimizationArtifact:
    return OptimizationArtifact(
        task_id=task.task_id,
        miner_id="honest-indexed",
        strategy="partial-index-v1",
        candidate_sql=task.reference_sql,
        setup_sql=(
            "CREATE INDEX idx_paid_customer_amount "
            "ON orders(customer_id, amount) WHERE status = 'paid'",
            "CREATE INDEX idx_active_customer ON customers(id, segment) WHERE active = 1",
        ),
    )


def baseline_miner(task: QueryTask) -> OptimizationArtifact:
    return OptimizationArtifact(
        task_id=task.task_id,
        miner_id="baseline",
        strategy="identity-v1",
        candidate_sql=task.reference_sql,
    )


def gaming_miner(task: QueryTask) -> OptimizationArtifact:
    return OptimizationArtifact(
        task_id=task.task_id,
        miner_id="gaming-fast-wrong",
        strategy="widen-filter-v1",
        candidate_sql=task.reference_sql.replace(
            "o.status = 'paid'", "o.status IN ('paid', 'pending')"
        ),
        setup_sql=("CREATE INDEX idx_status ON orders(status)",),
    )


REFERENCE_MINERS: tuple[MinerStrategy, ...] = (indexed_miner, baseline_miner, gaming_miner)
