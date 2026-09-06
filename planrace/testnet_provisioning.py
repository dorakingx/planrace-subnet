"""Read-only, digest-bound planning for the dedicated testnet subnet."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from importlib.metadata import version
from pathlib import Path
from typing import Literal, Protocol, SupportsInt, cast

from pydantic import BaseModel, ConfigDict, Field

from planrace.network import ensure_supported_network
from planrace.testnet_preflight import TESTNET_ENDPOINT, validate_public_ss58

WALLET_ALIAS = "planrace-testnet"
OWNER_HOTKEY_ALIAS = "validator-00"
MAX_TESTNET_BUDGET_RAO = 5_000_000_000
MAX_SUBNET_CREATION_COST_RAO = 1_250_000_000
EXPECTED_VALIDATORS = 3
EXPECTED_MINERS = 10


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class IdentityEntry(_StrictModel):
    name: str
    hotkey_ss58: str


class IdentityBalanceSnapshot(_StrictModel):
    block: int
    coldkey_balance_rao: int
    coldkey_balance_tao: str
    runtime_spec_version: int


class IdentityRegistration(_StrictModel):
    netuid: int | None
    registered_hotkeys: int
    status: str


class IdentitySecurity(_StrictModel):
    coldkey_encrypted: bool
    keyfile_mode: str
    mainnet_authorized: bool
    mnemonic_or_private_key_in_repository: bool
    wallet_directory_mode: str


class PublicIdentityManifest(_StrictModel):
    schema_version: Literal["planrace/testnet-identities/1"] = Field(alias="schema")
    network: Literal["test"]
    sdk_version: str
    wallet_alias: Literal["planrace-testnet"]
    custody: str
    generated_on: str
    coldkey_ss58: str
    validators: tuple[IdentityEntry, ...]
    miners: tuple[IdentityEntry, ...]
    balance_snapshot: IdentityBalanceSnapshot
    registration: IdentityRegistration
    security: IdentitySecurity


class ProvisionRole(_StrictModel):
    role: Literal["validator", "miner"]
    alias: str
    hotkey_ss58: str
    registered_netuids: tuple[int, ...]
    created_with_subnet: bool
    requires_burn_registration: bool


class ProvisionGates(_StrictModel):
    canonical_endpoint: bool
    snapshot_pinned: bool
    identities_valid: bool
    dedicated_wallet_only: bool
    exact_role_count: bool
    public_hotkeys_unique: bool
    owner_is_validator_00: bool
    coldkey_has_no_owned_hotkeys: bool
    all_hotkeys_unregistered: bool
    coldkey_balance_positive: bool
    balance_within_total_budget: bool
    subnet_cost_within_cap: bool
    can_cover_subnet_cost_and_existential_deposit: bool


class TestnetProvisionPlan(_StrictModel):
    schema_version: Literal["planrace/testnet-provision-plan/1"] = (
        "planrace/testnet-provision-plan/1"
    )
    read_only: bool = True
    transaction_constructed: bool = False
    signature_requested: bool = False
    network: Literal["test"] = "test"
    endpoint: str
    sdk_version: str
    block: int | None
    block_hash: str | None
    runtime_spec_version: int | None
    wallet_alias: Literal["planrace-testnet"] = "planrace-testnet"
    coldkey_ss58: str
    owner_hotkey_alias: Literal["validator-00"] = "validator-00"
    owner_hotkey_ss58: str
    coldkey_owned_hotkeys: tuple[str, ...]
    roles: tuple[ProvisionRole, ...]
    subnet_creation_cost_rao: int | None
    subnet_creation_cost_tao: str | None
    existential_deposit_rao: int | None
    existential_deposit_tao: str | None
    coldkey_balance_rao: int | None
    coldkey_balance_tao: str | None
    max_testnet_budget_rao: int = MAX_TESTNET_BUDGET_RAO
    max_subnet_creation_cost_rao: int = MAX_SUBNET_CREATION_COST_RAO
    burn_registrations_after_creation: int
    gates: ProvisionGates
    ready_for_authorized_subnet_creation: bool
    plan_digest: str | None
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


def _rao(value: object) -> int:
    amount = _optional_int(_field(value, "rao"))
    if amount is None or amount < 0:
        raise ValueError("testnet returned an invalid TAO balance")
    return amount


def _int_tuple(value: object, *, field: str) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"testnet returned invalid {field}")
    output = tuple(_optional_int(item) for item in value)
    if any(item is None or item < 0 for item in output):
        raise ValueError(f"testnet returned invalid {field}")
    return cast(tuple[int, ...], output)


def _string_tuple(value: object, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"testnet returned invalid {field}")
    output = tuple(str(item) for item in value)
    if any(not item for item in output):
        raise ValueError(f"testnet returned invalid {field}")
    return output


def _tao_string(rao: int) -> str:
    whole, fraction = divmod(rao, 1_000_000_000)
    return str(whole) if fraction == 0 else f"{whole}.{fraction:09d}".rstrip("0")


def load_public_identities(path: Path) -> PublicIdentityManifest:
    """Load the exact public-only identity schema used by the dedicated wallet."""

    try:
        manifest = PublicIdentityManifest.model_validate_json(path.read_bytes())
    except OSError as error:
        raise ValueError(f"cannot read public identity manifest: {type(error).__name__}") from error
    except ValueError as error:
        raise ValueError("public identity manifest schema validation failed") from error

    validate_public_ss58(manifest.coldkey_ss58)
    if len(manifest.validators) != EXPECTED_VALIDATORS or len(manifest.miners) != EXPECTED_MINERS:
        raise ValueError("public identity manifest must contain exactly 3 validators and 10 miners")
    expected_validators = tuple(f"validator-{index:02d}" for index in range(EXPECTED_VALIDATORS))
    expected_miners = tuple(f"miner-{index:02d}" for index in range(EXPECTED_MINERS))
    if tuple(item.name for item in manifest.validators) != expected_validators:
        raise ValueError("validator aliases must be validator-00 through validator-02")
    if tuple(item.name for item in manifest.miners) != expected_miners:
        raise ValueError("miner aliases must be miner-00 through miner-09")
    hotkeys = tuple(item.hotkey_ss58 for item in (*manifest.validators, *manifest.miners))
    for hotkey in hotkeys:
        validate_public_ss58(hotkey)
    if len(hotkeys) != len(set(hotkeys)) or manifest.coldkey_ss58 in hotkeys:
        raise ValueError("public coldkey and hotkeys must all be unique")
    if (
        manifest.security.mainnet_authorized
        or manifest.security.mnemonic_or_private_key_in_repository
        or manifest.security.keyfile_mode != "0600"
        or manifest.security.wallet_directory_mode != "0700"
    ):
        raise ValueError("public identity manifest does not satisfy the testnet custody boundary")
    return manifest


def _roles(
    manifest: PublicIdentityManifest,
    registrations: Mapping[str, tuple[int, ...]] | None = None,
) -> tuple[ProvisionRole, ...]:
    registrations = registrations or {}
    validators = tuple(
        ProvisionRole(
            role="validator",
            alias=item.name,
            hotkey_ss58=item.hotkey_ss58,
            registered_netuids=registrations.get(item.hotkey_ss58, ()),
            created_with_subnet=item.name == OWNER_HOTKEY_ALIAS,
            requires_burn_registration=item.name != OWNER_HOTKEY_ALIAS,
        )
        for item in manifest.validators
    )
    miners = tuple(
        ProvisionRole(
            role="miner",
            alias=item.name,
            hotkey_ss58=item.hotkey_ss58,
            registered_netuids=registrations.get(item.hotkey_ss58, ()),
            created_with_subnet=False,
            requires_burn_registration=True,
        )
        for item in manifest.miners
    )
    return validators + miners


def _empty_gates() -> ProvisionGates:
    return ProvisionGates(
        canonical_endpoint=False,
        snapshot_pinned=False,
        identities_valid=False,
        dedicated_wallet_only=False,
        exact_role_count=False,
        public_hotkeys_unique=False,
        owner_is_validator_00=False,
        coldkey_has_no_owned_hotkeys=False,
        all_hotkeys_unregistered=False,
        coldkey_balance_positive=False,
        balance_within_total_budget=False,
        subnet_cost_within_cap=False,
        can_cover_subnet_cost_and_existential_deposit=False,
    )


def _digest_payload(report: TestnetProvisionPlan) -> str:
    payload = report.model_dump(mode="json", exclude={"plan_digest", "next_action"})
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def collect_testnet_provision_plan(
    identities_path: Path,
    *,
    client_factory: ClientFactory = _default_client,
) -> TestnetProvisionPlan:
    """Bind public identities, costs, and budget gates to one testnet block."""

    ensure_supported_network("test")
    manifest = load_public_identities(identities_path)
    roles = _roles(manifest)
    owner_hotkey = manifest.validators[0].hotkey_ss58
    limitations = (
        "This latest-block plan is not finalized transaction evidence.",
        "The subnet creation price is dynamic and can change before inclusion.",
        "The new subnet creates validator-00 as UID 0; the other 12 hotkeys require later burns.",
        "No transaction, wallet unlock, signature, registration, or mainnet access is performed.",
    )
    client: TestnetClient | None = None
    try:
        client = client_factory()
        endpoint = str(client.endpoint)
        block = int(client.block)
        snapshot = client.at(block)
        info = snapshot.block_info()
        info_number = _optional_int(_field(info, "number"))
        block_hash = str(_field(info, "hash", ""))
        canonical = endpoint == TESTNET_ENDPOINT
        pinned = int(snapshot.block) == block and info_number == block
        balance_rao = _rao(snapshot.read("balance", coldkey_ss58=manifest.coldkey_ss58))
        cost_rao = _rao(snapshot.read("subnet_registration_cost"))
        existential_rao = _rao(snapshot.read("existential_deposit"))
        owned_hotkeys = _string_tuple(
            snapshot.read("owned_hotkeys", coldkey_ss58=manifest.coldkey_ss58),
            field="owned hotkeys",
        )
        registrations = {
            role.hotkey_ss58: _int_tuple(
                snapshot.read("netuids_for_hotkey", hotkey_ss58=role.hotkey_ss58),
                field=f"netuids for {role.alias}",
            )
            for role in roles
        }
        roles = _roles(manifest, registrations)
        errors: list[str] = []
        if not canonical:
            errors.append("SDK resolved an unexpected endpoint; provisioning is denied")
        if not block_hash.startswith("0x") or len(block_hash) != 66:
            errors.append("testnet returned an invalid block hash")

        hotkeys = tuple(role.hotkey_ss58 for role in roles)
        gates = ProvisionGates(
            canonical_endpoint=canonical,
            snapshot_pinned=pinned,
            identities_valid=True,
            dedicated_wallet_only=manifest.wallet_alias == WALLET_ALIAS,
            exact_role_count=len(manifest.validators) == 3 and len(manifest.miners) == 10,
            public_hotkeys_unique=len(hotkeys) == len(set(hotkeys)),
            owner_is_validator_00=roles[0].alias == OWNER_HOTKEY_ALIAS,
            coldkey_has_no_owned_hotkeys=not owned_hotkeys,
            all_hotkeys_unregistered=all(not role.registered_netuids for role in roles),
            coldkey_balance_positive=balance_rao > 0,
            balance_within_total_budget=0 < balance_rao <= MAX_TESTNET_BUDGET_RAO,
            subnet_cost_within_cap=cost_rao <= MAX_SUBNET_CREATION_COST_RAO,
            can_cover_subnet_cost_and_existential_deposit=(
                balance_rao >= cost_rao + existential_rao
            ),
        )
        ready = all(gates.model_dump().values()) and not errors
        if errors or not canonical or not pinned:
            next_action = "Stop: restore canonical pinned testnet reads and rerun."
        elif owned_hotkeys or any(role.registered_netuids for role in roles):
            next_action = (
                "Stop: reconcile existing ownership or registrations; do not create again."
            )
        elif balance_rao == 0:
            next_action = "Obtain the approved test TAO allocation, then rerun this plan."
        elif balance_rao > MAX_TESTNET_BUDGET_RAO:
            next_action = "Stop: balance exceeds the approved 5 test TAO project budget."
        elif cost_rao > MAX_SUBNET_CREATION_COST_RAO:
            next_action = "Stop: subnet creation cost exceeds the 1.25 test TAO operation cap."
        elif balance_rao < cost_rao + existential_rao:
            next_action = "Obtain enough test TAO to cover creation plus existential deposit."
        else:
            next_action = "Review this plan and explicitly authorize its digest before signing."
        report = TestnetProvisionPlan(
            endpoint=endpoint,
            sdk_version=version("bittensor"),
            block=block,
            block_hash=block_hash or None,
            runtime_spec_version=int(client.spec_version),
            coldkey_ss58=manifest.coldkey_ss58,
            owner_hotkey_ss58=owner_hotkey,
            coldkey_owned_hotkeys=owned_hotkeys,
            roles=roles,
            subnet_creation_cost_rao=cost_rao,
            subnet_creation_cost_tao=_tao_string(cost_rao),
            existential_deposit_rao=existential_rao,
            existential_deposit_tao=_tao_string(existential_rao),
            coldkey_balance_rao=balance_rao,
            coldkey_balance_tao=_tao_string(balance_rao),
            burn_registrations_after_creation=sum(
                role.requires_burn_registration for role in roles
            ),
            gates=gates,
            ready_for_authorized_subnet_creation=ready,
            plan_digest=None,
            next_action=next_action,
            limitations=limitations,
            errors=tuple(errors),
        )
        return report.model_copy(update={"plan_digest": _digest_payload(report)})
    except Exception as error:
        return TestnetProvisionPlan(
            endpoint=TESTNET_ENDPOINT,
            sdk_version=version("bittensor"),
            block=None,
            block_hash=None,
            runtime_spec_version=None,
            coldkey_ss58=manifest.coldkey_ss58,
            owner_hotkey_ss58=owner_hotkey,
            coldkey_owned_hotkeys=(),
            roles=roles,
            subnet_creation_cost_rao=None,
            subnet_creation_cost_tao=None,
            existential_deposit_rao=None,
            existential_deposit_tao=None,
            coldkey_balance_rao=None,
            coldkey_balance_tao=None,
            burn_registrations_after_creation=sum(
                role.requires_burn_registration for role in roles
            ),
            gates=_empty_gates(),
            ready_for_authorized_subnet_creation=False,
            plan_digest=None,
            next_action="Stop: restore canonical read-only testnet state and rerun.",
            limitations=limitations,
            errors=(f"read-only provisioning plan failed: {type(error).__name__}",),
        )
    finally:
        if client is not None:
            client.close()
