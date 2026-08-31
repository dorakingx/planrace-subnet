"""Persistent replay protection for authenticated miner requests."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


class SQLiteNonceStore:
    """Atomic `(hotkey, nonce)` admission compatible with Bittensor v11."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self._lock = threading.Lock()
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

    def check_and_store(self, hotkey_ss58: str, nonce_ns: int) -> bool:
        with self._lock, sqlite3.connect(self._path) as database:
            try:
                database.execute(
                    "INSERT INTO accepted_nonces(hotkey_ss58, nonce_ns) VALUES (?, ?)",
                    (hotkey_ss58, nonce_ns),
                )
            except sqlite3.IntegrityError:
                return False
            return True
