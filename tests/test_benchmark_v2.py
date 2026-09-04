import sqlite3
from pathlib import Path

import pytest

from planrace.benchmark_v2 import (
    HOLDOUT_PROFILES,
    PUBLIC_TRAINING_SEED,
    QUERY_FAMILIES,
    SCHEMA_V2,
    describe_hidden_fixtures,
    generate_hidden_fixtures,
    generate_mixed_family_fixtures_for_testing,
    generate_public_training_fixture,
    logical_fixture_content_digest,
    logical_fixture_content_digest_from_database,
    materialize_fixture,
    published_parameter_ranges,
    verify_logical_fixture_content_digest,
)


def test_money_is_integer_cents_not_real() -> None:
    assert "amount_cents INTEGER NOT NULL" in SCHEMA_V2
    assert "amount REAL" not in SCHEMA_V2


def test_hidden_fixture_set_is_diverse_and_deterministic() -> None:
    seed = bytes(range(32))
    for family in QUERY_FAMILIES:
        first = generate_hidden_fixtures(seed, family_id=family.family_id)
        second = generate_hidden_fixtures(seed, family_id=family.family_id)
        assert first == second
        assert len(first) == len(HOLDOUT_PROFILES) >= 8
        assert len({item.descriptor.content_digest for item in first}) == len(first)
        assert {item.query_family.family_id for item in first} == {family.family_id}
        assert {len(item.parameters) for item in first} == {len(family.parameter_kinds)}
        assert {item.profile.orders for item in first} >= {0, 42_000}
        assert any(item.profile.null_bps >= 6_000 for item in first)
        assert any(item.profile.duplicate_bps >= 5_000 for item in first)
        assert any(item.profile.correlation_bps >= 9_000 for item in first)
        if family.family_id == "paid-revenue-by-segment":
            assert all(item.parameters[2] <= item.parameters[3] for item in first)
        if family.family_id == "bounded-range-scan":
            assert all(item.parameters[1] <= item.parameters[2] for item in first)


def test_old_mixed_family_corpus_is_explicitly_test_only() -> None:
    fixtures = generate_mixed_family_fixtures_for_testing(bytes(range(32)))
    assert len({item.query_family.family_id for item in fixtures}) >= 5


def test_secret_change_changes_all_concrete_holdout_commitments() -> None:
    first = describe_hidden_fixtures(b"a" * 32, family_id="bounded-range-scan")
    second = describe_hidden_fixtures(b"b" * 32, family_id="bounded-range-scan")
    pairs = tuple(zip(first, second, strict=True))
    assert all(left.content_digest != right.content_digest for left, right in pairs)
    changed_parameters = sum(
        left.parameter_set_digest != right.parameter_set_digest for left, right in pairs
    )
    assert changed_parameters >= len(pairs) // 2


def test_descriptors_do_not_expose_seed() -> None:
    seed = b"private-seed-material-32-bytes!!"
    assert len(seed) == 32
    serialized = "".join(
        item.model_dump_json()
        for item in describe_hidden_fixtures(seed, family_id="nullable-coupon")
    )
    assert seed.hex() not in serialized


def test_public_training_fixture_is_separate_and_reproducible() -> None:
    assert len(PUBLIC_TRAINING_SEED) == 32
    for family in QUERY_FAMILIES:
        training = generate_public_training_fixture(family.family_id)
        assert training == generate_public_training_fixture(family.family_id)
        assert training.query_family == family
        assert len(training.parameters) == len(family.parameter_kinds)
        hidden_ids = {profile.fixture_id for profile in HOLDOUT_PROFILES}
        assert training.descriptor.fixture_id not in hidden_ids


def test_fixture_materialization_matches_logical_counts(tmp_path: Path) -> None:
    training = generate_public_training_fixture("paid-revenue-by-segment")
    database = tmp_path / "training.sqlite3"
    digest = materialize_fixture(training, database)
    assert digest.startswith("sha256:") and len(digest) == 71
    assert database.stat().st_size > 0
    assert (
        logical_fixture_content_digest(training.customers, training.orders)
        == training.descriptor.content_digest
    )
    assert (
        logical_fixture_content_digest_from_database(database)
        == training.descriptor.content_digest
    )
    assert verify_logical_fixture_content_digest(database, training.descriptor.content_digest)

    connection = sqlite3.connect(database)
    try:
        connection.execute("UPDATE orders SET amount_cents = amount_cents + 1 WHERE id = 1")
        connection.commit()
        assert not verify_logical_fixture_content_digest(
            connection, training.descriptor.content_digest
        )
    finally:
        connection.close()

    with pytest.raises(ValueError, match="lowercase sha256"):
        verify_logical_fixture_content_digest(database, "not-a-digest")


def test_published_ranges_are_complete_and_match_generated_parameters() -> None:
    expected_names = {
        "paid-revenue-by-segment": (
            "active",
            "status",
            "created_day_start",
            "created_day_end",
        ),
        "customer-order-threshold": (
            "minimum_amount_cents",
            "status",
            "minimum_order_count",
        ),
        "bounded-range-scan": (
            "status",
            "minimum_amount_cents",
            "maximum_amount_cents",
        ),
        "region-channel-aggregate": ("region", "channel"),
        "nullable-coupon": ("created_day_minimum",),
        "intentional-zero-result": ("status", "amount_cents_exclusive_floor"),
    }
    expected_types = {"integer": int, "text": str, "boolean": bool}
    seed = bytes(range(32))

    for family in QUERY_FAMILIES:
        ranges = published_parameter_ranges(family.family_id)
        assert tuple(item.name for item in ranges) == expected_names[family.family_id]
        assert len(ranges) == len(family.parameter_kinds)
        assert tuple(item.value_type for item in ranges) == family.parameter_kinds
        dump = "".join(item.model_dump_json() for item in ranges)
        for fixture in generate_hidden_fixtures(seed, family_id=family.family_id):
            assert fixture.descriptor.content_digest not in dump
            for value, parameter_range in zip(fixture.parameters, ranges, strict=True):
                assert type(value) is expected_types[parameter_range.value_type]
                if isinstance(value, str):
                    assert isinstance(parameter_range.minimum, str)
                    assert isinstance(parameter_range.maximum, str)
                    assert parameter_range.minimum <= value <= parameter_range.maximum
                elif isinstance(value, bool):
                    assert isinstance(parameter_range.minimum, bool)
                    assert isinstance(parameter_range.maximum, bool)
                    assert parameter_range.minimum <= value <= parameter_range.maximum
                else:
                    assert isinstance(value, int)
                    assert isinstance(parameter_range.minimum, int)
                    assert isinstance(parameter_range.maximum, int)
                    assert parameter_range.minimum <= value <= parameter_range.maximum


def test_parameter_distribution_labels_match_generators() -> None:
    expected = {
        "paid-revenue-by-segment": (
            "categorical",
            "categorical",
            "uniform",
            "uniform",
        ),
        "customer-order-threshold": ("uniform", "categorical", "uniform"),
        "bounded-range-scan": ("categorical", "uniform", "uniform"),
        "region-channel-aggregate": ("categorical", "categorical"),
        "nullable-coupon": ("uniform",),
        "intentional-zero-result": ("categorical", "categorical"),
    }
    for family in QUERY_FAMILIES:
        assert tuple(
            item.distribution for item in published_parameter_ranges(family.family_id)
        ) == expected[family.family_id]


def test_unknown_family_fails_closed() -> None:
    with pytest.raises(ValueError, match="unknown query family"):
        generate_hidden_fixtures(bytes(32), family_id="not-a-family")
    with pytest.raises(ValueError, match="unknown query family"):
        published_parameter_ranges("not-a-family")
