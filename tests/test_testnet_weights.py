from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

import pytest
from bittensor.intents.weights import clip_to_max_weight, normalize
from typer.testing import CliRunner

from planrace import cli
from planrace.cli import app
from planrace.testnet_preflight import TESTNET_ENDPOINT
from planrace.testnet_submission import (
    TestnetWeightSubmissionReceipt as SubmissionReceipt,
)
from planrace.testnet_submission import submit_testnet_weight_plan
from planrace.testnet_weights import TestnetWeightPlanReport as WeightPlanReport
from planrace.testnet_weights import TestnetWeightReadbackReport as ReadbackReport
from planrace.testnet_weights import (
    _conform_weight_vector,
    collect_testnet_weight_plan,
    load_testnet_weight_plan,
    parse_public_scores,
    verify_testnet_weight_readback,
)

VALIDATOR = "5" + "B" * 47
MINER_A = "5" + "C" * 47
MINER_B = "5" + "D" * 47


class FakeBlockInfo:
    hash = "0x" + "1" * 64
    number = 12_345


class FakeSnapshot:
    block = 12_345

    def block_info(self) -> FakeBlockInfo:
        return FakeBlockInfo()

    def query(self, item: object, params: list[object] | None = None) -> object:
        assert item.name == "NetworksAdded"  # type: ignore[attr-defined]
        assert params == [7]
        return True

    def read(self, name: str, **params: object) -> object:
        assert params["netuid"] == 7
        if name == "subnet":
            return {"netuid": 7}
        if name == "subnet_hyperparameters":
            return {
                "min_allowed_weights": 2,
                "max_weights_limit": 65_535,
                "weights_rate_limit": 100,
                "commit_reveal_weights_enabled": True,
                "commit_reveal_period": 1_000,
            }
        if name == "metagraph":
            return {
                "hotkeys": [VALIDATOR, MINER_A, MINER_B],
                "owner_hotkey": "5" + "E" * 47,
                "validator_permit": [True, False, False],
                "last_update": [12_000, 0, 0],
            }
        if name == "weights":
            return {0: {1: 0.25, 2: 0.75}}
        raise AssertionError(f"unexpected read {name}")


class FakeClient:
    endpoint = TESTNET_ENDPOINT
    block = 12_345
    spec_version = 454

    def __init__(self, *, endpoint: str = TESTNET_ENDPOINT) -> None:
        self.endpoint = endpoint
        self.closed = False

    def at(self, block: int) -> FakeSnapshot:
        assert block == self.block
        return FakeSnapshot()

    def close(self) -> None:
        self.closed = True


class FakePostBlockInfo:
    hash = "0x" + "2" * 64
    number = 12_400


class FakePostSnapshot:
    block = 12_400

    def __init__(
        self,
        *,
        hotkeys: list[str] | None = None,
        last_update: int = 12_350,
        row: dict[int, float] | None = None,
    ) -> None:
        self.hotkeys = hotkeys or [VALIDATOR, MINER_A, MINER_B]
        self.last_update = last_update
        self.row = row if row is not None else {1: 0.25, 2: 0.75}

    def block_info(self) -> FakePostBlockInfo:
        return FakePostBlockInfo()

    def query(self, item: object, params: list[object] | None = None) -> object:
        assert item.name == "NetworksAdded"  # type: ignore[attr-defined]
        assert params == [7]
        return True

    def read(self, name: str, **params: object) -> object:
        assert params["netuid"] == 7
        if name == "subnet":
            return {"netuid": 7}
        if name == "metagraph":
            return {
                "hotkeys": self.hotkeys,
                "owner_hotkey": "5" + "E" * 47,
                "validator_permit": [True, False, False],
                "last_update": [self.last_update, 0, 0],
            }
        if name == "weights":
            return {0: self.row}
        raise AssertionError(f"unexpected read {name}")


class FakePostClient:
    endpoint = TESTNET_ENDPOINT
    block = 12_400
    spec_version = 454

    def __init__(
        self,
        *,
        endpoint: str = TESTNET_ENDPOINT,
        snapshot: FakePostSnapshot | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.snapshot = snapshot or FakePostSnapshot()
        self.closed = False

    def at(self, block: int) -> FakePostSnapshot:
        assert block == self.block
        return self.snapshot

    def close(self) -> None:
        self.closed = True


def score_specs() -> tuple[str, ...]:
    return (f"{MINER_A}=1", f"{MINER_B}=3")


def weight_plan() -> WeightPlanReport:
    return collect_testnet_weight_plan(
        netuid=7,
        validator_hotkey_ss58=VALIDATOR,
        score_specs=score_specs(),
        client_factory=FakeClient,
    )


def test_plan_resolves_public_hotkeys_and_reads_existing_weights() -> None:
    client = FakeClient()
    report = collect_testnet_weight_plan(
        netuid=7,
        validator_hotkey_ss58=VALIDATOR,
        score_specs=score_specs(),
        client_factory=lambda: client,
    )

    assert report.read_only is True
    assert report.schema_version == "planrace/testnet-weight-plan/3"
    assert report.transaction_constructed is False
    assert report.signature_requested is False
    assert report.block_hash == FakeBlockInfo.hash
    assert [(target.uid, target.weight) for target in report.targets] == [
        (1, 0.25),
        (2, 0.75),
    ]
    assert [(target.planned_weight, target.u16_weight) for target in report.targets] == [
        (0.25, 21_845),
        (0.75, 65_535),
    ]
    assert report.max_weights_limit == 65_535
    assert report.weights_were_clipped is False
    assert report.current_readback.weights == ((1, 0.25), (2, 0.75))
    assert report.current_readback.last_update == 12_000
    assert report.current_readback.weight_setting_authorized is True
    assert report.gates.minimum_recipients_met is True
    assert report.ready_for_authorized_submission is True
    assert report.plan_digest is not None
    assert report.plan_digest.startswith("sha256:")
    assert client.closed is True


def test_plan_precomputes_sdk_max_weight_clipping_and_u16_readback() -> None:
    class ClippedSnapshot(FakeSnapshot):
        def read(self, name: str, **params: object) -> object:
            value = super().read(name, **params)
            if name == "subnet_hyperparameters":
                return {**value, "max_weights_limit": 40_000}  # type: ignore[arg-type]
            return value

    class ClippedClient(FakeClient):
        def at(self, block: int) -> ClippedSnapshot:
            assert block == self.block
            return ClippedSnapshot()

    report = collect_testnet_weight_plan(
        netuid=7,
        validator_hotkey_ss58=VALIDATOR,
        score_specs=score_specs(),
        client_factory=ClippedClient,
    )

    assert report.weights_were_clipped is True
    assert report.gates.maximum_weight_limit_met is True
    assert [target.planned_weight for target in report.targets] == [0.25, 0.75]
    assert [target.u16_weight for target in report.targets] == [41_836, 65_535]
    assert report.targets[1].weight == pytest.approx(40_000 / 65_535, abs=2 / 65_535)
    assert report.ready_for_authorized_submission is True


def test_subnet_owner_is_authorized_without_validator_permit() -> None:
    class OwnerSnapshot(FakeSnapshot):
        def read(self, name: str, **params: object) -> object:
            value = super().read(name, **params)
            if name == "metagraph":
                return {
                    **value,  # type: ignore[arg-type]
                    "owner_hotkey": VALIDATOR,
                    "validator_permit": [False, False, False],
                }
            return value

    class OwnerClient(FakeClient):
        def at(self, block: int) -> OwnerSnapshot:
            assert block == self.block
            return OwnerSnapshot()

    report = collect_testnet_weight_plan(
        netuid=7,
        validator_hotkey_ss58=VALIDATOR,
        score_specs=score_specs(),
        client_factory=OwnerClient,
    )

    assert report.current_readback.validator_permit is False
    assert report.current_readback.validator_is_subnet_owner is True
    assert report.current_readback.weight_setting_authorized is True
    assert report.gates.validator_authorized is True
    assert report.ready_for_authorized_submission is True


@pytest.mark.parametrize(
    "weights,raw_limit",
    [
        ([0.25, 0.75], 40_000),
        ([0.01, 0.19, 0.8], 30_000),
        ([1.0, 2.0, 3.0, 4.0], 65_535),
    ],
)
def test_conformed_vector_matches_pinned_sdk(weights: list[float], raw_limit: int) -> None:
    limit = raw_limit / 65_535
    conformed = (
        clip_to_max_weight(weights, limit)
        if raw_limit < 65_535
        else [weight / sum(weights) for weight in weights]
    )
    expected_uids, expected_u16 = normalize(list(range(len(weights))), conformed)
    actual, _ = _conform_weight_vector(weights, raw_limit)

    assert [index for index, _, _ in actual] == expected_uids
    assert [value for _, _, value in actual] == expected_u16


def test_digest_is_deterministic_across_score_input_order() -> None:
    first = collect_testnet_weight_plan(
        netuid=7,
        validator_hotkey_ss58=VALIDATOR,
        score_specs=score_specs(),
        client_factory=FakeClient,
    )
    second = collect_testnet_weight_plan(
        netuid=7,
        validator_hotkey_ss58=VALIDATOR,
        score_specs=tuple(reversed(score_specs())),
        client_factory=FakeClient,
    )
    assert first.plan_digest == second.plan_digest


def test_unexpected_endpoint_and_connection_failure_fail_closed() -> None:
    unexpected = collect_testnet_weight_plan(
        netuid=7,
        validator_hotkey_ss58=VALIDATOR,
        score_specs=score_specs(),
        client_factory=lambda: FakeClient(endpoint="wss://unexpected.invalid"),
    )
    assert unexpected.ready_for_authorized_submission is False
    assert unexpected.plan_digest is None
    assert unexpected.errors == ("SDK resolved an unexpected endpoint; planning is denied",)

    def fail() -> FakeClient:
        raise ConnectionError("credential-like transport details")

    failed = collect_testnet_weight_plan(
        netuid=7,
        validator_hotkey_ss58=VALIDATOR,
        score_specs=score_specs(),
        client_factory=fail,
    )
    assert failed.errors == ("read-only planning failed: ConnectionError",)
    assert "credential-like" not in failed.model_dump_json()


def test_missing_target_or_insufficient_positive_scores_are_not_ready() -> None:
    missing = collect_testnet_weight_plan(
        netuid=7,
        validator_hotkey_ss58=VALIDATOR,
        score_specs=(f"{MINER_A}=1", f"{'5' + 'E' * 47}=1"),
        client_factory=FakeClient,
    )
    assert missing.targets == ()
    assert missing.gates.all_targets_registered is False
    assert missing.ready_for_authorized_submission is False

    insufficient = collect_testnet_weight_plan(
        netuid=7,
        validator_hotkey_ss58=VALIDATOR,
        score_specs=(f"{MINER_A}=1", f"{MINER_B}=0"),
        client_factory=FakeClient,
    )
    assert insufficient.targets == ()
    assert insufficient.ready_for_authorized_submission is False


def test_rate_limit_and_invalid_max_limit_fail_closed() -> None:
    class RateLimitedSnapshot(FakeSnapshot):
        def read(self, name: str, **params: object) -> object:
            value = super().read(name, **params)
            if name == "metagraph":
                return {**value, "last_update": [12_300, 0, 0]}  # type: ignore[arg-type]
            return value

    class RateLimitedClient(FakeClient):
        def at(self, block: int) -> RateLimitedSnapshot:
            assert block == self.block
            return RateLimitedSnapshot()

    limited = collect_testnet_weight_plan(
        netuid=7,
        validator_hotkey_ss58=VALIDATOR,
        score_specs=score_specs(),
        client_factory=RateLimitedClient,
    )
    assert limited.gates.rate_limit_elapsed is False
    assert limited.ready_for_authorized_submission is False
    assert "rate limit" in limited.next_action

    class InvalidLimitSnapshot(FakeSnapshot):
        def read(self, name: str, **params: object) -> object:
            value = super().read(name, **params)
            if name == "subnet_hyperparameters":
                return {**value, "max_weights_limit": 0}  # type: ignore[arg-type]
            return value

    class InvalidLimitClient(FakeClient):
        def at(self, block: int) -> InvalidLimitSnapshot:
            assert block == self.block
            return InvalidLimitSnapshot()

    invalid = collect_testnet_weight_plan(
        netuid=7,
        validator_hotkey_ss58=VALIDATOR,
        score_specs=score_specs(),
        client_factory=InvalidLimitClient,
    )
    assert invalid.ready_for_authorized_submission is False
    assert invalid.errors == ("read-only planning failed: ValueError",)


def test_validator_cannot_be_scored_as_a_miner() -> None:
    with pytest.raises(ValueError, match="validator hotkey"):
        collect_testnet_weight_plan(
            netuid=7,
            validator_hotkey_ss58=VALIDATOR,
            score_specs=(f"{VALIDATOR}=1", f"{MINER_A}=1"),
            client_factory=FakeClient,
        )


@pytest.mark.parametrize("netuid", [-1, 65_536])
def test_weight_plan_rejects_out_of_range_netuid_before_connecting(netuid: int) -> None:
    called = False

    def factory() -> FakeClient:
        nonlocal called
        called = True
        return FakeClient()

    with pytest.raises(ValueError, match="between 0 and 65535"):
        collect_testnet_weight_plan(
            netuid=netuid,
            validator_hotkey_ss58=VALIDATOR,
            score_specs=score_specs(),
            client_factory=factory,
        )
    assert called is False


@pytest.mark.parametrize(
    "values, message",
    [
        (("missing-separator",), "SS58=VALUE"),
        ((f"{MINER_A}=nan",), "finite"),
        ((f"{MINER_A}=-1",), "non-negative"),
        ((f"{MINER_A}=1e308", f"{MINER_B}=1e308"), "total must be finite"),
        ((f"{MINER_A}=1", f"{MINER_A}=2"), "duplicate"),
    ],
)
def test_score_parser_rejects_invalid_input(values: tuple[str, ...], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_public_scores(values)


def test_cli_outputs_json_without_requesting_signing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = collect_testnet_weight_plan(
        netuid=7,
        validator_hotkey_ss58=VALIDATOR,
        score_specs=score_specs(),
        client_factory=FakeClient,
    )

    def fake_collect(**_: Any) -> WeightPlanReport:
        return expected

    monkeypatch.setattr(cli, "collect_testnet_weight_plan", fake_collect)
    result = CliRunner().invoke(
        app,
        [
            "testnet",
            "weight-plan",
            "--netuid",
            "7",
            "--validator-hotkey-ss58",
            VALIDATOR,
            "--score",
            f"{MINER_A}=1",
            "--score",
            f"{MINER_B}=3",
        ],
    )

    assert result.exit_code == 0
    assert '"transaction_constructed": false' in result.stdout
    assert '"signature_requested": false' in result.stdout


def test_saved_plan_loads_and_later_matching_readback_passes(tmp_path: Path) -> None:
    source = weight_plan()
    path = tmp_path / "weight-plan.json"
    path.write_text(source.model_dump_json(indent=2) + "\n")

    loaded = load_testnet_weight_plan(path)
    client = FakePostClient()
    report = verify_testnet_weight_readback(
        loaded,
        client_factory=lambda: client,
    )

    assert report.source_plan_digest == source.plan_digest
    assert report.schema_version == "planrace/testnet-weight-readback/3"
    assert report.block == 12_400
    assert report.current_readback.last_update == 12_350
    assert all(comparison.matches for comparison in report.comparisons)
    assert all(report.gates.model_dump().values())
    assert report.ready_for_testnet_evidence is True
    assert report.transaction_constructed is False
    assert report.signature_requested is False
    assert client.closed is True


def test_tampered_saved_plan_is_rejected_before_chain_access(tmp_path: Path) -> None:
    data = weight_plan().model_dump(mode="json")
    data["targets"][0]["weight"] = 0.5
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(data))

    with pytest.raises(ValueError, match="digest mismatch"):
        load_testnet_weight_plan(path)

    data = weight_plan().model_dump(mode="json")
    data["commit_reveal_weights_enabled"] = False
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="digest mismatch"):
        load_testnet_weight_plan(path)


@pytest.mark.parametrize(
    "snapshot, failed_gate",
    [
        (FakePostSnapshot(last_update=12_345), "last_update_advanced"),
        (
            FakePostSnapshot(hotkeys=[VALIDATOR, MINER_B, MINER_A]),
            "target_uids_stable",
        ),
        (FakePostSnapshot(row={1: 0.5, 2: 0.5}), "weight_values_match"),
        (FakePostSnapshot(row={1: 0.25, 2: 0.7, 3: 0.05}), "recipient_set_matches"),
    ],
)
def test_readback_fails_closed_on_stale_or_mismatched_state(
    snapshot: FakePostSnapshot,
    failed_gate: str,
) -> None:
    report = verify_testnet_weight_readback(
        weight_plan(),
        client_factory=lambda: FakePostClient(snapshot=snapshot),
    )

    assert report.ready_for_testnet_evidence is False
    assert report.gates.model_dump()[failed_gate] is False


def test_readback_transport_failure_is_sanitized() -> None:
    def fail() -> FakePostClient:
        raise ConnectionError("credential-like transport details")

    report = verify_testnet_weight_readback(weight_plan(), client_factory=fail)

    assert report.errors == ("read-only verification failed: ConnectionError",)
    assert "credential-like" not in report.model_dump_json()


def test_readback_cli_emits_json_and_fails_when_gates_do_not_pass(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = weight_plan()
    path = tmp_path / "weight-plan.json"
    path.write_text(source.model_dump_json())
    failed = verify_testnet_weight_readback(
        source,
        client_factory=lambda: FakePostClient(
            snapshot=FakePostSnapshot(last_update=source.block or 0)
        ),
    )

    def fake_verify(_: WeightPlanReport) -> ReadbackReport:
        return failed

    monkeypatch.setattr(cli, "verify_testnet_weight_readback", fake_verify)
    result = CliRunner().invoke(app, ["testnet", "weight-readback", str(path)])

    assert result.exit_code == 1
    assert '"ready_for_testnet_evidence": false' in result.stdout
    assert '"signature_requested": false' in result.stdout


class FakePublicKey:
    ss58_address = VALIDATOR


class FakeSigningWallet:
    hotkeypub = FakePublicKey()


class FakeFee:
    tao = 0.000123


class FakeExtrinsicResult:
    success = True
    block_hash = "0x" + "3" * 64
    extrinsic_id = "12351-0002"
    explorer_url = "https://example.invalid/extrinsic/12351-0002"
    fee = FakeFee()
    data: ClassVar[dict[str, Any]] = {"reveal_round": 998877}


def fresh_weight_plan(source: WeightPlanReport, *, age: int = 5) -> WeightPlanReport:
    assert source.block is not None
    return source.model_copy(
        update={
            "block": source.block + age,
            "block_hash": "0x" + "2" * 64,
        }
    )


def test_digest_authorized_submission_rechecks_state_and_emits_receipt() -> None:
    source = weight_plan()
    calls: list[dict[str, object]] = []

    def collect(**_: object) -> WeightPlanReport:
        return fresh_weight_plan(source)

    def wallet_factory(wallet_alias: str, hotkey_alias: str) -> FakeSigningWallet:
        assert (wallet_alias, hotkey_alias) == ("planrace-testnet", "validator-00")
        return FakeSigningWallet()

    def submitter(**kwargs: object) -> FakeExtrinsicResult:
        calls.append(kwargs)
        return FakeExtrinsicResult()

    receipt = submit_testnet_weight_plan(
        source,
        authorize_plan_digest=source.plan_digest or "",
        hotkey_alias="validator-00",
        plan_collector=collect,
        wallet_factory=wallet_factory,
        submitter=submitter,
        clock=lambda: datetime(2026, 9, 6, 12, tzinfo=UTC),
    )

    assert receipt.schema_version == "planrace/testnet-weight-submission/1"
    assert receipt.network == "test"
    assert receipt.endpoint == TESTNET_ENDPOINT
    assert receipt.signature_requested is True
    assert receipt.sdk_reported_success is True
    assert receipt.extrinsic_id == "12351-0002"
    assert receipt.reveal_round == 998877
    assert receipt.requires_delayed_readback is True
    assert receipt.evidence_complete is False
    assert receipt.fee_tao == "0.000123"
    assert calls == [
        {
            "netuid": 7,
            "weights": {1: 21_845, 2: 65_535},
            "wallet": calls[0]["wallet"],
        }
    ]


def test_submission_rejects_wrong_digest_before_wallet_or_network_access() -> None:
    source = weight_plan()
    called = False

    def wallet_factory(_: str, __: str) -> FakeSigningWallet:
        nonlocal called
        called = True
        return FakeSigningWallet()

    with pytest.raises(ValueError, match="authorized digest"):
        submit_testnet_weight_plan(
            source,
            authorize_plan_digest="sha256:" + "0" * 64,
            hotkey_alias="validator-00",
            wallet_factory=wallet_factory,
        )
    assert called is False


@pytest.mark.parametrize(
    "wallet_alias,hotkey_alias,message",
    [
        ("mainnet-wallet", "validator-00", "wallet alias"),
        ("planrace-testnet", "default", "hotkey alias"),
    ],
)
def test_submission_rejects_non_dedicated_wallet_names(
    wallet_alias: str, hotkey_alias: str, message: str
) -> None:
    source = weight_plan()
    with pytest.raises(ValueError, match=message):
        submit_testnet_weight_plan(
            source,
            authorize_plan_digest=source.plan_digest or "",
            wallet_alias=wallet_alias,
            hotkey_alias=hotkey_alias,
        )


def test_submission_rejects_signer_mismatch_and_stale_plan_before_signing() -> None:
    source = weight_plan()

    class WrongPublicKey:
        ss58_address = MINER_A

    class WrongWallet:
        hotkeypub = WrongPublicKey()

    with pytest.raises(ValueError, match="does not match"):
        submit_testnet_weight_plan(
            source,
            authorize_plan_digest=source.plan_digest or "",
            hotkey_alias="validator-00",
            wallet_factory=lambda *_: WrongWallet(),  # type: ignore[arg-type,return-value]
        )

    submitted = False

    def submitter(**_: object) -> FakeExtrinsicResult:
        nonlocal submitted
        submitted = True
        return FakeExtrinsicResult()

    with pytest.raises(ValueError, match="stale"):
        submit_testnet_weight_plan(
            source,
            authorize_plan_digest=source.plan_digest or "",
            hotkey_alias="validator-00",
            wallet_factory=lambda *_: FakeSigningWallet(),
            plan_collector=lambda **_: fresh_weight_plan(source, age=13),
            submitter=submitter,
        )
    assert submitted is False


def test_submission_rejects_changed_chain_state_before_signing() -> None:
    source = weight_plan()
    changed = fresh_weight_plan(source).model_copy(
        update={"commit_reveal_period": (source.commit_reveal_period or 0) + 1}
    )

    with pytest.raises(ValueError, match="state changed"):
        submit_testnet_weight_plan(
            source,
            authorize_plan_digest=source.plan_digest or "",
            hotkey_alias="validator-00",
            wallet_factory=lambda *_: FakeSigningWallet(),
            plan_collector=lambda **_: changed,
        )


def test_weight_submit_cli_outputs_receipt_without_error_details(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = weight_plan()
    path = tmp_path / "weight-plan.json"
    path.write_text(source.model_dump_json())
    expected = SubmissionReceipt(
        sdk_version="11.1.0",
        source_plan_digest=source.plan_digest or "",
        source_block=source.block or 0,
        pre_submit_block=(source.block or 0) + 1,
        pre_submit_block_hash="0x" + "2" * 64,
        runtime_spec_version=454,
        netuid=7,
        validator_hotkey_ss58=VALIDATOR,
        wallet_alias="planrace-testnet",
        hotkey_alias="validator-00",
        submitted_targets=(),
        sdk_reported_success=True,
        including_block_hash="0x" + "3" * 64,
        extrinsic_id="12351-0002",
        explorer_url=None,
        fee_tao=None,
        reveal_round=None,
        submitted_at="2026-09-06T12:00:00+00:00",
        requires_delayed_readback=False,
        next_action="Verify readback.",
    )

    monkeypatch.setattr(cli, "submit_testnet_weight_plan", lambda *_, **__: expected)
    result = CliRunner().invoke(
        app,
        [
            "testnet",
            "weight-submit",
            str(path),
            "--authorize-plan-digest",
            source.plan_digest or "",
            "--hotkey-alias",
            "validator-00",
        ],
    )

    assert result.exit_code == 0
    assert '"network": "test"' in result.stdout
    assert '"signature_requested": true' in result.stdout
    assert '"evidence_complete": false' in result.stdout
