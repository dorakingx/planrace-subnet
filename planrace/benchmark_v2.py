"""Deterministic expansion of private CSPRNG seeds into PlanRace v2 fixtures.

Only broad profile ranges and a separate public training fixture are shared
before a deadline.  The secret seed selects the concrete holdout rows and
parameters.  All money uses integer cents; no SQLite REAL value represents
currency.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import random
import sqlite3
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from planrace.models_v2 import HiddenFixtureDescriptor, ParameterRange

OrderPayload = tuple[int, int, str, str, int, str | None]
ParameterValue = int | str | bool

SCHEMA_V2: Final = """
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    segment TEXT NOT NULL,
    region TEXT NOT NULL,
    active INTEGER NOT NULL CHECK(active IN (0, 1)),
    tier TEXT
);
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    amount_cents INTEGER NOT NULL CHECK(amount_cents >= 0),
    status TEXT NOT NULL,
    channel TEXT NOT NULL,
    created_day INTEGER NOT NULL,
    coupon_code TEXT,
    FOREIGN KEY(customer_id) REFERENCES customers(id)
);
""".strip()

PUBLIC_TRAINING_SEED: Final = bytes.fromhex(
    "8e1c133978678672f5e31183dd86ef90f6061a59d9f82a643b708629f5adce1b"
)
GENERATOR_VERSION: Final = "planrace-benchmark-v2.1"


def benchmark_generator_source_digest() -> str:
    """Digest the exact generator source loaded by this worker."""

    source = Path(__file__).resolve().read_bytes()
    return "sha256:" + hashlib.sha256(
        b"planrace/2:benchmark-generator\x00" + GENERATOR_VERSION.encode("ascii") + b"\x00" + source
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class QueryFamily:
    family_id: str
    sql: str
    parameter_kinds: tuple[Literal["integer", "text", "boolean"], ...]
    ordered: bool


QUERY_FAMILIES: Final = (
    QueryFamily(
        "paid-revenue-by-segment",
        """
        SELECT c.segment, SUM(o.amount_cents) AS revenue_cents, COUNT(*) AS order_count
        FROM customers AS c JOIN orders AS o ON o.customer_id = c.id
        WHERE c.active = ? AND o.status = ? AND o.created_day BETWEEN ? AND ?
        GROUP BY c.segment ORDER BY c.segment
        """.strip(),
        ("boolean", "text", "integer", "integer"),
        True,
    ),
    QueryFamily(
        "customer-order-threshold",
        """
        SELECT c.id, COUNT(o.id) AS orders, SUM(o.amount_cents) AS spend_cents
        FROM customers AS c JOIN orders AS o ON o.customer_id = c.id
        WHERE o.amount_cents >= ? AND o.status = ?
        GROUP BY c.id HAVING COUNT(o.id) >= ? ORDER BY spend_cents DESC, c.id
        """.strip(),
        ("integer", "text", "integer"),
        True,
    ),
    QueryFamily(
        "bounded-range-scan",
        """
        SELECT id, customer_id, amount_cents
        FROM orders
        WHERE status = ? AND amount_cents BETWEEN ? AND ?
        ORDER BY amount_cents, id
        """.strip(),
        ("text", "integer", "integer"),
        True,
    ),
    QueryFamily(
        "region-channel-aggregate",
        """
        SELECT c.region, o.channel, COUNT(*) AS orders, SUM(o.amount_cents) AS cents
        FROM customers AS c JOIN orders AS o ON o.customer_id = c.id
        WHERE c.region = ? AND o.channel = ?
        GROUP BY c.region, o.channel ORDER BY c.region, o.channel
        """.strip(),
        ("text", "text"),
        True,
    ),
    QueryFamily(
        "nullable-coupon",
        """
        SELECT status, COUNT(*) AS orders, SUM(amount_cents) AS cents
        FROM orders
        WHERE coupon_code IS NULL AND created_day >= ?
        GROUP BY status ORDER BY status
        """.strip(),
        ("integer",),
        True,
    ),
    QueryFamily(
        "intentional-zero-result",
        """
        SELECT id, amount_cents FROM orders
        WHERE status = ? AND amount_cents > ? ORDER BY id
        """.strip(),
        ("text", "integer"),
        True,
    ),
)


@dataclass(frozen=True, slots=True)
class FixtureProfile:
    fixture_id: str
    customers: int
    orders: int
    paid_bps: int
    null_bps: int
    duplicate_bps: int
    skew_power_milli: int
    correlation_bps: int
    # Retained only to reproduce the pre-v2-hardening mixed-family test corpus.
    # Production task generation must select one QueryFamily explicitly.
    legacy_test_family_index: int


HOLDOUT_PROFILES: Final = (
    FixtureProfile("holdout_00_zero", 32, 0, 1_000, 0, 0, 1_000, 0, 5),
    FixtureProfile("holdout_01_small", 80, 420, 5_000, 1_000, 0, 1_000, 1_000, 0),
    FixtureProfile("holdout_02_skew", 500, 8_000, 800, 200, 500, 2_800, 2_000, 1),
    FixtureProfile("holdout_03_null", 900, 12_000, 3_500, 6_500, 300, 1_500, 4_000, 4),
    FixtureProfile("holdout_04_duplicates", 1_200, 18_000, 6_000, 1_000, 5_000, 1_100, 3_000, 2),
    FixtureProfile("holdout_05_correlated", 1_600, 24_000, 2_000, 500, 500, 1_800, 9_000, 3),
    FixtureProfile("holdout_06_boundary", 2_000, 30_000, 50, 2_000, 1_000, 3_500, 7_000, 2),
    FixtureProfile("holdout_07_large_agg", 2_500, 42_000, 4_300, 800, 2_000, 2_200, 8_000, 0),
)


@dataclass(frozen=True, slots=True)
class GeneratedFixture:
    descriptor: HiddenFixtureDescriptor
    profile: FixtureProfile
    query_family: QueryFamily
    parameters: tuple[int | str | bool, ...]
    customers: tuple[tuple[object, ...], ...]
    orders: tuple[tuple[object, ...], ...]


def _range(
    name: str,
    value_type: Literal["integer", "text", "boolean"],
    minimum: int | str | bool,
    maximum: int | str | bool,
    distribution: Literal["uniform", "log_uniform", "categorical", "boundary_weighted"],
) -> ParameterRange:
    return ParameterRange(
        name=name,
        value_type=value_type,
        minimum=minimum,
        maximum=maximum,
        distribution=distribution,
    )


def _query_family(family_id: str) -> QueryFamily:
    for family in QUERY_FAMILIES:
        if family.family_id == family_id:
            return family
    raise ValueError(f"unknown query family: {family_id}")


def _validate_hidden_seed(secret_seed: bytes) -> None:
    if len(secret_seed) != 32:
        raise ValueError("hidden fixture seed must contain exactly 32 bytes")


def published_parameter_ranges(family_id: str) -> tuple[ParameterRange, ...]:
    """Return complete, position-ordered parameter metadata for one SQL family.

    A :class:`~planrace.models_v2.PublicTaskV2` contains one ``reference_sql``.
    Its published ranges must therefore describe exactly that SQL statement's
    placeholders, in order, rather than a lossy union across all benchmark
    families.  Integer parameters are generated uniformly over the inclusive
    bounds below.  Text/boolean parameters are categorical; equal endpoints
    denote an intentionally constant category.
    """

    _query_family(family_id)
    if family_id == "paid-revenue-by-segment":
        return (
            _range("active", "boolean", False, True, "categorical"),
            _range("status", "text", "failed", "refunded", "categorical"),
            _range("created_day_start", "integer", 0, 3_650, "uniform"),
            _range("created_day_end", "integer", 0, 3_650, "uniform"),
        )
    if family_id == "customer-order-threshold":
        return (
            _range("minimum_amount_cents", "integer", 0, 5_000_000, "uniform"),
            _range("status", "text", "failed", "refunded", "categorical"),
            _range("minimum_order_count", "integer", 1, 12, "uniform"),
        )
    if family_id == "bounded-range-scan":
        return (
            _range("status", "text", "failed", "refunded", "categorical"),
            _range("minimum_amount_cents", "integer", 0, 5_000_000, "uniform"),
            _range("maximum_amount_cents", "integer", 0, 5_000_000, "uniform"),
        )
    if family_id == "region-channel-aggregate":
        return (
            _range("region", "text", "apac", "north-america", "categorical"),
            _range("channel", "text", "api", "web", "categorical"),
        )
    if family_id == "nullable-coupon":
        return (_range("created_day_minimum", "integer", 0, 3_650, "uniform"),)
    if family_id == "intentional-zero-result":
        return (
            _range(
                "status",
                "text",
                "nonexistent-status",
                "nonexistent-status",
                "categorical",
            ),
            _range(
                "amount_cents_exclusive_floor",
                "integer",
                5_000_000,
                5_000_000,
                "categorical",
            ),
        )
    raise AssertionError("unreachable query family")


def describe_hidden_fixtures(
    secret_seed: bytes, *, family_id: str
) -> tuple[HiddenFixtureDescriptor, ...]:
    return tuple(
        item.descriptor
        for item in generate_hidden_fixtures(secret_seed, family_id=family_id)
    )


def generate_hidden_fixtures(
    secret_seed: bytes, *, family_id: str
) -> tuple[GeneratedFixture, ...]:
    """Generate every hidden holdout for one PublicTask query family."""

    return generate_hidden_fixtures_for_family(secret_seed, family_id)


def generate_hidden_fixtures_for_family(
    secret_seed: bytes, family_id: str
) -> tuple[GeneratedFixture, ...]:
    """Generate a diverse holdout set with one SQL and one parameter arity."""

    _validate_hidden_seed(secret_seed)
    family = _query_family(family_id)
    return tuple(
        _generate_fixture(
            _derive_seed(secret_seed, profile.fixture_id, family.family_id),
            profile,
            family,
        )
        for profile in HOLDOUT_PROFILES
    )


def generate_mixed_family_fixtures_for_testing(
    secret_seed: bytes,
) -> tuple[GeneratedFixture, ...]:
    """Reproduce the old mixed-family corpus for tests; never use in a task."""

    _validate_hidden_seed(secret_seed)
    return tuple(
        _generate_fixture(
            _derive_seed(secret_seed, profile.fixture_id, family.family_id),
            profile,
            family,
        )
        for profile in HOLDOUT_PROFILES
        for family in (QUERY_FAMILIES[profile.legacy_test_family_index],)
    )


def generate_public_training_fixture(family_id: str) -> GeneratedFixture:
    """Generate the separately seeded public fixture for one query family."""

    profile = FixtureProfile(
        "training_public_v2", 180, 2_000, 2_500, 800, 500, 1_400, 4_000, 0
    )
    family = _query_family(family_id)
    return _generate_fixture(
        _derive_seed(PUBLIC_TRAINING_SEED, profile.fixture_id, family.family_id),
        profile,
        family,
    )


def materialize_fixture(fixture: GeneratedFixture, path: Path) -> str:
    """Write the canonical SQLite image and return its committed binary digest."""

    if path.exists():
        raise FileExistsError(path)
    payload = canonical_sqlite_database_bytes(fixture.customers, fixture.orders)
    path.write_bytes(payload)
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    if fixture.descriptor.database_file_digest != digest:
        path.unlink(missing_ok=True)
        raise ValueError("canonical database image does not match fixture commitment")
    return digest


def canonical_sqlite_database_bytes(
    customers: Sequence[Sequence[object]],
    orders: Sequence[Sequence[object]],
) -> bytes:
    """Create the one physical SQLite image allowed by benchmark v2."""

    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("PRAGMA page_size=4096")
        connection.execute("PRAGMA auto_vacuum=NONE")
        connection.execute("PRAGMA encoding='UTF-8'")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(SCHEMA_V2)
        connection.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?)", customers)
        connection.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?)", orders)
        connection.commit()
        connection.execute("VACUUM")
        return connection.serialize()
    finally:
        connection.close()


def _derive_seed(secret_seed: bytes, fixture_id: str, family_id: str) -> bytes:
    return hmac.new(
        secret_seed,
        b"planrace/2:hidden-fixture:"
        + family_id.encode("ascii")
        + b":"
        + fixture_id.encode("ascii"),
        hashlib.sha256,
    ).digest()


def _generate_fixture(
    seed: bytes, profile: FixtureProfile, family: QueryFamily
) -> GeneratedFixture:
    rng = random.Random(int.from_bytes(seed, "big"))  # noqa: S311 - deterministic expansion
    segments = ("enterprise", "midmarket", "small")
    regions = ("apac", "emea", "latam", "north-america")
    tiers: tuple[str | None, ...] = ("gold", "silver", "bronze", None)
    customers: list[tuple[object, ...]] = []
    for customer_id in range(1, profile.customers + 1):
        region = regions[rng.randrange(len(regions))]
        customers.append(
            (
                customer_id,
                segments[(customer_id + rng.randrange(len(segments))) % len(segments)],
                region,
                int(rng.randrange(10_000) >= 1_300),
                tiers[rng.randrange(len(tiers))],
            )
        )

    statuses = ("pending", "failed", "refunded")
    channels = ("api", "mobile", "partner", "web")
    orders: list[tuple[object, ...]] = []
    previous_payload: OrderPayload | None = None
    exponent = profile.skew_power_milli / 1_000
    for order_id in range(1, profile.orders + 1):
        if previous_payload is not None and rng.randrange(10_000) < profile.duplicate_bps:
            customer_id, amount_cents, status, channel, created_day, coupon = previous_payload
        else:
            customer_id = min(
                profile.customers,
                1 + int((rng.random() ** exponent) * profile.customers),
            )
            customer_region = str(customers[customer_id - 1][2])
            if rng.randrange(10_000) < profile.correlation_bps:
                channel = channels[regions.index(customer_region)]
            else:
                channel = channels[rng.randrange(len(channels))]
            status = "paid" if rng.randrange(10_000) < profile.paid_bps else rng.choice(statuses)
            # Heavy-tail integer cents, including exact 0 and upper boundaries.
            amount_cents = min(5_000_000, int((rng.random() ** 2.6) * 5_000_001))
            if order_id % 997 == 0:
                amount_cents = 5_000_000
            elif order_id % 499 == 0:
                amount_cents = 0
            created_day = rng.randrange(3_651)
            coupon = (
                None
                if rng.randrange(10_000) < profile.null_bps
                else f"C{rng.randrange(40):02d}"
            )
            previous_payload = (customer_id, amount_cents, status, channel, created_day, coupon)
        orders.append(
            (order_id, customer_id, amount_cents, status, channel, created_day, coupon)
        )

    parameters = _parameters_for(family.family_id, rng)
    content_digest = logical_fixture_content_digest(customers, orders)
    database_file_digest = "sha256:" + hashlib.sha256(
        canonical_sqlite_database_bytes(customers, orders)
    ).hexdigest()
    parameter_digest = fixture_parameter_set_digest(family.family_id, parameters)
    descriptor = HiddenFixtureDescriptor(
        fixture_id=profile.fixture_id,
        content_digest=content_digest,
        database_file_digest=database_file_digest,
        parameter_set_digest=parameter_digest,
        row_count=len(orders),
    )
    return GeneratedFixture(
        descriptor=descriptor,
        profile=profile,
        query_family=family,
        parameters=parameters,
        customers=tuple(customers),
        orders=tuple(orders),
    )


def _parameters_for(family_id: str, rng: random.Random) -> tuple[ParameterValue, ...]:
    statuses = ("failed", "paid", "pending", "refunded")
    if family_id == "paid-revenue-by-segment":
        start_day, end_day = sorted((rng.randrange(0, 3_651), rng.randrange(0, 3_651)))
        return (
            bool(rng.randrange(2)),
            statuses[rng.randrange(len(statuses))],
            start_day,
            end_day,
        )
    if family_id == "customer-order-threshold":
        return (
            rng.randrange(0, 5_000_001),
            statuses[rng.randrange(len(statuses))],
            rng.randrange(1, 13),
        )
    if family_id == "bounded-range-scan":
        minimum_cents, maximum_cents = sorted(
            (rng.randrange(0, 5_000_001), rng.randrange(0, 5_000_001))
        )
        return (
            statuses[rng.randrange(len(statuses))],
            minimum_cents,
            maximum_cents,
        )
    if family_id == "region-channel-aggregate":
        regions = ("apac", "emea", "latam", "north-america")
        channels = ("api", "mobile", "partner", "web")
        return (
            regions[rng.randrange(len(regions))],
            channels[rng.randrange(len(channels))],
        )
    if family_id == "nullable-coupon":
        return (rng.randrange(0, 3_651),)
    if family_id == "intentional-zero-result":
        return ("nonexistent-status", 5_000_000)
    raise ValueError(f"unknown query family: {family_id}")


def logical_fixture_content_digest(
    customers: Sequence[Sequence[object]],
    orders: Sequence[Sequence[object]],
) -> str:
    """Hash logical rows independently of SQLite's binary file layout."""

    hasher = hashlib.sha256()
    hasher.update(b"planrace/2:logical-fixture\x00")
    for relation, rows in (("customers", customers), ("orders", orders)):
        for row in _iter_rows(relation, rows):
            hasher.update(len(row).to_bytes(4, "big"))
            hasher.update(row)
    return "sha256:" + hasher.hexdigest()


def logical_fixture_content_digest_from_database(
    database: Path | sqlite3.Connection,
) -> str:
    """Recompute the logical fixture digest from a read-only database.

    The fixed column lists and primary-key ordering make this suitable for a
    sandbox admission check: a repacked SQLite file has the same digest, while
    any logical row or storage-class change does not.
    """

    if isinstance(database, sqlite3.Connection):
        connection = database
        owns_connection = False
    else:
        connection = sqlite3.connect(
            database.resolve().as_uri() + "?mode=ro&immutable=1", uri=True
        )
        owns_connection = True
    try:
        customers = tuple(
            connection.execute(
                "SELECT id, segment, region, active, tier FROM customers ORDER BY id"
            )
        )
        orders = tuple(
            connection.execute(
                """
                SELECT id, customer_id, amount_cents, status, channel, created_day, coupon_code
                FROM orders ORDER BY id
                """
            )
        )
        return logical_fixture_content_digest(customers, orders)
    finally:
        if owns_connection:
            connection.close()


def verify_logical_fixture_content_digest(
    database: Path | sqlite3.Connection, expected_digest: str
) -> bool:
    """Return whether a database matches a committed logical fixture digest."""

    if not _is_sha256_digest(expected_digest):
        raise ValueError("expected_digest must be a lowercase sha256 digest")
    actual = logical_fixture_content_digest_from_database(database)
    return hmac.compare_digest(actual, expected_digest)


def fixture_parameter_set_digest(
    family_id: str, parameters: Sequence[int | str | bool | None]
) -> str:
    """Bind a concrete ordered parameter tuple to its benchmark family."""

    if not family_id or len(family_id) > 63:
        raise ValueError("family_id must be non-empty and at most 63 characters")
    return _digest_json(
        "planrace/2:fixture-parameters",
        {"family": family_id, "parameters": list(parameters)},
    )


def _iter_rows(relation: str, rows: Sequence[Sequence[object]]) -> Iterator[bytes]:
    for row in rows:
        yield json.dumps(
            {"relation": relation, "row": row},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")


def _digest_json(domain: str, value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(domain.encode("ascii") + b"\x00" + payload).hexdigest()


def _is_sha256_digest(value: str) -> bool:
    return (
        len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )
