"""Fail-closed SQL admission and SQLite resource controls."""

from __future__ import annotations

import re
import sqlite3
import time
from collections.abc import Callable

_INDEX_PATTERN = re.compile(
    r"^CREATE\s+(?:UNIQUE\s+)?INDEX\s+[A-Za-z_][A-Za-z0-9_]*\s+"
    r"ON\s+(?:customers|orders)\s*\([^;]+\)(?:\s+WHERE\s+[^;]+)?$",
    re.IGNORECASE,
)


class AdmissionError(ValueError):
    """Artifact is outside the versioned SQL contract."""


def validate_candidate_sql(sql: str) -> str:
    normalized = sql.strip()
    if not normalized.upper().startswith(("SELECT ", "WITH ")):
        raise AdmissionError("candidate must be one read-only SELECT/WITH statement")
    if ";" in normalized.rstrip(";"):
        raise AdmissionError("multiple SQL statements are forbidden")
    forbidden = ("ATTACH", "DETACH", "PRAGMA", "INSERT", "UPDATE", "DELETE", "DROP", "ALTER")
    upper = normalized.upper()
    if any(re.search(rf"\b{word}\b", upper) for word in forbidden):
        raise AdmissionError("candidate contains a forbidden operation")
    return normalized.rstrip(";")


def validate_setup_sql(sql: str) -> str:
    normalized = sql.strip().rstrip(";")
    if not _INDEX_PATTERN.fullmatch(normalized):
        raise AdmissionError("setup artifact must be one bounded customers/orders CREATE INDEX")
    return normalized


def install_query_deadline(
    connection: sqlite3.Connection,
    *,
    timeout_ms: float,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    deadline = clock() + timeout_ms / 1000.0

    def should_abort() -> int:
        return int(clock() > deadline)

    connection.set_progress_handler(should_abort, 1_000)
