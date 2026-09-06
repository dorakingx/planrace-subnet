"""Bidirectional, receiver-bound response authentication for PlanRace v2."""

from __future__ import annotations

import hmac
import sqlite3
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol

import bittensor as bt

from planrace.models_v2 import (
    OptimizationBundle,
    OptimizationRequestV2,
    SignedOptimizationResponse,
    optimization_bundle_digest,
    optimization_request_digest,
    optimization_response_signing_bytes,
)


class ResponseSigner(Protocol):
    ss58_address: str

    def sign(self, message: bytes) -> bytes: ...


class ResponseReplayStore(Protocol):
    def check_and_store(
        self, *, miner_hotkey: str, request_nonce: int, request_id: str, expires_at_unix_ms: int
    ) -> bool: ...


class MemoryResponseReplayStore:
    """Thread-safe replay protection for tests and single-process demos."""

    def __init__(self, *, max_entries: int = 10_000) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self._keys: dict[tuple[str, int, str], None] = {}
        self._max_entries = max_entries
        self._lock = threading.Lock()

    def check_and_store(
        self, *, miner_hotkey: str, request_nonce: int, request_id: str, expires_at_unix_ms: int
    ) -> bool:
        del expires_at_unix_ms
        key = (miner_hotkey, request_nonce, request_id)
        with self._lock:
            if key in self._keys:
                return False
            if len(self._keys) >= self._max_entries:
                return False
            self._keys[key] = None
            return True


class SQLiteResponseReplayStore:
    """Persistent atomic replay protection for validator processes."""

    def __init__(
        self,
        path: str | Path,
        *,
        clock_unix_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
        max_entries: int = 100_000,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self._path = str(path)
        self._lock = threading.Lock()
        self._clock_unix_ms = clock_unix_ms
        self._max_entries = max_entries
        with sqlite3.connect(self._path) as database:
            database.execute(
                """
                CREATE TABLE IF NOT EXISTS accepted_v2_responses (
                    miner_hotkey TEXT NOT NULL,
                    request_nonce INTEGER NOT NULL,
                    request_id TEXT NOT NULL,
                    expires_at_unix_ms INTEGER NOT NULL,
                    PRIMARY KEY (miner_hotkey, request_nonce, request_id)
                )
                """
            )
            database.execute(
                """CREATE INDEX IF NOT EXISTS accepted_v2_responses_by_expiry
                ON accepted_v2_responses(expires_at_unix_ms)"""
            )

    def check_and_store(
        self, *, miner_hotkey: str, request_nonce: int, request_id: str, expires_at_unix_ms: int
    ) -> bool:
        with self._lock, sqlite3.connect(self._path) as database:
            database.execute(
                "DELETE FROM accepted_v2_responses WHERE expires_at_unix_ms <= ?",
                (self._clock_unix_ms(),),
            )
            count = int(
                database.execute("SELECT COUNT(*) FROM accepted_v2_responses").fetchone()[0]
            )
            if count >= self._max_entries:
                return False
            try:
                database.execute(
                    """
                    INSERT INTO accepted_v2_responses(
                        miner_hotkey, request_nonce, request_id, expires_at_unix_ms
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (miner_hotkey, request_nonce, request_id, expires_at_unix_ms),
                )
            except sqlite3.IntegrityError:
                return False
            return True


class ResponseVerificationError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def resolve_response_signer(wallet_or_signer: object) -> ResponseSigner:
    """Resolve a low-level hotkey signer without ever accessing a coldkey."""

    candidate = getattr(wallet_or_signer, "hotkey", wallet_or_signer)
    if not hasattr(candidate, "ss58_address") or not callable(getattr(candidate, "sign", None)):
        raise TypeError("response signer must expose hotkey ss58_address and sign(bytes)")
    if getattr(candidate, "crypto_type", None) != bt.sp_core.CRYPTO_SR25519:
        raise TypeError("response signer must be an sr25519 hotkey")
    return candidate  # type: ignore[return-value]


def sign_optimization_response(
    *,
    request: OptimizationRequestV2,
    artifact: OptimizationBundle,
    miner_signer: object,
    issued_at_unix_ms: int,
    expires_at_unix_ms: int,
) -> SignedOptimizationResponse:
    """Bind the complete artifact to both peers, request, nonce, task, and time."""

    signer = resolve_response_signer(miner_signer)
    if signer.ss58_address != request.miner_hotkey:
        raise ValueError("signer does not match request miner_hotkey")
    if artifact.task_id != request.task.task_id:
        raise ValueError("artifact belongs to a different task")
    if artifact.engine_image_digest != request.task.engine_image_digest:
        raise ValueError("artifact engine digest does not match task")
    if issued_at_unix_ms < request.issued_at_unix_ms:
        raise ValueError("response cannot predate request")
    if expires_at_unix_ms > request.expires_at_unix_ms:
        raise ValueError("response cannot outlive request")
    placeholder = SignedOptimizationResponse(
        request_id=request.request_id,
        task_id=request.task.task_id,
        request_digest=optimization_request_digest(request),
        validator_hotkey=request.validator_hotkey,
        miner_hotkey=request.miner_hotkey,
        request_nonce=request.request_nonce,
        issued_at_unix_ms=issued_at_unix_ms,
        expires_at_unix_ms=expires_at_unix_ms,
        artifact_digest=artifact.artifact_digest,
        artifact=artifact,
        signature="0" * 128,
    )
    signature = signer.sign(optimization_response_signing_bytes(placeholder))
    if not isinstance(signature, bytes) or len(signature) != 64:
        raise ValueError("hotkey signer returned an invalid signature")
    return SignedOptimizationResponse(
        **placeholder.model_dump(mode="python", exclude={"signature"}),
        signature=signature.hex(),
    )


def verify_signed_response(
    response: SignedOptimizationResponse,
    *,
    request: OptimizationRequestV2,
    expected_miner_uid: int,
    metagraph_hotkeys: Mapping[int, str],
    replay_store: ResponseReplayStore,
    now_unix_ms: int,
    max_clock_skew_ms: int = 5_000,
) -> OptimizationBundle:
    """Verify a response before it reaches lifecycle storage or a sandbox."""

    if max_clock_skew_ms < 0:
        raise ValueError("max_clock_skew_ms cannot be negative")
    if metagraph_hotkeys.get(expected_miner_uid) != request.miner_hotkey:
        raise ResponseVerificationError("metagraph_identity_mismatch")
    if response.miner_hotkey != request.miner_hotkey:
        raise ResponseVerificationError("wrong_miner")
    if response.validator_hotkey != request.validator_hotkey:
        raise ResponseVerificationError("wrong_receiver")
    if response.request_id != request.request_id:
        raise ResponseVerificationError("wrong_request")
    if response.task_id != request.task.task_id:
        raise ResponseVerificationError("wrong_task")
    if response.request_nonce != request.request_nonce:
        raise ResponseVerificationError("wrong_nonce")
    expected_request_digest = optimization_request_digest(request)
    if not hmac.compare_digest(response.request_digest, expected_request_digest):
        raise ResponseVerificationError("request_digest_mismatch")
    if response.artifact.engine_image_digest != request.task.engine_image_digest:
        raise ResponseVerificationError("engine_digest_mismatch")
    calculated_artifact_digest = optimization_bundle_digest(response.artifact)
    if not hmac.compare_digest(response.artifact_digest, calculated_artifact_digest):
        raise ResponseVerificationError("artifact_digest_mismatch")
    if response.issued_at_unix_ms < request.issued_at_unix_ms - max_clock_skew_ms:
        raise ResponseVerificationError("response_predates_request")
    if response.issued_at_unix_ms > now_unix_ms + max_clock_skew_ms:
        raise ResponseVerificationError("response_from_future")
    if response.expires_at_unix_ms > request.expires_at_unix_ms:
        raise ResponseVerificationError("response_outlives_request")
    if response.expires_at_unix_ms < now_unix_ms:
        raise ResponseVerificationError("response_expired")
    try:
        public_key = bt.sp_core.Keypair(ss58_address=response.miner_hotkey)
        signature_ok = public_key.verify(
            optimization_response_signing_bytes(response), bytes.fromhex(response.signature)
        )
    except (TypeError, ValueError):
        signature_ok = False
    if not signature_ok:
        raise ResponseVerificationError("bad_signature")
    if not replay_store.check_and_store(
        miner_hotkey=response.miner_hotkey,
        request_nonce=response.request_nonce,
        request_id=response.request_id,
        expires_at_unix_ms=response.expires_at_unix_ms,
    ):
        raise ResponseVerificationError("response_replayed")
    return response.artifact
