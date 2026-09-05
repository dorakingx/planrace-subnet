"""Persistent replay protection for authenticated miner requests."""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path


class SQLiteNonceStore:
    """Atomic `(hotkey, nonce)` admission compatible with Bittensor v11."""

    def __init__(
        self,
        path: str | Path,
        *,
        clock_ns: Callable[[], int] = time.time_ns,
        ttl_ns: int = 300_000_000_000,
        max_entries: int = 100_000,
    ) -> None:
        if ttl_ns < 1 or max_entries < 1:
            raise ValueError("nonce retention limits must be positive")
        self._path = str(path)
        self._lock = threading.Lock()
        self._clock_ns = clock_ns
        self._ttl_ns = ttl_ns
        self._max_entries = max_entries
        with sqlite3.connect(self._path) as database:
            database.execute(
                """
                CREATE TABLE IF NOT EXISTS accepted_nonces (
                    hotkey_ss58 TEXT NOT NULL,
                    nonce_ns INTEGER NOT NULL,
                    PRIMARY KEY (hotkey_ss58, nonce_ns)
                )
                """
            )
            database.execute(
                "CREATE INDEX IF NOT EXISTS accepted_nonces_by_time ON accepted_nonces(nonce_ns)"
            )

    def check_and_store(self, hotkey_ss58: str, nonce_ns: int) -> bool:
        with self._lock, sqlite3.connect(self._path) as database:
            database.execute(
                "DELETE FROM accepted_nonces WHERE nonce_ns < ?",
                (self._clock_ns() - self._ttl_ns,),
            )
            try:
                database.execute(
                    "INSERT INTO accepted_nonces(hotkey_ss58, nonce_ns) VALUES (?, ?)",
                    (hotkey_ss58, nonce_ns),
                )
            except sqlite3.IntegrityError:
                return False
            database.execute(
                """
                DELETE FROM accepted_nonces
                WHERE rowid IN (
                    SELECT rowid FROM accepted_nonces
                    ORDER BY nonce_ns ASC
                    LIMIT MAX(0, (SELECT COUNT(*) FROM accepted_nonces) - ?)
                )
                """,
                (self._max_entries,),
            )
            return True
