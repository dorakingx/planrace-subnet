"""Digest-authorized, testnet-only subnet creation boundary."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, SupportsInt, cast

from pydantic import BaseModel, ConfigDict

from planrace.network import ensure_supported_network
from planrace.testnet_preflight import MAX_NETUID, TESTNET_ENDPOINT, validate_public_ss58
from planrace.testnet_provisioning import (
    MAX_CREATION_WALLET_BALANCE_RAO,
    MAX_SUBNET_CREATION_REVIEW_COST_RAO,
    MAX_TESTNET_BUDGET_RAO,
    MAX_TRANSACTION_FEE_RAO,
    OWNER_HOTKEY_ALIAS,
    WALLET_ALIAS,
    TestnetProvisionPlan,
    _tao_string,
    _validated_provision_plan_digest,
    collect_testnet_provision_plan,
)

SCHEMA_VERSION = "planrace/testnet-provision-submission/1"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class TestnetProvisionSubmissionReceipt(_StrictModel):
    schema_version: str = SCHEMA_VERSION
    network: str = "test"
    endpoint: str = TESTNET_ENDPOINT
    sdk_version: str
    source_plan_digest: str
    source_block: int
    pre_submit_block: int
    pre_submit_block_hash: str
    runtime_spec_version: int
    wallet_alias: str
    coldkey_ss58: str
    owner_hotkey_alias: str
    owner_hotkey_ss58: str
    creation_cost_snapshot_rao: int
    creation_cost_snapshot_tao: str
    authorized_wallet_balance_snapshot_rao: int
    authorized_wallet_balance_snapshot_tao: str
    max_transaction_fee_rao: int
    onchain_creation_cost_limit_available: bool = False
    dynamic_cost_acknowledged: bool = True
    transaction_constructed: bool = True
    signature_requested: bool = True
    sdk_reported_success: bool
    netuid: int
    registration_mode: str | None
    actual_registration_price_rao: int | None
    actual_registration_price_tao: str | None
    snapshot_review_cap_exceeded_at_inclusion: bool | None
    including_block_hash: str | None
    extrinsic_id: str | None
    explorer_url: str | None
    fee_tao: str | None
    submitted_at: str
    requires_finalized_readback: bool = True
    evidence_complete: bool = False
    receipt_digest: str | None
    next_action: str


class PublicKey(Protocol):
    ss58_address: str


class SigningWallet(Protocol):
    coldkeypub: PublicKey
    hotkeypub: PublicKey


class ExtrinsicResult(Protocol):
    success: bool
    block_hash: str | None
    extrinsic_id: str | None
    explorer_url: str | None
    fee: object | None
    data: dict[str, Any]


PlanCollector = Callable[[Path], TestnetProvisionPlan]
WalletFactory = Callable[[str, str], SigningWallet]
Submitter = Callable[..., ExtrinsicResult]
Clock = Callable[[], datetime]


def _default_wallet_factory(wallet_alias: str, hotkey_alias: str) -> SigningWallet:
    import bittensor as bt

    return cast(SigningWallet, bt.Wallet(name=wallet_alias, hotkey=hotkey_alias))


def _default_submitter(*, wallet: SigningWallet, owner_hotkey_ss58: str) -> ExtrinsicResult:
    import bittensor as bt

    ensure_supported_network("test")
    client = bt.Subtensor(network="test")
    try:
        if client.endpoint != TESTNET_ENDPOINT:
            raise ValueError("SDK resolved an unexpected endpoint; submission is denied")
        result = cast(Any, client).execute(
            bt.RegisterSubnet(hotkey_ss58=owner_hotkey_ss58),
            cast(Any, wallet),
            policy=bt.Policy(max_fee_tao=_tao_string(MAX_TRANSACTION_FEE_RAO)),
            retries=0,
            wait_for_inclusion=True,
            wait_for_finalization=True,
            wait_for_registration=True,
            registration_timeout=300,
        )
        return cast(ExtrinsicResult, result)
    finally:
        client.close()


def _require_fresh_equivalent_plan(
    source: TestnetProvisionPlan,
    fresh: TestnetProvisionPlan,
    *,
    max_plan_age_blocks: int,
) -> None:
    _validated_provision_plan_digest(fresh)
    if source.block is None or fresh.block is None:
        raise ValueError("provision plan has no chain block")
    age = fresh.block - source.block
    if age < 0 or age > max_plan_age_blocks:
        raise ValueError(f"provision plan is stale by {age} blocks; authorize a fresh plan")
    invariant_fields = (
        "endpoint",
        "sdk_version",
        "network",
        "runtime_spec_version",
        "wallet_alias",
        "coldkey_ss58",
        "owner_hotkey_alias",
        "owner_hotkey_ss58",
        "roles",
        "coldkey_owned_hotkeys",
        "subnet_creation_cost_rao",
        "existential_deposit_rao",
        "coldkey_balance_rao",
        "max_testnet_budget_rao",
        "max_subnet_creation_review_cost_rao",
        "max_transaction_fee_rao",
        "max_creation_wallet_balance_rao",
        "onchain_creation_cost_limit_available",
        "burn_registrations_after_creation",
        "gates",
    )
    if any(getattr(source, name) != getattr(fresh, name) for name in invariant_fields):
        raise ValueError(
            "testnet ownership, registration, balance, or price changed after approval"
        )


def _optional_nonnegative_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, (str, bytes, bytearray)):
            output = int(value)
        elif hasattr(value, "__int__"):
            output = int(cast(SupportsInt, value))
        else:
            return None
    except (TypeError, ValueError):
        return None
    return output if output >= 0 else None


def _fee_tao(value: object | None) -> str | None:
    if value is None:
        return None
    tao = getattr(value, "tao", None)
    return None if tao is None else str(tao)


def _receipt_digest_payload(receipt: TestnetProvisionSubmissionReceipt) -> str:
    payload = receipt.model_dump(mode="json", exclude={"receipt_digest", "next_action"})
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _validated_provision_receipt_digest(
    receipt: TestnetProvisionSubmissionReceipt,
) -> str:
    if (
        receipt.network != "test"
        or receipt.endpoint != TESTNET_ENDPOINT
        or receipt.wallet_alias != WALLET_ALIAS
        or receipt.owner_hotkey_alias != OWNER_HOTKEY_ALIAS
        or receipt.onchain_creation_cost_limit_available
        or not receipt.dynamic_cost_acknowledged
        or not receipt.transaction_constructed
        or not receipt.signature_requested
        or not receipt.sdk_reported_success
        or not receipt.requires_finalized_readback
        or receipt.evidence_complete
        or receipt.max_transaction_fee_rao != MAX_TRANSACTION_FEE_RAO
    ):
        raise ValueError("provision receipt violates the fixed testnet safety boundary")
    if (
        not 0 < receipt.netuid <= MAX_NETUID
        or receipt.source_block < 0
        or receipt.pre_submit_block < 0
    ):
        raise ValueError("provision receipt contains an invalid chain location")
    if receipt.source_block > receipt.pre_submit_block:
        raise ValueError("provision receipt source block is later than its pre-submit block")
    if (
        not receipt.pre_submit_block_hash.startswith("0x")
        or len(receipt.pre_submit_block_hash) != 66
    ):
        raise ValueError("provision receipt contains an invalid pre-submit block hash")
    if receipt.including_block_hash is None:
        raise ValueError("provision receipt is missing its finalized including block hash")
    if not receipt.including_block_hash.startswith("0x") or len(receipt.including_block_hash) != 66:
        raise ValueError("provision receipt contains an invalid including block hash")
    if receipt.extrinsic_id is None or not receipt.extrinsic_id:
        raise ValueError("provision receipt is missing its extrinsic identifier")
    if (
        not receipt.source_plan_digest.startswith("sha256:")
        or len(receipt.source_plan_digest) != 71
    ):
        raise ValueError("provision receipt contains an invalid source digest")
    validate_public_ss58(receipt.coldkey_ss58)
    validate_public_ss58(receipt.owner_hotkey_ss58)
    if receipt.coldkey_ss58 == receipt.owner_hotkey_ss58:
        raise ValueError("provision receipt reuses its coldkey as the owner hotkey")
    if (
        receipt.creation_cost_snapshot_rao < 0
        or receipt.authorized_wallet_balance_snapshot_rao <= 0
        or receipt.authorized_wallet_balance_snapshot_rao > MAX_CREATION_WALLET_BALANCE_RAO
        or receipt.creation_cost_snapshot_tao != _tao_string(receipt.creation_cost_snapshot_rao)
        or receipt.authorized_wallet_balance_snapshot_tao
        != _tao_string(receipt.authorized_wallet_balance_snapshot_rao)
    ):
        raise ValueError("provision receipt contains invalid snapshot amounts")
    if receipt.registration_mode not in (None, "immediate", "queued"):
        raise ValueError("provision receipt contains an invalid registration mode")
    if receipt.actual_registration_price_rao is None:
        if (
            receipt.actual_registration_price_tao is not None
            or receipt.snapshot_review_cap_exceeded_at_inclusion is not None
        ):
            raise ValueError("provision receipt has an inconsistent actual price")
    elif (
        receipt.actual_registration_price_rao < 0
        or receipt.actual_registration_price_tao
        != _tao_string(receipt.actual_registration_price_rao)
        or receipt.snapshot_review_cap_exceeded_at_inclusion
        != (receipt.actual_registration_price_rao > MAX_SUBNET_CREATION_REVIEW_COST_RAO)
    ):
        raise ValueError("provision receipt contains an inconsistent actual price")
    if receipt.receipt_digest is None:
        raise ValueError("provision receipt has no digest")
    expected = _receipt_digest_payload(receipt)
    if receipt.receipt_digest != expected:
        raise ValueError("provision receipt digest mismatch")
    return expected


def load_testnet_provision_receipt(path: Path) -> TestnetProvisionSubmissionReceipt:
    """Load a strict successful receipt and reject semantic or digest tampering."""

    try:
        receipt = TestnetProvisionSubmissionReceipt.model_validate_json(path.read_bytes())
    except OSError as error:
        raise ValueError(f"cannot read provision receipt: {type(error).__name__}") from error
    except ValueError as error:
        raise ValueError("provision receipt schema validation failed") from error
    _validated_provision_receipt_digest(receipt)
    return receipt


def submit_testnet_provision_plan(
    source: TestnetProvisionPlan,
    *,
    identities_path: Path,
    authorize_plan_digest: str,
    acknowledge_dynamic_cost: bool,
    wallet_alias: str = WALLET_ALIAS,
    owner_hotkey_alias: str = OWNER_HOTKEY_ALIAS,
    max_plan_age_blocks: int = 12,
    plan_collector: PlanCollector = collect_testnet_provision_plan,
    wallet_factory: WalletFactory = _default_wallet_factory,
    submitter: Submitter = _default_submitter,
    clock: Clock = lambda: datetime.now(UTC),
) -> TestnetProvisionSubmissionReceipt:
    """Revalidate one approved plan, bind both public keys, and create on testnet."""

    ensure_supported_network("test")
    digest = _validated_provision_plan_digest(source)
    if authorize_plan_digest != digest:
        raise ValueError("authorized digest does not match the saved provision plan")
    if not acknowledge_dynamic_cost:
        raise ValueError(
            "runtime price has no on-chain limit; explicitly acknowledge execution-block risk"
        )
    if wallet_alias != WALLET_ALIAS or owner_hotkey_alias != OWNER_HOTKEY_ALIAS:
        raise ValueError("submission is pinned to planrace-testnet and validator-00")
    if max_plan_age_blocks < 1 or max_plan_age_blocks > 24:
        raise ValueError("max plan age must be between 1 and 24 blocks")

    fresh = plan_collector(identities_path)
    _require_fresh_equivalent_plan(source, fresh, max_plan_age_blocks=max_plan_age_blocks)
    if (
        fresh.block is None
        or fresh.block_hash is None
        or fresh.runtime_spec_version is None
        or fresh.subnet_creation_cost_rao is None
        or fresh.coldkey_balance_rao is None
    ):
        raise ValueError("fresh provision plan has incomplete chain coordinates")
    if fresh.coldkey_balance_rao > MAX_TESTNET_BUDGET_RAO:
        raise ValueError("fresh wallet exposure exceeds the approved testnet budget")

    wallet = wallet_factory(wallet_alias, owner_hotkey_alias)
    if wallet.coldkeypub.ss58_address != fresh.coldkey_ss58:
        raise ValueError("local signing coldkey does not match the authorized plan")
    if wallet.hotkeypub.ss58_address != fresh.owner_hotkey_ss58:
        raise ValueError("local owner hotkey does not match the authorized plan")

    result = submitter(wallet=wallet, owner_hotkey_ss58=fresh.owner_hotkey_ss58)
    if not result.success:
        raise RuntimeError("Bittensor SDK reported unsuccessful testnet subnet creation")
    netuid = _optional_nonnegative_int(result.data.get("netuid"))
    if netuid is None or not 0 < netuid <= MAX_NETUID:
        raise RuntimeError("successful subnet creation result did not contain a non-root netuid")
    actual_price = _optional_nonnegative_int(result.data.get("registration_price_rao"))
    review_exceeded = (
        None if actual_price is None else actual_price > fresh.max_subnet_creation_review_cost_rao
    )
    receipt = TestnetProvisionSubmissionReceipt(
        sdk_version=fresh.sdk_version,
        source_plan_digest=digest,
        source_block=cast(int, source.block),
        pre_submit_block=fresh.block,
        pre_submit_block_hash=fresh.block_hash,
        runtime_spec_version=fresh.runtime_spec_version,
        wallet_alias=wallet_alias,
        coldkey_ss58=fresh.coldkey_ss58,
        owner_hotkey_alias=owner_hotkey_alias,
        owner_hotkey_ss58=fresh.owner_hotkey_ss58,
        creation_cost_snapshot_rao=fresh.subnet_creation_cost_rao,
        creation_cost_snapshot_tao=_tao_string(fresh.subnet_creation_cost_rao),
        authorized_wallet_balance_snapshot_rao=fresh.coldkey_balance_rao,
        authorized_wallet_balance_snapshot_tao=_tao_string(fresh.coldkey_balance_rao),
        max_transaction_fee_rao=MAX_TRANSACTION_FEE_RAO,
        sdk_reported_success=True,
        netuid=netuid,
        registration_mode=(
            str(result.data["registration_mode"])
            if result.data.get("registration_mode") is not None
            else None
        ),
        actual_registration_price_rao=actual_price,
        actual_registration_price_tao=(
            _tao_string(actual_price) if actual_price is not None else None
        ),
        snapshot_review_cap_exceeded_at_inclusion=review_exceeded,
        including_block_hash=result.block_hash,
        extrinsic_id=result.extrinsic_id,
        explorer_url=result.explorer_url,
        fee_tao=_fee_tao(result.fee),
        submitted_at=clock().astimezone(UTC).isoformat(),
        receipt_digest=None,
        next_action=(
            "Verify the finalized subnet owner, validator-00 UID 0 binding, locked price, "
            "and extrinsic before any activation or additional registration."
        ),
    )
    return receipt.model_copy(update={"receipt_digest": _receipt_digest_payload(receipt)})
