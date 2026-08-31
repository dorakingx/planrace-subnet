"""Validator-to-miner dispatch over receiver-bound Bittensor HTTP auth."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from bittensor.signing import WalletLike
from pydantic import ValidationError

from planrace.auth import build_signed_request
from planrace.models import OptimizationArtifact, QueryTask


@dataclass(frozen=True, slots=True)
class DispatchOutcome:
    accepted: bool
    artifact: OptimizationArtifact | None
    failure_code: str | None
    status_code: int | None


async def request_optimization(
    client: httpx.AsyncClient,
    *,
    wallet: WalletLike,
    endpoint: str,
    receiver_ss58: str,
    task: QueryTask,
) -> DispatchOutcome:
    body = task.model_dump_json().encode()
    try:
        request = build_signed_request(
            client,
            wallet=wallet,
            method="POST",
            url=endpoint,
            body=body,
            receiver_ss58=receiver_ss58,
            headers={"content-type": "application/json"},
        )
        response = await client.send(request)
    except httpx.TimeoutException:
        return DispatchOutcome(False, None, "timeout", None)
    except httpx.HTTPError:
        return DispatchOutcome(False, None, "transport_error", None)
    if response.status_code != 200:
        return DispatchOutcome(False, None, "http_error", response.status_code)
    try:
        artifact = OptimizationArtifact.model_validate_json(response.content)
    except ValidationError:
        return DispatchOutcome(False, None, "response_validation_failed", response.status_code)
    if artifact.task_id != task.task_id or artifact.miner_id != receiver_ss58:
        return DispatchOutcome(False, None, "identity_or_task_mismatch", response.status_code)
    return DispatchOutcome(True, artifact, None, response.status_code)
