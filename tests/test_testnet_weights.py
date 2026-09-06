from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner

from planrace import cli
from planrace.cli import app
from planrace.testnet_preflight import TESTNET_ENDPOINT
from planrace.testnet_weights import TestnetWeightPlanReport as WeightPlanReport
from planrace.testnet_weights import collect_testnet_weight_plan, parse_public_scores

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

    def read(self, name: str, **params: object) -> object:
        assert params["netuid"] == 7
        if name == "subnet":
            return {"netuid": 7}
        if name == "subnet_hyperparameters":
            return {
                "min_allowed_weights": 2,
                "weights_rate_limit": 100,
                "commit_reveal_weights_enabled": True,
                "commit_reveal_period": 1_000,
            }
        if name == "metagraph":
            return {
                "hotkeys": [VALIDATOR, MINER_A, MINER_B],
                "validator_permit": [True, False, False],
                "last_update": [12_300, 0, 0],
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


def score_specs() -> tuple[str, ...]:
    return (f"{MINER_A}=1", f"{MINER_B}=3")


def test_plan_resolves_public_hotkeys_and_reads_existing_weights() -> None:
    client = FakeClient()
    report = collect_testnet_weight_plan(
        netuid=7,
        validator_hotkey_ss58=VALIDATOR,
        score_specs=score_specs(),
        client_factory=lambda: client,
    )

    assert report.read_only is True
    assert report.transaction_constructed is False
    assert report.signature_requested is False
    assert report.block_hash == FakeBlockInfo.hash
    assert [(target.uid, target.weight) for target in report.targets] == [
        (1, 0.25),
        (2, 0.75),
    ]
    assert report.current_readback.weights == ((1, 0.25), (2, 0.75))
    assert report.current_readback.last_update == 12_300
    assert report.gates.minimum_recipients_met is True
    assert report.ready_for_authorized_submission is True
    assert report.plan_digest is not None
    assert report.plan_digest.startswith("sha256:")
    assert client.closed is True


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


def test_validator_cannot_be_scored_as_a_miner() -> None:
    with pytest.raises(ValueError, match="validator hotkey"):
        collect_testnet_weight_plan(
            netuid=7,
            validator_hotkey_ss58=VALIDATOR,
            score_specs=(f"{VALIDATOR}=1", f"{MINER_A}=1"),
            client_factory=FakeClient,
        )


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
