"""Exact-byte Bittensor `btauth/1` adapters for HTTPX and FastAPI."""

from __future__ import annotations

import threading
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Final, NoReturn

import bittensor as bt
import httpx
from bittensor.signing import WalletLike
from fastapi import HTTPException
from starlette.requests import Request
from starlette.types import Scope

_AUTH_PREFIX: Final = "x-bittensor-"


@dataclass(frozen=True, slots=True)
class AuthenticatedRequest:
    caller: bt.http_auth.Caller
    raw_body: bytes
    raw_target: str


AuthorizationHook = Callable[[str], bool | Awaitable[bool]]


class FreshNonceGenerator:
    def __init__(self, clock_ns: Callable[[], int] = time.time_ns) -> None:
        self._clock_ns = clock_ns
        self._last = -1
        self._lock = threading.Lock()

    def __call__(self) -> int:
        with self._lock:
            value = max(int(self._clock_ns()), self._last + 1)
            self._last = value
            return value


_fresh_nonce = FreshNonceGenerator()


def build_signed_request(
    client: httpx.Client | httpx.AsyncClient,
    *,
    wallet: WalletLike,
    method: str,
    url: str | httpx.URL,
    body: bytes,
    receiver_ss58: str,
    headers: Mapping[str, str] | None = None,
    nonce_factory: Callable[[], int] = _fresh_nonce,
) -> httpx.Request:
    if not isinstance(body, bytes):
        raise TypeError("body must be exact bytes")
    if headers and any(key.lower().startswith(_AUTH_PREFIX) for key in headers):
        raise ValueError("caller-supplied Bittensor auth headers are forbidden")
    request = client.build_request(method, url, content=body, headers=headers)
    if any(key.lower().startswith(_AUTH_PREFIX) for key in request.headers):
        raise ValueError("HTTPX defaults contain Bittensor auth headers")
    target = request.url.raw_path.decode("ascii")
    request.headers.update(
        bt.http_auth.sign(
            wallet,
            method=request.method,
            path=target,
            body=body,
            receiver_ss58=receiver_ss58,
            nonce_ns=nonce_factory(),
        )
    )
    return request


async def authenticate_request(
    request: Request,
    *,
    self_hotkey_ss58: str,
    nonce_store: bt.http_auth.NonceStore,
    max_body_bytes: int,
    authorize_hotkey: AuthorizationHook | None = None,
) -> AuthenticatedRequest:
    body = await read_bounded_body(request, max_body_bytes=max_body_bytes)
    target = raw_target(request.scope)
    try:
        caller = bt.http_auth.verify(
            request.headers,
            body,
            method=request.method,
            path=target,
            self_hotkey_ss58=self_hotkey_ss58,
            nonce_store=nonce_store,
        )
    except bt.http_auth.MalformedAuth:
        _fail(401, "auth_malformed")
    except bt.http_auth.WrongReceiver:
        _fail(401, "auth_wrong_receiver")
    except bt.http_auth.StaleRequest:
        _fail(401, "auth_stale")
    except bt.http_auth.BadSignature:
        _fail(401, "auth_bad_signature")
    except bt.http_auth.ReplayedRequest:
        _fail(401, "auth_replayed")

    if authorize_hotkey is not None:
        allowed = authorize_hotkey(caller.hotkey_ss58)
        if isinstance(allowed, Awaitable):
            allowed = await allowed
        if not allowed:
            _fail(403, "hotkey_forbidden")
    return AuthenticatedRequest(caller=caller, raw_body=body, raw_target=target)


async def read_bounded_body(request: Request, *, max_body_bytes: int) -> bytes:
    if max_body_bytes < 0:
        raise ValueError("max_body_bytes must be non-negative")
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > max_body_bytes:
                _fail(413, "body_too_large")
        except ValueError:
            _fail(400, "content_length_invalid")
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_body_bytes:
            _fail(413, "body_too_large")
        chunks.append(chunk)
    return b"".join(chunks)


def raw_target(scope: Scope) -> str:
    path = scope.get("raw_path")
    query = scope.get("query_string", b"")
    if not isinstance(path, bytes) or not isinstance(query, bytes):
        _fail(400, "request_target_invalid")
    try:
        decoded_path = path.decode("ascii")
        decoded_query = query.decode("ascii")
    except UnicodeDecodeError:
        _fail(400, "request_target_invalid")
    if not decoded_path.startswith("/"):
        _fail(400, "request_target_invalid")
    return decoded_path + (f"?{decoded_query}" if decoded_query else "")


def _fail(status_code: int, code: str) -> NoReturn:
    raise HTTPException(status_code=status_code, detail={"code": code}) from None
