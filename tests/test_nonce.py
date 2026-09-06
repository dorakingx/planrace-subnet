from pathlib import Path

from planrace.nonce import SQLiteNonceStore


def test_nonce_store_is_persistent_and_atomic(tmp_path: Path) -> None:
    path = tmp_path / "nonces.sqlite3"
    first = SQLiteNonceStore(path, clock_ns=lambda: 10)
    assert first.check_and_store("hotkey", 1)
    assert not first.check_and_store("hotkey", 1)
    second = SQLiteNonceStore(path, clock_ns=lambda: 10)
    assert not second.check_and_store("hotkey", 1)
    assert second.check_and_store("hotkey", 2)
    assert second.check_and_store("other", 1)


def test_capacity_never_evicts_a_fresh_nonce(tmp_path: Path) -> None:
    path = tmp_path / "capacity.sqlite3"
    store = SQLiteNonceStore(path, clock_ns=lambda: 10, ttl_ns=100, max_entries=1)
    assert store.retention == 100 / 1_000_000_000
    assert store.check_and_store("victim", 9)
    assert not store.check_and_store("attacker", 10)
    assert not store.check_and_store("victim", 9)
