"""Fail-closed, digest-authorized Bittensor testnet weight submission."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from pydantic import BaseModel, ConfigDict

from planrace.network import ensure_supported_network
from planrace.testnet_preflight import TESTNET_ENDPOINT
from planrace.testnet_weights import (
    TestnetWeightPlanReport,
    WeightTarget,
    _validated_plan_digest,
    collect_testnet_weight_plan,
)

SCHEMA_VERSION = "planrace/testnet-weight-submission/1"
WALLET_ALIAS = "planrace-testnet"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SubmittedTarget(_StrictModel):
    hotkey_ss58: str
    uid: int
    u16_weight: int


class TestnetWeightSubmissionReceipt(_StrictModel):
    schema_version: str = SCHEMA_VERSION
    network: str = "test"
    endpoint: str = TESTNET_ENDPOINT
    sdk_version: str
    source_plan_digest: str
    source_block: int
    pre_submit_block: int
    pre_submit_block_hash: str
    runtime_spec_version: int
    netuid: int
    validator_hotkey_ss58: str
    wallet_alias: str
    hotkey_alias: str
    submitted_targets: tuple[SubmittedTarget, ...]
    transaction_constructed: bool = True
    signature_requested: bool = True
    sdk_reported_success: bool
    including_block_hash: str | None
    extrinsic_id: str | None
    explorer_url: str | None
    fee_tao: str | None
    reveal_round: int | None
    submitted_at: str
    requires_delayed_readback: bool
    evidence_complete: bool = False
    next_action: str


class PublicKey(Protocol):
    ss58_address: str


class SigningWallet(Protocol):
    hotkeypub: PublicKey


class ExtrinsicResult(Protocol):
    success: bool
    block_hash: str | None
    extrinsic_id: str | None
    explorer_url: str | None
    fee: object | None
    data: dict[str, Any]


PlanCollector = Callable[..., TestnetWeightPlanReport]
WalletFactory = Callable[[str, str], SigningWallet]
Submitter = Callable[..., ExtrinsicResult]
Clock = Callable[[], datetime]


def _default_wallet_factory(wallet_alias: str, hotkey_alias: str) -> SigningWallet:
    import bittensor as bt

    return cast(SigningWallet, bt.Wallet(name=wallet_alias, hotkey=hotkey_alias))


def _default_submitter(
    *, netuid: int, weights: dict[int, int], wallet: SigningWallet
) -> ExtrinsicResult:
    import bittensor as bt

    ensure_supported_network("test")
    return cast(
        ExtrinsicResult,
        bt.set_weights(
            netuid,
            weights,
            wallet=cast(Any, wallet),
            network="test",
            retries=0,
        ),
    )


def _target_fingerprint(targets: tuple[WeightTarget, ...]) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            target.hotkey_ss58,
            target.uid,
            target.score,
            target.planned_weight,
            target.weight,
            target.u16_weight,
        )
        for target in targets
    )


def _require_fresh_equivalent_plan(
    source: TestnetWeightPlanReport,
    fresh: TestnetWeightPlanReport,
    *,
    max_plan_age_blocks: int,
) -> None:
    if not fresh.ready_for_authorized_submission or fresh.errors:
        raise ValueError("fresh testnet plan did not pass every pre-signing gate")
    if source.block is None or fresh.block is None:
        raise ValueError("weight plan has no chain block")
    age = fresh.block - source.block
    if age < 0 or age > max_plan_age_blocks:
        raise ValueError(f"weight plan is stale by {age} blocks; create and authorize a fresh plan")
    invariant_fields = (
        "endpoint",
        "sdk_version",
        "network",
        "netuid",
        "runtime_spec_version",
        "validator_hotkey_ss58",
        "min_allowed_weights",
        "max_weights_limit",
        "weights_rate_limit",
        "commit_reveal_weights_enabled",
        "commit_reveal_period",
        "weights_were_clipped",
        "current_readback",
    )
    if any(getattr(source, name) != getattr(fresh, name) for name in invariant_fields):
        raise ValueError("testnet state changed after the authorized plan was created")
    if _target_fingerprint(source.targets) != _target_fingerprint(fresh.targets):
        raise ValueError("testnet UID bindings or conformed weights changed after authorization")


def _fee_tao(value: object | None) -> str | None:
    if value is None:
        return None
    tao = getattr(value, "tao", None)
    return None if tao is None else str(tao)


def submit_testnet_weight_plan(
    source: TestnetWeightPlanReport,
    *,
    authorize_plan_digest: str,
    hotkey_alias: str,
    wallet_alias: str = WALLET_ALIAS,
    max_plan_age_blocks: int = 12,
    plan_collector: PlanCollector = collect_testnet_weight_plan,
    wallet_factory: WalletFactory = _default_wallet_factory,
    submitter: Submitter = _default_submitter,
    clock: Clock = lambda: datetime.now(UTC),
) -> TestnetWeightSubmissionReceipt:
    """Revalidate a recent approved plan, bind its signer, and submit on `test` only."""

    ensure_supported_network("test")
    digest = _validated_plan_digest(source)
    if authorize_plan_digest != digest:
        raise ValueError("authorized digest does not match the saved weight plan")
    if wallet_alias != WALLET_ALIAS:
        raise ValueError(f"wallet alias must be exactly {WALLET_ALIAS!r}")
    if not hotkey_alias.startswith("validator-") or not hotkey_alias[10:].isdigit():
        raise ValueError("hotkey alias must be a named PlanRace validator")
    if max_plan_age_blocks < 1 or max_plan_age_blocks > 24:
        raise ValueError("max plan age must be between 1 and 24 blocks")

    wallet = wallet_factory(wallet_alias, hotkey_alias)
    if wallet.hotkeypub.ss58_address != source.validator_hotkey_ss58:
        raise ValueError("local signing hotkey does not match the authorized validator")

    score_specs = tuple(f"{target.hotkey_ss58}={target.score!r}" for target in source.targets)
    fresh = plan_collector(
        netuid=source.netuid,
        validator_hotkey_ss58=source.validator_hotkey_ss58,
        score_specs=score_specs,
        minimum_positive_hotkeys=1,
    )
    _require_fresh_equivalent_plan(source, fresh, max_plan_age_blocks=max_plan_age_blocks)
    if fresh.block is None or fresh.block_hash is None or fresh.runtime_spec_version is None:
        raise ValueError("fresh weight plan has incomplete chain coordinates")

    result = submitter(
        netuid=source.netuid,
        weights={target.uid: target.u16_weight for target in source.targets},
        wallet=wallet,
    )
    if not result.success:
        raise RuntimeError("Bittensor SDK reported an unsuccessful testnet submission")
    reveal_round_raw = result.data.get("reveal_round")
    reveal_round = int(reveal_round_raw) if reveal_round_raw is not None else None
    return TestnetWeightSubmissionReceipt(
        sdk_version=source.sdk_version,
        source_plan_digest=digest,
        source_block=cast(int, source.block),
        pre_submit_block=fresh.block,
        pre_submit_block_hash=fresh.block_hash,
        runtime_spec_version=fresh.runtime_spec_version,
        netuid=source.netuid,
        validator_hotkey_ss58=source.validator_hotkey_ss58,
        wallet_alias=wallet_alias,
        hotkey_alias=hotkey_alias,
        submitted_targets=tuple(
            SubmittedTarget(
                hotkey_ss58=target.hotkey_ss58,
                uid=target.uid,
                u16_weight=target.u16_weight,
            )
            for target in source.targets
        ),
        sdk_reported_success=True,
        including_block_hash=result.block_hash,
        extrinsic_id=result.extrinsic_id,
        explorer_url=result.explorer_url,
        fee_tao=_fee_tao(result.fee),
        reveal_round=reveal_round,
        submitted_at=clock().astimezone(UTC).isoformat(),
        requires_delayed_readback=reveal_round is not None,
        next_action=(
            "Wait for the timelock reveal round, then verify a later metagraph readback."
            if reveal_round is not None
            else "Verify a later metagraph readback and bind it to this receipt."
        ),
    )
