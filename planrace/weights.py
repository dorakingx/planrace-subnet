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


@dataclass(frozen=True, slots=True)
class HotkeyWeightPlan:
    """A score plan whose stable identity is the miner hotkey, not a mutable UID."""

    planned: bool
    reason: str | None
    hotkeys: tuple[str, ...]
    weights: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class FinalizedMetagraphSnapshot:
    """Hotkey-to-UID binding sampled at one finalized block."""

    block_hash: str
    uid_by_hotkey: Mapping[str, int]


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


def plan_hotkey_weights(
    scores: Mapping[str, float], *, minimum_positive_hotkeys: int = 1
) -> HotkeyWeightPlan:
    if minimum_positive_hotkeys < 1:
        raise ValueError("minimum_positive_hotkeys must be positive")
    if any(not isinstance(hotkey, str) or not hotkey for hotkey in scores):
        raise ValueError("hotkeys must be non-empty strings")
    if any(not math.isfinite(score) or score < 0.0 for score in scores.values()):
        raise ValueError("scores must be finite and non-negative")
    positive = {hotkey: score for hotkey, score in scores.items() if score > 0.0}
    if len(positive) < minimum_positive_hotkeys:
        return HotkeyWeightPlan(False, "insufficient_positive_hotkeys", (), ())
    total = math.fsum(positive.values())
    hotkeys = tuple(sorted(positive))
    weights = tuple(positive[hotkey] / total for hotkey in hotkeys)
    return HotkeyWeightPlan(True, None, hotkeys, weights)


def resolve_hotkey_weight_plan(
    plan: HotkeyWeightPlan, *, snapshot: FinalizedMetagraphSnapshot
) -> WeightPlan:
    """Resolve stable hotkeys against one recorded finalized metagraph snapshot."""

    if not plan.planned:
        return WeightPlan(False, plan.reason, (), ())
    if not snapshot.block_hash.startswith("0x") or len(snapshot.block_hash) != 66:
        raise ValueError("snapshot block_hash must be a 32-byte 0x-prefixed digest")
    try:
        uids = tuple(snapshot.uid_by_hotkey[hotkey] for hotkey in plan.hotkeys)
    except KeyError as error:
        raise ValueError(
            f"scored hotkey missing from finalized metagraph: {error.args[0]}"
        ) from None
    if any(isinstance(uid, bool) or not isinstance(uid, int) or uid < 0 for uid in uids):
        raise ValueError("snapshot contains an invalid UID")
    if len(set(uids)) != len(uids):
        raise ValueError("snapshot maps multiple scored hotkeys to one UID")
    pairs = sorted(zip(uids, plan.weights, strict=True))
    return WeightPlan(
        True, None, tuple(uid for uid, _ in pairs), tuple(weight for _, weight in pairs)
    )


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
