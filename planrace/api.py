"""Authenticated miner HTTP service for the PlanRace v1 data plane."""

from __future__ import annotations

import bittensor as bt
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from planrace.auth import AuthorizationHook, authenticate_request
from planrace.miners import MinerStrategy, indexed_miner
from planrace.models import MAX_SQL_BYTES, OptimizationArtifact, QueryTask


def create_miner_app(
    *,
    self_hotkey_ss58: str,
    nonce_store: bt.http_auth.NonceStore,
    strategy: MinerStrategy = indexed_miner,
    authorize_hotkey: AuthorizationHook | None = None,
) -> FastAPI:
    if not self_hotkey_ss58:
        raise ValueError("self_hotkey_ss58 must not be empty")
    app = FastAPI(title="PlanRace Miner", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "protocol": "planrace/1"}

    @app.post("/v1/optimize", response_model=OptimizationArtifact)
    async def optimize(request: Request) -> OptimizationArtifact:
        authenticated = await authenticate_request(
            request,
            self_hotkey_ss58=self_hotkey_ss58,
            nonce_store=nonce_store,
            max_body_bytes=MAX_SQL_BYTES * 3,
            authorize_hotkey=authorize_hotkey,
        )
        try:
            task = QueryTask.model_validate_json(authenticated.raw_body)
        except ValidationError:
            raise HTTPException(
                status_code=422, detail={"code": "task_validation_failed"}
            ) from None
        artifact = strategy(task)
        return artifact.model_copy(update={"miner_id": self_hotkey_ss58})

    return app
