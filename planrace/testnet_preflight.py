"""Read-only, fail-closed Bittensor testnet readiness checks.

The preflight accepts public chain identifiers only.  It deliberately exposes no
wallet-path, signing, registration, weight-setting, or arbitrary-RPC surface.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from importlib.metadata import version
from ipaddress import ip_address
from typing import Protocol, SupportsInt, cast

from pydantic import BaseModel, ConfigDict

from planrace.network import ensure_supported_network

TESTNET_ENDPOINT = "wss://test.finney.opentensor.ai:443"
SCHEMA_VERSION = "planrace/testnet-preflight/2"
MAX_NETUID = 65_535
_ROLE_RE = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
_SS58_RE = re.compile(r"5[1-9A-HJ-NP-Za-km-z]{47}\Z")


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PublicAxon(_StrictModel):
    ip: str
    port: int
    ip_type: int
    protocol: int
    version: int


class RoleStatus(_StrictModel):
    role: str
    hotkey_ss58: str
    uid: int | None
    registered: bool
    coldkey_matches: bool | None
    axon_served: bool
    axon: PublicAxon | None
    validator_permit: bool
    is_subnet_owner: bool
    weight_setting_authorized: bool
    blocks_since_last_update: int | None


class SubnetStatus(_StrictModel):
    netuid: int
    exists: bool
    neuron_count: int | None = None
    tempo: int | None = None
    registration_allowed: bool | None = None
    subnet_is_active: bool | None = None
    max_uids: int | None = None
    min_allowed_weights: int | None = None
    max_weights_limit: int | None = None
    weights_rate_limit: int | None = None
    commit_reveal_weights_enabled: bool | None = None
    commit_reveal_period: int | None = None


class ColdkeyStatus(_StrictModel):
    ss58: str
    balance_rao: int
    balance_tao: str
    positive_balance: bool


class PreflightGates(_StrictModel):
    canonical_endpoint: bool
    snapshot_pinned: bool
    subnet_exists: bool
    coldkey_balance_positive: bool
    required_roles_present: bool
    all_roles_registered: bool
    validator_authorized: bool
    miner_axons_served: bool
    registration_requirement_met: bool
    served_axon_requirement_met: bool


class TestnetPreflightReport(_StrictModel):
    schema_version: str = SCHEMA_VERSION
    read_only: bool = True
    network: str = "test"
    endpoint: str = TESTNET_ENDPOINT
    sdk_version: str
    block: int | None
    runtime_spec_version: int | None
    chain_reachable: bool
    subnet: SubnetStatus | None
    coldkey: ColdkeyStatus | None
    roles: tuple[RoleStatus, ...]
    gates: PreflightGates
    ready_for_registration: bool
    ready_for_protocol_run: bool
    next_action: str
    limitations: tuple[str, ...]
    errors: tuple[str, ...]


class Snapshot(Protocol):
    block: int

    def read(self, name: str, **params: object) -> object: ...

    def query(self, item: object, params: list[object] | None = None) -> object: ...


class TestnetClient(Protocol):
    endpoint: str
    block: int
    spec_version: int

    def at(self, block: int) -> Snapshot: ...

    def close(self) -> None: ...


ClientFactory = Callable[[], TestnetClient]


def parse_public_roles(values: Sequence[str]) -> tuple[tuple[str, str], ...]:
    """Parse unique ``role=public-hotkey`` values without accepting key material."""

    parsed: list[tuple[str, str]] = []
    seen_roles: set[str] = set()
    seen_addresses: set[str] = set()
    for value in values:
        if "=" not in value:
            raise ValueError("hotkey must use role=SS58 format")
        role, address = value.split("=", 1)
        if not _ROLE_RE.fullmatch(role):
            raise ValueError(f"invalid role name {role!r}")
        validate_public_ss58(address)
        if role in seen_roles:
            raise ValueError(f"duplicate role {role!r}")
        if address in seen_addresses:
            raise ValueError("one public hotkey cannot be assigned to multiple roles")
        seen_roles.add(role)
        seen_addresses.add(address)
        parsed.append((role, address))
    return tuple(parsed)


def validate_public_ss58(address: str) -> str:
    """Perform conservative format validation before a read-only chain lookup."""

    if not _SS58_RE.fullmatch(address):
        raise ValueError("public SS58 address must be a 48-character Bittensor address")
    return address


def _default_client() -> TestnetClient:
    import bittensor as bt

    ensure_supported_network("test")
    return cast(TestnetClient, bt.Subtensor(network="test"))


def _field(value: object, name: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _indexed(value: object, index: int, default: object = None) -> object:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value[index] if index < len(value) else default
    return default


def _optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, (str, bytes, bytearray)):
            return int(value)
        if hasattr(value, "__int__"):
            return int(cast(SupportsInt, value))
        return None
    except (TypeError, ValueError):
        return None


def _optional_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def testnet_subnet_exists(snapshot: Snapshot, netuid: int) -> bool:
    """Read the authoritative runtime existence flag for one subnet."""

    import bittensor as bt

    value = snapshot.query(bt.storage.SubtensorModule.NetworksAdded, [netuid])
    if not isinstance(value, bool):
        raise ValueError("testnet returned an invalid subnet existence flag")
    return value


def _axon_status(value: object) -> tuple[bool, PublicAxon | None]:
    if value is None:
        return False, None
    ip = str(_field(value, "ip", ""))
    port = _optional_int(_field(value, "port", 0)) or 0
    axon = PublicAxon(
        ip=ip,
        port=port,
        ip_type=_optional_int(_field(value, "ip_type", 0)) or 0,
        protocol=_optional_int(_field(value, "protocol", 0)) or 0,
        version=_optional_int(_field(value, "version", 0)) or 0,
    )
    try:
        unspecified = ip_address(ip).is_unspecified
    except ValueError:
        unspecified = not ip
    served = port > 0 and not unspecified
    return served, axon


def _subnet_status(snapshot: Snapshot, netuid: int) -> tuple[SubnetStatus, object | None]:
    if not testnet_subnet_exists(snapshot, netuid):
        return SubnetStatus(netuid=netuid, exists=False), None
    subnet = snapshot.read("subnet", netuid=netuid)
    if subnet is None:
        raise ValueError("existing testnet subnet returned no subnet data")
    hyper = snapshot.read("subnet_hyperparameters", netuid=netuid)
    return (
        SubnetStatus(
            netuid=netuid,
            exists=True,
            neuron_count=_optional_int(_field(subnet, "neuron_count")),
            tempo=_optional_int(_field(subnet, "tempo", _field(hyper, "tempo"))),
            registration_allowed=_optional_bool(_field(hyper, "registration_allowed")),
            subnet_is_active=_optional_bool(_field(hyper, "subnet_is_active")),
            max_uids=_optional_int(_field(hyper, "max_uids")),
            min_allowed_weights=_optional_int(_field(hyper, "min_allowed_weights")),
            max_weights_limit=_optional_int(_field(hyper, "max_weights_limit")),
            weights_rate_limit=_optional_int(_field(hyper, "weights_rate_limit")),
            commit_reveal_weights_enabled=_optional_bool(
                _field(hyper, "commit_reveal_weights_enabled")
            ),
            commit_reveal_period=_optional_int(_field(hyper, "commit_reveal_period")),
        ),
        hyper,
    )


def _coldkey_status(snapshot: Snapshot, address: str) -> ColdkeyStatus:
    balance = snapshot.read("balance", coldkey_ss58=address)
    rao = _optional_int(_field(balance, "rao"))
    if rao is None or rao < 0:
        raise ValueError("testnet returned an invalid coldkey balance")
    tao = format(Decimal(rao) / Decimal(1_000_000_000), "f")
    return ColdkeyStatus(
        ss58=address,
        balance_rao=rao,
        balance_tao=tao,
        positive_balance=rao > 0,
    )


def _role_statuses(
    snapshot: Snapshot,
    *,
    netuid: int,
    roles: Sequence[tuple[str, str]],
    coldkey: str | None,
) -> tuple[RoleStatus, ...]:
    if not roles:
        return ()
    metagraph = snapshot.read("metagraph", netuid=netuid)
    hotkeys = _field(metagraph, "hotkeys", ())
    coldkeys = _field(metagraph, "coldkeys", ())
    axons = _field(metagraph, "axons", ())
    permits = _field(metagraph, "validator_permit", ())
    owner_hotkey = str(_field(metagraph, "owner_hotkey", ""))
    last_updates = _field(metagraph, "last_update", ())
    hotkey_list = list(hotkeys) if isinstance(hotkeys, Sequence) else []

    output: list[RoleStatus] = []
    for role, address in roles:
        uid = hotkey_list.index(address) if address in hotkey_list else None
        served, axon = _axon_status(_indexed(axons, uid)) if uid is not None else (False, None)
        registered_coldkey = _indexed(coldkeys, uid) if uid is not None else None
        last_update = _optional_int(_indexed(last_updates, uid)) if uid is not None else None
        blocks_since = max(0, snapshot.block - last_update) if last_update is not None else None
        validator_permit = bool(_indexed(permits, uid, False)) if uid is not None else False
        is_subnet_owner = bool(uid is not None and owner_hotkey and address == owner_hotkey)
        output.append(
            RoleStatus(
                role=role,
                hotkey_ss58=address,
                uid=uid,
                registered=uid is not None,
                coldkey_matches=(
                    str(registered_coldkey) == coldkey
                    if coldkey is not None and registered_coldkey is not None
                    else None
                ),
                axon_served=served,
                axon=axon,
                validator_permit=validator_permit,
                is_subnet_owner=is_subnet_owner,
                weight_setting_authorized=validator_permit or is_subnet_owner,
                blocks_since_last_update=blocks_since,
            )
        )
    return tuple(output)


def _empty_gates() -> PreflightGates:
    return PreflightGates(
        canonical_endpoint=False,
        snapshot_pinned=False,
        subnet_exists=False,
        coldkey_balance_positive=False,
        required_roles_present=False,
        all_roles_registered=False,
        validator_authorized=False,
        miner_axons_served=False,
        registration_requirement_met=False,
        served_axon_requirement_met=False,
    )


def collect_testnet_preflight(
    *,
    netuid: int | None = None,
    coldkey_ss58: str | None = None,
    role_specs: Sequence[str] = (),
    require_registered: bool = False,
    require_served_axon: bool = False,
    client_factory: ClientFactory = _default_client,
) -> TestnetPreflightReport:
    """Collect a bounded public snapshot without constructing any transaction."""

    ensure_supported_network("test")
    if netuid is not None and not 0 <= netuid <= MAX_NETUID:
        raise ValueError("netuid must be between 0 and 65535")
    if coldkey_ss58 is not None:
        validate_public_ss58(coldkey_ss58)
    roles = parse_public_roles(role_specs)
    errors: list[str] = []
    limitations = (
        "This is a read-only latest-block snapshot, not finalized transaction evidence.",
        "A positive balance does not prove ownership or authorize spending.",
        "No registration, serving, staking, signing, or weight operation is performed.",
    )
    client: TestnetClient | None = None
    try:
        client = client_factory()
        endpoint = str(client.endpoint)
        if endpoint != TESTNET_ENDPOINT:
            errors.append("SDK resolved an unexpected endpoint; further readiness is denied")
        block = int(client.block)
        snapshot = client.at(block)
        snapshot_pinned = int(snapshot.block) == block
        subnet_status: SubnetStatus | None = None
        coldkey_status: ColdkeyStatus | None = None
        role_statuses: tuple[RoleStatus, ...] = ()
        if netuid is not None:
            try:
                subnet_status, _ = _subnet_status(snapshot, netuid)
            except Exception as error:  # chain errors are data in this diagnostic
                errors.append(f"subnet lookup failed: {type(error).__name__}")
                subnet_status = SubnetStatus(netuid=netuid, exists=False)
        if coldkey_ss58 is not None:
            try:
                coldkey_status = _coldkey_status(snapshot, coldkey_ss58)
            except Exception as error:
                errors.append(f"coldkey balance lookup failed: {type(error).__name__}")
        if roles and netuid is not None and subnet_status is not None and subnet_status.exists:
            try:
                role_statuses = _role_statuses(
                    snapshot,
                    netuid=netuid,
                    roles=roles,
                    coldkey=coldkey_ss58,
                )
            except Exception as error:
                errors.append(f"metagraph lookup failed: {type(error).__name__}")

        role_names = {role for role, _ in roles}
        required_roles = (
            "validator" in role_names
            and sum(1 for role in role_names if role.startswith("miner")) >= 2
        )
        all_registered = bool(role_statuses) and all(item.registered for item in role_statuses)
        validator_authorized = any(
            item.role == "validator" and item.weight_setting_authorized for item in role_statuses
        )
        miners = tuple(item for item in role_statuses if item.role.startswith("miner"))
        miners_served = len(miners) >= 2 and all(item.axon_served for item in miners)
        subnet_exists = subnet_status is not None and subnet_status.exists
        balance_positive = coldkey_status is not None and coldkey_status.positive_balance
        canonical = endpoint == TESTNET_ENDPOINT
        registration_met = not require_registered or all_registered
        served_met = not require_served_axon or miners_served
        gates = PreflightGates(
            canonical_endpoint=canonical,
            snapshot_pinned=snapshot_pinned,
            subnet_exists=subnet_exists,
            coldkey_balance_positive=balance_positive,
            required_roles_present=required_roles,
            all_roles_registered=all_registered,
            validator_authorized=validator_authorized,
            miner_axons_served=miners_served,
            registration_requirement_met=registration_met,
            served_axon_requirement_met=served_met,
        )
        ready_for_registration = (
            all((canonical, snapshot_pinned, subnet_exists, balance_positive, required_roles))
            and not errors
        )
        ownership_matches = bool(role_statuses) and all(
            item.coldkey_matches is not False for item in role_statuses
        )
        ready_for_protocol = all(
            (
                ready_for_registration,
                all_registered,
                ownership_matches,
                validator_authorized,
                miners_served,
                registration_met,
                served_met,
            )
        )
        if not canonical:
            next_action = "Stop: inspect the SDK endpoint before any testnet action."
        elif netuid is None or coldkey_ss58 is None or not required_roles:
            next_action = (
                "Provide public netuid, coldkey, validator hotkey, and two miner hotkeys; "
                "never provide private keys or mnemonics."
            )
        elif not subnet_exists:
            next_action = "Choose an existing testnet subnet and rerun this read-only preflight."
        elif not balance_positive:
            next_action = "Obtain test TAO for the dedicated public coldkey, then rerun."
        elif not all_registered:
            next_action = (
                "Registration is pending and requires an explicit user-authorized signature."
            )
        elif not validator_authorized or not miners_served:
            next_action = (
                "Serve public Axons and satisfy validator authorization before protocol run."
            )
        else:
            next_action = (
                "Public readback gates pass; request explicit authorization before signing."
            )
        return TestnetPreflightReport(
            sdk_version=version("bittensor"),
            endpoint=endpoint,
            block=block,
            runtime_spec_version=int(client.spec_version),
            chain_reachable=True,
            subnet=subnet_status,
            coldkey=coldkey_status,
            roles=role_statuses,
            gates=gates,
            ready_for_registration=ready_for_registration,
            ready_for_protocol_run=ready_for_protocol,
            next_action=next_action,
            limitations=limitations,
            errors=tuple(errors),
        )
    except Exception as error:
        return TestnetPreflightReport(
            sdk_version=version("bittensor"),
            block=None,
            runtime_spec_version=None,
            chain_reachable=False,
            subnet=None,
            coldkey=None,
            roles=(),
            gates=_empty_gates(),
            ready_for_registration=False,
            ready_for_protocol_run=False,
            next_action="Stop: restore read-only canonical testnet connectivity and rerun.",
            limitations=limitations,
            errors=(f"connection failed: {type(error).__name__}",),
        )
    finally:
        if client is not None:
            client.close()
