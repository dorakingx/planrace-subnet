from __future__ import annotations

from pathlib import Path

import bittensor as bt
import pytest
from pydantic import ValidationError

import planrace.evaluation_v2 as evaluation_v2
from planrace.evaluation_v2 import (
    EvaluationConfigurationError,
    create_benchmark_task_v2,
    evaluate_bundle_on_committed_holdouts,
    evaluate_task_cohort,
)
from planrace.models_v2 import (
    BundleMetadata,
    IndexColumn,
    IndexSpec,
    OptimizationBundle,
    validator_index_name,
)
from planrace.oracle_v2 import PINNED_SQLITE_ENGINE
from planrace.sandbox_v2 import (
    SandboxPolicy,
    SandboxRequestV2,
    SandboxResultV2,
    SandboxTrialV2,
    execute_request,
)


class FixedEntropy:
    def __init__(self) -> None:
        self.values = [b"t" * 16, b"s" * 32, b"z" * 32]

    def token_bytes(self, size: int) -> bytes:
        value = self.values.pop(0)
        assert len(value) == size
        return value


def test_portable_audit_allows_only_sqlite_file_digest_variance(monkeypatch) -> None:
    validator = bt.sp_core.Keypair.create_from_uri("//Alice")
    task = create_benchmark_task_v2(
        validator_hotkey=validator.ss58_address,
        engine_image_digest="sha256:" + "1" * 64,
        family_id="intentional-zero-result",
        deadline_unix_ms=2_000_000,
        entropy=FixedEntropy(),
    )
    generate = evaluation_v2.generate_hidden_fixtures

    def with_changed_digest(seed: bytes, family_id: str):
        return tuple(
            fixture.__class__(
                descriptor=fixture.descriptor.model_copy(
                    update={"database_file_digest": "sha256:" + "f" * 64}
                ),
                profile=fixture.profile,
                query_family=fixture.query_family,
                parameters=fixture.parameters,
                customers=fixture.customers,
                orders=fixture.orders,
            )
            for fixture in generate(seed, family_id=family_id)
        )

    monkeypatch.setattr(evaluation_v2, "generate_hidden_fixtures", with_changed_digest)
    with pytest.raises(EvaluationConfigurationError, match="regenerated fixtures"):
        evaluation_v2._validate_and_regenerate_task(task)
    evaluation_v2._validate_and_regenerate_task(task, portable_database_digest=True)

    def with_changed_content(seed: bytes, family_id: str):
        return tuple(
            fixture.__class__(
                descriptor=fixture.descriptor.model_copy(
                    update={"content_digest": "sha256:" + "e" * 64}
                ),
                profile=fixture.profile,
                query_family=fixture.query_family,
                parameters=fixture.parameters,
                customers=fixture.customers,
                orders=fixture.orders,
            )
            for fixture in generate(seed, family_id=family_id)
        )

    monkeypatch.setattr(evaluation_v2, "generate_hidden_fixtures", with_changed_content)
    with pytest.raises(EvaluationConfigurationError, match="regenerated fixtures"):
        evaluation_v2._validate_and_regenerate_task(task, portable_database_digest=True)


def test_full_committed_holdout_path_is_exact_first_and_worker_derived() -> None:
    validator = bt.sp_core.Keypair.create_from_uri("//Alice")
    policy = SandboxPolicy(query_timeout_ms=5_000)
    task = create_benchmark_task_v2(
        validator_hotkey=validator.ss58_address,
        engine_image_digest="sha256:" + "1" * 64,
        family_id="intentional-zero-result",
        deadline_unix_ms=2_000_000,
        sandbox_policy=policy,
        entropy=FixedEntropy(),
    )
    bundle = OptimizationBundle.create(
        task_id=task.public.task_id,
        engine_image_digest=task.public.engine_image_digest,
        indexes=(),
        metadata=BundleMetadata(
            strategy="fixed-query-no-index",
            estimated_intent="no_index",
            rationale="A constant-result response is not part of the structured grammar.",
        ),
    )

    evaluation = evaluate_bundle_on_committed_holdouts(
        task,
        bundle,
        worker_image="unused-in-explicit-test-runner",
        sandbox_policy=policy,
        worker_runner=lambda database, request: execute_request(
            database,
            request,
            policy=policy,
            require_pinned_engine=False,
        ),
    )

    assert len(evaluation.fixture_evaluations) == task.public.hidden_holdout_count == 8
    assert evaluation.exact_passed
    assert evaluation.compliant
    assert all(item.result.correct for item in evaluation.fixture_evaluations)
    assert all(
        item.result.fixture_content_digest == task.reveal.hidden_fixtures[index].content_digest
        for index, item in enumerate(evaluation.fixture_evaluations)
    )
    assert evaluation.reward == 0.0
    assert evaluation.failure_code == "no_robust_improvement"


def test_constant_result_or_raw_query_artifact_cannot_enter_v2_bundle() -> None:
    try:
        OptimizationBundle.model_validate(
            {
                "protocol_version": "planrace/2",
                "task_id": "a" * 32,
                "engine_image_digest": "sha256:" + "1" * 64,
                "indexes": [],
                "candidate_query": "SELECT 42",
                "metadata": {
                    "strategy": "constant-answer",
                    "estimated_intent": "no_index",
                    "rationale": "attack",
                },
                "artifact_digest": "sha256:" + "2" * 64,
            }
        )
    except ValidationError as error:
        assert "candidate_query" in str(error)
    else:  # pragma: no cover - this is a protocol safety invariant
        raise AssertionError("raw candidate SQL unexpectedly entered OptimizationBundle")


def test_cohort_evaluates_duplicate_executable_strategy_once() -> None:
    validator = bt.sp_core.Keypair.create_from_uri("//Alice")
    policy = SandboxPolicy(query_timeout_ms=5_000)
    task = create_benchmark_task_v2(
        validator_hotkey=validator.ss58_address,
        engine_image_digest="sha256:" + "1" * 64,
        family_id="intentional-zero-result",
        deadline_unix_ms=2_000_000,
        sandbox_policy=policy,
        entropy=FixedEntropy(),
    )
    index = IndexSpec(
        table="orders",
        key_columns=(IndexColumn(column="status"),),
    )
    bundles = {
        miner_id: OptimizationBundle.create(
            task_id=task.public.task_id,
            engine_image_digest=task.public.engine_image_digest,
            indexes=(index,),
            metadata=BundleMetadata(
                strategy=label,
                estimated_intent="filter",
                rationale=f"metadata variant {label}",
            ),
        )
        for miner_id, label in (("miner-a", "alpha"), ("miner-b", "beta"))
    }
    calls: list[str] = []

    def deterministic_worker(_database: Path, request: SandboxRequestV2) -> SandboxResultV2:
        calls.append(request.fixture.fixture_id)
        trials = tuple(
            SandboxTrialV2(
                worker_id="worker-evaluate-once",
                order="baseline-first" if index % 2 == 0 else "candidate-first",
                baseline_cold_ms=80.0,
                candidate_cold_ms=40.0,
                baseline_warm_ms=20.0,
                candidate_warm_ms=10.0,
            )
            for index in range(request.trial_count)
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
            reference_digest="sha256:" + "a" * 64,
            candidate_digest="sha256:" + "a" * 64,
            correct=True,
            compliant=True,
            row_count=0,
            setup_ms=1.0,
            worker_id="worker-evaluate-once",
            trials=trials,
            database_bytes=1_000_000,
            artifact_storage_bytes=4_096,
            candidate_plan=(f"SEARCH orders USING INDEX {validator_index_name(index)} (status=?)",),
            used_index_names=(validator_index_name(index),),
        )

    cohort = evaluate_task_cohort(
        task,
        bundles,
        epoch=7,
        worker_image="unused-in-explicit-test-runner",
        sandbox_policy=policy,
        worker_runner=deterministic_worker,
    )

    assert len(calls) == task.public.hidden_holdout_count
    assert cohort.unique_strategy_count == 1
    assert cohort.cache_hit_count == 1
    assert len(cohort.strategy_evaluations) == 1
    assert len(cohort.observations) == 2
    assert len({item.strategy_digest for item in cohort.observations}) == 1
    assert len({item.evidence_digest for item in cohort.observations}) == 1
    assert len({item.reward for item in cohort.observations}) == 1
    assert cohort.observations[0].reward > 0.0


def test_cohort_fails_closed_before_exceeding_unique_strategy_budget() -> None:
    validator = bt.sp_core.Keypair.create_from_uri("//Alice")
    task = create_benchmark_task_v2(
        validator_hotkey=validator.ss58_address,
        engine_image_digest="sha256:" + "1" * 64,
        family_id="intentional-zero-result",
        deadline_unix_ms=2_000_000,
        entropy=FixedEntropy(),
    )
    bundles = {
        "miner-a": OptimizationBundle.create(
            task_id=task.public.task_id,
            engine_image_digest=task.public.engine_image_digest,
            indexes=(IndexSpec(table="orders", key_columns=(IndexColumn(column="status"),)),),
            metadata=BundleMetadata(
                strategy="a", estimated_intent="filter", rationale="budget test"
            ),
        ),
        "miner-b": OptimizationBundle.create(
            task_id=task.public.task_id,
            engine_image_digest=task.public.engine_image_digest,
            indexes=(IndexSpec(table="orders", key_columns=(IndexColumn(column="amount_cents"),)),),
            metadata=BundleMetadata(
                strategy="b", estimated_intent="filter", rationale="budget test"
            ),
        ),
    }
    with pytest.raises(EvaluationConfigurationError, match="evaluation budget exceeded"):
        evaluate_task_cohort(
            task,
            bundles,
            epoch=0,
            worker_image="unused",
            max_unique_strategies=1,
        )
