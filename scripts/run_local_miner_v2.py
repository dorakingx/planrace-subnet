#!/usr/bin/env python3
"""Serve one public-key PlanRace v2 miner profile on localhost."""

from __future__ import annotations

import argparse
from pathlib import Path

import bittensor as bt
import uvicorn

from planrace.api_v2 import create_miner_app_v2
from planrace.localnet_v2 import PROFILE_NAMES, strategy_for_profile
from planrace.nonce import SQLiteNonceStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=PROFILE_NAMES, required=True)
    parser.add_argument("--index", type=int, choices=range(10), required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--network", choices=("local",), default="local")
    arguments = parser.parse_args()

    miner = bt.sp_core.Keypair.create_from_uri(f"//PlanRaceMinerV2-{arguments.index}")
    validators = {
        bt.sp_core.Keypair.create_from_uri(f"//PlanRaceValidator{index}").ss58_address
        for index in range(3)
    }
    state_dir = Path(".localnet-state/v2-miners")
    state_dir.mkdir(parents=True, exist_ok=True)
    app = create_miner_app_v2(
        miner_wallet_or_signer=miner,
        nonce_store=SQLiteNonceStore(state_dir / f"miner-{arguments.index}-nonces.sqlite3"),
        strategy=strategy_for_profile(arguments.profile),
        authorize_hotkey=validators.__contains__,
    )
    uvicorn.run(app, host="127.0.0.1", port=arguments.port, log_level="warning")


if __name__ == "__main__":
    main()
