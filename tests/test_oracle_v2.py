import sqlite3
from decimal import Decimal

import pytest

from planrace.oracle_v2 import (
    ResultLimitExceeded,
    ResultOracleError,
    ResultPolicy,
    UnsupportedResultType,
    canonicalize_result,
    exact_results_equal,
)


def test_type_tags_prevent_cross_type_collisions() -> None:
    values = [None, "null", 0, False, b"", Decimal("0"), 0.0]
    digests = {canonicalize_result([(value,)]).digest for value in values}
    # bool deliberately maps to SQLite INTEGER and therefore collides with 0.
    assert len(digests) == len(values) - 1


def test_ordered_and_unordered_semantics_are_explicit() -> None:
    left = [(1, "a"), (2, "b")]
    right = list(reversed(left))
    assert not exact_results_equal(left, right, policy=ResultPolicy(ordered=True))
    assert exact_results_equal(left, right, policy=ResultPolicy(ordered=False))


def test_multiset_preserves_duplicate_rows() -> None:
    policy = ResultPolicy(ordered=False)
    assert not exact_results_equal([(1,), (1,)], [(1,)], policy=policy)


def test_numeric_edge_cases_have_defined_encodings() -> None:
    result = canonicalize_result(
        [(Decimal("1.00"), Decimal("-0.00"), -0.0, float("nan"), float("inf"))]
    )
    text = result.canonical_bytes.decode()
    assert '["decimal","1"]' in text
    assert '["decimal","-0"]' in text
    assert '["float64","-0x0.0p+0"]' in text
    assert '["float64","nan"]' in text
    assert '["float64","+infinity"]' in text


def test_blob_and_unicode_are_lossless() -> None:
    first = canonicalize_result([("e\u0301", b"\x00\xff")])
    second = canonicalize_result([("é", b"\x00\xff")])
    assert first.digest != second.digest
    assert "AP8=" in first.canonical_bytes.decode()


@pytest.mark.parametrize(
    ("rows", "policy", "code"),
    [
        ([(1,), (2,)], ResultPolicy(max_rows=1), "row_limit"),
        ([(1, 2)], ResultPolicy(max_cells=1), "cell_limit"),
        ([("x" * 300,)], ResultPolicy(max_output_bytes=256), "output_limit"),
    ],
)
def test_result_bounds_fail_closed(
    rows: list[tuple[object, ...]], policy: ResultPolicy, code: str
) -> None:
    with pytest.raises(ResultLimitExceeded, match=code):
        canonicalize_result(rows, policy=policy)


def test_unsupported_values_fail_closed() -> None:
    with pytest.raises(UnsupportedResultType):
        canonicalize_result([({"not": "a SQL cell"},)])


def test_inconsistent_column_count_fails_closed() -> None:
    with pytest.raises(ValueError, match="inconsistent"):
        canonicalize_result([(1,), (1, 2)])


def test_empty_sqlite_results_bind_actual_projection_column_count() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        one_column = canonicalize_result(connection.execute("SELECT 1 WHERE 0"))
        two_columns = canonicalize_result(connection.execute("SELECT 1, 2 WHERE 0"))
    finally:
        connection.close()

    assert one_column.row_count == two_columns.row_count == 0
    assert one_column.column_count == 1
    assert two_columns.column_count == 2
    assert one_column.digest != two_columns.digest


def test_empty_plain_iterable_requires_explicit_projection_count() -> None:
    with pytest.raises(ResultOracleError, match="empty results require"):
        canonicalize_result([])

    one_column = canonicalize_result([], projection_column_count=1)
    two_columns = canonicalize_result([], projection_column_count=2)
    assert one_column.digest != two_columns.digest


def test_projection_metadata_disagreement_fails_closed() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        cursor = connection.execute("SELECT 1, 2 WHERE 0")
        with pytest.raises(ResultOracleError, match="disagrees"):
            canonicalize_result(cursor, projection_column_count=1)
    finally:
        connection.close()
