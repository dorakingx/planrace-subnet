from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

import planrace.sandbox_v2 as sandbox_module
from planrace.benchmark_v2 import (
    SCHEMA_V2,
    benchmark_generator_source_digest,
    fixture_parameter_set_digest,
    logical_fixture_content_digest_from_database,
)
from planrace.models_v2 import (
    ArtifactBudget,
    ArtifactGrammar,
    BundleMetadata,
    HiddenFixtureDescriptor,
    IndexColumn,
    IndexSpec,
    OptimizationBundle,
    ParameterRange,
    PublicTrainingFixture,
    PublishedStatistics,
    validator_index_name,
)
from planrace.sandbox_v2 import (
    AdmissionError,
    SandboxPolicy,
    SandboxRequestV2,
    benchmark_runtime_policy_digest,
    build_docker_worker_command,
    execute_request,
    run_bounded_process,
    validate_reference_query,
)
from planrace.scoring_v2 import BenchmarkPolicy, benchmark_evidence_from_sandbox, score_benchmark
from planrace.taskgen_v2 import create_task_v2

TASK_ID = "a" * 32
ENGINE_DIGEST = "sha256:" + "b" * 64
SCHEMA_SQL = SCHEMA_V2


class FixedEntropy:
    def __init__(self) -> None:
        self.values = [bytes.fromhex(TASK_ID), b"s" * 32, b"z" * 32]

    def token_bytes(self, size: int) -> bytes:
        value = self.values.pop(0)
        assert len(value) == size
        return value


def _fixture_descriptors(
    seed: bytes,
    *,
    content_digest: str,
    database_file_digest: str,
    parameter_digest: str,
    row_count: int,
) -> tuple[HiddenFixtureDescriptor, ...]:
    return tuple(
        HiddenFixtureDescriptor(
            fixture_id=f"holdout_{index}",
            content_digest=content_digest,
            database_file_digest=database_file_digest,
            parameter_set_digest=parameter_digest,
            row_count=row_count,
        )
        for index in range(2)
    )


def _bundle(*indexes: IndexSpec) -> OptimizationBundle:
    return OptimizationBundle.create(
        task_id=TASK_ID,
        engine_image_digest=ENGINE_DIGEST,
        indexes=indexes,
        metadata=BundleMetadata(
            strategy="test",
            estimated_intent="filter" if indexes else "no_index",
            rationale="",
        ),
    )


def _request(
    database: Path,
    reference_sql: str,
    *,
    bundle: OptimizationBundle | None = None,
    parameters: tuple[int | str | bool | None, ...] = (),
    artifact_budget: ArtifactBudget | None = None,
    artifact_grammar: ArtifactGrammar | None = None,
    schema_sql: str = SCHEMA_SQL,
    sandbox_policy: SandboxPolicy | None = None,
    benchmark_policy: BenchmarkPolicy | None = None,
    trial_count: int = 6,
) -> SandboxRequestV2:
    effective_policy = sandbox_policy or SandboxPolicy()
    effective_benchmark_policy = benchmark_policy or BenchmarkPolicy()
    content_digest = logical_fixture_content_digest_from_database(database)
    database_file_digest = "sha256:" + hashlib.sha256(database.read_bytes()).hexdigest()
    parameter_digest = fixture_parameter_set_digest("sandbox-test", parameters)
    with sqlite3.connect(database) as connection:
        row_count = int(connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0])
    private = create_task_v2(
        validator_hotkey="5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXQVRvNbCcxgxv",
        engine_image_digest=ENGINE_DIGEST,
        generator_source_digest=benchmark_generator_source_digest(),
        benchmark_policy_digest=benchmark_runtime_policy_digest(
            sandbox_policy=effective_policy,
            benchmark_policy=effective_benchmark_policy,
            trial_count=trial_count,
        ),
        benchmark_family_id="sandbox-test",
        schema_sql=schema_sql,
        reference_sql=reference_sql,
        public_training_fixture=PublicTrainingFixture(
            fixture_id="training",
            generator_seed_hex="e" * 64,
            content_digest="sha256:" + "f" * 64,
            row_count=4,
        ),
        parameter_ranges=(
            ParameterRange(
                name="parameter",
                value_type="integer",
                minimum=0,
                maximum=1_000,
                distribution="uniform",
            ),
        ),
        published_statistics=PublishedStatistics(
            row_count_min=0,
            row_count_max=1_000,
            selectivity_min_bps=0,
            selectivity_max_bps=10_000,
            data_profiles=("uniform", "duplicate_heavy"),
        ),
        deadline_unix_ms=2_000_000,
        hidden_fixture_factory=lambda seed: _fixture_descriptors(
            seed,
            content_digest=content_digest,
            database_file_digest=database_file_digest,
            parameter_digest=parameter_digest,
            row_count=row_count,
        ),
        artifact_budget=artifact_budget,
        artifact_grammar=artifact_grammar,
        entropy=FixedEntropy(),
    )
    return SandboxRequestV2(
        task=private.public,
        reveal=private.reveal,
        fixture=private.reveal.hidden_fixtures[0],
        bundle=bundle or _bundle(),
        parameters=parameters,
        trial_count=trial_count,
        benchmark_policy=effective_benchmark_policy,
    )


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = tmp_path / "fixture.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA_V2)
    connection.execute(
        "INSERT INTO customers(id, segment, region, active, tier) "
        "VALUES (1, 'small', 'apac', 1, NULL)"
    )
    connection.executemany(
        """
        INSERT INTO orders(
            id, customer_id, amount_cents, status, channel, created_day, coupon_code
        ) VALUES (?, 1, ?, ?, 'web', 1, NULL)
        """,
        ((1, 100, "paid"), (2, 250, "paid"), (3, 900, "pending"), (4, 100, "paid")),
    )
    connection.commit()
    connection.close()
    return path


def test_structured_bundle_exact_result_passes_in_test_engine(database: Path) -> None:
    index = IndexSpec(table="orders", key_columns=(IndexColumn(column="status"),))
    request = _request(
        database,
        (
            "SELECT status, SUM(amount_cents) FROM orders "
            "WHERE status = ? GROUP BY status ORDER BY status"
        ),
        bundle=_bundle(index),
        parameters=("paid",),
    )
    result = execute_request(database, request, require_pinned_engine=False)
    assert result.success
    assert result.correct
    assert result.reference_digest == result.candidate_digest
    assert len(result.trials) == request.trial_count
    assert {trial.order for trial in result.trials} == {"baseline-first", "candidate-first"}
    assert len({trial.worker_id for trial in result.trials}) == 1
    assert result.worker_id == result.trials[0].worker_id
    assert result.used_index_names == (validator_index_name(index),)
    assert any(validator_index_name(index) in line for line in result.candidate_plan)


def test_custom_scoring_policy_is_serialized_and_bound_to_task(database: Path) -> None:
    custom_policy = BenchmarkPolicy(confidence_z=2.0)
    request = _request(
        database,
        "SELECT id FROM orders ORDER BY id",
        benchmark_policy=custom_policy,
    )
    assert execute_request(database, request, require_pinned_engine=False).success

    tampered = request.model_copy(update={"benchmark_policy": BenchmarkPolicy()})
    result = execute_request(database, tampered, require_pinned_engine=False)
    assert result.failure_code == "benchmark_policy_mismatch"


@pytest.mark.parametrize(
    ("sql", "code"),
    [
        ("PRAGMA writable_schema=ON", "read_only_query_required"),
        ("ATTACH DATABASE '/tmp/x' AS x", "read_only_query_required"),
        ("SELECT 1; DROP TABLE orders", "multiple_statements"),
        (
            "WITH RECURSIVE x(v) AS (SELECT 1 UNION ALL SELECT v+1 FROM x) SELECT * FROM x",
            "recursive_cte",
        ),
        ("SELECT zeroblob(1000)", "forbidden_function"),
        ("SELECT random()", "forbidden_function"),
        ("SELECT sqlite_version()", "forbidden_function"),
        ("SELECT printf('%s', 'x')", "forbidden_function"),
        ("SELECT * FROM orders CROSS JOIN orders AS other", "unbounded_join"),
        ("SELECT * FROM orders JOIN orders AS other", "unbounded_join"),
    ],
)
def test_adversarial_reference_sql_is_rejected(sql: str, code: str) -> None:
    with pytest.raises(AdmissionError, match=code):
        validate_reference_query(sql)


def test_parameter_placeholder_is_allowed() -> None:
    assert validate_reference_query("SELECT ?") == "SELECT ?"


def test_expression_index_cannot_enter_structured_grammar() -> None:
    with pytest.raises(ValidationError):
        IndexColumn(column="lower(status)")


def test_unknown_table_and_column_fail_closed(database: Path) -> None:
    for spec in (
        IndexSpec(table="secrets", key_columns=(IndexColumn(column="value"),)),
        IndexSpec(table="orders", key_columns=(IndexColumn(column="secret"),)),
    ):
        result = execute_request(
            database,
            _request(database, "SELECT id FROM orders", bundle=_bundle(spec)),
            require_pinned_engine=False,
        )
        assert not result.success
        assert result.failure_code in {"unknown_table", "unknown_column"}


def test_committed_fixture_content_parameters_and_schema_are_enforced(database: Path) -> None:
    content_request = _request(database, "SELECT id FROM orders")
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE orders SET amount_cents = amount_cents + 1 WHERE id = 1")
        connection.commit()
    substituted = execute_request(database, content_request, require_pinned_engine=False)
    assert substituted.failure_code == "fixture_file_mismatch"

    parameter_request = _request(
        database,
        "SELECT id FROM orders WHERE status = ?",
        parameters=("paid",),
    )
    tampered_parameters = parameter_request.model_copy(update={"parameters": ("pending",)})
    parameter_result = execute_request(database, tampered_parameters, require_pinned_engine=False)
    assert parameter_result.failure_code == "fixture_parameters_mismatch"

    schema_request = _request(
        database,
        "SELECT id FROM orders",
        schema_sql=(
            "CREATE TABLE orders("
            "id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL, amount_cents INTEGER NOT NULL, "
            "status TEXT NOT NULL, channel TEXT NOT NULL, created_day INTEGER NOT NULL, "
            "coupon_code TEXT)"
        ),
    )
    schema_result = execute_request(database, schema_request, require_pinned_engine=False)
    assert schema_result.failure_code == "fixture_schema_mismatch"


def test_virtual_schema_and_preexisting_indexes_are_rejected(database: Path) -> None:
    virtual_request = _request(
        database,
        "SELECT id FROM orders",
        schema_sql="CREATE VIRTUAL TABLE docs USING fts5(content)",
    )
    virtual_result = execute_request(database, virtual_request, require_pinned_engine=False)
    assert virtual_result.failure_code == "virtual_table_forbidden"

    with sqlite3.connect(database) as connection:
        connection.execute("CREATE INDEX undisclosed_status ON orders(status)")
        connection.commit()
    index_request = _request(database, "SELECT id FROM orders")
    index_result = execute_request(database, index_request, require_pinned_engine=False)
    assert index_result.failure_code == "preexisting_index"


def test_task_specific_artifact_budget_and_grammar_are_enforced(database: Path) -> None:
    index = IndexSpec(table="orders", key_columns=(IndexColumn(column="status"),))
    budget_request = _request(
        database,
        "SELECT id FROM orders",
        bundle=_bundle(index),
        artifact_budget=ArtifactBudget(max_indexes=0),
    )
    assert (
        execute_request(database, budget_request, require_pinned_engine=False).failure_code
        == "index_count_policy"
    )

    unique = IndexSpec(
        table="orders",
        key_columns=(IndexColumn(column="id"),),
        unique=True,
    )
    grammar_request = _request(
        database,
        "SELECT id FROM orders",
        bundle=_bundle(unique),
        artifact_grammar=ArtifactGrammar(allows_unique=False),
    )
    assert (
        execute_request(database, grammar_request, require_pinned_engine=False).failure_code
        == "unique_index_policy"
    )


def test_row_limit_becomes_zero_score_not_validator_crash(database: Path) -> None:
    policy = SandboxPolicy(max_rows=2)
    result = execute_request(
        database,
        _request(database, "SELECT * FROM orders", sandbox_policy=policy),
        policy=policy,
        require_pinned_engine=False,
    )
    assert not result.success
    assert result.failure_code == "row_limit"


def test_index_growth_cannot_exceed_database_file_limit(database: Path) -> None:
    with sqlite3.connect(database) as connection:
        connection.executemany(
            """
            INSERT INTO orders(
                customer_id, amount_cents, status, channel, created_day, coupon_code
            ) VALUES (1, ?, 'paid', 'web', 1, ?)
            """,
            ((number, f"coupon-{number:08d}-" + "x" * 96) for number in range(20_000)),
        )
        connection.commit()
    input_size = database.stat().st_size
    policy = SandboxPolicy(max_database_bytes=max(1024 * 1024, input_size + 64 * 1024))
    index = IndexSpec(
        table="orders",
        key_columns=(IndexColumn(column="coupon_code"),),
    )
    result = execute_request(
        database,
        _request(
            database,
            "SELECT id FROM orders WHERE coupon_code IS NULL",
            bundle=_bundle(index),
            sandbox_policy=policy,
        ),
        policy=policy,
        require_pinned_engine=False,
    )
    assert result.failure_code == "database_limit"


def test_candidate_timeout_is_recorded_and_scored_without_aborting(
    database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = sandbox_module._run_candidate_once
    attempts = 0

    def first_two_timeout(*args: Any, **kwargs: Any) -> Any:
        nonlocal attempts
        attempts += 1
        if attempts <= 2:
            return None, 10.0, True
        return original(*args, **kwargs)

    monkeypatch.setattr(sandbox_module, "_run_candidate_once", first_two_timeout)
    request = _request(database, "SELECT id FROM orders ORDER BY id")
    result = execute_request(database, request, require_pinned_engine=False)
    score = score_benchmark(benchmark_evidence_from_sandbox(result))

    assert result.success and result.correct
    assert sum(trial.candidate_timed_out for trial in result.trials) == 2
    assert score.timeout_rate == pytest.approx(2 / 6)
    assert score.failure_code == "timeout_rate"


def test_malformed_utf8_fails_closed(database: Path) -> None:
    request = _request(database, "SELECT status FROM orders")
    connection = sqlite3.connect(database)
    connection.execute(
        """
        INSERT INTO orders(
            customer_id, amount_cents, status, channel, created_day, coupon_code
        ) VALUES (1, 1, CAST(X'80' AS TEXT), 'web', 1, NULL)
        """
    )
    connection.commit()
    connection.close()
    result = execute_request(
        database,
        request,
        require_pinned_engine=False,
    )
    assert not result.success
    assert result.failure_code == "fixture_file_mismatch"


def test_crash_and_timeout_do_not_stop_next_worker() -> None:
    crash = run_bounded_process([sys.executable, "-c", "import os; os._exit(23)"])
    timeout = run_bounded_process(
        [sys.executable, "-c", "while True: pass"],
        policy=SandboxPolicy(wall_timeout_seconds=0.1),
    )
    healthy = run_bounded_process([sys.executable, "-c", "print('ok')"])
    assert crash.status == "crash"
    assert timeout.status == "timeout"
    assert healthy.status == "ok" and healthy.stdout.strip() == b"ok"


def test_worker_spawn_failure_is_zero_score_outcome_not_validator_exception() -> None:
    missing = run_bounded_process(["/definitely/missing/planrace-worker"])
    healthy = run_bounded_process([sys.executable, "-c", "print('still-alive')"])
    assert missing.status == "spawn_error"
    assert healthy.status == "ok"


def test_oom_style_worker_failure_does_not_stop_validator() -> None:
    failed = run_bounded_process(
        [sys.executable, "-c", "raise MemoryError('simulated allocation refusal')"]
    )
    healthy = run_bounded_process([sys.executable, "-c", "print('validator-alive')"])
    assert failed.status == "crash"
    assert healthy.status == "ok"


def test_expensive_query_hits_phase_deadline(database: Path) -> None:
    connection = sqlite3.connect(database)
    connection.executemany(
        """
        INSERT INTO orders(
            customer_id, amount_cents, status, channel, created_day, coupon_code
        ) VALUES (1, ?, 'paid', 'web', 1, NULL)
        """,
        ((number,) for number in range(1_200)),
    )
    connection.commit()
    connection.close()
    policy = SandboxPolicy(query_timeout_ms=10)
    result = execute_request(
        database,
        _request(
            database,
            (
                "SELECT SUM(a.amount_cents * b.amount_cents * c.amount_cents) "
                "FROM orders AS a "
                "JOIN orders AS b ON a.id > 0 "
                "JOIN orders AS c ON b.id > 0"
            ),
            sandbox_policy=policy,
        ),
        policy=policy,
        require_pinned_engine=False,
    )
    assert not result.success
    assert result.failure_code == "query_timeout"


def test_worker_output_is_bounded() -> None:
    outcome = run_bounded_process(
        [sys.executable, "-c", "print('x' * 10000)"],
        policy=SandboxPolicy(max_worker_output_bytes=1024),
    )
    assert outcome.status in {"crash", "output_limit"}


def test_production_docker_command_has_all_isolation_controls(database: Path) -> None:
    image = "registry.example/planrace-worker@sha256:" + "c" * 64
    command = build_docker_worker_command(database, image=image)
    joined = " ".join(command)
    assert "--network none" in joined
    assert "--read-only" in command
    assert "--cap-drop ALL" in joined
    assert "no-new-privileges:true" in command
    assert "--pids-limit" in command
    assert "--memory" in command
    assert "--memory-swap" in command
    assert "--user 65532:65532" in joined
    assert f"{database.resolve()}:/input/fixture.sqlite3:ro" in command
    assert not any(key in joined.upper() for key in ("TOKEN=", "SECRET=", "MNEMONIC="))


def test_local_content_digest_is_an_immutable_worker_reference(database: Path) -> None:
    image = "sha256:" + "c" * 64
    command = build_docker_worker_command(database, image=image)
    assert image in command


def test_production_worker_rejects_mutable_image_tag(database: Path) -> None:
    with pytest.raises(ValueError, match="pinned"):
        build_docker_worker_command(database, image="planrace-worker:latest")


def test_trial_count_must_support_balanced_interleaving(database: Path) -> None:
    with pytest.raises(ValidationError, match="even"):
        _request(database, "SELECT id FROM orders", trial_count=7)


def test_process_outcome_json_is_bounded_model() -> None:
    outcome = run_bounded_process(
        [sys.executable, "-c", "import json; print(json.dumps({'ok': True}))"]
    )
    assert json.loads(outcome.stdout) == {"ok": True}
    assert os.getpid() > 0  # the validator process is still alive
