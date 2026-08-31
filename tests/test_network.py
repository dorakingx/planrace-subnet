import pytest

from planrace.network import UnsupportedNetworkError, ensure_supported_network


@pytest.mark.parametrize("value", ["local", "test", " TEST "])
def test_local_and_testnet_are_allowed(value: str) -> None:
    assert ensure_supported_network(value) in {"local", "test"}


@pytest.mark.parametrize(
    "value", ["finney", "mainnet", "wss://entrypoint-finney.opentensor.ai:443", "custom"]
)
def test_mainnet_and_arbitrary_targets_fail_closed(value: str) -> None:
    with pytest.raises(UnsupportedNetworkError):
        ensure_supported_network(value)
