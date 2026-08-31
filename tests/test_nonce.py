from pathlib import Path

from planrace.nonce import SQLiteNonceStore


def test_nonce_store_is_persistent_and_atomic(tmp_path: Path) -> None:
    path = tmp_path / "nonces.sqlite3"
    first = SQLiteNonceStore(path)
    assert first.check_and_store("hotkey", 1)
    assert not first.check_and_store("hotkey", 1)
    second = SQLiteNonceStore(path)
    assert not second.check_and_store("hotkey", 1)
    assert second.check_and_store("hotkey", 2)
    assert second.check_and_store("other", 1)
