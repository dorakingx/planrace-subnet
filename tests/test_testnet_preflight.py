from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner

from planrace import cli
from planrace.cli import app
from planrace.testnet_preflight import (
    TESTNET_ENDPOINT,
    collect_testnet_preflight,
    parse_public_roles,
    validate_public_ss58,
)
from planrace.testnet_preflight import TestnetPreflightReport as PreflightReport

COLDKEY = "5" + "A" * 47
VALIDATOR = "5" + "B" * 47
MINER_A = "5" + "C" * 47
MINER_B = "5" + "D" * 47


class FakeBalance:
    rao = 2_500_000_000


class FakeSubnet:
    neuron_count = 3
    tempo = 99


class FakeSnapshot:
    block = 12_345

    def __init__(self, *, lookup_error: bool = False) -> None:
        self.lookup_error = lookup_error

    def read(self, name: str, **params: object) -> object:
        if self.lookup_error and name == "subnet":
            raise RuntimeError("secret transport details must not escape")
        if name == "subnet":
            return FakeSubnet() if params["netuid"] == 7 else None
        if name == "subnet_hyperparameters":
            return {
                "registration_allowed": True,
                "subnet_is_active": True,
                "max_uids": 256,
                "min_allowed_weights": 2,
                "max_weights_limit": 65_535,
                "weights_rate_limit": 100,
                "commit_reveal_weights_enabled": True,
                "commit_reveal_period": 1_000,
            }
        if name == "balance":
            return FakeBalance()
        if name == "metagraph":
            return {
                "hotkeys": [VALIDATOR, MINER_A, MINER_B],
                "coldkeys": [COLDKEY, COLDKEY, COLDKEY],
                "axons": [
                    {"ip": "203.0.113.10", "port": 8091, "ip_type": 4},
                    {"ip": "203.0.113.11", "port": 8092, "ip_type": 4},
                    {"ip": "2001:db8::12", "port": 8093, "ip_type": 6},
                ],
                "validator_permit": [True, False, False],
                "last_update": [12_340, 12_341, 12_342],
            }
        raise AssertionError(f"unexpected read {name}")


class FakeClient:
    block = 12_345
    spec_version = 454

    def __init__(
        self,
        *,
        endpoint: str = TESTNET_ENDPOINT,
        snapshot: FakeSnapshot | None = None,
    ) -> None:
        self.endpoint = endpoint
        self.snapshot = snapshot or FakeSnapshot()
        self.closed = False

    def at(self, block: int) -> FakeSnapshot:
        assert block == self.block
        return self.snapshot

    def close(self) -> None:
        self.closed = True


def role_specs() -> tuple[str, ...]:
    return (
        f"validator={VALIDATOR}",
        f"miner-a={MINER_A}",
        f"miner-b={MINER_B}",
    )


def test_complete_public_snapshot_passes_both_readiness_phases() -> None:
    client = FakeClient()

    report = collect_testnet_preflight(
        netuid=7,
        coldkey_ss58=COLDKEY,
        role_specs=role_specs(),
        require_registered=True,
        require_served_axon=True,
        client_factory=lambda: client,
    )

    assert report.chain_reachable is True
    assert report.block == 12_345
    assert report.runtime_spec_version == 454
    assert report.subnet is not None
    assert report.subnet.commit_reveal_weights_enabled is True
    assert report.coldkey is not None
    assert report.coldkey.balance_rao == 2_500_000_000
    assert report.coldkey.balance_tao == "2.5"
    assert all(item.registered and item.coldkey_matches for item in report.roles)
    assert report.roles[0].blocks_since_last_update == 5
    assert report.roles[2].axon is not None
    assert report.roles[2].axon.ip_type == 6
    assert report.gates.registration_requirement_met is True
    assert report.gates.served_axon_requirement_met is True
    assert report.ready_for_registration is True
    assert report.ready_for_protocol_run is True
    assert client.closed is True


def test_chain_only_snapshot_is_reachable_but_not_ready() -> None:
    report = collect_testnet_preflight(client_factory=FakeClient)

    assert report.chain_reachable is True
    assert report.subnet is None
    assert report.roles == ()
    assert report.ready_for_registration is False
    assert report.ready_for_protocol_run is False
    assert report.errors == ()
    assert "Provide public netuid" in report.next_action


def test_absent_subnet_fails_closed() -> None:
    report = collect_testnet_preflight(
        netuid=999,
        coldkey_ss58=COLDKEY,
        role_specs=role_specs(),
        client_factory=FakeClient,
    )

    assert report.subnet is not None and report.subnet.exists is False
    assert report.roles == ()
    assert report.ready_for_registration is False
    assert "existing testnet subnet" in report.next_action


def test_unexpected_endpoint_is_reported_and_denies_readiness() -> None:
    client = FakeClient(endpoint="wss://unexpected.invalid")
    report = collect_testnet_preflight(
        netuid=7,
        coldkey_ss58=COLDKEY,
        role_specs=role_specs(),
        client_factory=lambda: client,
    )

    assert report.chain_reachable is True
    assert report.gates.canonical_endpoint is False
    assert report.ready_for_registration is False
    assert report.errors == ("SDK resolved an unexpected endpoint; further readiness is denied",)
    assert report.next_action.startswith("Stop")
    assert client.closed is True


def test_chain_failures_are_bounded_by_exception_type() -> None:
    def fail() -> FakeClient:
        raise ConnectionError("credential-like transport text")

    report = collect_testnet_preflight(client_factory=fail)

    assert report.chain_reachable is False
    assert report.errors == ("connection failed: ConnectionError",)
    assert "credential-like" not in report.model_dump_json()


def test_lookup_failures_are_bounded_and_client_is_closed() -> None:
    client = FakeClient(snapshot=FakeSnapshot(lookup_error=True))
    report = collect_testnet_preflight(netuid=7, client_factory=lambda: client)

    assert report.chain_reachable is True
    assert report.subnet is not None and report.subnet.exists is False
    assert report.errors == ("subnet lookup failed: RuntimeError",)
    assert "secret transport" not in report.model_dump_json()
    assert client.closed is True


@pytest.mark.parametrize(
    "value, message",
    [
        ("validator", "role=SS58"),
        (f"Validator={VALIDATOR}", "invalid role"),
        ("validator=not-an-address", "48-character"),
    ],
)
def test_role_parser_rejects_invalid_public_inputs(value: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_public_roles((value,))


def test_role_parser_rejects_duplicate_roles_and_addresses() -> None:
    with pytest.raises(ValueError, match="duplicate role"):
        parse_public_roles((f"validator={VALIDATOR}", f"validator={MINER_A}"))
    with pytest.raises(ValueError, match="multiple roles"):
        parse_public_roles((f"validator={VALIDATOR}", f"miner-a={VALIDATOR}"))


def test_public_address_validator_rejects_non_base58_characters() -> None:
    with pytest.raises(ValueError, match="48-character"):
        validate_public_ss58("5" + "0" * 47)


def test_negative_netuid_is_rejected_before_connecting() -> None:
    called = False

    def factory() -> FakeClient:
        nonlocal called
        called = True
        return FakeClient()

    with pytest.raises(ValueError, match="non-negative"):
        collect_testnet_preflight(netuid=-1, client_factory=factory)
    assert called is False


def test_cli_emits_json_and_nonzero_on_validation_error() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["testnet", "preflight", "--hotkey", "validator"])

    assert result.exit_code == 2
    assert result.stdout.startswith('{"error":')


def test_cli_emits_report_from_read_only_collector(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = collect_testnet_preflight(client_factory=FakeClient)

    def fake_collect(**_: Any) -> PreflightReport:
        return expected

    monkeypatch.setattr(cli, "collect_testnet_preflight", fake_collect)
    result = CliRunner().invoke(app, ["testnet", "preflight"])

    assert result.exit_code == 0
    assert '"schema_version": "planrace/testnet-preflight/1"' in result.stdout
    assert '"read_only": true' in result.stdout


def test_cli_strict_requirement_returns_nonzero_when_unmet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = collect_testnet_preflight(
        require_registered=True,
        client_factory=FakeClient,
    )

    def fake_collect(**_: Any) -> PreflightReport:
        return expected

    monkeypatch.setattr(cli, "collect_testnet_preflight", fake_collect)
    result = CliRunner().invoke(
        app,
        ["testnet", "preflight", "--require-registered"],
    )

    assert result.exit_code == 1
    assert '"registration_requirement_met": false' in result.stdout
