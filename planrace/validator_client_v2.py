"""Bounded validator-to-miner transport for signed PlanRace v2 responses."""

from __future__ import annotations

import asyncio
import ipaddress
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

import httpx
from bittensor.signing import WalletLike
from pydantic import ValidationError

from planrace.auth import build_signed_request
from planrace.auth_v2 import ResponseReplayStore, ResponseVerificationError, verify_signed_response
from planrace.models_v2 import (
    OptimizationBundle,
    OptimizationRequestV2,
    SignedOptimizationResponse,
)

DEFAULT_V2_TIMEOUT: Final = httpx.Timeout(connect=3.0, read=15.0, write=5.0, pool=2.0)
DEFAULT_MAX_RESPONSE_BYTES: Final = 128 * 1024
DEFAULT_MAX_RESPONSE_HEADER_BYTES: Final = 16 * 1024
DEFAULT_TOTAL_TIMEOUT_SECONDS: Final = 20.0
_HTTP_SCHEMES: Final = frozenset({"http", "https"})
_HEADER_NAME_BYTES: Final = frozenset(
    b"!#$%&'*+-.^_`|~0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
)


def _system_clock_unix_ms() -> int:
    return time.time_ns() // 1_000_000


@dataclass(frozen=True, slots=True)
class DispatchOutcomeV2:
    accepted: bool
    artifact: OptimizationBundle | None
    response: SignedOptimizationResponse | None
    failure_code: str | None
    status_code: int | None


async def request_optimization_v2(
    client: httpx.AsyncClient,
    *,
    wallet: WalletLike,
    endpoint: str,
    receiver_ss58: str,
    request_model: OptimizationRequestV2,
    expected_miner_uid: int,
    metagraph_hotkeys: dict[int, str],
    replay_store: ResponseReplayStore,
    now_unix_ms: int | None = None,
    clock_unix_ms: Callable[[], int] = _system_clock_unix_ms,
    timeout: httpx.Timeout = DEFAULT_V2_TIMEOUT,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    max_response_header_bytes: int = DEFAULT_MAX_RESPONSE_HEADER_BYTES,
    total_timeout_seconds: float = DEFAULT_TOTAL_TIMEOUT_SECONDS,
    allow_local_endpoint_for_tests: bool = False,
) -> DispatchOutcomeV2:
    """Dispatch one request with fail-closed endpoint, time, and size boundaries.

    ``now_unix_ms`` is retained only for call compatibility and is intentionally ignored:
    response verification samples ``clock_unix_ms`` after the complete body stream arrives.
    Test transports that use local or reserved addresses must explicitly opt in with
    ``allow_local_endpoint_for_tests``.
    """

    del now_unix_ms
    if receiver_ss58 != request_model.miner_hotkey:
        return _failed("receiver_mismatch")
    if max_response_bytes <= 0:
        raise ValueError("max_response_bytes must be positive")
    if max_response_header_bytes <= 0:
        raise ValueError("max_response_header_bytes must be positive")
    if total_timeout_seconds <= 0 or not math.isfinite(total_timeout_seconds):
        raise ValueError("total_timeout_seconds must be finite and positive")
    if not _client_transport_is_safe(client):
        return _failed("client_configuration_unsafe")
    body = request_model.model_dump_json().encode("utf-8")
    try:
        async with asyncio.timeout(total_timeout_seconds):
            request = build_signed_request(
                client,
                wallet=wallet,
                method="POST",
                url=endpoint,
                body=body,
                receiver_ss58=receiver_ss58,
                headers={"content-type": "application/json", "accept": "application/json"},
            )
            await _validate_endpoint(
                request.url,
                allow_local_endpoint_for_tests=allow_local_endpoint_for_tests,
            )
            request.extensions["timeout"] = timeout.as_dict()
            # Let asyncio deliver an already-expired monotonic deadline before any I/O.
            await asyncio.sleep(0)
            try:
                response = await client.send(request, stream=True, follow_redirects=False)
            except httpx.TimeoutException:
                return _failed("timeout")
            except httpx.HTTPError:
                return _failed("transport_error")
            try:
                _validate_response_headers(
                    response,
                    max_response_header_bytes=max_response_header_bytes,
                    require_json=response.status_code == 200,
                )
                if response.status_code != 200:
                    return _failed("http_error", status_code=response.status_code)
                raw = await _read_bounded_response(response, max_response_bytes=max_response_bytes)
                received_at_unix_ms = _sample_clock_unix_ms(clock_unix_ms)
            except ResponseHeadersTooLargeError:
                return _failed("response_headers_too_large", status_code=response.status_code)
            except ResponseHeadersInvalidError:
                return _failed("response_headers_invalid", status_code=response.status_code)
            except ResponseTooLargeError:
                return _failed("response_too_large", status_code=response.status_code)
            except (httpx.TimeoutException, httpx.HTTPError):
                return _failed("response_read_failed", status_code=response.status_code)
            finally:
                await response.aclose()
    except TimeoutError:
        return _failed("timeout")
    except EndpointResolutionError:
        return _failed("endpoint_resolution_failed")
    except EndpointForbiddenError:
        return _failed("endpoint_forbidden")
    except (EndpointInvalidError, httpx.InvalidURL):
        return _failed("endpoint_invalid")
    try:
        signed = SignedOptimizationResponse.model_validate_json(raw)
    except ValidationError:
        return _failed("response_validation_failed", status_code=200)
    try:
        artifact = verify_signed_response(
            signed,
            request=request_model,
            expected_miner_uid=expected_miner_uid,
            metagraph_hotkeys=metagraph_hotkeys,
            replay_store=replay_store,
            now_unix_ms=received_at_unix_ms,
        )
    except ResponseVerificationError as error:
        return DispatchOutcomeV2(False, None, signed, error.code, 200)
    return DispatchOutcomeV2(True, artifact, signed, None, 200)


class ResponseTooLargeError(ValueError):
    pass


class ResponseHeadersTooLargeError(ValueError):
    pass


class ResponseHeadersInvalidError(ValueError):
    pass


class EndpointInvalidError(ValueError):
    pass


class EndpointResolutionError(ValueError):
    pass


class EndpointForbiddenError(ValueError):
    pass


def _client_transport_is_safe(client: httpx.AsyncClient) -> bool:
    """Fail closed on HTTPX environment and explicit proxy configuration.

    HTTPX 0.28 does not expose these settings publicly. The project pins that exact
    version, so checking its internal configuration is preferable to silently honoring
    ambient proxy variables or proxy mounts.
    """

    if getattr(client, "_trust_env", True):
        return False
    mounts = getattr(client, "_mounts", None)
    return isinstance(mounts, dict) and not mounts


async def _validate_endpoint(url: httpx.URL, *, allow_local_endpoint_for_tests: bool) -> None:
    if url.scheme not in _HTTP_SCHEMES or not url.host:
        raise EndpointInvalidError
    if url.username or url.password or url.fragment:
        raise EndpointInvalidError
    if allow_local_endpoint_for_tests:
        return
    # Metagraph Axon endpoints are numeric IP addresses. Requiring that form
    # prevents a hostname from resolving once during validation and again to a
    # private address inside HTTPX (DNS rebinding / TOCTOU).
    try:
        address = ipaddress.ip_address(url.host.split("%", 1)[0])
    except ValueError as error:
        raise EndpointForbiddenError from error
    if _address_is_forbidden(address):
        raise EndpointForbiddenError


def _address_is_forbidden(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    mapped = address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) else None
    candidate = mapped or address
    # Fail closed unless the numeric Axon address is positively classified as
    # globally routable. This also excludes RFC6598 shared/CGNAT space.
    return not candidate.is_global


def _validate_response_headers(
    response: httpx.Response,
    *,
    max_response_header_bytes: int,
    require_json: bool,
) -> None:
    total = 2  # Account for the terminating CRLF.
    content_lengths = 0
    content_types: list[bytes] = []
    content_encodings: list[bytes] = []
    saw_transfer_encoding = False
    for name, value in response.headers.raw:
        total += len(name) + 2 + len(value) + 2
        if total > max_response_header_bytes:
            raise ResponseHeadersTooLargeError
        if not name or any(byte not in _HEADER_NAME_BYTES for byte in name):
            raise ResponseHeadersInvalidError
        if any((byte < 32 and byte != 9) or byte == 127 for byte in value):
            raise ResponseHeadersInvalidError
        lowered = name.lower()
        if lowered == b"content-length":
            content_lengths += 1
            if content_lengths > 1 or not value.isdigit():
                raise ResponseHeadersInvalidError
        elif lowered == b"transfer-encoding":
            saw_transfer_encoding = True
        elif lowered == b"content-type":
            content_types.append(value)
        elif lowered == b"content-encoding":
            content_encodings.append(value.strip().lower())
    if content_lengths and saw_transfer_encoding:
        raise ResponseHeadersInvalidError
    if content_encodings and content_encodings != [b"identity"]:
        # HTTPX can materialize an entire decoded gzip/deflate chunk before an
        # application byte limit is checked. The protocol requires identity JSON.
        raise ResponseHeadersInvalidError
    if require_json:
        if len(content_types) != 1:
            raise ResponseHeadersInvalidError
        media_type = content_types[0].split(b";", 1)[0].strip().lower()
        if media_type != b"application/json":
            raise ResponseHeadersInvalidError


def _sample_clock_unix_ms(clock_unix_ms: Callable[[], int]) -> int:
    value = clock_unix_ms()
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("clock_unix_ms must return an integer")
    return value


async def _read_bounded_response(response: httpx.Response, *, max_response_bytes: int) -> bytes:
    content_length = response.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > max_response_bytes:
                raise ResponseTooLargeError
        except ValueError:
            raise ResponseTooLargeError from None
    if response.is_stream_consumed:
        # Mock/in-process transports may materialize identity content before
        # returning. Production network streams remain unconsumed here.
        if len(response.content) > max_response_bytes:
            raise ResponseTooLargeError
        return response.content
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_raw():
        total += len(chunk)
        if total > max_response_bytes:
            raise ResponseTooLargeError
        chunks.append(chunk)
    return b"".join(chunks)


def _failed(code: str, *, status_code: int | None = None) -> DispatchOutcomeV2:
    return DispatchOutcomeV2(False, None, None, code, status_code)
