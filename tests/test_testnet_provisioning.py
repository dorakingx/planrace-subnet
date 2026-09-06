from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from planrace import cli
from planrace.cli import app
from planrace.testnet_preflight import TESTNET_ENDPOINT
from planrace.testnet_provisioning import (
    MAX_TESTNET_BUDGET_RAO,
    collect_testnet_provision_plan,
    load_public_identities,
)
from planrace.testnet_provisioning import TestnetProvisionPlan as ProvisionPlan

IDENTITIES = Path("results/testnet/identities.public.json")
PUBLIC_TEST_COLDKEY = (
    "5Ehsb7JthQxuaXwgLJrzGksA6CSHDxC39QotGKaBMHGkfftJ"  # pragma: allowlist secret -- public SS58
)
PUBLIC_TEST_OWNER = (
    "5HH5toXTBj2Fdu7LNrZ7fbaFkT22xK2hc3ExCLu15pp6fznC"  # pragma: allowlist secret -- public SS58
)


class FakeAmount:
    def __init__(self, rao: int) -> None:
        self.rao = rao


class FakeBlockInfo:
    number = 12_345
    hash = "0x" + "1" * 64


class FakeSnapshot:
    block = 12_345

    def __init__(
        self,
        *,
        balance_rao: int = 0,
        cost_rao: int = 1_000_000_000,
        owned_hotkeys: tuple[str, ...] = (),
        registered_netuids: tuple[int, ...] = (),
    ) -> None:
        self.balance_rao = balance_rao
        self.cost_rao = cost_rao
        self.owned_hotkeys = owned_hotkeys
        self.registered_netuids = registered_netuids

    def block_info(self) -> FakeBlockInfo:
        return FakeBlockInfo()

    def read(self, name: str, **params: object) -> object:
        if name == "balance":
            assert params == {"coldkey_ss58": PUBLIC_TEST_COLDKEY}
            return FakeAmount(self.balance_rao)
        if name == "subnet_registration_cost":
            assert params == {}
            return FakeAmount(self.cost_rao)
        if name == "existential_deposit":
            assert params == {}
            return FakeAmount(500)
        if name == "owned_hotkeys":
            assert params == {"coldkey_ss58": PUBLIC_TEST_COLDKEY}
            return list(self.owned_hotkeys)
        if name == "netuids_for_hotkey":
            assert tuple(params) == ("hotkey_ss58",)
            return list(self.registered_netuids)
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


def test_zero_balance_plan_binds_costs_and_all_public_roles() -> None:
    client = FakeClient()
    report = collect_testnet_provision_plan(IDENTITIES, client_factory=lambda: client)

    assert report.schema_version == "planrace/testnet-provision-plan/1"
    assert report.read_only is True
    assert report.transaction_constructed is False
    assert report.signature_requested is False
    assert report.block_hash == FakeBlockInfo.hash
    assert report.subnet_creation_cost_tao == "1"
    assert report.existential_deposit_tao == "0.0000005"
    assert report.coldkey_balance_tao == "0"
    assert len(report.roles) == 13
    assert report.roles[0].alias == "validator-00"
    assert report.roles[0].registered_netuids == ()
    assert report.roles[0].created_with_subnet is True
    assert report.roles[0].requires_burn_registration is False
    assert report.burn_registrations_after_creation == 12
    assert report.gates.coldkey_has_no_owned_hotkeys is True
    assert report.gates.all_hotkeys_unregistered is True
    assert report.gates.coldkey_balance_positive is False
    assert report.ready_for_authorized_subnet_creation is False
    assert report.plan_digest is not None and report.plan_digest.startswith("sha256:")
    assert client.closed is True


def test_funded_plan_passes_every_gate_with_bounded_budget() -> None:
    report = collect_testnet_provision_plan(
        IDENTITIES,
        client_factory=lambda: FakeClient(snapshot=FakeSnapshot(balance_rao=5_000_000_000)),
    )

    assert all(report.gates.model_dump().values())
    assert report.ready_for_authorized_subnet_creation is True
    assert report.next_action.startswith("Review this plan")


def test_overfunded_or_over_cap_plan_fails_closed() -> None:
    overfunded = collect_testnet_provision_plan(
        IDENTITIES,
        client_factory=lambda: FakeClient(
            snapshot=FakeSnapshot(balance_rao=MAX_TESTNET_BUDGET_RAO + 1)
        ),
    )
    assert overfunded.gates.balance_within_total_budget is False
    assert overfunded.ready_for_authorized_subnet_creation is False
    assert "exceeds the approved" in overfunded.next_action

    expensive = collect_testnet_provision_plan(
        IDENTITIES,
        client_factory=lambda: FakeClient(
            snapshot=FakeSnapshot(balance_rao=5_000_000_000, cost_rao=1_250_000_001)
        ),
    )
    assert expensive.gates.subnet_cost_within_cap is False
    assert expensive.ready_for_authorized_subnet_creation is False
    assert "operation cap" in expensive.next_action


def test_existing_registration_denies_duplicate_creation() -> None:
    report = collect_testnet_provision_plan(
        IDENTITIES,
        client_factory=lambda: FakeClient(
            snapshot=FakeSnapshot(
                balance_rao=5_000_000_000,
                owned_hotkeys=(PUBLIC_TEST_OWNER,),
                registered_netuids=(321,),
            )
        ),
    )

    assert report.coldkey_owned_hotkeys == (PUBLIC_TEST_OWNER,)
    assert report.roles[0].registered_netuids == (321,)
    assert report.gates.coldkey_has_no_owned_hotkeys is False
    assert report.gates.all_hotkeys_unregistered is False
    assert report.ready_for_authorized_subnet_creation is False
    assert "do not create again" in report.next_action


def test_identity_manifest_rejects_extra_or_changed_security_fields(tmp_path: Path) -> None:
    data = json.loads(IDENTITIES.read_text())
    data["private_seed"] = "must never be accepted"
    path = tmp_path / "extra.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="schema validation"):
        load_public_identities(path)

    data = json.loads(IDENTITIES.read_text())
    data["security"]["mainnet_authorized"] = True
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="custody boundary"):
        load_public_identities(path)


def test_transport_failure_is_sanitized_and_client_is_closed() -> None:
    client = FakeClient(endpoint="wss://unexpected.invalid")
    unexpected = collect_testnet_provision_plan(IDENTITIES, client_factory=lambda: client)
    assert unexpected.ready_for_authorized_subnet_creation is False
    assert unexpected.errors == ("SDK resolved an unexpected endpoint; provisioning is denied",)
    assert client.closed is True

    def fail() -> FakeClient:
        raise ConnectionError("credential-like transport details")

    failed = collect_testnet_provision_plan(IDENTITIES, client_factory=fail)
    assert failed.errors == ("read-only provisioning plan failed: ConnectionError",)
    assert "credential-like" not in failed.model_dump_json()


def test_cli_emits_json_and_nonzero_until_funded(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = collect_testnet_provision_plan(IDENTITIES, client_factory=FakeClient)

    def fake_collect(_: Path) -> ProvisionPlan:
        return expected

    monkeypatch.setattr(cli, "collect_testnet_provision_plan", fake_collect)
    result = CliRunner().invoke(app, ["testnet", "provision-plan"])

    assert result.exit_code == 1
    assert '"schema_version": "planrace/testnet-provision-plan/1"' in result.stdout
    assert '"transaction_constructed": false' in result.stdout
    assert '"signature_requested": false' in result.stdout
