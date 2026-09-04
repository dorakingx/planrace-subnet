"""Reproducible heterogeneous miner profiles for PlanRace v2 localnet evidence.

These profiles are deliberately public and deterministic. They exercise the
wire protocol and incentive mechanism; they are not production recommendations
for every SQL workload.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from planrace.models_v2 import (
    BundleMetadata,
    IndexColumn,
    IndexSpec,
    NullLiteral,
    OptimizationBundle,
    PredicateAtom,
    PredicateExpression,
    PublicTaskV2,
)

MinerStrategyV2 = Callable[
    [PublicTaskV2], OptimizationBundle | Awaitable[OptimizationBundle]
]

PROFILE_NAMES = (
    "baseline",
    "selective-index",
    "composite-index",
    "covering-index",
    "restricted-rewrite",
    "hybrid",
    "over-indexing",
    "constant-answer-attempt",
    "timeout-resource-attempt",
    "copycat-sybil",
)


def strategy_for_profile(profile: str, *, timeout_seconds: float = 2.0) -> MinerStrategyV2:
    if profile not in PROFILE_NAMES:
        raise ValueError(f"unknown localnet v2 profile: {profile}")
    if profile == "timeout-resource-attempt":
        return lambda task: _delayed_bundle(task, timeout_seconds)
    return lambda task: bundle_for_profile(task, profile)


async def _delayed_bundle(task: PublicTaskV2, delay: float) -> OptimizationBundle:
    await asyncio.sleep(delay)
    return _bundle(task, "timeout-resource-attempt", ())


def bundle_for_profile(task: PublicTaskV2, profile: str) -> OptimizationBundle:
    """Return one of ten behaviorally distinct localnet submissions.

    The constant-answer profile demonstrates the protocol boundary: v2 has no
    field in which a miner can submit a query result, so its attempted exploit
    collapses to a no-index bundle and earns no performance reward. Copycat is
    intentionally executable-identical to selective-index to test task-level
    duplicate reward splitting.
    """

    if profile not in PROFILE_NAMES:
        raise ValueError(f"unknown localnet v2 profile: {profile}")
    if profile in {"baseline", "constant-answer-attempt"}:
        return _bundle(task, profile, ())

    selective, composite, covering, partial, secondary = _family_indexes(
        task.benchmark_family_id
    )
    indexes: tuple[IndexSpec, ...]
    if profile in {"selective-index", "copycat-sybil"}:
        indexes = (selective,)
    elif profile == "composite-index":
        indexes = (composite,)
    elif profile == "covering-index":
        indexes = (covering,)
    elif profile == "restricted-rewrite":
        indexes = (partial,)
    elif profile == "hybrid":
        indexes = (composite, secondary)
    elif profile == "over-indexing":
        indexes = (selective, composite, covering, secondary)
    else:
        raise ValueError("timeout profile must be resolved through strategy_for_profile")
    return _bundle(task, profile, indexes)


def _bundle(
    task: PublicTaskV2, profile: str, indexes: tuple[IndexSpec, ...]
) -> OptimizationBundle:
    return OptimizationBundle.create(
        task_id=task.task_id,
        engine_image_digest=task.engine_image_digest,
        indexes=indexes,
        metadata=BundleMetadata(
            strategy=profile,
            estimated_intent=("no_index" if not indexes else "mixed"),
            rationale=f"Public deterministic localnet profile: {profile}.",
        ),
    )


def _columns(*names: str) -> tuple[IndexColumn, ...]:
    return tuple(IndexColumn(column=name) for name in names)


def _index(
    table: str,
    *keys: str,
    include: tuple[str, ...] = (),
    predicate: PredicateExpression | None = None,
) -> IndexSpec:
    return IndexSpec(
        table=table,
        key_columns=_columns(*keys),
        include_columns=include,
        predicate=predicate,
    )


def _family_indexes(
    family: str,
) -> tuple[IndexSpec, IndexSpec, IndexSpec, IndexSpec, IndexSpec]:
    if family == "paid-revenue-by-segment":
        return (
            _index("orders", "status"),
            _index("orders", "status", "created_day", "customer_id"),
            _index(
                "orders",
                "status",
                "created_day",
                "customer_id",
                include=("amount_cents",),
            ),
            _index(
                "orders",
                "created_day",
                "status",
                "customer_id",
            ),
            _index("customers", "active", "id", include=("segment",)),
        )
    if family == "customer-order-threshold":
        return (
            _index("orders", "status"),
            _index("orders", "status", "amount_cents", "customer_id"),
            _index(
                "orders",
                "status",
                "amount_cents",
                "customer_id",
                include=("id",),
            ),
            _index(
                "orders",
                "amount_cents",
                "status",
                "customer_id",
            ),
            _index("customers", "id"),
        )
    if family == "bounded-range-scan":
        return (
            _index("orders", "status"),
            _index("orders", "status", "amount_cents", "id"),
            _index(
                "orders",
                "status",
                "amount_cents",
                "id",
                include=("customer_id",),
            ),
            _index(
                "orders",
                "amount_cents",
                "status",
                "id",
            ),
            _index("orders", "amount_cents", "id"),
        )
    if family == "region-channel-aggregate":
        return (
            _index("customers", "region"),
            _index("orders", "channel", "customer_id"),
            _index("orders", "channel", "customer_id", include=("amount_cents",)),
            _index(
                "orders",
                "customer_id",
                "channel",
            ),
            _index("customers", "region", "id"),
        )
    if family == "nullable-coupon":
        null_only = PredicateExpression(
            atoms=(
                PredicateAtom(
                    column="coupon_code", operator="is_null", value=NullLiteral()
                ),
            )
        )
        return (
            _index("orders", "created_day"),
            _index("orders", "created_day", "status"),
            _index("orders", "created_day", "status", include=("amount_cents",)),
            _index("orders", "created_day", "status", predicate=null_only),
            _index("orders", "coupon_code", "created_day"),
        )
    if family == "intentional-zero-result":
        return (
            _index("orders", "status"),
            _index("orders", "status", "amount_cents", "id"),
            _index("orders", "status", "amount_cents", "id", include=("customer_id",)),
            _index(
                "orders",
                "status",
                "amount_cents",
                "id",
            ),
            _index("orders", "amount_cents"),
        )
    raise ValueError(f"unknown benchmark family: {family}")
