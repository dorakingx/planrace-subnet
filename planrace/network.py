"""Fail-closed Bittensor network configuration."""

from __future__ import annotations

from typing import Final

ALLOWED_NETWORKS: Final = frozenset({"local", "test"})
MAINNET_ALIASES: Final = frozenset(
    {
        "finney",
        "main",
        "mainnet",
        "wss://entrypoint-finney.opentensor.ai",
        "wss://entrypoint-finney.opentensor.ai:443",
    }
)


class UnsupportedNetworkError(ValueError):
    """Raised before any connection to a non-allowlisted chain target."""


def ensure_supported_network(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in ALLOWED_NETWORKS:
        return normalized
    reason = "mainnet is prohibited" if normalized in MAINNET_ALIASES else "not allowlisted"
    raise UnsupportedNetworkError(f"unsupported Bittensor network {value!r}: {reason}")
