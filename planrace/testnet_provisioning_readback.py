"""Finalized public-chain readback for a subnet-creation receipt."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from importlib.metadata import version
from typing import Protocol, SupportsInt, cast

from pydantic import BaseModel, ConfigDict

from planrace.network import ensure_supported_network
from planrace.testnet_preflight import TESTNET_ENDPOINT
from planrace.testnet_provisioning import _tao_string
from planrace.testnet_provisioning_submission import (
    TestnetProvisionSubmissionReceipt,
    _validated_provision_receipt_digest,
)

SCHEMA_VERSION = "planrace/testnet-provision-readback/1"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ProvisionReadbackGates(_StrictModel):
    canonical_endpoint: bool
    finalized_snapshot_pinned: bool
    readback_not_before_inclusion: bool
    including_block_hash_matches: bool
    including_extrinsic_index_valid: bool
    including_extrinsic_is_register_network: bool
    including_extrinsic_owner_hotkey_matches: bool
    subnet_exists: bool
    owner_coldkey_matches: bool
    owner_hotkey_matches: bool
    metagraph_owners_match_storage: bool
    owner_hotkey_is_uid_zero: bool
    owner_hotkey_registered_on_netuid: bool
    owner_hotkey_owned_by_coldkey: bool
    registration_block_plausible: bool
    locked_price_positive_and_receipt_consistent: bool


class TestnetProvisionReadbackReport(_StrictModel):
    schema_version: str = SCHEMA_VERSION
    read_only: bool = True
    network: str = "test"
    endpoint: str
    sdk_version: str
    runtime_spec_version: int | None
    source_receipt_digest: str
    netuid: int
    receipt_including_block: int | None
    receipt_including_block_hash: str | None
    including_extrinsic_index: int | None
    including_extrinsic_hash: str | None
    including_call_module: str | None
    including_call_function: str | None
    finalized_readback_block: int | None
    finalized_readback_block_hash: str | None
    network_registered_at: int | None
    subnet_locked_rao: int | None
    subnet_locked_tao: str | None
    owner_coldkey_ss58: str | None
    owner_hotkey_ss58: str | None
    uid_zero_hotkey_ss58: str | None
    owner_hotkey_netuids: tuple[int, ...]
    coldkey_owned_hotkeys: tuple[str, ...]
    gates: ProvisionReadbackGates
    ready_for_testnet_evidence: bool
    next_action: str
    limitations: tuple[str, ...]
    errors: tuple[str, ...]


class FinalizedHeader(Protocol):
    number: int


class Snapshot(Protocol):
    block: int

    def read(self, name: str, **params: object) -> object: ...

    def query(self, item: object, params: list[object] | None = None) -> object: ...

    def block_info(self) -> object: ...


class TestnetClient(Protocol):
    endpoint: str
    spec_version: int

    def blocks(self, *, finalized: bool = False) -> Iterator[FinalizedHeader]: ...

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


def _int_tuple(value: object) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError("testnet returned invalid hotkey netuids")
    output = tuple(_optional_int(item) for item in value)
    if any(item is None or item < 0 for item in output):
        raise ValueError("testnet returned invalid hotkey netuids")
    return cast(tuple[int, ...], output)


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError("testnet returned invalid owned hotkeys")
    return tuple(str(item) for item in value)


def _including_coordinate(extrinsic_id: str | None) -> tuple[int, int] | None:
    if not extrinsic_id:
        return None
    height, separator, index = extrinsic_id.partition("-")
    if not separator or not height.isdigit() or not index.isdigit():
        return None
    return int(height), int(index)


def _call_arg(call: object, name: str) -> object:
    arguments = _field(call, "call_args", ())
    if not isinstance(arguments, Sequence) or isinstance(arguments, (str, bytes, bytearray)):
        return None
    for argument in arguments:
        if isinstance(argument, Mapping) and argument.get("name") == name:
            return argument.get("value")
    return None


def _empty_gates() -> ProvisionReadbackGates:
    return ProvisionReadbackGates(
        canonical_endpoint=False,
        finalized_snapshot_pinned=False,
        readback_not_before_inclusion=False,
        including_block_hash_matches=False,
        including_extrinsic_index_valid=False,
        including_extrinsic_is_register_network=False,
        including_extrinsic_owner_hotkey_matches=False,
        subnet_exists=False,
        owner_coldkey_matches=False,
        owner_hotkey_matches=False,
        metagraph_owners_match_storage=False,
        owner_hotkey_is_uid_zero=False,
        owner_hotkey_registered_on_netuid=False,
        owner_hotkey_owned_by_coldkey=False,
        registration_block_plausible=False,
        locked_price_positive_and_receipt_consistent=False,
    )


def verify_testnet_provision_readback(
    receipt: TestnetProvisionSubmissionReceipt,
    *,
    client_factory: ClientFactory = _default_client,
) -> TestnetProvisionReadbackReport:
    """Verify finalized ownership, UID 0, price, and block coordinates publicly."""

    import bittensor as bt

    ensure_supported_network("test")
    receipt_digest = _validated_provision_receipt_digest(receipt)
    coordinate = _including_coordinate(receipt.extrinsic_id)
    included_block = coordinate[0] if coordinate is not None else None
    included_index = coordinate[1] if coordinate is not None else None
    limitations = (
        "This verifies finalized public chain state, not control of the private keys.",
        "The receipt digest provides file integrity, not an independent trusted signature.",
        "Activation, Axon serving, additional registrations, and weights are separate evidence.",
    )
    client: TestnetClient | None = None
    try:
        if included_block is None or included_index is None:
            raise ValueError("receipt extrinsic identifier has no block-index coordinate")
        client = client_factory()
        endpoint = str(client.endpoint)
        finalized_stream = client.blocks(finalized=True)
        try:
            finalized_block = int(next(finalized_stream).number)
        finally:
            close_stream = getattr(finalized_stream, "close", None)
            if callable(close_stream):
                close_stream()
        snapshot = client.at(finalized_block)
        info = snapshot.block_info()
        readback_hash = str(_field(info, "hash", ""))
        readback_number = _optional_int(_field(info, "number"))
        inclusion_info = client.at(included_block).block_info()
        canonical_inclusion_hash = str(_field(inclusion_info, "hash", ""))
        inclusion_extrinsics = _field(inclusion_info, "extrinsics", ())
        index_valid = (
            isinstance(inclusion_extrinsics, Sequence)
            and not isinstance(inclusion_extrinsics, (str, bytes, bytearray))
            and included_index < len(inclusion_extrinsics)
        )
        included_extrinsic = (
            cast(Sequence[object], inclusion_extrinsics)[included_index] if index_valid else None
        )
        included_hash = str(_field(included_extrinsic, "extrinsic_hash", ""))
        included_call = _field(included_extrinsic, "call", {})
        call_module = str(_field(included_call, "call_module", ""))
        call_function = str(_field(included_call, "call_function", ""))
        call_hotkey = str(_call_arg(included_call, "hotkey") or "")

        storage = bt.storage.SubtensorModule
        netuid_param: list[object] = [receipt.netuid]
        exists = bool(snapshot.query(storage.NetworksAdded, netuid_param))
        owner_coldkey = str(snapshot.query(storage.SubnetOwner, netuid_param))
        owner_hotkey = str(snapshot.query(storage.SubnetOwnerHotkey, netuid_param))
        locked = _optional_int(snapshot.query(storage.SubnetLocked, netuid_param))
        registered_at = _optional_int(snapshot.query(storage.NetworkRegisteredAt, netuid_param))
        metagraph = snapshot.read("metagraph", netuid=receipt.netuid)
        graph_hotkeys_raw = _field(metagraph, "hotkeys", ())
        graph_hotkeys = _string_tuple(graph_hotkeys_raw)
        graph_owner_coldkey = str(_field(metagraph, "owner_coldkey", ""))
        graph_owner_hotkey = str(_field(metagraph, "owner_hotkey", ""))
        owner_netuids = _int_tuple(
            snapshot.read("netuids_for_hotkey", hotkey_ss58=receipt.owner_hotkey_ss58)
        )
        owned_hotkeys = _string_tuple(
            snapshot.read("owned_hotkeys", coldkey_ss58=receipt.coldkey_ss58)
        )

        pinned = (
            snapshot.block == finalized_block
            and readback_number == finalized_block
            and readback_hash.startswith("0x")
            and len(readback_hash) == 66
        )
        price_consistent = (
            locked is not None
            and locked > 0
            and (
                receipt.actual_registration_price_rao is None
                or receipt.actual_registration_price_rao == locked
            )
        )
        gates = ProvisionReadbackGates(
            canonical_endpoint=endpoint == TESTNET_ENDPOINT,
            finalized_snapshot_pinned=pinned,
            readback_not_before_inclusion=finalized_block >= included_block,
            including_block_hash_matches=(canonical_inclusion_hash == receipt.including_block_hash),
            including_extrinsic_index_valid=index_valid,
            including_extrinsic_is_register_network=(
                call_module == "SubtensorModule" and call_function == "register_network"
            ),
            including_extrinsic_owner_hotkey_matches=call_hotkey == receipt.owner_hotkey_ss58,
            subnet_exists=exists,
            owner_coldkey_matches=owner_coldkey == receipt.coldkey_ss58,
            owner_hotkey_matches=owner_hotkey == receipt.owner_hotkey_ss58,
            metagraph_owners_match_storage=(
                graph_owner_coldkey == owner_coldkey and graph_owner_hotkey == owner_hotkey
            ),
            owner_hotkey_is_uid_zero=(
                bool(graph_hotkeys) and graph_hotkeys[0] == receipt.owner_hotkey_ss58
            ),
            owner_hotkey_registered_on_netuid=receipt.netuid in owner_netuids,
            owner_hotkey_owned_by_coldkey=receipt.owner_hotkey_ss58 in owned_hotkeys,
            registration_block_plausible=(
                registered_at is not None
                and receipt.source_block <= registered_at <= finalized_block
            ),
            locked_price_positive_and_receipt_consistent=price_consistent,
        )
        ready = all(gates.model_dump().values())
        return TestnetProvisionReadbackReport(
            endpoint=endpoint,
            sdk_version=version("bittensor"),
            runtime_spec_version=int(client.spec_version),
            source_receipt_digest=receipt_digest,
            netuid=receipt.netuid,
            receipt_including_block=included_block,
            receipt_including_block_hash=receipt.including_block_hash,
            including_extrinsic_index=included_index,
            including_extrinsic_hash=included_hash or None,
            including_call_module=call_module or None,
            including_call_function=call_function or None,
            finalized_readback_block=finalized_block,
            finalized_readback_block_hash=readback_hash or None,
            network_registered_at=registered_at,
            subnet_locked_rao=locked,
            subnet_locked_tao=_tao_string(locked) if locked is not None else None,
            owner_coldkey_ss58=owner_coldkey or None,
            owner_hotkey_ss58=owner_hotkey or None,
            uid_zero_hotkey_ss58=graph_hotkeys[0] if graph_hotkeys else None,
            owner_hotkey_netuids=owner_netuids,
            coldkey_owned_hotkeys=owned_hotkeys,
            gates=gates,
            ready_for_testnet_evidence=ready,
            next_action=(
                "Bind this finalized readback and receipt into the signed testnet manifest."
                if ready
                else "Stop: reconcile the failed finalized ownership or receipt gates."
            ),
            limitations=limitations,
            errors=(),
        )
    except Exception as error:
        return TestnetProvisionReadbackReport(
            endpoint=TESTNET_ENDPOINT,
            sdk_version=version("bittensor"),
            runtime_spec_version=None,
            source_receipt_digest=receipt_digest,
            netuid=receipt.netuid,
            receipt_including_block=included_block,
            receipt_including_block_hash=receipt.including_block_hash,
            including_extrinsic_index=included_index,
            including_extrinsic_hash=None,
            including_call_module=None,
            including_call_function=None,
            finalized_readback_block=None,
            finalized_readback_block_hash=None,
            network_registered_at=None,
            subnet_locked_rao=None,
            subnet_locked_tao=None,
            owner_coldkey_ss58=None,
            owner_hotkey_ss58=None,
            uid_zero_hotkey_ss58=None,
            owner_hotkey_netuids=(),
            coldkey_owned_hotkeys=(),
            gates=_empty_gates(),
            ready_for_testnet_evidence=False,
            next_action="Stop: restore canonical finalized testnet reads and rerun.",
            limitations=limitations,
            errors=(f"finalized provision readback failed: {type(error).__name__}",),
        )
    finally:
        if client is not None:
            client.close()
