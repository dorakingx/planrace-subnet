import json
import time
from pathlib import Path

import bittensor as bt
import httpx
import pytest

from planrace.api import create_miner_app
from planrace.auth import FreshNonceGenerator, build_signed_request
from planrace.nonce import SQLiteNonceStore
from planrace.taskgen import generate_workload

ALICE = bt.sp_core.Keypair.create_from_uri("//Alice")
BOB = bt.sp_core.Keypair.create_from_uri("//Bob")


@pytest.mark.anyio
async def test_signed_task_reaches_miner_and_replay_fails(tmp_path: Path) -> None:
    app = create_miner_app(
        self_hotkey_ss58=BOB.ss58_address,
        nonce_store=SQLiteNonceStore(tmp_path / "nonces.sqlite3"),
        authorize_hotkey=lambda hotkey: hotkey == ALICE.ss58_address,
    )
    body = generate_workload(0).task.model_dump_json().encode()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://miner.test") as client:
        request = build_signed_request(
            client,
            wallet=ALICE,
            method="POST",
            url="/v1/optimize",
            body=body,
            receiver_ss58=BOB.ss58_address,
        )
        first = await client.send(request)
        replay = await client.send(request)
    assert first.status_code == 200
    assert first.json()["miner_id"] == BOB.ss58_address
    assert replay.status_code == 401
    assert replay.json()["detail"]["code"] == "auth_replayed"


@pytest.mark.anyio
async def test_wrong_receiver_and_unauthorized_hotkey_fail(tmp_path: Path) -> None:
    app = create_miner_app(
        self_hotkey_ss58=BOB.ss58_address,
        nonce_store=SQLiteNonceStore(tmp_path / "nonces.sqlite3"),
        authorize_hotkey=lambda _hotkey: False,
    )
    body = generate_workload(1).task.model_dump_json().encode()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://miner.test") as client:
        wrong = build_signed_request(
            client,
            wallet=ALICE,
            method="POST",
            url="/v1/optimize",
            body=body,
            receiver_ss58=ALICE.ss58_address,
        )
        forbidden = build_signed_request(
            client,
            wallet=ALICE,
            method="POST",
            url="/v1/optimize",
            body=body,
            receiver_ss58=BOB.ss58_address,
        )
        wrong_response = await client.send(wrong)
        forbidden_response = await client.send(forbidden)
    assert wrong_response.status_code == 401
    assert forbidden_response.status_code == 403


def test_nonce_generator_is_monotonic_when_clock_stalls() -> None:
    generator = FreshNonceGenerator(lambda: 123)
    assert [generator(), generator(), generator()] == [123, 124, 125]


def test_builder_rejects_non_bytes_and_header_injection() -> None:
    with httpx.Client(base_url="https://miner.test") as client:
        with pytest.raises(TypeError):
            build_signed_request(
                client,
                wallet=ALICE,
                method="POST",
                url="/v1/optimize",
                body={"bad": True},  # type: ignore[arg-type]
                receiver_ss58=BOB.ss58_address,
            )
        with pytest.raises(ValueError):
            build_signed_request(
                client,
                wallet=ALICE,
                method="POST",
                url="/v1/optimize",
                body=b"{}",
                receiver_ss58=BOB.ss58_address,
                headers={bt.http_auth.HEADER_SIGNATURE: "forged"},
            )


@pytest.mark.anyio
async def test_stale_signature_is_rejected(tmp_path: Path) -> None:
    app = create_miner_app(
        self_hotkey_ss58=BOB.ss58_address,
        nonce_store=SQLiteNonceStore(tmp_path / "nonces.sqlite3"),
    )
    body = json.dumps(generate_workload(0).task.model_dump(mode="json")).encode()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://miner.test") as client:
        request = build_signed_request(
            client,
            wallet=ALICE,
            method="POST",
            url="/v1/optimize",
            body=body,
            receiver_ss58=BOB.ss58_address,
            nonce_factory=lambda: time.time_ns() - 60_000_000_000,
        )
        response = await client.send(request)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "auth_stale"
