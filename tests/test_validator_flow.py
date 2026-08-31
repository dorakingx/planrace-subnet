from pathlib import Path

import bittensor as bt
import httpx
import pytest

from planrace.api import create_miner_app
from planrace.nonce import SQLiteNonceStore
from planrace.scoring import evaluate_artifact
from planrace.taskgen import generate_workload
from planrace.validator_client import request_optimization

VALIDATOR = bt.sp_core.Keypair.create_from_uri("//Alice")
MINER = bt.sp_core.Keypair.create_from_uri("//Bob")


@pytest.mark.anyio
async def test_signed_miner_validator_oracle_flow(tmp_path: Path) -> None:
    workload = generate_workload(2)
    app = create_miner_app(
        self_hotkey_ss58=MINER.ss58_address,
        nonce_store=SQLiteNonceStore(tmp_path / "nonces.sqlite3"),
        authorize_hotkey=lambda hotkey: hotkey == VALIDATOR.ss58_address,
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://miner.test") as client:
        outcome = await request_optimization(
            client,
            wallet=VALIDATOR,
            endpoint="/v1/optimize",
            receiver_ss58=MINER.ss58_address,
            task=workload.task,
        )
    assert outcome.accepted
    assert outcome.artifact is not None
    score = evaluate_artifact(workload, outcome.artifact)
    assert score.correct
    assert score.score > 0.0
