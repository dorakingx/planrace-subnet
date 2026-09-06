"""Transaction-free testnet weight planning against one pinned chain snapshot."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from importlib.metadata import version
from pathlib import Path
from typing import Protocol, SupportsFloat, SupportsInt, cast

from pydantic import BaseModel, ConfigDict

from planrace.network import ensure_supported_network
from planrace.testnet_preflight import TESTNET_ENDPOINT, validate_public_ss58
from planrace.weights import plan_hotkey_weights

SCHEMA_VERSION = "planrace/testnet-weight-plan/1"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class WeightTarget(_StrictModel):
    hotkey_ss58: str
    uid: int
    score: float
    weight: float


class WeightReadback(_StrictModel):
    validator_uid: int | None
    validator_permit: bool
    last_update: int | None
    weights: tuple[tuple[int, float], ...]


class WeightPlanGates(_StrictModel):
    canonical_endpoint: bool
    snapshot_pinned: bool
    subnet_exists: bool
    validator_registered: bool
    validator_permit: bool
    all_targets_registered: bool
    minimum_recipients_met: bool


class TestnetWeightPlanReport(_StrictModel):
    schema_version: str = SCHEMA_VERSION
    read_only: bool = True
    transaction_constructed: bool = False
    signature_requested: bool = False
    network: str = "test"
    endpoint: str
    sdk_version: str
    netuid: int
    block: int | None
    block_hash: str | None
    runtime_spec_version: int | None
    validator_hotkey_ss58: str
    min_allowed_weights: int | None
    weights_rate_limit: int | None
    commit_reveal_weights_enabled: bool | None
    commit_reveal_period: int | None
    targets: tuple[WeightTarget, ...]
    current_readback: WeightReadback
    gates: WeightPlanGates
    ready_for_authorized_submission: bool
    plan_digest: str | None
    next_action: str
    limitations: tuple[str, ...]
    errors: tuple[str, ...]


class WeightComparison(_StrictModel):
    uid: int
    hotkey_ss58: str
    expected: float
    observed: float | None
    absolute_error: float | None
    matches: bool


class WeightReadbackGates(_StrictModel):
    canonical_endpoint: bool
    snapshot_pinned: bool
    later_block: bool
    subnet_exists: bool
    validator_uid_stable: bool
    target_uids_stable: bool
    validator_permit: bool
    last_update_advanced: bool
    recipient_set_matches: bool
    weight_values_match: bool


class TestnetWeightReadbackReport(_StrictModel):
    schema_version: str = "planrace/testnet-weight-readback/1"
    read_only: bool = True
    transaction_constructed: bool = False
    signature_requested: bool = False
    network: str = "test"
    endpoint: str
    sdk_version: str
    netuid: int
    source_plan_digest: str
    source_block: int
    block: int | None
    block_hash: str | None
    runtime_spec_version: int | None
    validator_hotkey_ss58: str
    comparisons: tuple[WeightComparison, ...]
    current_readback: WeightReadback
    gates: WeightReadbackGates
    ready_for_testnet_evidence: bool
    next_action: str
    limitations: tuple[str, ...]
    errors: tuple[str, ...]


class Snapshot(Protocol):
    block: int

    def read(self, name: str, **params: object) -> object: ...

    def block_info(self) -> object: ...


class TestnetClient(Protocol):
    endpoint: str
    block: int
    spec_version: int

    def at(self, block: int) -> Snapshot: ...

    def close(self) -> None: ...


ClientFactory = Callable[[], TestnetClient]


def _default_client() -> TestnetClient:
    import bittensor as bt

    ensure_supported_network("test")
    return cast(TestnetClient, bt.Subtensor(network="test"))


def _field(value: object, name: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, (str, bytes, bytearray)):
            return int(value)
        if hasattr(value, "__int__"):
            return int(cast(SupportsInt, value))
    except (TypeError, ValueError):
        pass
    return None


def _optional_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _finite_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        output = float(cast(SupportsFloat, value))
    except (TypeError, ValueError, OverflowError):
        return None
    return output if math.isfinite(output) else None


def parse_public_scores(values: Sequence[str]) -> dict[str, float]:
    """Parse unique ``public-hotkey=score`` values without accepting key material."""

    scores: dict[str, float] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("score must use SS58=VALUE format")
        hotkey, raw_score = value.split("=", 1)
        validate_public_ss58(hotkey)
        score = _finite_float(raw_score)
        if score is None or score < 0.0:
            raise ValueError("scores must be finite and non-negative")
        if hotkey in scores:
            raise ValueError(f"duplicate scored hotkey {hotkey}")
        scores[hotkey] = score
    if not scores:
        raise ValueError("at least one public hotkey score is required")
    try:
        total = math.fsum(scores.values())
    except OverflowError:
        total = math.inf
    if not math.isfinite(total):
        raise ValueError("score total must be finite")
    return scores


def _hotkeys(metagraph: object) -> list[str]:
    value = _field(metagraph, "hotkeys", ())
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("testnet returned invalid metagraph hotkeys")
    output = [str(item) for item in value]
    if len(output) != len(set(output)):
        raise ValueError("testnet returned duplicate metagraph hotkeys")
    return output


def _indexed(value: object, index: int, default: object = None) -> object:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value[index] if index < len(value) else default
    return default


def _weight_readback(
    snapshot: Snapshot,
    *,
    netuid: int,
    metagraph: object,
    validator_uid: int | None,
) -> WeightReadback:
    permits = _field(metagraph, "validator_permit", ())
    last_updates = _field(metagraph, "last_update", ())
    permit = bool(_indexed(permits, validator_uid, False)) if validator_uid is not None else False
    last_update = (
        _optional_int(_indexed(last_updates, validator_uid)) if validator_uid is not None else None
    )
    if validator_uid is None:
        return WeightReadback(
            validator_uid=None,
            validator_permit=False,
            last_update=None,
            weights=(),
        )
    rows = snapshot.read("weights", netuid=netuid)
    if not isinstance(rows, Mapping):
        raise ValueError("testnet returned invalid weight rows")
    row = rows.get(validator_uid, rows.get(str(validator_uid), {}))
    if not isinstance(row, Mapping):
        raise ValueError("testnet returned an invalid validator weight row")
    weights: list[tuple[int, float]] = []
    for raw_uid, raw_weight in row.items():
        uid = _optional_int(raw_uid)
        weight = _finite_float(raw_weight)
        if uid is None or uid < 0 or weight is None or weight < 0.0:
            raise ValueError("testnet returned an invalid weight entry")
        if weight > 0.0:
            weights.append((uid, weight))
    return WeightReadback(
        validator_uid=validator_uid,
        validator_permit=permit,
        last_update=last_update,
        weights=tuple(sorted(weights)),
    )


def _digest_payload(
    *,
    netuid: int,
    block: int,
    block_hash: str,
    validator_hotkey: str,
    targets: Sequence[WeightTarget],
) -> str:
    payload = {
        "block": block,
        "block_hash": block_hash,
        "netuid": netuid,
        "targets": [target.model_dump(mode="json") for target in targets],
        "validator_hotkey_ss58": validator_hotkey,
    }
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _validated_plan_digest(report: TestnetWeightPlanReport) -> str:
    if (
        report.block is None
        or report.block_hash is None
        or report.plan_digest is None
        or not report.targets
    ):
        raise ValueError("weight plan has no complete proposed operation")
    expected = _digest_payload(
        netuid=report.netuid,
        block=report.block,
        block_hash=report.block_hash,
        validator_hotkey=report.validator_hotkey_ss58,
        targets=report.targets,
    )
    if report.plan_digest != expected:
        raise ValueError("weight plan digest mismatch")
    if (
        report.endpoint != TESTNET_ENDPOINT
        or report.network != "test"
        or not report.read_only
        or report.transaction_constructed
        or report.signature_requested
        or report.errors
        or not report.ready_for_authorized_submission
        or not all(report.gates.model_dump().values())
    ):
        raise ValueError("source weight plan did not pass every pre-signing gate")
    if len({target.uid for target in report.targets}) != len(report.targets):
        raise ValueError("weight plan contains duplicate target UIDs")
    if len({target.hotkey_ss58 for target in report.targets}) != len(report.targets):
        raise ValueError("weight plan contains duplicate target hotkeys")
    if not math.isclose(
        math.fsum(target.weight for target in report.targets),
        1.0,
        abs_tol=1e-12,
    ):
        raise ValueError("weight plan target weights are not normalized")
    return expected


def load_testnet_weight_plan(path: Path) -> TestnetWeightPlanReport:
    """Load and validate a saved pre-signing plan without accepting extra fields."""

    try:
        report = TestnetWeightPlanReport.model_validate_json(path.read_bytes())
    except OSError as error:
        raise ValueError(f"cannot read weight plan: {type(error).__name__}") from error
    except ValueError as error:
        raise ValueError("weight plan schema validation failed") from error
    _validated_plan_digest(report)
    return report


def collect_testnet_weight_plan(
    *,
    netuid: int,
    validator_hotkey_ss58: str,
    score_specs: Sequence[str],
    minimum_positive_hotkeys: int = 2,
    client_factory: ClientFactory = _default_client,
) -> TestnetWeightPlanReport:
    """Resolve scores and current weights without constructing or signing a call."""

    ensure_supported_network("test")
    if netuid < 0:
        raise ValueError("netuid must be non-negative")
    if minimum_positive_hotkeys < 1:
        raise ValueError("minimum_positive_hotkeys must be positive")
    validate_public_ss58(validator_hotkey_ss58)
    scores = parse_public_scores(score_specs)
    if validator_hotkey_ss58 in scores:
        raise ValueError("validator hotkey cannot be a scored miner")
    proposed = plan_hotkey_weights(scores, minimum_positive_hotkeys=minimum_positive_hotkeys)
    limitations = (
        "This exact-block snapshot is not proof that the block is finalized.",
        "The plan can become stale if UID bindings or subnet parameters change.",
        "No wallet path, private key, transaction, signature, or submission is used.",
    )
    client: TestnetClient | None = None
    empty_readback = WeightReadback(
        validator_uid=None,
        validator_permit=False,
        last_update=None,
        weights=(),
    )
    try:
        client = client_factory()
        endpoint = str(client.endpoint)
        block = int(client.block)
        snapshot = client.at(block)
        info = snapshot.block_info()
        block_hash = str(_field(info, "hash", ""))
        info_number = _optional_int(_field(info, "number"))
        snapshot_pinned = int(snapshot.block) == block and info_number == block
        canonical = endpoint == TESTNET_ENDPOINT
        errors: list[str] = []
        if not canonical:
            errors.append("SDK resolved an unexpected endpoint; planning is denied")
        if not block_hash.startswith("0x") or len(block_hash) != 66:
            errors.append("testnet returned an invalid block hash")

        subnet = snapshot.read("subnet", netuid=netuid)
        subnet_exists = subnet is not None
        hyper: object = {}
        metagraph: object = {}
        validator_uid: int | None = None
        targets: tuple[WeightTarget, ...] = ()
        readback = empty_readback
        min_allowed: int | None = None
        rate_limit: int | None = None
        commit_reveal: bool | None = None
        reveal_period: int | None = None
        all_targets_registered = False
        validator_registered = False
        if subnet_exists:
            hyper = snapshot.read("subnet_hyperparameters", netuid=netuid)
            metagraph = snapshot.read("metagraph", netuid=netuid)
            min_allowed = _optional_int(_field(hyper, "min_allowed_weights"))
            rate_limit = _optional_int(_field(hyper, "weights_rate_limit"))
            commit_reveal = _optional_bool(_field(hyper, "commit_reveal_weights_enabled"))
            reveal_period = _optional_int(_field(hyper, "commit_reveal_period"))
            hotkeys = _hotkeys(metagraph)
            uid_by_hotkey = {hotkey: uid for uid, hotkey in enumerate(hotkeys)}
            validator_uid = uid_by_hotkey.get(validator_hotkey_ss58)
            validator_registered = validator_uid is not None
            all_targets_registered = proposed.planned and all(
                hotkey in uid_by_hotkey for hotkey in proposed.hotkeys
            )
            if proposed.planned and all_targets_registered:
                target_rows = [
                    WeightTarget(
                        hotkey_ss58=hotkey,
                        uid=uid_by_hotkey[hotkey],
                        score=scores[hotkey],
                        weight=weight,
                    )
                    for hotkey, weight in zip(proposed.hotkeys, proposed.weights, strict=True)
                ]
                targets = tuple(sorted(target_rows, key=lambda item: item.uid))
            readback = _weight_readback(
                snapshot,
                netuid=netuid,
                metagraph=metagraph,
                validator_uid=validator_uid,
            )

        minimum_recipients_met = bool(targets) and (
            min_allowed is not None and len(targets) >= min_allowed
        )
        gates = WeightPlanGates(
            canonical_endpoint=canonical,
            snapshot_pinned=snapshot_pinned,
            subnet_exists=subnet_exists,
            validator_registered=validator_registered,
            validator_permit=readback.validator_permit,
            all_targets_registered=all_targets_registered,
            minimum_recipients_met=minimum_recipients_met,
        )
        ready = (
            proposed.planned
            and all(gates.model_dump().values())
            and not errors
            and block_hash.startswith("0x")
            and len(block_hash) == 66
        )
        digest = (
            _digest_payload(
                netuid=netuid,
                block=block,
                block_hash=block_hash,
                validator_hotkey=validator_hotkey_ss58,
                targets=targets,
            )
            if targets and not errors
            else None
        )
        if not canonical or errors:
            next_action = "Stop: restore canonical read-only testnet state and rerun."
        elif not subnet_exists:
            next_action = "Choose an existing testnet subnet and rerun."
        elif not validator_registered:
            next_action = "Register the validator only after explicit signing authorization."
        elif not readback.validator_permit:
            next_action = "Wait for validator permit before any weight operation."
        elif not all_targets_registered:
            next_action = "Register every scored miner and rerun against a fresh block."
        elif not minimum_recipients_met:
            next_action = "Provide enough positive scored miners for the subnet minimum."
        else:
            next_action = (
                "Review this digest, rerun at a fresh block, then explicitly authorize signing."
            )
        return TestnetWeightPlanReport(
            endpoint=endpoint,
            sdk_version=version("bittensor"),
            netuid=netuid,
            block=block,
            block_hash=block_hash or None,
            runtime_spec_version=int(client.spec_version),
            validator_hotkey_ss58=validator_hotkey_ss58,
            min_allowed_weights=min_allowed,
            weights_rate_limit=rate_limit,
            commit_reveal_weights_enabled=commit_reveal,
            commit_reveal_period=reveal_period,
            targets=targets,
            current_readback=readback,
            gates=gates,
            ready_for_authorized_submission=ready,
            plan_digest=digest,
            next_action=next_action,
            limitations=limitations,
            errors=tuple(errors),
        )
    except Exception as error:
        return TestnetWeightPlanReport(
            endpoint=TESTNET_ENDPOINT,
            sdk_version=version("bittensor"),
            netuid=netuid,
            block=None,
            block_hash=None,
            runtime_spec_version=None,
            validator_hotkey_ss58=validator_hotkey_ss58,
            min_allowed_weights=None,
            weights_rate_limit=None,
            commit_reveal_weights_enabled=None,
            commit_reveal_period=None,
            targets=(),
            current_readback=empty_readback,
            gates=WeightPlanGates(
                canonical_endpoint=False,
                snapshot_pinned=False,
                subnet_exists=False,
                validator_registered=False,
                validator_permit=False,
                all_targets_registered=False,
                minimum_recipients_met=False,
            ),
            ready_for_authorized_submission=False,
            plan_digest=None,
            next_action="Stop: restore canonical read-only testnet state and rerun.",
            limitations=limitations,
            errors=(f"read-only planning failed: {type(error).__name__}",),
        )
    finally:
        if client is not None:
            client.close()


def _empty_readback_gates() -> WeightReadbackGates:
    return WeightReadbackGates(
        canonical_endpoint=False,
        snapshot_pinned=False,
        later_block=False,
        subnet_exists=False,
        validator_uid_stable=False,
        target_uids_stable=False,
        validator_permit=False,
        last_update_advanced=False,
        recipient_set_matches=False,
        weight_values_match=False,
    )


def verify_testnet_weight_readback(
    source: TestnetWeightPlanReport,
    *,
    client_factory: ClientFactory = _default_client,
    quantization_tolerance: float = 2.0 / 65_535.0,
) -> TestnetWeightReadbackReport:
    """Verify a later public chain row against a saved, digest-bound plan."""

    if quantization_tolerance <= 0.0 or not math.isfinite(quantization_tolerance):
        raise ValueError("quantization_tolerance must be finite and positive")
    _validated_plan_digest(source)
    source_block = cast(int, source.block)
    source_plan_digest = cast(str, source.plan_digest)

    limitations = (
        "This exact-block readback is not proof that the block is finalized.",
        "A matching row does not identify or prove success of a specific extrinsic.",
        "Final evidence must separately bind the finalized extrinsic and block hash.",
        "No wallet path, private key, transaction, signature, or submission is used.",
    )
    empty_readback = WeightReadback(
        validator_uid=None,
        validator_permit=False,
        last_update=None,
        weights=(),
    )
    client: TestnetClient | None = None
    try:
        client = client_factory()
        endpoint = str(client.endpoint)
        block = int(client.block)
        snapshot = client.at(block)
        info = snapshot.block_info()
        block_hash = str(_field(info, "hash", ""))
        info_number = _optional_int(_field(info, "number"))
        canonical = endpoint == TESTNET_ENDPOINT
        pinned = int(snapshot.block) == block and info_number == block
        later_block = block > source_block
        errors: list[str] = []
        if not canonical:
            errors.append("SDK resolved an unexpected endpoint; readback is denied")
        if not block_hash.startswith("0x") or len(block_hash) != 66:
            errors.append("testnet returned an invalid block hash")

        subnet = snapshot.read("subnet", netuid=source.netuid)
        subnet_exists = subnet is not None
        validator_uid_stable = False
        target_uids_stable = False
        readback = empty_readback
        comparisons: tuple[WeightComparison, ...] = ()
        recipient_set_matches = False
        weight_values_match = False
        if subnet_exists:
            metagraph = snapshot.read("metagraph", netuid=source.netuid)
            hotkeys = _hotkeys(metagraph)
            uid_by_hotkey = {hotkey: uid for uid, hotkey in enumerate(hotkeys)}
            validator_uid = uid_by_hotkey.get(source.validator_hotkey_ss58)
            validator_uid_stable = (
                validator_uid is not None and validator_uid == source.current_readback.validator_uid
            )
            target_uids_stable = all(
                uid_by_hotkey.get(target.hotkey_ss58) == target.uid for target in source.targets
            )
            readback = _weight_readback(
                snapshot,
                netuid=source.netuid,
                metagraph=metagraph,
                validator_uid=validator_uid,
            )
            observed = dict(readback.weights)
            expected_uids = {target.uid for target in source.targets}
            recipient_set_matches = set(observed) == expected_uids
            comparison_rows: list[WeightComparison] = []
            for target in source.targets:
                observed_weight = observed.get(target.uid)
                error = (
                    abs(observed_weight - target.weight) if observed_weight is not None else None
                )
                comparison_rows.append(
                    WeightComparison(
                        uid=target.uid,
                        hotkey_ss58=target.hotkey_ss58,
                        expected=target.weight,
                        observed=observed_weight,
                        absolute_error=error,
                        matches=(error is not None and error <= quantization_tolerance),
                    )
                )
            comparisons = tuple(comparison_rows)
            weight_values_match = bool(comparisons) and all(
                comparison.matches for comparison in comparisons
            )

        last_update_advanced = (
            readback.last_update is not None and readback.last_update > source_block
        )
        gates = WeightReadbackGates(
            canonical_endpoint=canonical,
            snapshot_pinned=pinned,
            later_block=later_block,
            subnet_exists=subnet_exists,
            validator_uid_stable=validator_uid_stable,
            target_uids_stable=target_uids_stable,
            validator_permit=readback.validator_permit,
            last_update_advanced=last_update_advanced,
            recipient_set_matches=recipient_set_matches,
            weight_values_match=weight_values_match,
        )
        ready = all(gates.model_dump().values()) and not errors
        next_action = (
            "Bind this readback to the separately finalized extrinsic in signed evidence."
            if ready
            else "Do not claim weight completion; inspect failed gates and rerun later."
        )
        return TestnetWeightReadbackReport(
            endpoint=endpoint,
            sdk_version=version("bittensor"),
            netuid=source.netuid,
            source_plan_digest=source_plan_digest,
            source_block=source_block,
            block=block,
            block_hash=block_hash or None,
            runtime_spec_version=int(client.spec_version),
            validator_hotkey_ss58=source.validator_hotkey_ss58,
            comparisons=comparisons,
            current_readback=readback,
            gates=gates,
            ready_for_testnet_evidence=ready,
            next_action=next_action,
            limitations=limitations,
            errors=tuple(errors),
        )
    except Exception as error:
        return TestnetWeightReadbackReport(
            endpoint=TESTNET_ENDPOINT,
            sdk_version=version("bittensor"),
            netuid=source.netuid,
            source_plan_digest=source_plan_digest,
            source_block=source_block,
            block=None,
            block_hash=None,
            runtime_spec_version=None,
            validator_hotkey_ss58=source.validator_hotkey_ss58,
            comparisons=(),
            current_readback=empty_readback,
            gates=_empty_readback_gates(),
            ready_for_testnet_evidence=False,
            next_action="Do not claim weight completion; restore canonical read-only state.",
            limitations=limitations,
            errors=(f"read-only verification failed: {type(error).__name__}",),
        )
    finally:
        if client is not None:
            client.close()
