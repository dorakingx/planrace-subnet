from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
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
    load_testnet_provision_plan,
)
from planrace.testnet_provisioning import TestnetProvisionPlan as ProvisionPlan
from planrace.testnet_provisioning_readback import verify_testnet_provision_readback
from planrace.testnet_provisioning_submission import (
    TestnetProvisionSubmissionReceipt as ProvisionReceipt,
)
from planrace.testnet_provisioning_submission import (
    _default_submitter,
    load_testnet_provision_receipt,
    submit_testnet_provision_plan,
)

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


class FakePublicKey:
    def __init__(self, address: str) -> None:
        self.ss58_address = address


class FakeWallet:
    def __init__(self, coldkey: str = PUBLIC_TEST_COLDKEY, hotkey: str = PUBLIC_TEST_OWNER) -> None:
        self.coldkeypub = FakePublicKey(coldkey)
        self.hotkeypub = FakePublicKey(hotkey)


class FakeFee:
    tao = "0.0001"


class FakeExtrinsicResult:
    success = True
    block_hash = "0x" + "2" * 64
    extrinsic_id = "12346-2"
    explorer_url = "https://example.test/extrinsic/12346-2"
    fee = FakeFee()

    def __init__(
        self,
        *,
        price_rao: int = 1_000_000_000,
        netuid: int = 321,
    ) -> None:
        self.data = {
            "netuid": netuid,
            "registration_mode": "immediate",
            "registration_price_rao": price_rao,
        }


class FakeFinalizedHeader:
    number = 12_400


class FakeReadbackInfo:
    number = 12_400
    hash = "0x" + "3" * 64


class FakeReadbackSnapshot:
    def __init__(
        self,
        block: int,
        *,
        wrong_owner: bool = False,
        wrong_call: bool = False,
    ) -> None:
        self.block = block
        self.wrong_owner = wrong_owner
        self.wrong_call = wrong_call

    def block_info(self) -> object:
        if self.block == 12_346:
            extrinsics: list[object] = [{}, {}]
            extrinsics.append(
                {
                    "extrinsic_hash": "0x" + "4" * 64,
                    "call": {
                        "call_module": "SubtensorModule",
                        "call_function": (
                            "burned_register" if self.wrong_call else "register_network"
                        ),
                        "call_args": [
                            {
                                "name": "hotkey",
                                "value": PUBLIC_TEST_OWNER,
                            }
                        ],
                    },
                }
            )
            return type(
                "Included",
                (),
                {
                    "number": 12_346,
                    "hash": "0x" + "2" * 64,
                    "extrinsics": extrinsics,
                },
            )()
        return FakeReadbackInfo()

    def query(self, item: object, params: list[object] | None = None) -> object:
        assert params == [321]
        name = item.name  # type: ignore[attr-defined]
        if name == "NetworksAdded":
            return True
        if name == "SubnetOwner":
            return PUBLIC_TEST_OWNER if self.wrong_owner else PUBLIC_TEST_COLDKEY
        if name == "SubnetOwnerHotkey":
            return PUBLIC_TEST_OWNER
        if name == "SubnetLocked":
            return 1_251_000_000
        if name == "NetworkRegisteredAt":
            return 12_346
        raise AssertionError(f"unexpected storage read {name}")

    def read(self, name: str, **params: object) -> object:
        if name == "metagraph":
            assert params == {"netuid": 321}
            return {
                "hotkeys": [PUBLIC_TEST_OWNER],
                "owner_coldkey": PUBLIC_TEST_OWNER if self.wrong_owner else PUBLIC_TEST_COLDKEY,
                "owner_hotkey": PUBLIC_TEST_OWNER,
            }
        if name == "netuids_for_hotkey":
            assert params == {"hotkey_ss58": PUBLIC_TEST_OWNER}
            return [321]
        if name == "owned_hotkeys":
            assert params == {"coldkey_ss58": PUBLIC_TEST_COLDKEY}
            return [PUBLIC_TEST_OWNER]
        raise AssertionError(f"unexpected read {name}")


class FakeReadbackClient:
    endpoint = TESTNET_ENDPOINT
    spec_version = 454

    def __init__(self, *, wrong_owner: bool = False, wrong_call: bool = False) -> None:
        self.wrong_owner = wrong_owner
        self.wrong_call = wrong_call
        self.closed = False

    def blocks(self, *, finalized: bool = False) -> Iterator[FakeFinalizedHeader]:
        assert finalized is True
        return iter([FakeFinalizedHeader()])

    def at(self, block: int) -> FakeReadbackSnapshot:
        return FakeReadbackSnapshot(
            block,
            wrong_owner=self.wrong_owner,
            wrong_call=self.wrong_call,
        )

    def close(self) -> None:
        self.closed = True


def test_zero_balance_plan_binds_costs_and_all_public_roles() -> None:
    client = FakeClient()
    report = collect_testnet_provision_plan(IDENTITIES, client_factory=lambda: client)

    assert report.schema_version == "planrace/testnet-provision-plan/2"
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
        client_factory=lambda: FakeClient(snapshot=FakeSnapshot(balance_rao=1_260_000_000)),
    )

    assert all(report.gates.model_dump().values())
    assert report.ready_for_authorized_subnet_creation is True
    assert report.next_action.startswith("Review this plan")


def test_staged_cap_covers_review_cost_fee_policy_and_existential_deposit() -> None:
    report = collect_testnet_provision_plan(
        IDENTITIES,
        client_factory=lambda: FakeClient(
            snapshot=FakeSnapshot(
                balance_rao=1_260_001_000,
                cost_rao=1_250_000_000,
            )
        ),
    )

    assert all(report.gates.model_dump().values())
    assert report.max_creation_wallet_balance_rao == 1_260_001_000
    assert report.ready_for_authorized_subnet_creation is True


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

    over_staged_cap = collect_testnet_provision_plan(
        IDENTITIES,
        client_factory=lambda: FakeClient(snapshot=FakeSnapshot(balance_rao=2_000_000_000)),
    )
    assert over_staged_cap.gates.creation_wallet_balance_within_exposure_cap is False
    assert over_staged_cap.ready_for_authorized_subnet_creation is False
    assert "staged creation-wallet" in over_staged_cap.next_action

    expensive = collect_testnet_provision_plan(
        IDENTITIES,
        client_factory=lambda: FakeClient(
            snapshot=FakeSnapshot(balance_rao=1_260_000_000, cost_rao=1_250_000_001)
        ),
    )
    assert expensive.gates.subnet_cost_snapshot_within_review_cap is False
    assert expensive.ready_for_authorized_subnet_creation is False
    assert "review cap" in expensive.next_action


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
    assert '"schema_version": "planrace/testnet-provision-plan/2"' in result.stdout
    assert '"transaction_constructed": false' in result.stdout
    assert '"signature_requested": false' in result.stdout


def _funded_plan() -> ProvisionPlan:
    return collect_testnet_provision_plan(
        IDENTITIES,
        client_factory=lambda: FakeClient(snapshot=FakeSnapshot(balance_rao=1_260_000_000)),
    )


def test_saved_provision_plan_rejects_schema_or_digest_tampering(tmp_path: Path) -> None:
    source = _funded_plan()
    path = tmp_path / "plan.json"
    path.write_text(source.model_dump_json())
    assert load_testnet_provision_plan(path) == source

    tampered = source.model_copy(update={"limitations": (*source.limitations, "tampered")})
    path.write_text(tampered.model_dump_json())
    with pytest.raises(ValueError, match="digest mismatch"):
        load_testnet_provision_plan(path)

    data = source.model_dump(mode="json")
    data["seed"] = "rejected-extra-field"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="schema validation"):
        load_testnet_provision_plan(path)


def test_submission_requires_exact_digest_and_dynamic_cost_acknowledgement() -> None:
    source = _funded_plan()
    assert source.plan_digest is not None

    with pytest.raises(ValueError, match="does not match"):
        submit_testnet_provision_plan(
            source,
            identities_path=IDENTITIES,
            authorize_plan_digest="sha256:" + "0" * 64,
            acknowledge_dynamic_cost=True,
        )


def test_submission_rejects_out_of_range_result_netuid() -> None:
    source = _funded_plan()
    assert source.plan_digest is not None

    with pytest.raises(RuntimeError, match="non-root netuid"):
        submit_testnet_provision_plan(
            source,
            identities_path=IDENTITIES,
            authorize_plan_digest=source.plan_digest,
            acknowledge_dynamic_cost=True,
            plan_collector=lambda _: source,
            wallet_factory=lambda _wallet, _hotkey: FakeWallet(),
            submitter=lambda **_kwargs: FakeExtrinsicResult(netuid=65_536),
        )
    with pytest.raises(ValueError, match="explicitly acknowledge"):
        submit_testnet_provision_plan(
            source,
            identities_path=IDENTITIES,
            authorize_plan_digest=source.plan_digest,
            acknowledge_dynamic_cost=False,
        )


def test_submission_revalidates_keys_state_and_returns_incomplete_receipt() -> None:
    source = _funded_plan()
    assert source.plan_digest is not None
    submit_calls: list[tuple[str, str]] = []

    def submitter(*, wallet: FakeWallet, owner_hotkey_ss58: str) -> FakeExtrinsicResult:
        submit_calls.append((wallet.coldkeypub.ss58_address, owner_hotkey_ss58))
        return FakeExtrinsicResult(price_rao=1_251_000_000)

    receipt = submit_testnet_provision_plan(
        source,
        identities_path=IDENTITIES,
        authorize_plan_digest=source.plan_digest,
        acknowledge_dynamic_cost=True,
        plan_collector=lambda _: source,
        wallet_factory=lambda _wallet, _hotkey: FakeWallet(),
        submitter=submitter,
        clock=lambda: datetime(2026, 9, 6, tzinfo=UTC),
    )

    assert submit_calls == [(PUBLIC_TEST_COLDKEY, PUBLIC_TEST_OWNER)]
    assert receipt.netuid == 321
    assert receipt.actual_registration_price_tao == "1.251"
    assert receipt.snapshot_review_cap_exceeded_at_inclusion is True
    assert receipt.authorized_wallet_balance_snapshot_tao == "1.26"
    assert receipt.dynamic_cost_acknowledged is True
    assert receipt.receipt_digest is not None
    assert receipt.evidence_complete is False
    assert receipt.requires_finalized_readback is True

    with pytest.raises(ValueError, match="coldkey does not match"):
        submit_testnet_provision_plan(
            source,
            identities_path=IDENTITIES,
            authorize_plan_digest=source.plan_digest,
            acknowledge_dynamic_cost=True,
            plan_collector=lambda _: source,
            wallet_factory=lambda _wallet, _hotkey: FakeWallet(coldkey=PUBLIC_TEST_OWNER),
        )

    changed = collect_testnet_provision_plan(
        IDENTITIES,
        client_factory=lambda: FakeClient(snapshot=FakeSnapshot(balance_rao=1_200_000_000)),
    )
    with pytest.raises(ValueError, match="changed after approval"):
        submit_testnet_provision_plan(
            source,
            identities_path=IDENTITIES,
            authorize_plan_digest=source.plan_digest,
            acknowledge_dynamic_cost=True,
            plan_collector=lambda _: changed,
        )


def _successful_receipt() -> ProvisionReceipt:
    source = _funded_plan()
    assert source.plan_digest is not None
    return submit_testnet_provision_plan(
        source,
        identities_path=IDENTITIES,
        authorize_plan_digest=source.plan_digest,
        acknowledge_dynamic_cost=True,
        plan_collector=lambda _: source,
        wallet_factory=lambda _wallet, _hotkey: FakeWallet(),
        submitter=lambda **_kwargs: FakeExtrinsicResult(price_rao=1_251_000_000),
        clock=lambda: datetime(2026, 9, 6, tzinfo=UTC),
    )


def test_receipt_digest_and_finalized_readback(tmp_path: Path) -> None:
    receipt = _successful_receipt()
    path = tmp_path / "receipt.json"
    path.write_text(receipt.model_dump_json())
    assert load_testnet_provision_receipt(path) == receipt

    tampered = receipt.model_copy(update={"netuid": 322})
    path.write_text(tampered.model_dump_json())
    with pytest.raises(ValueError, match="digest mismatch"):
        load_testnet_provision_receipt(path)

    client = FakeReadbackClient()
    report = verify_testnet_provision_readback(receipt, client_factory=lambda: client)
    assert report.finalized_readback_block == 12_400
    assert report.finalized_readback_block_hash == FakeReadbackInfo.hash
    assert report.subnet_locked_tao == "1.251"
    assert report.owner_coldkey_ss58 == PUBLIC_TEST_COLDKEY
    assert report.owner_hotkey_ss58 == PUBLIC_TEST_OWNER
    assert report.uid_zero_hotkey_ss58 == PUBLIC_TEST_OWNER
    assert report.including_extrinsic_index == 2
    assert report.including_extrinsic_hash == "0x" + "4" * 64
    assert report.including_call_module == "SubtensorModule"
    assert report.including_call_function == "register_network"
    assert all(report.gates.model_dump().values())
    assert report.ready_for_testnet_evidence is True
    assert client.closed is True

    mismatch = verify_testnet_provision_readback(
        receipt,
        client_factory=lambda: FakeReadbackClient(wrong_owner=True),
    )
    assert mismatch.gates.owner_coldkey_matches is False
    assert mismatch.ready_for_testnet_evidence is False

    wrong_call = verify_testnet_provision_readback(
        receipt,
        client_factory=lambda: FakeReadbackClient(wrong_call=True),
    )
    assert wrong_call.gates.including_extrinsic_is_register_network is False
    assert wrong_call.ready_for_testnet_evidence is False


def test_default_submitter_is_testnet_only_fee_capped_and_never_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import bittensor as bt

    calls: dict[str, object] = {}

    class FakeIntent:
        def __init__(self, *, hotkey_ss58: str) -> None:
            self.hotkey_ss58 = hotkey_ss58

    class FakePolicy:
        def __init__(self, **kwargs: object) -> None:
            calls["policy"] = kwargs

    class FakeSubmitClient:
        endpoint = TESTNET_ENDPOINT

        def __init__(self, network: str) -> None:
            calls["network"] = network

        def execute(
            self,
            intent: FakeIntent,
            wallet: FakeWallet,
            **kwargs: object,
        ) -> FakeExtrinsicResult:
            calls["intent"] = intent
            calls["wallet"] = wallet
            calls["execute"] = kwargs
            return FakeExtrinsicResult()

        def close(self) -> None:
            calls["closed"] = True

    monkeypatch.setattr(bt, "RegisterSubnet", FakeIntent)
    monkeypatch.setattr(bt, "Policy", FakePolicy)
    monkeypatch.setattr(bt, "Subtensor", FakeSubmitClient)

    wallet = FakeWallet()
    result = _default_submitter(wallet=wallet, owner_hotkey_ss58=PUBLIC_TEST_OWNER)

    assert result.success is True
    assert calls["network"] == "test"
    assert calls["wallet"] is wallet
    assert isinstance(calls["intent"], FakeIntent)
    assert calls["intent"].hotkey_ss58 == PUBLIC_TEST_OWNER  # type: ignore[union-attr]
    assert calls["policy"] == {"max_fee_tao": "0.01"}
    assert calls["execute"] == {
        "policy": calls["execute"]["policy"],  # type: ignore[index]
        "retries": 0,
        "wait_for_inclusion": True,
        "wait_for_finalization": True,
        "wait_for_registration": True,
        "registration_timeout": 300,
    }
    assert calls["closed"] is True
