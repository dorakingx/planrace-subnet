"""Commit/reveal task generation and deterministic hidden database fixtures."""

from __future__ import annotations

import hashlib
import json
import random
import sqlite3
from dataclasses import dataclass

from planrace.models import PROTOCOL_VERSION, QueryTask, SeedReveal

SCHEMA_SQL = """
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    segment TEXT NOT NULL,
    active INTEGER NOT NULL CHECK(active IN (0, 1))
);
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    status TEXT NOT NULL
);
""".strip()

REFERENCE_SQL = """
SELECT c.segment, ROUND(SUM(o.amount), 2) AS revenue
FROM customers AS c JOIN orders AS o ON o.customer_id = c.id
WHERE c.active = 1 AND o.status = 'paid'
GROUP BY c.segment ORDER BY c.segment
""".strip()


@dataclass(frozen=True, slots=True)
class HiddenWorkload:
    task: QueryTask
    reveal: SeedReveal
    customer_count: int
    order_count: int
    paid_probability: float


def seed_commitment(*, task_id: str, seed: int, salt: str) -> str:
    payload = json.dumps(
        {"protocol": PROTOCOL_VERSION, "salt": salt, "seed": seed, "task_id": task_id},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def generate_workload(epoch: int, *, root_seed: int = 202_608_31) -> HiddenWorkload:
    seed = root_seed + epoch * 7919
    task_id = f"orders-v1-e{epoch}-{seed}"
    salt = hashlib.sha256(f"planrace:{root_seed}:{epoch}".encode()).hexdigest()[:32]
    paid_probability = (0.08, 0.21, 0.43)[epoch % 3]
    task = QueryTask(
        task_id=task_id,
        epoch=epoch,
        engine="sqlite-3",
        schema_sql=SCHEMA_SQL,
        reference_sql=REFERENCE_SQL,
        generator_version="orders-v1",
        seed_commitment=seed_commitment(task_id=task_id, seed=seed, salt=salt),
        max_setup_statements=2,
        repetitions=7,
    )
    return HiddenWorkload(
        task=task,
        reveal=SeedReveal(task_id=task_id, seed=seed, salt=salt),
        customer_count=700 + epoch * 130,
        order_count=18_000 + epoch * 4_000,
        paid_probability=paid_probability,
    )


def verify_reveal(task: QueryTask, reveal: SeedReveal) -> bool:
    if task.task_id != reveal.task_id:
        return False
    return task.seed_commitment == seed_commitment(
        task_id=reveal.task_id, seed=reveal.seed, salt=reveal.salt
    )


def build_database(workload: HiddenWorkload) -> sqlite3.Connection:
    if not verify_reveal(workload.task, workload.reveal):
        raise ValueError("seed reveal does not match task commitment")
    # Determinism after reveal is the protocol property. Production validators
    # choose the unrevealed seed with secrets.randbits; this PRNG only expands it.
    rng = random.Random(workload.reveal.seed)  # noqa: S311
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA temp_store=MEMORY")
    connection.executescript(workload.task.schema_sql)
    segments = ("enterprise", "midmarket", "small")
    customers = [
        (customer_id, segments[(customer_id + rng.randrange(3)) % 3], rng.random() >= 0.13)
        for customer_id in range(1, workload.customer_count + 1)
    ]
    other_statuses = ("pending", "failed", "refunded")
    orders = []
    for order_id in range(1, workload.order_count + 1):
        status = "paid" if rng.random() < workload.paid_probability else rng.choice(other_statuses)
        customer_id = 1 + int((rng.random() ** 1.7) * workload.customer_count)
        amount = round(5 + (rng.random() ** 2) * 2500, 2)
        orders.append((order_id, customer_id, amount, status))
    connection.executemany("INSERT INTO customers VALUES (?, ?, ?)", customers)
    connection.executemany("INSERT INTO orders VALUES (?, ?, ?, ?)", orders)
    connection.commit()
    return connection
