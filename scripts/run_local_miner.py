#!/usr/bin/env python3
"""Run a throwaway miner with public Substrate development keys.

This command refuses every network except the local development chain. The
`//Alice`, `//Bob`, and `//Charlie` keys are publicly known and must never be
reused outside localnet.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import bittensor as bt
import uvicorn

from planrace.api import create_miner_app
from planrace.miners import gaming_miner, indexed_miner
from planrace.nonce import SQLiteNonceStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("honest", "gaming"), required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--network", choices=("local",), default="local")
    args = parser.parse_args()

    role_uri = "//Bob" if args.profile == "honest" else "//Charlie"
    miner = bt.sp_core.Keypair.create_from_uri(role_uri)
    validator = bt.sp_core.Keypair.create_from_uri("//Alice")
    state_dir = Path(".localnet-state")
    state_dir.mkdir(exist_ok=True)
    app = create_miner_app(
        self_hotkey_ss58=miner.ss58_address,
        nonce_store=SQLiteNonceStore(state_dir / f"{args.profile}-nonces.sqlite3"),
        strategy=indexed_miner if args.profile == "honest" else gaming_miner,
        authorize_hotkey=lambda hotkey: hotkey == validator.ss58_address,
    )
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")  # noqa: S104


if __name__ == "__main__":
    main()
