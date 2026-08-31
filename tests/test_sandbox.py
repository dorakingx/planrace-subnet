import pytest

from planrace.sandbox import AdmissionError, validate_candidate_sql, validate_setup_sql


def test_read_only_query_is_admitted() -> None:
    assert validate_candidate_sql("SELECT * FROM orders") == "SELECT * FROM orders"


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM orders",
        "SELECT * FROM orders; DROP TABLE orders",
        "PRAGMA journal_mode=OFF",
        "ATTACH DATABASE '/tmp/x' AS x",
    ],
)
def test_mutating_or_multi_statement_query_is_rejected(sql: str) -> None:
    with pytest.raises(AdmissionError):
        validate_candidate_sql(sql)


def test_only_bounded_index_artifacts_are_admitted() -> None:
    assert validate_setup_sql("CREATE INDEX idx_status ON orders(status)")
    with pytest.raises(AdmissionError):
        validate_setup_sql("CREATE TABLE stolen(value TEXT)")
    with pytest.raises(AdmissionError):
        validate_setup_sql("CREATE INDEX idx_secret ON secrets(value)")
