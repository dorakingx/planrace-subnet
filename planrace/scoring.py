"""Exact-first validator scoring for PlanRace artifacts."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import statistics
import time
from collections.abc import Iterable

from planrace.models import OptimizationArtifact, ScoreBreakdown
from planrace.sandbox import (
    AdmissionError,
    install_query_deadline,
    validate_candidate_sql,
    validate_setup_sql,
)
from planrace.taskgen import HiddenWorkload, build_database


def canonical_result_hash(rows: Iterable[tuple[object, ...]]) -> str:
    payload = json.dumps(list(rows), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _failure(
    workload: HiddenWorkload,
    artifact: OptimizationArtifact,
    reference_hash: str,
    code: str,
) -> ScoreBreakdown:
    return ScoreBreakdown(
        task_id=workload.task.task_id,
        miner_id=artifact.miner_id,
        correct=False,
        score=0.0,
        result_hash=None,
        reference_hash=reference_hash,
        plan_cost=0,
        median_warm_ms=0.0,
        setup_ms=0.0,
        failure_code=code,
    )


def evaluate_artifact(
    workload: HiddenWorkload,
    artifact: OptimizationArtifact,
    *,
    timeout_ms: float = 2_000.0,
) -> ScoreBreakdown:
    reference_db = build_database(workload)
    try:
        reference_rows = list(reference_db.execute(workload.task.reference_sql))
        reference_hash = canonical_result_hash(reference_rows)
    finally:
        reference_db.close()

    if artifact.task_id != workload.task.task_id:
        return _failure(workload, artifact, reference_hash, "task_mismatch")
    if len(artifact.setup_sql) > workload.task.max_setup_statements:
        return _failure(workload, artifact, reference_hash, "setup_limit")

    database = build_database(workload)
    try:
        candidate = validate_candidate_sql(artifact.candidate_sql)
        setup = tuple(validate_setup_sql(statement) for statement in artifact.setup_sql)
        install_query_deadline(database, timeout_ms=timeout_ms)
        setup_start = time.perf_counter_ns()
        for statement in setup:
            database.execute(statement)
        setup_ms = (time.perf_counter_ns() - setup_start) / 1_000_000

        rows = list(database.execute(candidate))
        result_hash = canonical_result_hash(rows)
        if result_hash != reference_hash:
            return _failure(workload, artifact, reference_hash, "result_mismatch")

        plan_cost = len(list(database.execute(f"EXPLAIN {candidate}")))
        timings = []
        for _ in range(workload.task.repetitions):
            start = time.perf_counter_ns()
            list(database.execute(candidate))
            timings.append((time.perf_counter_ns() - start) / 1_000_000)
        median_ms = statistics.median(timings)
        amortized_ms = median_ms + setup_ms / 100.0
        score = 100.0 / (1.0 + amortized_ms + plan_cost / 1_000.0)
        return ScoreBreakdown(
            task_id=workload.task.task_id,
            miner_id=artifact.miner_id,
            correct=True,
            score=score,
            result_hash=result_hash,
            reference_hash=reference_hash,
            plan_cost=plan_cost,
            median_warm_ms=median_ms,
            setup_ms=setup_ms,
            failure_code=None,
        )
    except AdmissionError:
        return _failure(workload, artifact, reference_hash, "admission_rejected")
    except sqlite3.OperationalError as error:
        code = "timeout" if "interrupted" in str(error).lower() else "sql_error"
        return _failure(workload, artifact, reference_hash, code)
    finally:
        database.close()
