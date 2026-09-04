"""Authenticated miner service that returns signed PlanRace v2 bundles."""

from __future__ import annotations

import inspect
import time
from collections.abc import Awaitable, Callable

import bittensor as bt
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from planrace.auth import AuthorizationHook, authenticate_request
from planrace.auth_v2 import resolve_response_signer, sign_optimization_response
from planrace.models_v2 import (
    BundleMetadata,
    OptimizationBundle,
    OptimizationRequestV2,
    PublicTaskV2,
    SignedOptimizationResponse,
)

MAX_V2_REQUEST_BYTES = 256 * 1024
MAX_REQUEST_LIFETIME_MS = 120_000

V2Strategy = Callable[[PublicTaskV2], OptimizationBundle | Awaitable[OptimizationBundle]]


def no_index_strategy(task: PublicTaskV2) -> OptimizationBundle:
    """Safe baseline miner: a valid structured bundle containing no indexes."""

    return OptimizationBundle.create(
        task_id=task.task_id,
        engine_image_digest=task.engine_image_digest,
        indexes=(),
        metadata=BundleMetadata(
            strategy="no-index-baseline",
            estimated_intent="no_index",
            rationale="Return the fixed reference-query baseline.",
        ),
    )


def create_miner_app_v2(
    *,
    miner_wallet_or_signer: object,
    nonce_store: bt.http_auth.NonceStore,
    strategy: V2Strategy = no_index_strategy,
    authorize_hotkey: AuthorizationHook | None = None,
    clock_unix_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
) -> FastAPI:
    signer = resolve_response_signer(miner_wallet_or_signer)
    self_hotkey_ss58 = signer.ss58_address
    app = FastAPI(title="PlanRace v2 Miner", version="0.2.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "protocol": "planrace/2"}

    @app.post("/v2/optimize", response_model=SignedOptimizationResponse)
    async def optimize(request: Request) -> SignedOptimizationResponse:
        authenticated = await authenticate_request(
            request,
            self_hotkey_ss58=self_hotkey_ss58,
            nonce_store=nonce_store,
            max_body_bytes=MAX_V2_REQUEST_BYTES,
            authorize_hotkey=authorize_hotkey,
        )
        try:
            request_model = OptimizationRequestV2.model_validate_json(authenticated.raw_body)
        except ValidationError:
            raise HTTPException(
                status_code=422, detail={"code": "task_validation_failed"}
            ) from None
        if authenticated.caller.hotkey_ss58 != request_model.validator_hotkey:
            raise HTTPException(status_code=403, detail={"code": "validator_identity_mismatch"})
        if request_model.miner_hotkey != self_hotkey_ss58:
            raise HTTPException(status_code=403, detail={"code": "wrong_receiver"})
        now = clock_unix_ms()
        if request_model.issued_at_unix_ms > now + 5_000:
            raise HTTPException(status_code=422, detail={"code": "request_from_future"})
        if request_model.expires_at_unix_ms <= now:
            raise HTTPException(status_code=408, detail={"code": "request_expired"})
        if (
            request_model.expires_at_unix_ms - request_model.issued_at_unix_ms
            > MAX_REQUEST_LIFETIME_MS
        ):
            raise HTTPException(status_code=422, detail={"code": "request_lifetime_too_long"})
        if now >= request_model.task.deadline_unix_ms:
            raise HTTPException(status_code=408, detail={"code": "task_deadline_elapsed"})
        artifact_result = strategy(request_model.task)
        artifact = (
            await artifact_result if inspect.isawaitable(artifact_result) else artifact_result
        )
        if artifact.task_id != request_model.task.task_id:
            raise HTTPException(status_code=500, detail={"code": "strategy_wrong_task"})
        if artifact.engine_image_digest != request_model.task.engine_image_digest:
            raise HTTPException(status_code=500, detail={"code": "strategy_wrong_engine"})
        artifact_size = len(artifact.model_dump_json().encode("utf-8"))
        if artifact_size > request_model.task.artifact_budget.max_bundle_bytes:
            raise HTTPException(status_code=500, detail={"code": "strategy_bundle_too_large"})
        return sign_optimization_response(
            request=request_model,
            artifact=artifact,
            miner_signer=signer,
            issued_at_unix_ms=now,
            expires_at_unix_ms=request_model.expires_at_unix_ms,
        )

    return app
