"""Deterministic score-to-weight planning and guarded chain submission."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import bittensor as bt

from planrace.network import ensure_supported_network


@dataclass(frozen=True, slots=True)
class WeightPlan:
    planned: bool
    reason: str | None
    uids: tuple[int, ...]
    weights: tuple[float, ...]


def plan_weights(scores: Mapping[int, float], *, minimum_positive_uids: int = 1) -> WeightPlan:
    if minimum_positive_uids < 1:
        raise ValueError("minimum_positive_uids must be positive")
    if any(isinstance(uid, bool) or not isinstance(uid, int) or uid < 0 for uid in scores):
        raise ValueError("UIDs must be non-negative integers")
    if any(not math.isfinite(score) or score < 0.0 for score in scores.values()):
        raise ValueError("scores must be finite and non-negative")
    positive = {uid: score for uid, score in scores.items() if score > 0.0}
    if len(positive) < minimum_positive_uids:
        return WeightPlan(False, "insufficient_positive_uids", (), ())
    total = math.fsum(positive.values())
    uids = tuple(sorted(positive))
    weights = tuple(positive[uid] / total for uid in uids)
    return WeightPlan(True, None, uids, weights)


WeightSetter = Callable[..., Any]


def submit_weight_plan(
    plan: WeightPlan,
    *,
    network: str,
    netuid: int,
    wallet_name: str,
    hotkey_name: str,
    dry_run: bool = True,
    setter: WeightSetter = bt.set_weights,
) -> Any | None:
    safe_network = ensure_supported_network(network)
    if not plan.planned:
        raise ValueError(f"cannot submit an unplanned update: {plan.reason}")
    if netuid < 0:
        raise ValueError("netuid must be non-negative")
    if dry_run:
        return None
    return setter(
        netuid,
        list(plan.weights),
        uids=list(plan.uids),
        wallet=wallet_name,
        hotkey=hotkey_name,
        network=safe_network,
    )
