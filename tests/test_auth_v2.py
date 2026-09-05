import asyncio
from pathlib import Path

import bittensor as bt
import httpx
import pytest

from planrace.api_v2 import create_miner_app_v2
from planrace.auth import build_signed_request
from planrace.auth_v2 import (
    MemoryResponseReplayStore,
    ResponseReplayStore,
    ResponseVerificationError,
    SQLiteResponseReplayStore,
    resolve_response_signer,
    sign_optimization_response,
    verify_signed_response,
)
from planrace.models_v2 import (
    BundleMetadata,
    HiddenFixtureDescriptor,
    OptimizationBundle,
    OptimizationRequestV2,
    ParameterRange,
    PublicTaskV2,
    PublicTrainingFixture,
    PublishedStatistics,
    SignedOptimizationResponse,
    domain_separated_digest,
)
from planrace.nonce import SQLiteNonceStore
from planrace.taskgen_v2 import (
    LifecycleError,
    PrivateTaskV2,
    TaskLifecycleV2,
    TaskPhase,
    create_task_v2,
)
from planrace.validator_client_v2 import request_optimization_v2

ALICE = bt.sp_core.Keypair.create_from_uri("//Alice")
BOB = bt.sp_core.Keypair.create_from_uri("//Bob")
CHARLIE = bt.sp_core.Keypair.create_from_uri("//Charlie")
NOW_MS = 1_000_000


class FixedEntropy:
    def __init__(self) -> None:
        self.values = [b"t" * 16, b"s" * 32, b"z" * 32]

    def token_bytes(self, size: int) -> bytes:
        value = self.values.pop(0)
        assert len(value) == size
        return value


def fixtures(seed: bytes) -> tuple[HiddenFixtureDescriptor, ...]:
    return tuple(
        HiddenFixtureDescriptor(
            fixture_id=f"holdout_{index}",
            content_digest=domain_separated_digest(
                "planrace/2:auth-test-fixture", {"index": index, "seed": seed.hex()}
            ),
            parameter_set_digest=domain_separated_digest(
                "planrace/2:auth-test-params", {"index": index}
            ),
            row_count=100,
        )
        for index in range(2)
    )


def private_task_state() -> PrivateTaskV2:
    return create_task_v2(
        validator_hotkey=ALICE.ss58_address,
        engine_image_digest="sha256:" + "1" * 64,
        generator_source_digest="sha256:" + "2" * 64,
        benchmark_policy_digest="sha256:" + "3" * 64,
        schema_sql="CREATE TABLE t(id INTEGER PRIMARY KEY)",
        reference_sql="SELECT id FROM t ORDER BY id",
        public_training_fixture=PublicTrainingFixture(
            fixture_id="training",
            generator_seed_hex="4" * 64,
            content_digest="sha256:" + "5" * 64,
            row_count=10,
        ),
        parameter_ranges=(
            ParameterRange(
                name="limit_value",
                value_type="integer",
                minimum=1,
                maximum=100,
                distribution="uniform",
            ),
        ),
        published_statistics=PublishedStatistics(
            row_count_min=0,
            row_count_max=10_000,
            selectivity_min_bps=0,
            selectivity_max_bps=10_000,
            data_profiles=("uniform", "skewed"),
        ),
        deadline_unix_ms=2_000_000,
        hidden_fixture_factory=fixtures,
        entropy=FixedEntropy(),
    )


def task() -> PublicTaskV2:
    return private_task_state().public


def request_model(
    *, issued_at: int = NOW_MS, expires_at: int = NOW_MS + 10_000
) -> OptimizationRequestV2:
    public = task()
    return OptimizationRequestV2(
        request_id="ab" * 16,
        task=public,
        validator_hotkey=ALICE.ss58_address,
        miner_hotkey=BOB.ss58_address,
        request_nonce=123_456,
        issued_at_unix_ms=issued_at,
        expires_at_unix_ms=expires_at,
    )


def artifact(request: OptimizationRequestV2) -> OptimizationBundle:
    return OptimizationBundle.create(
        task_id=request.task.task_id,
        engine_image_digest=request.task.engine_image_digest,
        indexes=(),
        metadata=BundleMetadata(
            strategy="baseline",
            estimated_intent="no_index",
            rationale="A signed constant baseline artifact.",
        ),
    )


def signed_response(request: OptimizationRequestV2) -> SignedOptimizationResponse:
    return sign_optimization_response(
        request=request,
        artifact=artifact(request),
        miner_signer=BOB,
        issued_at_unix_ms=NOW_MS,
        expires_at_unix_ms=request.expires_at_unix_ms,
    )


def verify(
    response: SignedOptimizationResponse,
    request: OptimizationRequestV2,
    store: ResponseReplayStore | None = None,
    now: int = NOW_MS,
) -> OptimizationBundle:
    return verify_signed_response(
        response,
        request=request,
        expected_miner_uid=7,
        metagraph_hotkeys={7: BOB.ss58_address},
        replay_store=store or MemoryResponseReplayStore(),
        now_unix_ms=now,
    )


def test_signed_response_validates_and_replay_fails() -> None:
    request = request_model()
    response = signed_response(request)
    store = MemoryResponseReplayStore()
    assert verify(response, request, store=store) == response.artifact
    with pytest.raises(ResponseVerificationError, match="response_replayed"):
        verify(response, request, store=store)


def test_memory_response_replay_store_is_bounded() -> None:
    store = MemoryResponseReplayStore(max_entries=2)
    assert store.check_and_store(
        miner_hotkey="a", request_nonce=1, request_id="one", expires_at_unix_ms=1
    )
    assert store.check_and_store(
        miner_hotkey="a", request_nonce=2, request_id="two", expires_at_unix_ms=1
    )
    assert store.check_and_store(
        miner_hotkey="a", request_nonce=3, request_id="three", expires_at_unix_ms=1
    )
    # The oldest demo-only entry is evicted; production uses SQLite retention.
    assert store.check_and_store(
        miner_hotkey="a", request_nonce=1, request_id="one", expires_at_unix_ms=1
    )


def test_lifecycle_accepts_only_verified_on_time_unique_responses() -> None:
    private = private_task_state()
    request = OptimizationRequestV2(
        request_id="ab" * 16,
        task=private.public,
        validator_hotkey=ALICE.ss58_address,
        miner_hotkey=BOB.ss58_address,
        request_nonce=123_456,
        issued_at_unix_ms=NOW_MS,
        expires_at_unix_ms=NOW_MS + 10_000,
    )
    response = signed_response(request)
    verified = verify(response, request)
    assert verified == response.artifact
    lifecycle = TaskLifecycleV2(private)
    assert lifecycle.phase is TaskPhase.OPEN
    with pytest.raises(LifecycleError, match="submissions_not_sealed"):
        lifecycle.sealed_bundles()
    lifecycle.submit_verified(
        response,
        request=request,
        expected_miner_uid=7,
        metagraph_hotkeys={7: BOB.ss58_address},
        replay_store=MemoryResponseReplayStore(),
        now_unix_ms=NOW_MS,
    )
    with pytest.raises(LifecycleError, match="wrong_task"):
        lifecycle.submit_verified(
            response.model_copy(update={"task_id": "ff" * 16}),
            request=request,
            expected_miner_uid=7,
            metagraph_hotkeys={7: BOB.ss58_address},
            replay_store=MemoryResponseReplayStore(),
            now_unix_ms=NOW_MS,
        )
    with pytest.raises(LifecycleError, match="duplicate_request"):
        lifecycle.submit_verified(
            response,
            request=request,
            expected_miner_uid=7,
            metagraph_hotkeys={7: BOB.ss58_address},
            replay_store=MemoryResponseReplayStore(),
            now_unix_ms=NOW_MS,
        )
    sealed = lifecycle.seal(now_unix_ms=private.public.deadline_unix_ms)
    assert sealed == (response,)
    assert lifecycle.sealed_bundles() == (response.artifact,)
    reveal = lifecycle.reveal(now_unix_ms=private.public.deadline_unix_ms)
    assert reveal == private.reveal
    with pytest.raises(LifecycleError, match="already_revealed"):
        lifecycle.seal(now_unix_ms=private.public.deadline_unix_ms)


def test_lifecycle_cannot_store_an_unverified_forged_response() -> None:
    private = private_task_state()
    request = OptimizationRequestV2(
        request_id="ab" * 16,
        task=private.public,
        validator_hotkey=ALICE.ss58_address,
        miner_hotkey=BOB.ss58_address,
        request_nonce=123_456,
        issued_at_unix_ms=NOW_MS,
        expires_at_unix_ms=NOW_MS + 10_000,
    )
    forged = signed_response(request).model_copy(update={"signature": "0" * 128})
    lifecycle = TaskLifecycleV2(private)
    with pytest.raises(ResponseVerificationError, match="bad_signature"):
        lifecycle.submit_verified(
            forged,
            request=request,
            expected_miner_uid=7,
            metagraph_hotkeys={7: BOB.ss58_address},
            replay_store=MemoryResponseReplayStore(),
            now_unix_ms=NOW_MS,
        )
    assert lifecycle.phase is TaskPhase.OPEN
    with pytest.raises(LifecycleError, match="submissions_not_sealed"):
        lifecycle.sealed_bundles()


@pytest.mark.parametrize(
    ("field", "replacement", "code"),
    [
        ("validator_hotkey", CHARLIE.ss58_address, "wrong_receiver"),
        ("miner_hotkey", CHARLIE.ss58_address, "wrong_miner"),
        ("request_id", "cd" * 16, "wrong_request"),
        ("task_id", "ef" * 16, "wrong_task"),
        ("request_nonce", 99, "wrong_nonce"),
        ("request_digest", "sha256:" + "9" * 64, "request_digest_mismatch"),
    ],
)
def test_response_binding_rejects_mismatch(field: str, replacement: object, code: str) -> None:
    request = request_model()
    tampered = signed_response(request).model_copy(update={field: replacement})
    with pytest.raises(ResponseVerificationError, match=code):
        verify(tampered, request)


def test_signature_artifact_and_engine_tampering_fail() -> None:
    request = request_model()
    response = signed_response(request)
    replacement = ("0" if response.signature[0] != "0" else "1") + response.signature[1:]
    with pytest.raises(ResponseVerificationError, match="bad_signature"):
        verify(response.model_copy(update={"signature": replacement}), request)

    changed_artifact = response.artifact.model_copy(
        update={"metadata": response.artifact.metadata.model_copy(update={"rationale": "changed"})}
    )
    with pytest.raises(ResponseVerificationError, match="artifact_digest_mismatch"):
        verify(response.model_copy(update={"artifact": changed_artifact}), request)

    wrong_engine = response.artifact.model_copy(
        update={"engine_image_digest": "sha256:" + "8" * 64}
    )
    with pytest.raises(ResponseVerificationError, match="engine_digest_mismatch"):
        verify(response.model_copy(update={"artifact": wrong_engine}), request)


def test_stale_future_and_metagraph_mismatch_fail() -> None:
    request = request_model()
    response = signed_response(request)
    with pytest.raises(ResponseVerificationError, match="response_expired"):
        verify(response, request, now=request.expires_at_unix_ms + 1)
    future = sign_optimization_response(
        request=request,
        artifact=artifact(request),
        miner_signer=BOB,
        issued_at_unix_ms=NOW_MS + 6_000,
        expires_at_unix_ms=request.expires_at_unix_ms,
    )
    with pytest.raises(ResponseVerificationError, match="response_from_future"):
        verify(future, request)
    with pytest.raises(ResponseVerificationError, match="metagraph_identity_mismatch"):
        verify_signed_response(
            response,
            request=request,
            expected_miner_uid=7,
            metagraph_hotkeys={7: CHARLIE.ss58_address},
            replay_store=MemoryResponseReplayStore(),
            now_unix_ms=NOW_MS,
        )


def test_signer_must_match_expected_miner() -> None:
    request = request_model()
    with pytest.raises(ValueError, match="signer"):
        sign_optimization_response(
            request=request,
            artifact=artifact(request),
            miner_signer=CHARLIE,
            issued_at_unix_ms=NOW_MS,
            expires_at_unix_ms=request.expires_at_unix_ms,
        )


def test_response_signing_fails_closed_on_invalid_inputs() -> None:
    request = request_model()
    good_artifact = artifact(request)
    with pytest.raises(TypeError, match="signer"):
        resolve_response_signer(object())
    ed25519_signer = bt.sp_core.Keypair.create_from_uri(
        "//Bob", crypto_type=bt.sp_core.CRYPTO_ED25519
    )
    with pytest.raises(TypeError, match="sr25519"):
        resolve_response_signer(ed25519_signer)
    with pytest.raises(ValueError, match="different task"):
        sign_optimization_response(
            request=request,
            artifact=good_artifact.model_copy(update={"task_id": "ff" * 16}),
            miner_signer=BOB,
            issued_at_unix_ms=NOW_MS,
            expires_at_unix_ms=request.expires_at_unix_ms,
        )
    with pytest.raises(ValueError, match="engine"):
        sign_optimization_response(
            request=request,
            artifact=good_artifact.model_copy(update={"engine_image_digest": "sha256:" + "f" * 64}),
            miner_signer=BOB,
            issued_at_unix_ms=NOW_MS,
            expires_at_unix_ms=request.expires_at_unix_ms,
        )
    with pytest.raises(ValueError, match="predate"):
        sign_optimization_response(
            request=request,
            artifact=good_artifact,
            miner_signer=BOB,
            issued_at_unix_ms=NOW_MS - 1,
            expires_at_unix_ms=request.expires_at_unix_ms,
        )
    with pytest.raises(ValueError, match="outlive"):
        sign_optimization_response(
            request=request,
            artifact=good_artifact,
            miner_signer=BOB,
            issued_at_unix_ms=NOW_MS,
            expires_at_unix_ms=request.expires_at_unix_ms + 1,
        )

    class BadSigner:
        ss58_address = BOB.ss58_address
        crypto_type = bt.sp_core.CRYPTO_SR25519

        def sign(self, _message: bytes) -> bytes:
            return b"short"

    with pytest.raises(ValueError, match="invalid signature"):
        sign_optimization_response(
            request=request,
            artifact=good_artifact,
            miner_signer=BadSigner(),
            issued_at_unix_ms=NOW_MS,
            expires_at_unix_ms=request.expires_at_unix_ms,
        )


def test_response_verifier_rejects_invalid_time_policy() -> None:
    request = request_model()
    response = signed_response(request)
    with pytest.raises(ValueError, match="negative"):
        verify_signed_response(
            response,
            request=request,
            expected_miner_uid=7,
            metagraph_hotkeys={7: BOB.ss58_address},
            replay_store=MemoryResponseReplayStore(),
            now_unix_ms=NOW_MS,
            max_clock_skew_ms=-1,
        )
    with pytest.raises(ResponseVerificationError, match="predates"):
        verify(
            response.model_copy(update={"issued_at_unix_ms": NOW_MS - 5_001}),
            request,
        )
    with pytest.raises(ResponseVerificationError, match="outlives"):
        verify(
            response.model_copy(update={"expires_at_unix_ms": request.expires_at_unix_ms + 1}),
            request,
        )


def test_signed_response_model_rejects_broken_internal_links() -> None:
    request = request_model()
    response = signed_response(request)
    for update in (
        {"task_id": "ff" * 16},
        {"artifact_digest": "sha256:" + "f" * 64},
        {"expires_at_unix_ms": response.issued_at_unix_ms},
    ):
        raw = response.model_dump(mode="python")
        raw.update(update)
        with pytest.raises(ValueError):
            type(response).model_validate(raw)


def test_sqlite_response_replay_store_is_persistent(tmp_path: Path) -> None:
    path = tmp_path / "responses.sqlite3"
    first = SQLiteResponseReplayStore(path, clock_unix_ms=lambda: 1_000)
    assert first.check_and_store(
        miner_hotkey=BOB.ss58_address,
        request_nonce=1,
        request_id="a" * 32,
        expires_at_unix_ms=2_000,
    )
    reopened = SQLiteResponseReplayStore(path, clock_unix_ms=lambda: 1_000)
    assert not reopened.check_and_store(
        miner_hotkey=BOB.ss58_address,
        request_nonce=1,
        request_id="a" * 32,
        expires_at_unix_ms=2_000,
    )


def test_miner_service_requires_explicit_authorizer(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="authorize_hotkey"):
        create_miner_app_v2(
            miner_wallet_or_signer=BOB,
            nonce_store=SQLiteNonceStore(tmp_path / "closed.sqlite3"),
        )


@pytest.mark.anyio
async def test_miner_strategy_is_bounded_by_request_deadline(tmp_path: Path) -> None:
    async def slow_strategy(public: PublicTaskV2) -> OptimizationBundle:
        await asyncio.sleep(0.05)
        return artifact(request_model(expires_at=NOW_MS + 1).model_copy(update={"task": public}))

    app = create_miner_app_v2(
        miner_wallet_or_signer=BOB,
        nonce_store=SQLiteNonceStore(tmp_path / "deadline.sqlite3"),
        strategy=slow_strategy,
        authorize_hotkey=lambda _hotkey: True,
        clock_unix_ms=lambda: NOW_MS,
    )
    request = request_model(expires_at=NOW_MS + 1)
    body = request.model_dump_json().encode()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://miner.test") as client:
        signed = build_signed_request(
            client,
            wallet=ALICE,
            method="POST",
            url="/v2/optimize",
            body=body,
            receiver_ss58=BOB.ss58_address,
            headers={"content-type": "application/json"},
        )
        response = await client.send(signed)
    assert response.status_code == 408
    assert response.json()["detail"]["code"] == "strategy_deadline_elapsed"


@pytest.mark.anyio
async def test_end_to_end_authenticated_request_and_signed_response(tmp_path: Path) -> None:
    app = create_miner_app_v2(
        miner_wallet_or_signer=BOB,
        nonce_store=SQLiteNonceStore(tmp_path / "request-nonces.sqlite3"),
        authorize_hotkey=lambda hotkey: hotkey == ALICE.ss58_address,
        clock_unix_ms=lambda: NOW_MS,
    )
    request = request_model()
    response_replays = MemoryResponseReplayStore()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://miner.test", trust_env=False
    ) as client:
        outcome = await request_optimization_v2(
            client,
            wallet=ALICE,
            endpoint="/v2/optimize",
            receiver_ss58=BOB.ss58_address,
            request_model=request,
            expected_miner_uid=7,
            metagraph_hotkeys={7: BOB.ss58_address},
            replay_store=response_replays,
            clock_unix_ms=lambda: NOW_MS,
            allow_local_endpoint_for_tests=True,
        )
        replay = await request_optimization_v2(
            client,
            wallet=ALICE,
            endpoint="/v2/optimize",
            receiver_ss58=BOB.ss58_address,
            request_model=request,
            expected_miner_uid=7,
            metagraph_hotkeys={7: BOB.ss58_address},
            replay_store=response_replays,
            clock_unix_ms=lambda: NOW_MS,
            allow_local_endpoint_for_tests=True,
        )
    assert outcome.accepted
    assert outcome.response is not None
    assert outcome.response.miner_hotkey == BOB.ss58_address
    assert not replay.accepted
    assert replay.failure_code == "response_replayed"


@pytest.mark.anyio
async def test_miner_api_rejects_malformed_identity_and_time_windows(tmp_path: Path) -> None:
    app = create_miner_app_v2(
        miner_wallet_or_signer=BOB,
        nonce_store=SQLiteNonceStore(tmp_path / "api-branches.sqlite3"),
        authorize_hotkey=lambda _hotkey: True,
        clock_unix_ms=lambda: NOW_MS,
    )
    base = request_model()
    cases = (
        (b"{", 422, "task_validation_failed"),
        (
            base.model_copy(update={"miner_hotkey": CHARLIE.ss58_address})
            .model_dump_json()
            .encode(),
            403,
            "wrong_receiver",
        ),
        (
            base.model_copy(
                update={
                    "issued_at_unix_ms": NOW_MS + 6_000,
                    "expires_at_unix_ms": NOW_MS + 7_000,
                }
            )
            .model_dump_json()
            .encode(),
            422,
            "request_from_future",
        ),
        (
            base.model_copy(
                update={
                    "issued_at_unix_ms": NOW_MS - 100,
                    "expires_at_unix_ms": NOW_MS,
                }
            )
            .model_dump_json()
            .encode(),
            408,
            "request_expired",
        ),
        (
            base.model_copy(
                update={
                    "issued_at_unix_ms": NOW_MS - 200_000,
                    "expires_at_unix_ms": NOW_MS + 1,
                }
            )
            .model_dump_json()
            .encode(),
            422,
            "request_lifetime_too_long",
        ),
        (
            base.model_copy(
                update={"task": base.task.model_copy(update={"deadline_unix_ms": NOW_MS})}
            )
            .model_dump_json()
            .encode(),
            408,
            "task_deadline_elapsed",
        ),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://miner.test") as client:
        health = await client.get("/health")
        assert health.json() == {"status": "ok", "protocol": "planrace/2"}
        for body, status, code in cases:
            signed = build_signed_request(
                client,
                wallet=ALICE,
                method="POST",
                url="/v2/optimize",
                body=body,
                receiver_ss58=BOB.ss58_address,
                headers={"content-type": "application/json"},
            )
            response = await client.send(signed)
            assert response.status_code == status
            assert response.json()["detail"]["code"] == code


@pytest.mark.anyio
async def test_miner_rejects_body_validator_different_from_http_signer(tmp_path: Path) -> None:
    app = create_miner_app_v2(
        miner_wallet_or_signer=BOB,
        nonce_store=SQLiteNonceStore(tmp_path / "nonces.sqlite3"),
        authorize_hotkey=lambda _hotkey: True,
        clock_unix_ms=lambda: NOW_MS,
    )
    body = request_model().model_dump_json().encode()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://miner.test") as client:
        signed = build_signed_request(
            client,
            wallet=CHARLIE,
            method="POST",
            url="/v2/optimize",
            body=body,
            receiver_ss58=BOB.ss58_address,
            headers={"content-type": "application/json"},
        )
        response = await client.send(signed)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "validator_identity_mismatch"


@pytest.mark.anyio
async def test_validator_client_rejects_oversized_stream_before_parsing() -> None:
    request = request_model()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-length": "999999", "content-type": "application/json"},
            content=b"{}",
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://miner.test",
        trust_env=False,
    ) as client:
        outcome = await request_optimization_v2(
            client,
            wallet=ALICE,
            endpoint="/v2/optimize",
            receiver_ss58=BOB.ss58_address,
            request_model=request,
            expected_miner_uid=7,
            metagraph_hotkeys={7: BOB.ss58_address},
            replay_store=MemoryResponseReplayStore(),
            clock_unix_ms=lambda: NOW_MS,
            max_response_bytes=1024,
            allow_local_endpoint_for_tests=True,
        )
    assert outcome.failure_code == "response_too_large"


@pytest.mark.anyio
async def test_validator_client_maps_explicit_transport_timeout() -> None:
    request = request_model()

    def handler(incoming: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("simulated", request=incoming)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://miner.test",
        trust_env=False,
    ) as client:
        outcome = await request_optimization_v2(
            client,
            wallet=ALICE,
            endpoint="/v2/optimize",
            receiver_ss58=BOB.ss58_address,
            request_model=request,
            expected_miner_uid=7,
            metagraph_hotkeys={7: BOB.ss58_address},
            replay_store=MemoryResponseReplayStore(),
            clock_unix_ms=lambda: NOW_MS,
            allow_local_endpoint_for_tests=True,
        )
    assert outcome.failure_code == "timeout"


@pytest.mark.anyio
async def test_validator_client_fails_closed_on_receiver_and_response_errors() -> None:
    request = request_model()
    async with httpx.AsyncClient(base_url="https://miner.test") as unused_client:
        receiver = await request_optimization_v2(
            unused_client,
            wallet=ALICE,
            endpoint="/v2/optimize",
            receiver_ss58=CHARLIE.ss58_address,
            request_model=request,
            expected_miner_uid=7,
            metagraph_hotkeys={7: BOB.ss58_address},
            replay_store=MemoryResponseReplayStore(),
            now_unix_ms=NOW_MS,
        )
        assert receiver.failure_code == "receiver_mismatch"
        with pytest.raises(ValueError, match="positive"):
            await request_optimization_v2(
                unused_client,
                wallet=ALICE,
                endpoint="/v2/optimize",
                receiver_ss58=BOB.ss58_address,
                request_model=request,
                expected_miner_uid=7,
                metagraph_hotkeys={7: BOB.ss58_address},
                replay_store=MemoryResponseReplayStore(),
                now_unix_ms=NOW_MS,
                max_response_bytes=0,
            )

    def status_handler(_incoming: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=b"unavailable")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(status_handler),
        base_url="https://miner.test",
        trust_env=False,
    ) as client:
        status = await request_optimization_v2(
            client,
            wallet=ALICE,
            endpoint="/v2/optimize",
            receiver_ss58=BOB.ss58_address,
            request_model=request,
            expected_miner_uid=7,
            metagraph_hotkeys={7: BOB.ss58_address},
            replay_store=MemoryResponseReplayStore(),
            clock_unix_ms=lambda: NOW_MS,
            allow_local_endpoint_for_tests=True,
        )
    assert status.failure_code == "http_error"
    assert status.status_code == 503

    def invalid_handler(_incoming: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=b"{}",
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(invalid_handler),
        base_url="https://miner.test",
        trust_env=False,
    ) as client:
        invalid = await request_optimization_v2(
            client,
            wallet=ALICE,
            endpoint="/v2/optimize",
            receiver_ss58=BOB.ss58_address,
            request_model=request,
            expected_miner_uid=7,
            metagraph_hotkeys={7: BOB.ss58_address},
            replay_store=MemoryResponseReplayStore(),
            clock_unix_ms=lambda: NOW_MS,
            allow_local_endpoint_for_tests=True,
        )
    assert invalid.failure_code == "response_validation_failed"


@pytest.mark.anyio
async def test_validator_client_maps_non_timeout_transport_error() -> None:
    request = request_model()

    def handler(incoming: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated", request=incoming)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://miner.test",
        trust_env=False,
    ) as client:
        outcome = await request_optimization_v2(
            client,
            wallet=ALICE,
            endpoint="/v2/optimize",
            receiver_ss58=BOB.ss58_address,
            request_model=request,
            expected_miner_uid=7,
            metagraph_hotkeys={7: BOB.ss58_address},
            replay_store=MemoryResponseReplayStore(),
            clock_unix_ms=lambda: NOW_MS,
            allow_local_endpoint_for_tests=True,
        )
    assert outcome.failure_code == "transport_error"


@pytest.mark.anyio
async def test_validator_client_rejects_private_endpoint_without_test_opt_in() -> None:
    request = request_model()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(500)),
        trust_env=False,
    ) as client:
        outcome = await request_optimization_v2(
            client,
            wallet=ALICE,
            endpoint="http://127.0.0.1/v2/optimize",
            receiver_ss58=BOB.ss58_address,
            request_model=request,
            expected_miner_uid=7,
            metagraph_hotkeys={7: BOB.ss58_address},
            replay_store=MemoryResponseReplayStore(),
            clock_unix_ms=lambda: NOW_MS,
        )
    assert outcome.failure_code == "endpoint_forbidden"


@pytest.mark.anyio
async def test_validator_client_rejects_hostname_to_remove_dns_rebinding_window() -> None:
    request = request_model()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(500)),
        trust_env=False,
    ) as client:
        outcome = await request_optimization_v2(
            client,
            wallet=ALICE,
            endpoint="https://miner.example/v2/optimize",
            receiver_ss58=BOB.ss58_address,
            request_model=request,
            expected_miner_uid=7,
            metagraph_hotkeys={7: BOB.ss58_address},
            replay_store=MemoryResponseReplayStore(),
            clock_unix_ms=lambda: NOW_MS,
        )
    assert outcome.failure_code == "endpoint_forbidden"


@pytest.mark.anyio
async def test_validator_client_rejects_unsafe_ambient_proxy_configuration() -> None:
    request = request_model()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(500)),
        trust_env=True,
    ) as client:
        outcome = await request_optimization_v2(
            client,
            wallet=ALICE,
            endpoint="https://miner.example/v2/optimize",
            receiver_ss58=BOB.ss58_address,
            request_model=request,
            expected_miner_uid=7,
            metagraph_hotkeys={7: BOB.ss58_address},
            replay_store=MemoryResponseReplayStore(),
            clock_unix_ms=lambda: NOW_MS,
        )
    assert outcome.failure_code == "client_configuration_unsafe"


@pytest.mark.anyio
async def test_validator_client_enforces_total_monotonic_deadline() -> None:
    request = request_model()

    async def handler(_incoming: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.05)
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=signed_response(request).model_dump_json().encode(),
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://miner.test",
        trust_env=False,
    ) as client:
        outcome = await request_optimization_v2(
            client,
            wallet=ALICE,
            endpoint="/v2/optimize",
            receiver_ss58=BOB.ss58_address,
            request_model=request,
            expected_miner_uid=7,
            metagraph_hotkeys={7: BOB.ss58_address},
            replay_store=MemoryResponseReplayStore(),
            clock_unix_ms=lambda: NOW_MS,
            total_timeout_seconds=0.001,
            allow_local_endpoint_for_tests=True,
        )
    assert outcome.failure_code == "timeout"


@pytest.mark.anyio
async def test_validator_samples_clock_only_after_stream_completion() -> None:
    request = request_model()
    payload = signed_response(request).model_dump_json().encode()

    class CompletingStream(httpx.AsyncByteStream):
        complete = False

        async def __aiter__(self):  # type: ignore[no-untyped-def]
            midpoint = len(payload) // 2
            yield payload[:midpoint]
            await asyncio.sleep(0)
            yield payload[midpoint:]
            self.complete = True

    stream = CompletingStream()

    def handler(_incoming: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            stream=stream,
        )

    def clock() -> int:
        assert stream.complete
        return NOW_MS

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://miner.test",
        trust_env=False,
    ) as client:
        outcome = await request_optimization_v2(
            client,
            wallet=ALICE,
            endpoint="/v2/optimize",
            receiver_ss58=BOB.ss58_address,
            request_model=request,
            expected_miner_uid=7,
            metagraph_hotkeys={7: BOB.ss58_address},
            replay_store=MemoryResponseReplayStore(),
            now_unix_ms=0,
            clock_unix_ms=clock,
            allow_local_endpoint_for_tests=True,
        )
    assert outcome.accepted


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("headers", "maximum", "expected"),
    [
        (
            {"content-type": "application/json", "x-oversized": "x" * 256},
            64,
            "response_headers_too_large",
        ),
        ({"content-type": "text/plain"}, 16 * 1024, "response_headers_invalid"),
    ],
)
async def test_validator_rejects_invalid_or_oversized_response_headers(
    headers: dict[str, str], maximum: int, expected: str
) -> None:
    request = request_model()

    def handler(_incoming: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers=headers, content=b"{}")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://miner.test",
        trust_env=False,
    ) as client:
        outcome = await request_optimization_v2(
            client,
            wallet=ALICE,
            endpoint="/v2/optimize",
            receiver_ss58=BOB.ss58_address,
            request_model=request,
            expected_miner_uid=7,
            metagraph_hotkeys={7: BOB.ss58_address},
            replay_store=MemoryResponseReplayStore(),
            clock_unix_ms=lambda: NOW_MS,
            max_response_header_bytes=maximum,
            allow_local_endpoint_for_tests=True,
        )
    assert outcome.failure_code == expected
