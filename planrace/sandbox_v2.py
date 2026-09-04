"""Fail-closed SQLite worker and disposable-container boundary for PlanRace v2."""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import os
import re
import secrets
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlglot import exp, parse
from sqlglot.errors import ParseError

from planrace.benchmark_v2 import (
    benchmark_generator_source_digest,
    fixture_parameter_set_digest,
    verify_logical_fixture_content_digest,
)
from planrace.models_v2 import (
    HiddenFixtureDescriptor,
    OptimizationBundle,
    PublicTaskV2,
    TaskRevealV2,
    compile_index_sql,
    domain_separated_digest,
    validator_index_name,
)
from planrace.oracle_v2 import (
    PINNED_SQLITE_ENGINE,
    CanonicalResult,
    ResultLimitExceeded,
    ResultPolicy,
    canonicalize_result,
)
from planrace.scoring_v2 import DEFAULT_BENCHMARK_POLICY, BenchmarkPolicy
from planrace.taskgen_v2 import audit_task_reveal

PINNED_WORKER_BASE: Final = (
    "python@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285"
)
PINNED_SQLITE_VERSION: Final = PINNED_SQLITE_ENGINE.removeprefix("sqlite-")
DEFAULT_WORKER_IMAGE: Final = "planrace-validator-worker:local"

_REPOSITORY_DIGEST_IMAGE = re.compile(r"^[a-z0-9./_:-]+@sha256:[0-9a-f]{64}$")
_LOCAL_CONTENT_DIGEST_IMAGE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ALLOWED_FUNCTIONS: Final = frozenset(
    {
        "abs",
        "avg",
        "cast",
        "coalesce",
        "count",
        "ifnull",
        "instr",
        "length",
        "lower",
        "max",
        "min",
        "nullif",
        "round",
        "substr",
        "substring",
        "sum",
        "total",
        "typeof",
        "unicode",
        "upper",
    }
)


class StrictSandboxModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


ParameterValue = int | str | bool | None


class SandboxRequestV2(StrictSandboxModel):
    protocol_version: Literal["planrace/2"] = "planrace/2"
    task: PublicTaskV2
    reveal: TaskRevealV2
    fixture: HiddenFixtureDescriptor
    bundle: OptimizationBundle
    parameters: Annotated[tuple[ParameterValue, ...], Field(max_length=32)] = ()
    ordered: bool = True
    collation: Literal["sqlite-binary", "sqlite-nocase", "sqlite-rtrim"] = "sqlite-binary"
    trial_count: Annotated[int, Field(ge=6, le=24)] = 6
    benchmark_policy: BenchmarkPolicy = DEFAULT_BENCHMARK_POLICY

    @model_validator(mode="after")
    def require_balanced_trials(self) -> SandboxRequestV2:
        if self.trial_count % 2:
            raise ValueError("trial_count must be even for balanced interleaving")
        if self.bundle.task_id != self.task.task_id or self.reveal.task_id != self.task.task_id:
            raise ValueError("task, reveal, and bundle IDs must match")
        if self.bundle.engine_image_digest != self.task.engine_image_digest:
            raise ValueError("bundle engine must match the committed task engine")
        if self.fixture not in self.reveal.hidden_fixtures:
            raise ValueError("fixture must be a member of the committed reveal")
        return self


class SandboxTrialV2(StrictSandboxModel):
    worker_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    order: Literal["baseline-first", "candidate-first"]
    baseline_cold_ms: Annotated[float, Field(gt=0.0)]
    candidate_cold_ms: Annotated[float, Field(gt=0.0)]
    baseline_warm_ms: Annotated[float, Field(gt=0.0)]
    candidate_warm_ms: Annotated[float, Field(gt=0.0)]
    baseline_timed_out: bool = False
    candidate_timed_out: bool = False


class SandboxResultV2(StrictSandboxModel):
    protocol_version: Literal["planrace/2"] = "planrace/2"
    success: bool
    failure_code: str | None
    engine: str
    artifact_digest: str
    task_id: str
    task_commitment: str
    fixture_id: str
    fixture_content_digest: str
    hidden_fixture_merkle_root: str
    reference_digest: str | None = None
    candidate_digest: str | None = None
    correct: bool = False
    compliant: bool = False
    row_count: Annotated[int, Field(ge=0)] = 0
    setup_ms: Annotated[float, Field(ge=0.0)] = 0.0
    worker_id: str | None = None
    trials: tuple[SandboxTrialV2, ...] = ()
    database_bytes: Annotated[int, Field(ge=0)] = 0
    artifact_storage_bytes: Annotated[int, Field(ge=0)] = 0
    candidate_plan: tuple[str, ...] = ()
    used_index_names: tuple[str, ...] = ()


class SandboxPolicy(StrictSandboxModel):
    wall_timeout_seconds: Annotated[float, Field(gt=0.0, le=60.0)] = 20.0
    query_timeout_ms: Annotated[int, Field(ge=10, le=10_000)] = 750
    memory_bytes: Annotated[int, Field(ge=64 * 1024 * 1024)] = 256 * 1024 * 1024
    cpu_seconds: Annotated[int, Field(ge=1, le=30)] = 10
    pids_limit: Annotated[int, Field(ge=4, le=64)] = 16
    max_database_bytes: Annotated[int, Field(ge=1024 * 1024)] = 64 * 1024 * 1024
    max_rows: Annotated[int, Field(ge=1, le=100_000)] = 10_000
    max_cells: Annotated[int, Field(ge=1, le=1_000_000)] = 100_000
    max_result_bytes: Annotated[int, Field(ge=1024, le=16 * 1024 * 1024)] = 2 * 1024 * 1024
    max_worker_input_bytes: Annotated[int, Field(ge=64 * 1024, le=1024 * 1024)] = 256 * 1024
    max_worker_output_bytes: Annotated[int, Field(ge=1024, le=1024 * 1024)] = 64 * 1024


DEFAULT_SANDBOX_POLICY: Final = SandboxPolicy()


def benchmark_runtime_policy_digest(
    *,
    sandbox_policy: SandboxPolicy = DEFAULT_SANDBOX_POLICY,
    benchmark_policy: BenchmarkPolicy = DEFAULT_BENCHMARK_POLICY,
    trial_count: int = 6,
    ordered: bool = True,
    collation: str = "sqlite-binary",
) -> str:
    """Commit the exact measurement, resource and scoring policy."""

    def number(value: float) -> str:
        return format(value, ".17g")

    payload = {
        "policy_version": "planrace-benchmark-policy/2.1",
        "engine": PINNED_SQLITE_ENGINE,
        "interleaving": "abba-fresh-connections-cold-warm-v1",
        "trial_count": trial_count,
        "ordered": ordered,
        "collation": collation,
        "scoring": {
            "horizons": list(benchmark_policy.horizons),
            "horizon_weights": [number(value) for value in benchmark_policy.horizon_weights],
            "minimum_trials": benchmark_policy.minimum_trials,
            "winsor_fraction": number(benchmark_policy.winsor_fraction),
            "confidence_z": number(benchmark_policy.confidence_z),
            "maximum_timeout_rate": number(benchmark_policy.maximum_timeout_rate),
            "storage_penalty_at_database_size": number(
                benchmark_policy.storage_penalty_at_database_size
            ),
        },
        "sandbox": {
            key: number(value) if isinstance(value, float) else value
            for key, value in sandbox_policy.model_dump(mode="python").items()
        },
    }
    return domain_separated_digest("planrace/2:benchmark-runtime-policy", payload)


class AdmissionError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class WorkerFailure(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def validate_reference_query(sql: str) -> str:
    """Parse a validator-owned reference query with a pinned SQLite AST parser."""

    if len(sql.encode("utf-8")) > 65_536:
        raise AdmissionError("sql_size")
    try:
        statements = parse(sql, read="sqlite")
    except ParseError as error:
        raise AdmissionError("parse_error") from error
    if len(statements) != 1 or statements[0] is None:
        raise AdmissionError("multiple_statements")
    statement = statements[0]
    if not isinstance(statement, exp.Query):
        raise AdmissionError("read_only_query_required")
    forbidden = (
        exp.Alter,
        exp.Attach,
        exp.Command,
        exp.Create,
        exp.Delete,
        exp.Detach,
        exp.Drop,
        exp.Insert,
        exp.Merge,
        exp.Pragma,
        exp.Transaction,
        exp.Update,
        exp.Use,
    )
    if any(isinstance(node, forbidden) for node in statement.walk()):
        raise AdmissionError("forbidden_statement")
    for with_clause in statement.find_all(exp.With):
        if bool(with_clause.args.get("recursive")):
            raise AdmissionError("recursive_cte")
    for join in statement.find_all(exp.Join):
        on_clause = join.args.get("on")
        if (
            str(join.args.get("kind") or "").upper() == "CROSS"
            or not on_clause
            or (isinstance(on_clause, exp.Boolean) and on_clause.this is True)
        ):
            raise AdmissionError("unbounded_join")
    for function in statement.find_all(exp.Func):
        # SQLGlot models boolean/arithmetic operators such as AND as Func via
        # multiple inheritance. They are bounded AST operators, not SQLite
        # function calls governed by the runtime function allowlist.
        if isinstance(function, exp.Binary):
            continue
        name = function.sql_name().lower()
        if name == "anonymous":
            name = str(getattr(function, "name", "")).lower()
        if name not in _ALLOWED_FUNCTIONS:
            raise AdmissionError("forbidden_function")
    return statement.sql(dialect="sqlite", pretty=False)


def execute_request(
    database_path: Path,
    request: SandboxRequestV2,
    *,
    policy: SandboxPolicy = DEFAULT_SANDBOX_POLICY,
    require_pinned_engine: bool = True,
) -> SandboxResultV2:
    """Evaluate one structured bundle; all exceptions become a zero-score result."""

    artifact_bytes = len(request.bundle.model_dump_json().encode("utf-8"))
    try:
        database_bytes = _safe_database_size(database_path, policy)
    except WorkerFailure as error:
        return _failure(request, error.code, 0, artifact_bytes)
    if not audit_task_reveal(request.task, request.reveal):
        return _failure(request, "task_reveal_mismatch", database_bytes, artifact_bytes)
    if not hmac.compare_digest(
        request.task.generator_source_digest, benchmark_generator_source_digest()
    ):
        return _failure(request, "generator_source_mismatch", database_bytes, artifact_bytes)
    expected_policy_digest = benchmark_runtime_policy_digest(
        sandbox_policy=policy,
        benchmark_policy=request.benchmark_policy,
        trial_count=request.trial_count,
        ordered=request.ordered,
        collation=request.collation,
    )
    if not hmac.compare_digest(request.task.benchmark_policy_digest, expected_policy_digest):
        return _failure(request, "benchmark_policy_mismatch", database_bytes, artifact_bytes)
    if request.fixture not in request.reveal.hidden_fixtures:
        return _failure(request, "fixture_not_committed", database_bytes, artifact_bytes)
    if request.fixture.database_file_digest is None:
        return _failure(request, "fixture_file_digest_missing", database_bytes, artifact_bytes)
    actual_file_digest = _sha256_file(database_path)
    if not hmac.compare_digest(actual_file_digest, request.fixture.database_file_digest):
        return _failure(request, "fixture_file_mismatch", database_bytes, artifact_bytes)
    try:
        if not verify_logical_fixture_content_digest(database_path, request.fixture.content_digest):
            return _failure(request, "fixture_content_mismatch", database_bytes, artifact_bytes)
    except (OSError, sqlite3.DatabaseError, UnicodeError, ValueError):
        return _failure(request, "fixture_digest_rejected", database_bytes, artifact_bytes)
    expected_parameters = fixture_parameter_set_digest(
        request.task.benchmark_family_id, request.parameters
    )
    if not hmac.compare_digest(expected_parameters, request.fixture.parameter_set_digest):
        return _failure(request, "fixture_parameters_mismatch", database_bytes, artifact_bytes)
    if artifact_bytes > request.task.artifact_budget.max_bundle_bytes:
        return _failure(request, "artifact_size", database_bytes, artifact_bytes)
    try:
        _validate_task_artifact_policy(request)
    except AdmissionError as error:
        return _failure(request, error.code, database_bytes, artifact_bytes)
    if require_pinned_engine and sqlite3.sqlite_version != PINNED_SQLITE_VERSION:
        return _failure(request, "engine_mismatch", database_bytes, artifact_bytes)
    result_policy = ResultPolicy(
        ordered=request.ordered,
        collation=request.collation,
        max_rows=policy.max_rows,
        max_cells=policy.max_cells,
        max_output_bytes=policy.max_result_bytes,
    )
    worker_dir: Path | None = None
    baseline_path: Path | None = None
    candidate_path: Path | None = None
    baseline: sqlite3.Connection | None = None
    candidate: sqlite3.Connection | None = None
    try:
        query = validate_reference_query(request.task.reference_sql)
        baseline = _open_connection(database_path, read_only=True, policy=policy)
        allowed_schema = _read_schema(baseline)
        if baseline.execute(
            "SELECT 1 FROM sqlite_schema WHERE type='index' AND sql IS NOT NULL LIMIT 1"
        ).fetchone():
            raise AdmissionError("preexisting_index")
        if _schema_fingerprint(baseline) != _expected_schema_fingerprint(request.task.schema_sql):
            raise AdmissionError("fixture_schema_mismatch")
        _validate_bundle_schema(request.bundle, allowed_schema)
        baseline.close()
        baseline = None

        temporary_root = "/work" if Path("/work").is_dir() else None
        worker_dir = Path(tempfile.mkdtemp(prefix="planrace-worker-", dir=temporary_root))
        baseline_path = worker_dir / "baseline.sqlite3"
        candidate_path = worker_dir / "fixture.sqlite3"
        shutil.copyfile(database_path, baseline_path)
        shutil.copyfile(database_path, candidate_path)
        candidate = _open_connection(candidate_path, read_only=False, policy=policy)
        _enable_setup_phase(candidate, allowed_schema, policy)
        setup_start = time.perf_counter_ns()
        for index_spec in request.bundle.indexes:
            _install_deadline(candidate, policy.query_timeout_ms)
            candidate.execute(compile_index_sql(index_spec))
        candidate.commit()
        setup_ms = (time.perf_counter_ns() - setup_start) / 1_000_000
        try:
            candidate_database_bytes = _safe_database_size(candidate_path, policy)
        except WorkerFailure as error:
            return _failure(
                request,
                error.code,
                database_bytes,
                max(artifact_bytes, candidate_path.stat().st_size - database_bytes),
            )
        artifact_storage_bytes = max(0, candidate_database_bytes - database_bytes)
        _enable_query_phase(candidate, allowed_schema, policy)
        _install_deadline(candidate, policy.query_timeout_ms)
        plan_rows = candidate.execute(
            "EXPLAIN QUERY PLAN " + query,
            request.parameters,
        ).fetchall()
        candidate_plan = tuple(str(row[3])[:512] for row in plan_rows[:64])
        installed_names = {
            validator_index_name(index_spec) for index_spec in request.bundle.indexes
        }
        used_index_names = tuple(
            sorted(
                name for name in installed_names if any(name in detail for detail in candidate_plan)
            )
        )

        # Setup is measured once, then every paired timing trial gets fresh
        # connections.  ABBA-balanced execution removes fixed cache/order bias;
        # each arm records a first-execution (cold-track) and immediate repeat
        # (warm-track) measurement in the same disposable worker.
        candidate.close()
        candidate = None
        worker_id = f"worker-{os.getpid()}-{secrets.token_hex(8)}"
        trials: list[SandboxTrialV2] = []
        reference_result: CanonicalResult | None = None
        candidate_result: CanonicalResult | None = None
        for order in _balanced_interleave_orders(request.trial_count):
            baseline_trial = _open_connection(baseline_path, read_only=True, policy=policy)
            candidate_trial = _open_connection(candidate_path, read_only=True, policy=policy)
            candidate_cold_timeout = False
            candidate_warm_timeout = False
            try:
                _enable_query_phase(baseline_trial, allowed_schema, policy)
                _enable_query_phase(candidate_trial, allowed_schema, policy)
                if order == "baseline-first":
                    baseline_cold, baseline_cold_ms = _run_once(
                        baseline_trial,
                        query,
                        request.parameters,
                        result_policy,
                        policy.query_timeout_ms,
                    )
                    candidate_cold, candidate_cold_ms, candidate_cold_timeout = _run_candidate_once(
                        candidate_trial,
                        query,
                        request.parameters,
                        result_policy,
                        policy.query_timeout_ms,
                    )
                    baseline_warm, baseline_warm_ms = _run_once(
                        baseline_trial,
                        query,
                        request.parameters,
                        result_policy,
                        policy.query_timeout_ms,
                    )
                    if candidate_cold_timeout:
                        candidate_warm = None
                        candidate_warm_ms = candidate_cold_ms
                        candidate_warm_timeout = True
                    else:
                        candidate_warm, candidate_warm_ms, candidate_warm_timeout = (
                            _run_candidate_once(
                                candidate_trial,
                                query,
                                request.parameters,
                                result_policy,
                                policy.query_timeout_ms,
                            )
                        )
                else:
                    candidate_cold, candidate_cold_ms, candidate_cold_timeout = _run_candidate_once(
                        candidate_trial,
                        query,
                        request.parameters,
                        result_policy,
                        policy.query_timeout_ms,
                    )
                    baseline_cold, baseline_cold_ms = _run_once(
                        baseline_trial,
                        query,
                        request.parameters,
                        result_policy,
                        policy.query_timeout_ms,
                    )
                    if candidate_cold_timeout:
                        candidate_warm = None
                        candidate_warm_ms = candidate_cold_ms
                        candidate_warm_timeout = True
                    else:
                        candidate_warm, candidate_warm_ms, candidate_warm_timeout = (
                            _run_candidate_once(
                                candidate_trial,
                                query,
                                request.parameters,
                                result_policy,
                                policy.query_timeout_ms,
                            )
                        )
                    baseline_warm, baseline_warm_ms = _run_once(
                        baseline_trial,
                        query,
                        request.parameters,
                        result_policy,
                        policy.query_timeout_ms,
                    )
            finally:
                baseline_trial.close()
                candidate_trial.close()
            if baseline_cold.digest != baseline_warm.digest:
                raise AdmissionError("nondeterministic_result")
            completed_candidates = tuple(
                item for item in (candidate_cold, candidate_warm) if item is not None
            )
            mismatched = next(
                (item for item in completed_candidates if item.digest != baseline_cold.digest),
                None,
            )
            if mismatched is not None:
                return SandboxResultV2(
                    success=False,
                    failure_code="result_mismatch",
                    engine=PINNED_SQLITE_ENGINE,
                    artifact_digest=request.bundle.artifact_digest,
                    task_id=request.task.task_id,
                    task_commitment=request.task.commitment,
                    fixture_id=request.fixture.fixture_id,
                    fixture_content_digest=request.fixture.content_digest,
                    hidden_fixture_merkle_root=request.reveal.hidden_fixture_merkle_root,
                    reference_digest=baseline_cold.digest,
                    candidate_digest=mismatched.digest,
                    correct=False,
                    compliant=True,
                    row_count=mismatched.row_count,
                    setup_ms=setup_ms,
                    worker_id=worker_id,
                    trials=tuple(trials),
                    database_bytes=database_bytes,
                    artifact_storage_bytes=artifact_storage_bytes,
                    candidate_plan=candidate_plan,
                    used_index_names=used_index_names,
                )
            if reference_result is not None and reference_result.digest != baseline_cold.digest:
                raise AdmissionError("nondeterministic_result")
            reference_result = baseline_cold
            if completed_candidates:
                candidate_result = completed_candidates[0]
            trials.append(
                SandboxTrialV2(
                    worker_id=worker_id,
                    order=order,
                    baseline_cold_ms=baseline_cold_ms,
                    candidate_cold_ms=candidate_cold_ms,
                    baseline_warm_ms=baseline_warm_ms,
                    candidate_warm_ms=candidate_warm_ms,
                    candidate_timed_out=(candidate_cold_timeout or candidate_warm_timeout),
                )
            )
        if reference_result is None:
            raise AdmissionError("missing_result")
        if candidate_result is None:
            return SandboxResultV2(
                success=False,
                failure_code="candidate_timeout",
                engine=PINNED_SQLITE_ENGINE,
                artifact_digest=request.bundle.artifact_digest,
                task_id=request.task.task_id,
                task_commitment=request.task.commitment,
                fixture_id=request.fixture.fixture_id,
                fixture_content_digest=request.fixture.content_digest,
                hidden_fixture_merkle_root=request.reveal.hidden_fixture_merkle_root,
                reference_digest=reference_result.digest,
                candidate_digest=None,
                correct=False,
                compliant=True,
                row_count=0,
                setup_ms=setup_ms,
                worker_id=worker_id,
                trials=tuple(trials),
                database_bytes=database_bytes,
                artifact_storage_bytes=artifact_storage_bytes,
                candidate_plan=candidate_plan,
                used_index_names=used_index_names,
            )
        correct = reference_result.digest == candidate_result.digest
        if not correct:
            return SandboxResultV2(
                success=False,
                failure_code="result_mismatch",
                engine=PINNED_SQLITE_ENGINE,
                artifact_digest=request.bundle.artifact_digest,
                task_id=request.task.task_id,
                task_commitment=request.task.commitment,
                fixture_id=request.fixture.fixture_id,
                fixture_content_digest=request.fixture.content_digest,
                hidden_fixture_merkle_root=request.reveal.hidden_fixture_merkle_root,
                reference_digest=reference_result.digest,
                candidate_digest=candidate_result.digest,
                correct=False,
                compliant=True,
                row_count=candidate_result.row_count,
                setup_ms=setup_ms,
                worker_id=worker_id,
                trials=tuple(trials),
                database_bytes=database_bytes,
                artifact_storage_bytes=artifact_storage_bytes,
                candidate_plan=candidate_plan,
                used_index_names=used_index_names,
            )
        return SandboxResultV2(
            success=True,
            failure_code=None,
            engine=PINNED_SQLITE_ENGINE,
            artifact_digest=request.bundle.artifact_digest,
            task_id=request.task.task_id,
            task_commitment=request.task.commitment,
            fixture_id=request.fixture.fixture_id,
            fixture_content_digest=request.fixture.content_digest,
            hidden_fixture_merkle_root=request.reveal.hidden_fixture_merkle_root,
            reference_digest=reference_result.digest,
            candidate_digest=candidate_result.digest,
            correct=True,
            compliant=True,
            row_count=candidate_result.row_count,
            setup_ms=setup_ms,
            worker_id=worker_id,
            trials=tuple(trials),
            database_bytes=database_bytes,
            artifact_storage_bytes=artifact_storage_bytes,
            candidate_plan=candidate_plan,
            used_index_names=used_index_names,
        )
    except AdmissionError as error:
        return _failure(request, error.code, database_bytes, artifact_bytes)
    except ResultLimitExceeded as error:
        return _failure(request, str(error), database_bytes, artifact_bytes)
    except sqlite3.DatabaseError as error:
        message = str(error).lower()
        if "interrupted" in message:
            code = "query_timeout"
        elif "utf-8" in message or "decode" in message:
            code = "malformed_text"
        else:
            code = "sqlite_rejected"
        return _failure(request, code, database_bytes, artifact_bytes)
    except (OSError, UnicodeError, ValueError):
        return _failure(request, "worker_rejected", database_bytes, artifact_bytes)
    finally:
        if baseline is not None:
            baseline.close()
        if candidate is not None:
            candidate.close()
        if worker_dir is not None:
            shutil.rmtree(worker_dir, ignore_errors=True)


def _safe_database_size(path: Path, policy: SandboxPolicy) -> int:
    try:
        resolved = path.resolve(strict=True)
        size = resolved.stat().st_size
    except OSError as error:
        raise WorkerFailure("database_missing") from error
    if not resolved.is_file() or size > policy.max_database_bytes:
        raise WorkerFailure("database_limit")
    return size


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return "sha256:" + hasher.hexdigest()


def _validate_task_artifact_policy(request: SandboxRequestV2) -> None:
    budget = request.task.artifact_budget
    grammar = request.task.artifact_grammar
    indexes = request.bundle.indexes
    if len(indexes) > budget.max_indexes:
        raise AdmissionError("index_count_policy")
    for index in indexes:
        if len(index.key_columns) + len(index.include_columns) > budget.max_columns_per_index:
            raise AdmissionError("index_column_policy")
        if index.unique and not grammar.allows_unique:
            raise AdmissionError("unique_index_policy")
        if index.predicate is None:
            continue
        if not grammar.allows_partial:
            raise AdmissionError("partial_index_policy")
        if len(index.predicate.atoms) > budget.max_predicates_per_index:
            raise AdmissionError("predicate_count_policy")
        allowed = set(grammar.allowed_predicate_operators)
        if any(atom.operator not in allowed for atom in index.predicate.atoms):
            raise AdmissionError("predicate_operator_policy")


def _schema_fingerprint(connection: sqlite3.Connection) -> str:
    rows = connection.execute(
        """
        SELECT type, name, tbl_name, sql
        FROM sqlite_schema
        WHERE name NOT LIKE 'sqlite_%' AND type IN ('table', 'view', 'trigger')
        ORDER BY type, name
        """
    ).fetchall()
    normalized: list[list[str | None]] = []
    for object_type, name, table_name, sql in rows:
        normalized_sql: str | None = None
        if sql is not None:
            try:
                parsed = parse(str(sql), read="sqlite")
            except ParseError as error:
                raise AdmissionError("schema_parse_error") from error
            if len(parsed) != 1 or parsed[0] is None:
                raise AdmissionError("schema_parse_error")
            normalized_sql = parsed[0].sql(dialect="sqlite", pretty=False)
        normalized.append([str(object_type), str(name), str(table_name), normalized_sql])
    return domain_separated_digest(
        "planrace/2:sqlite-schema",
        {"objects": normalized},
    )


def _expected_schema_fingerprint(schema_sql: str) -> str:
    try:
        statements = parse(schema_sql, read="sqlite")
    except ParseError as error:
        raise AdmissionError("schema_parse_error") from error
    if not statements:
        raise AdmissionError("empty_schema")
    create_statements: list[exp.Create] = []
    for statement in statements:
        if not isinstance(statement, exp.Create) or str(statement.args.get("kind", "")).upper() != (
            "TABLE"
        ):
            raise AdmissionError("schema_create_table_only")
        if any(
            isinstance(node, (exp.VirtualProperty, exp.ModuleProperty)) for node in statement.walk()
        ):
            raise AdmissionError("virtual_table_forbidden")
        create_statements.append(statement)
    connection = sqlite3.connect(":memory:")
    try:
        connection.setconfig(sqlite3.SQLITE_DBCONFIG_TRUSTED_SCHEMA, False)
        connection.setconfig(sqlite3.SQLITE_DBCONFIG_DQS_DDL, False)
        connection.setconfig(sqlite3.SQLITE_DBCONFIG_DQS_DML, False)
        for statement in create_statements:
            connection.execute(statement.sql(dialect="sqlite"))
        return _schema_fingerprint(connection)
    except sqlite3.DatabaseError as error:
        raise AdmissionError("schema_rejected") from error
    finally:
        connection.close()


def _failure(
    request: SandboxRequestV2,
    code: str,
    database_bytes: int,
    artifact_bytes: int,
) -> SandboxResultV2:
    return SandboxResultV2(
        success=False,
        failure_code=code,
        engine=PINNED_SQLITE_ENGINE,
        artifact_digest=request.bundle.artifact_digest,
        task_id=request.task.task_id,
        task_commitment=request.task.commitment,
        fixture_id=request.fixture.fixture_id,
        fixture_content_digest=request.fixture.content_digest,
        hidden_fixture_merkle_root=request.reveal.hidden_fixture_merkle_root,
        database_bytes=database_bytes,
        artifact_storage_bytes=artifact_bytes,
    )


def _open_connection(path: Path, *, read_only: bool, policy: SandboxPolicy) -> sqlite3.Connection:
    if read_only:
        uri = f"file:{path.resolve()}?mode=ro&immutable=1"
        connection = sqlite3.connect(uri, uri=True, timeout=0.1, check_same_thread=True)
    else:
        connection = sqlite3.connect(path, timeout=0.1, check_same_thread=True)
    connection.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True)
    connection.setconfig(sqlite3.SQLITE_DBCONFIG_TRUSTED_SCHEMA, False)
    connection.setconfig(sqlite3.SQLITE_DBCONFIG_DQS_DDL, False)
    connection.setconfig(sqlite3.SQLITE_DBCONFIG_DQS_DML, False)
    connection.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION, False)
    connection.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_TRIGGER, False)
    connection.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_VIEW, False)
    connection.setconfig(sqlite3.SQLITE_DBCONFIG_WRITABLE_SCHEMA, False)
    connection.enable_load_extension(False)
    connection.execute("PRAGMA trusted_schema=OFF")
    connection.execute("PRAGMA recursive_triggers=OFF")
    connection.execute("PRAGMA mmap_size=0")
    connection.execute("PRAGMA cell_size_check=ON")
    connection.execute("PRAGMA temp_store=MEMORY")
    _apply_sqlite_limits(connection, policy)
    return connection


def _apply_sqlite_limits(connection: sqlite3.Connection, policy: SandboxPolicy) -> None:
    limits = {
        sqlite3.SQLITE_LIMIT_LENGTH: min(policy.max_result_bytes, 1_000_000),
        sqlite3.SQLITE_LIMIT_SQL_LENGTH: 65_536,
        sqlite3.SQLITE_LIMIT_COLUMN: 100,
        sqlite3.SQLITE_LIMIT_EXPR_DEPTH: 20,
        sqlite3.SQLITE_LIMIT_COMPOUND_SELECT: 3,
        sqlite3.SQLITE_LIMIT_VDBE_OP: 25_000,
        sqlite3.SQLITE_LIMIT_FUNCTION_ARG: 8,
        sqlite3.SQLITE_LIMIT_ATTACHED: 0,
        sqlite3.SQLITE_LIMIT_LIKE_PATTERN_LENGTH: 128,
        sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER: 32,
        sqlite3.SQLITE_LIMIT_TRIGGER_DEPTH: 0,
        sqlite3.SQLITE_LIMIT_WORKER_THREADS: 0,
    }
    for category, value in limits.items():
        connection.setlimit(category, value)


def _read_schema(connection: sqlite3.Connection) -> dict[str, frozenset[str]]:
    schema: dict[str, frozenset[str]] = {}
    tables = connection.execute(
        "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    for (table,) in tables:
        # Table names originate from the committed fixture schema, not a miner.
        quoted = '"' + str(table).replace('"', '""') + '"'
        columns = connection.execute(f"PRAGMA table_info({quoted})")
        schema[str(table)] = frozenset(str(row[1]) for row in columns)
    if not schema:
        raise AdmissionError("empty_schema")
    return schema


def _validate_bundle_schema(bundle: OptimizationBundle, schema: dict[str, frozenset[str]]) -> None:
    for spec in bundle.indexes:
        columns = schema.get(spec.table)
        if columns is None:
            raise AdmissionError("unknown_table")
        requested = {item.column for item in spec.key_columns} | set(spec.include_columns)
        if spec.predicate is not None:
            requested.update(atom.column for atom in spec.predicate.atoms)
        if not requested <= columns:
            raise AdmissionError("unknown_column")


def _enable_setup_phase(
    connection: sqlite3.Connection,
    schema: dict[str, frozenset[str]],
    policy: SandboxPolicy,
) -> None:
    connection.execute("PRAGMA query_only=OFF")
    connection.set_authorizer(_authorizer(schema, allow_create_index=True))
    _install_deadline(connection, policy.query_timeout_ms)


def _enable_query_phase(
    connection: sqlite3.Connection,
    schema: dict[str, frozenset[str]],
    policy: SandboxPolicy,
) -> None:
    connection.set_authorizer(None)
    connection.execute("PRAGMA query_only=ON")
    connection.set_authorizer(_authorizer(schema, allow_create_index=False))
    _install_deadline(connection, policy.query_timeout_ms)


def _authorizer(
    schema: dict[str, frozenset[str]], *, allow_create_index: bool
) -> Callable[[int, str | None, str | None, str | None, str | None], int]:
    allowed_tables = frozenset(schema)
    allowed_actions = {sqlite3.SQLITE_READ, sqlite3.SQLITE_SELECT, sqlite3.SQLITE_FUNCTION}
    if allow_create_index:
        allowed_actions.update(
            {sqlite3.SQLITE_CREATE_INDEX, sqlite3.SQLITE_INSERT, sqlite3.SQLITE_REINDEX}
        )

    def authorize(
        action: int,
        arg1: str | None,
        arg2: str | None,
        _database: str | None,
        _source: str | None,
    ) -> int:
        if action not in allowed_actions:
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_READ and arg1 not in allowed_tables:
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_CREATE_INDEX and arg2 not in allowed_tables:
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_INSERT and arg1 != "sqlite_master":
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_REINDEX and not (arg1 or "").startswith("planrace_"):
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() not in _ALLOWED_FUNCTIONS:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    return authorize


def _install_deadline(connection: sqlite3.Connection, timeout_ms: int) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    connection.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1_000)


def _balanced_interleave_orders(
    trial_count: int,
) -> tuple[Literal["baseline-first", "candidate-first"], ...]:
    if trial_count < 6 or trial_count % 2:
        raise AdmissionError("unbalanced_trial_count")
    pattern: tuple[Literal["baseline-first", "candidate-first"], ...] = (
        "baseline-first",
        "candidate-first",
        "candidate-first",
        "baseline-first",
    )
    orders = [pattern[index % len(pattern)] for index in range(trial_count)]
    # ABBA blocks are balanced; an incomplete final block is repaired with a
    # deterministic AB pair.  This remains reproducible in an evidence replay.
    baseline_count = orders.count("baseline-first")
    candidate_count = orders.count("candidate-first")
    if baseline_count != candidate_count:
        orders[-2:] = ["baseline-first", "candidate-first"]
    return tuple(orders)


def _run_once(
    connection: sqlite3.Connection,
    query: str,
    parameters: tuple[ParameterValue, ...],
    result_policy: ResultPolicy,
    timeout_ms: int,
) -> tuple[CanonicalResult, float]:
    _install_deadline(connection, timeout_ms)
    start = time.perf_counter_ns()
    cursor = connection.execute(query, parameters)
    result = canonicalize_result(cursor, policy=result_policy)
    elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
    return result, max(elapsed_ms, sys.float_info.min)


def _run_candidate_once(
    connection: sqlite3.Connection,
    query: str,
    parameters: tuple[ParameterValue, ...],
    result_policy: ResultPolicy,
    timeout_ms: int,
) -> tuple[CanonicalResult | None, float, bool]:
    """Record a candidate timeout without aborting the remaining miner cohort."""

    start = time.perf_counter_ns()
    try:
        result, elapsed_ms = _run_once(
            connection,
            query,
            parameters,
            result_policy,
            timeout_ms,
        )
    except sqlite3.DatabaseError as error:
        if "interrupted" not in str(error).lower():
            raise
        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
        return None, max(elapsed_ms, sys.float_info.min), True
    return result, elapsed_ms, False


class ProcessOutcome(StrictSandboxModel):
    status: Literal["ok", "timeout", "crash", "input_limit", "output_limit", "spawn_error"]
    returncode: int | None
    stdout: bytes = b""


def run_bounded_process(
    argv: Sequence[str],
    *,
    stdin: bytes = b"",
    policy: SandboxPolicy = DEFAULT_SANDBOX_POLICY,
    apply_rlimits: bool = True,
    wall_timeout_seconds: float | None = None,
    max_input_bytes: int | None = None,
    max_output_bytes: int | None = None,
) -> ProcessOutcome:
    """Run a fixed worker command without letting a crash stop the validator."""

    input_limit = policy.max_worker_input_bytes if max_input_bytes is None else max_input_bytes
    output_limit = policy.max_worker_output_bytes if max_output_bytes is None else max_output_bytes
    wall_timeout = (
        policy.wall_timeout_seconds if wall_timeout_seconds is None else wall_timeout_seconds
    )
    if input_limit <= 0 or output_limit <= 0 or wall_timeout <= 0:
        raise ValueError("process limits must be positive")
    if len(stdin) > input_limit:
        return ProcessOutcome(status="input_limit", returncode=None)

    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        try:
            process = subprocess.Popen(  # noqa: S603 - argv is validator-owned
                list(argv),
                stdin=subprocess.PIPE,
                stdout=stdout_file,
                stderr=stderr_file,
                start_new_session=True,
                preexec_fn=(
                    _resource_limiter(policy)
                    if apply_rlimits and os.name == "posix" and sys.platform.startswith("linux")
                    else None
                ),
            )
        except OSError:
            return ProcessOutcome(status="spawn_error", returncode=None)
        try:
            process.communicate(stdin, timeout=wall_timeout)
        except subprocess.TimeoutExpired:
            _kill_process_group(process)
            process.wait(timeout=2)
            return ProcessOutcome(status="timeout", returncode=process.returncode)
        stdout_file.seek(0, os.SEEK_END)
        size = stdout_file.tell()
        if size > output_limit:
            return ProcessOutcome(status="output_limit", returncode=process.returncode)
        stdout_file.seek(0)
        output = stdout_file.read(output_limit + 1)
        if process.returncode != 0:
            return ProcessOutcome(status="crash", returncode=process.returncode, stdout=output)
        return ProcessOutcome(status="ok", returncode=0, stdout=output)


def _resource_limiter(policy: SandboxPolicy) -> Callable[[], None]:
    def limit() -> None:
        import resource

        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_CPU, (policy.cpu_seconds, policy.cpu_seconds))
        resource.setrlimit(resource.RLIMIT_AS, (policy.memory_bytes, policy.memory_bytes))
        resource.setrlimit(
            resource.RLIMIT_FSIZE,
            (policy.max_worker_output_bytes, policy.max_worker_output_bytes),
        )
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        if hasattr(resource, "RLIMIT_NPROC"):
            resource.setrlimit(resource.RLIMIT_NPROC, (policy.pids_limit, policy.pids_limit))

    return limit


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)


def build_docker_worker_command(
    database_path: Path,
    *,
    image: str,
    policy: SandboxPolicy = DEFAULT_SANDBOX_POLICY,
    require_digest: bool = True,
) -> list[str]:
    """Build the production worker command with no ambient authority."""

    resolved = database_path.resolve(strict=True)
    _safe_database_size(resolved, policy)
    if require_digest and _worker_image_digest(image) is None:
        raise ValueError("production worker image must be pinned by sha256 digest")
    memory_mib = policy.memory_bytes // (1024 * 1024)
    tmpfs_mib = min(128, max(32, memory_mib // 2))
    return [
        "docker",
        "run",
        "--rm",
        "--interactive",
        "--pull",
        "never",
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        f"/work:rw,noexec,nosuid,nodev,size={tmpfs_mib}m,mode=1777",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--pids-limit",
        str(policy.pids_limit),
        "--memory",
        str(policy.memory_bytes),
        "--memory-swap",
        str(policy.memory_bytes),
        "--cpus",
        "1.0",
        "--user",
        "65532:65532",
        "--ulimit",
        "nofile=64:64",
        "--ulimit",
        f"cpu={policy.cpu_seconds}:{policy.cpu_seconds}",
        "--volume",
        f"{resolved}:/input/fixture.sqlite3:ro",
        "--workdir",
        "/work",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        image,
        "--database",
        "/input/fixture.sqlite3",
    ]


def run_docker_worker(
    database_path: Path,
    request: SandboxRequestV2,
    *,
    image: str,
    policy: SandboxPolicy = DEFAULT_SANDBOX_POLICY,
    require_digest: bool = True,
) -> SandboxResultV2:
    artifact_bytes = len(request.bundle.model_dump_json().encode())
    try:
        database_bytes = _safe_database_size(database_path, policy)
        command = build_docker_worker_command(
            database_path, image=image, policy=policy, require_digest=require_digest
        )
    except WorkerFailure as error:
        return _failure(request, error.code, 0, artifact_bytes)
    image_digest = _worker_image_digest(image)
    if require_digest and image_digest != request.bundle.engine_image_digest:
        return _failure(
            request,
            "engine_image_mismatch",
            database_bytes,
            artifact_bytes,
        )
    outcome = run_bounded_process(
        command,
        stdin=request.model_dump_json().encode("utf-8"),
        policy=policy,
        apply_rlimits=False,
    )
    if outcome.status != "ok":
        return _failure(
            request,
            f"worker_{outcome.status}",
            database_bytes,
            artifact_bytes,
        )
    try:
        return SandboxResultV2.model_validate_json(outcome.stdout)
    except ValueError:
        return _failure(
            request,
            "worker_malformed_output",
            database_bytes,
            artifact_bytes,
        )


class SandboxBatchItemV2(StrictSandboxModel):
    database_name: Annotated[
        str, StringConstraints(pattern=r"^fixture-[0-9]{3}\.sqlite3$")
    ]
    request: SandboxRequestV2


class SandboxBatchRequestV2(StrictSandboxModel):
    protocol_version: Literal["planrace/2"] = "planrace/2"
    items: Annotated[tuple[SandboxBatchItemV2, ...], Field(min_length=1, max_length=64)]


class SandboxBatchResultV2(StrictSandboxModel):
    protocol_version: Literal["planrace/2"] = "planrace/2"
    results: tuple[SandboxResultV2, ...]


def run_docker_batch_worker(
    database_directory: Path,
    items: Sequence[tuple[str, SandboxRequestV2]],
    *,
    image: str,
    policy: SandboxPolicy = DEFAULT_SANDBOX_POLICY,
) -> tuple[SandboxResultV2, ...]:
    """Run up to 64 independent evaluations in one disposable container.

    This is a throughput optimization for closed localnet cohorts. It retains
    the same network, filesystem, capability, PID, CPU and memory isolation as
    the single-request boundary and adds a bounded whole-batch wall clock.
    """

    image_digest = _worker_image_digest(image)
    if image_digest is None:
        raise ValueError("batch worker image must be pinned by sha256 digest")
    root = database_directory.resolve(strict=True)
    if not root.is_dir():
        raise WorkerFailure("database_directory_missing")
    batch_items: list[SandboxBatchItemV2] = []
    for name, request in items:
        candidate = root / name
        if candidate.is_symlink() or candidate.resolve(strict=True).parent != root:
            raise WorkerFailure("database_path_rejected")
        _safe_database_size(candidate, policy)
        if request.bundle.engine_image_digest != image_digest:
            raise WorkerFailure("engine_image_mismatch")
        batch_items.append(SandboxBatchItemV2(database_name=name, request=request))
    batch = SandboxBatchRequestV2(items=tuple(batch_items))
    command = [
        *_docker_security_prefix(
            policy, cpu_seconds=min(300, policy.cpu_seconds * len(items))
        ),
        "--volume",
        f"{root}:/input:ro",
        "--workdir",
        "/work",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        image,
        "--batch-directory",
        "/input",
    ]
    outcome = run_bounded_process(
        command,
        stdin=batch.model_dump_json().encode("utf-8"),
        policy=policy,
        apply_rlimits=False,
        wall_timeout_seconds=min(900.0, max(60.0, policy.wall_timeout_seconds * len(items))),
        max_input_bytes=4 * 1024 * 1024,
        max_output_bytes=4 * 1024 * 1024,
    )
    if outcome.status != "ok":
        raise WorkerFailure(f"worker_{outcome.status}")
    try:
        parsed = SandboxBatchResultV2.model_validate_json(outcome.stdout)
    except ValueError as error:
        raise WorkerFailure("worker_malformed_output") from error
    if len(parsed.results) != len(items):
        raise WorkerFailure("worker_result_count")
    return parsed.results


def _worker_image_digest(image: str) -> str | None:
    """Return the immutable content identity accepted by the worker boundary.

    Published images use a registry repository digest. Localnet builds may use
    Docker's equally content-addressed local image ID, which avoids pretending
    an unpublished image has a registry provenance it does not have.
    """

    if _REPOSITORY_DIGEST_IMAGE.fullmatch(image):
        return image.rsplit("@", maxsplit=1)[1]
    if _LOCAL_CONTENT_DIGEST_IMAGE.fullmatch(image):
        return image
    return None


def _docker_security_prefix(
    policy: SandboxPolicy, *, cpu_seconds: int | None = None
) -> list[str]:
    memory_mib = policy.memory_bytes // (1024 * 1024)
    tmpfs_mib = min(128, max(32, memory_mib // 2))
    return [
        "docker",
        "run",
        "--rm",
        "--interactive",
        "--pull",
        "never",
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        f"/work:rw,noexec,nosuid,nodev,size={tmpfs_mib}m,mode=1777",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--pids-limit",
        str(policy.pids_limit),
        "--memory",
        str(policy.memory_bytes),
        "--memory-swap",
        str(policy.memory_bytes),
        "--cpus",
        "1.0",
        "--user",
        "65532:65532",
        "--ulimit",
        "nofile=64:64",
        "--ulimit",
        f"cpu={cpu_seconds or policy.cpu_seconds}:{cpu_seconds or policy.cpu_seconds}",
    ]


def worker_main(argv: Sequence[str] | None = None) -> int:
    """Fixed container entrypoint: one request on stdin, one bounded result."""

    import argparse

    parser = argparse.ArgumentParser(add_help=False)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--database")
    group.add_argument("--batch-directory")
    arguments = parser.parse_args(argv)
    try:
        if arguments.database is not None:
            raw = sys.stdin.buffer.read(DEFAULT_SANDBOX_POLICY.max_worker_input_bytes + 1)
            if len(raw) > DEFAULT_SANDBOX_POLICY.max_worker_input_bytes:
                return 70
            request = SandboxRequestV2.model_validate_json(raw)
            output: StrictSandboxModel = execute_request(Path(arguments.database), request)
        else:
            raw = sys.stdin.buffer.read(4 * 1024 * 1024 + 1)
            if len(raw) > 4 * 1024 * 1024:
                return 70
            batch = SandboxBatchRequestV2.model_validate_json(raw)
            root = Path(arguments.batch_directory).resolve(strict=True)
            results: list[SandboxResultV2] = []
            for item in batch.items:
                database = root / item.database_name
                if database.is_symlink() or database.resolve(strict=True).parent != root:
                    return 70
                results.append(execute_request(database, item.request))
            output = SandboxBatchResultV2(results=tuple(results))
    except Exception:  # fail closed at the process boundary; never emit internals
        return 70
    sys.stdout.write(output.model_dump_json())
    sys.stdout.write("\n")
    return 0
