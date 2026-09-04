"""Typed, bounded exact-result canonicalization for PlanRace protocol v2.

The oracle compares results produced by the same pinned database engine.  It
does not claim cross-engine SQL equivalence.  Type tags prevent JSON values
such as ``null`` and the string ``"null"`` from colliding, duplicate rows are
preserved, and ordered versus unordered result contracts are explicit.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

RESULT_DOMAIN_V2: Final = b"planrace/2:exact-result"
PINNED_SQLITE_ENGINE: Final = "sqlite-3.46.1"


class ResultOracleError(ValueError):
    """A result cannot be safely represented by the v2 exact oracle."""


class ResultLimitExceeded(ResultOracleError):
    """A validator-owned result bound was exceeded."""


class UnsupportedResultType(ResultOracleError):
    """A cell has no protocol-defined canonical representation."""


@dataclass(frozen=True, slots=True)
class ResultPolicy:
    """Precommitted exact-result semantics and resource bounds."""

    engine: str = PINNED_SQLITE_ENGINE
    ordered: bool = True
    collation: str = "sqlite-binary"
    max_rows: int = 10_000
    max_cells: int = 100_000
    max_output_bytes: int = 2 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.engine != PINNED_SQLITE_ENGINE:
            raise ValueError(f"engine must be exactly {PINNED_SQLITE_ENGINE}")
        if self.collation not in {"sqlite-binary", "sqlite-nocase", "sqlite-rtrim"}:
            raise ValueError("collation is not in the v2 SQLite policy")
        if self.max_rows < 0 or self.max_cells < 0 or self.max_output_bytes < 256:
            raise ValueError("result bounds must be non-negative and output must allow a header")


@dataclass(frozen=True, slots=True)
class CanonicalResult:
    digest: str
    row_count: int
    column_count: int
    cell_count: int
    canonical_bytes: bytes

    @property
    def byte_count(self) -> int:
        return len(self.canonical_bytes)


DEFAULT_RESULT_POLICY: Final = ResultPolicy()


def canonicalize_result(
    rows: Iterable[Sequence[object]],
    *,
    policy: ResultPolicy = DEFAULT_RESULT_POLICY,
    projection_column_count: int | None = None,
) -> CanonicalResult:
    """Canonicalize and hash one complete, bounded SQL result.

    Unordered results are a sorted multiset of canonical row bytes.  Sorting
    does not deduplicate, so multiplicity remains part of equality.  Ordered
    results preserve the engine-returned sequence exactly.
    """

    cursor_column_count = _projection_count_from_cursor(rows)
    if projection_column_count is not None:
        _validate_projection_column_count(projection_column_count, policy)
        if cursor_column_count is not None and cursor_column_count != projection_column_count:
            raise ResultOracleError("projection_column_count disagrees with cursor.description")
    else:
        projection_column_count = cursor_column_count

    encoded_rows: list[bytes] = []
    column_count = projection_column_count
    cell_count = 0
    running_size = 0
    for row_count, row in enumerate(rows, start=1):
        if row_count > policy.max_rows:
            raise ResultLimitExceeded("row_limit")
        if not isinstance(row, Sequence) or isinstance(row, str | bytes | bytearray):
            raise UnsupportedResultType("each result row must be a non-string sequence")
        if column_count is None:
            column_count = len(row)
        elif len(row) != column_count:
            raise ResultOracleError("result rows have inconsistent column counts")
        cell_count += len(row)
        if cell_count > policy.max_cells:
            raise ResultLimitExceeded("cell_limit")
        encoded = _canonical_json([_encode_cell(value) for value in row])
        running_size += len(encoded)
        if running_size > policy.max_output_bytes:
            raise ResultLimitExceeded("output_limit")
        encoded_rows.append(encoded)

    if column_count is None:
        raise ResultOracleError(
            "empty results require projection_column_count or cursor.description"
        )
    if not policy.ordered:
        encoded_rows.sort()
    header = _canonical_json(
        {
            "collation": policy.collation,
            "column_count": column_count,
            "engine": policy.engine,
            "order": "ordered" if policy.ordered else "multiset",
            "protocol": "planrace/2",
            "row_count": len(encoded_rows),
        }
    )
    canonical = header + b"\n" + b"\n".join(encoded_rows)
    if len(canonical) > policy.max_output_bytes:
        raise ResultLimitExceeded("output_limit")
    framed = (
        len(RESULT_DOMAIN_V2).to_bytes(2, "big")
        + RESULT_DOMAIN_V2
        + len(canonical).to_bytes(8, "big")
        + canonical
    )
    digest = "sha256:" + hashlib.sha256(framed).hexdigest()
    return CanonicalResult(
        digest=digest,
        row_count=len(encoded_rows),
        column_count=column_count,
        cell_count=cell_count,
        canonical_bytes=canonical,
    )


def exact_results_equal(
    reference_rows: Iterable[Sequence[object]],
    candidate_rows: Iterable[Sequence[object]],
    *,
    policy: ResultPolicy = DEFAULT_RESULT_POLICY,
    projection_column_count: int | None = None,
) -> bool:
    """Compare two results under one explicit engine/order/collation policy."""

    return (
        canonicalize_result(
            reference_rows,
            policy=policy,
            projection_column_count=projection_column_count,
        ).digest
        == canonicalize_result(
            candidate_rows,
            policy=policy,
            projection_column_count=projection_column_count,
        ).digest
    )


def _projection_count_from_cursor(rows: object) -> int | None:
    """Read DB-API projection metadata without coupling to sqlite internals.

    A DB-API cursor exposes ``description`` after statement execution even
    when the result contains zero rows.  Binding that count into the result
    header prevents ``SELECT a WHERE false`` from colliding with a different
    empty projection such as ``SELECT a, b WHERE false``.
    """

    description = getattr(rows, "description", None)
    if description is None:
        return None
    if not isinstance(description, Sequence) or isinstance(description, str | bytes | bytearray):
        raise ResultOracleError("cursor.description must be a sequence")
    return len(description)


def _validate_projection_column_count(count: int, policy: ResultPolicy) -> None:
    if type(count) is not int or count < 0:
        raise ResultOracleError("projection_column_count must be a non-negative integer")
    if count > policy.max_cells:
        raise ResultLimitExceeded("cell_limit")


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _encode_cell(value: object) -> list[str]:
    if value is None:
        return ["null", ""]
    # SQLite has INTEGER rather than a distinct Boolean storage class.  Map a
    # Python bool to that storage class so adapters cannot create two encodings.
    if isinstance(value, bool):
        return ["integer", "1" if value else "0"]
    if isinstance(value, int):
        return ["integer", str(value)]
    if isinstance(value, Decimal):
        return ["decimal", _canonical_decimal(value)]
    if isinstance(value, float):
        if math.isnan(value):
            return ["float64", "nan"]
        if math.isinf(value):
            return ["float64", "+infinity" if value > 0 else "-infinity"]
        # float.hex() is an exact IEEE-754 representation and preserves -0.
        return ["float64", value.hex()]
    if isinstance(value, str):
        return ["string", value]
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytearray):
        value = bytes(value)
    if isinstance(value, bytes):
        return ["blob-base64", base64.b64encode(value).decode("ascii")]
    raise UnsupportedResultType(f"unsupported SQL result type: {type(value).__name__}")


def _canonical_decimal(value: Decimal) -> str:
    if not value.is_finite():
        if value.is_nan():
            return "nan"
        return "+infinity" if value > 0 else "-infinity"
    if value.is_zero():
        return "-0" if value.is_signed() else "0"
    normalized = value.normalize()
    rendered = format(normalized, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered
