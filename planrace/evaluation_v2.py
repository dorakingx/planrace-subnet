"""End-to-end committed-holdout evaluation for PlanRace protocol v2."""

from __future__ import annotations

import math
import statistics
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from planrace.benchmark_v2 import (
    HOLDOUT_PROFILES,
    PUBLIC_TRAINING_SEED,
    QUERY_FAMILIES,
    SCHEMA_V2,
    QueryFamily,
    benchmark_generator_source_digest,
    describe_hidden_fixtures,
    generate_hidden_fixtures,
    generate_public_training_fixture,
    materialize_fixture,
    published_parameter_ranges,
)
from planrace.models_v2 import (
    ArtifactBudget,
    ArtifactGrammar,
    HiddenFixtureDescriptor,
    OptimizationBundle,
    PublicTrainingFixture,
    PublishedStatistics,
    domain_separated_digest,
    optimization_strategy_digest,
)
from planrace.sandbox_v2 import (
    DEFAULT_SANDBOX_POLICY,
    SandboxPolicy,
    SandboxRequestV2,
    SandboxResultV2,
    benchmark_runtime_policy_digest,
    run_docker_worker,
)
from planrace.scoring_v2 import (
    DEFAULT_BENCHMARK_POLICY,
    BenchmarkPolicy,
    BenchmarkScore,
    EpochObservation,
    benchmark_evidence_from_sandbox,
    score_benchmark,
)
from planrace.taskgen_v2 import (
    EntropySource,
    PrivateTaskV2,
    audit_task_reveal,
    create_task_v2,
)

WorkerRunner = Callable[[Path, SandboxRequestV2], SandboxResultV2]


class EvaluationConfigurationError(ValueError):
    """The published task cannot be reproduced from its committed policy."""


@dataclass(frozen=True, slots=True)
class FixtureEvaluationV2:
    fixture_id: str
    result: SandboxResultV2
    score: BenchmarkScore


@dataclass(frozen=True, slots=True)
class HoldoutEvaluationV2:
    task_id: str
    task_commitment: str
    artifact_digest: str
    strategy_digest: str
    family_id: str
    exact_passed: bool
    compliant: bool
    eligible: bool
    reward: float
    failure_code: str | None
    fixture_evaluations: tuple[FixtureEvaluationV2, ...]


@dataclass(frozen=True, slots=True)
class CohortEvaluationV2:
    """Evaluate-once result for every submitted executable strategy."""

    task_id: str
    task_commitment: str
    unique_strategy_count: int
    cache_hit_count: int
    strategy_evaluations: tuple[tuple[str, HoldoutEvaluationV2], ...]
    observations: tuple[EpochObservation, ...]


def create_benchmark_task_v2(
    *,
    validator_hotkey: str,
    engine_image_digest: str,
    family_id: str,
    deadline_unix_ms: int,
    sandbox_policy: SandboxPolicy = DEFAULT_SANDBOX_POLICY,
    benchmark_policy: BenchmarkPolicy = DEFAULT_BENCHMARK_POLICY,
    trial_count: int = 6,
    artifact_budget: ArtifactBudget | None = None,
    artifact_grammar: ArtifactGrammar | None = None,
    entropy: EntropySource | None = None,
) -> PrivateTaskV2:
    """Build the only production v2 task shape accepted by the evaluator."""

    family = next(
        (candidate for candidate in QUERY_FAMILIES if candidate.family_id == family_id),
        None,
    )
    if family is None:
        raise EvaluationConfigurationError("unknown benchmark family")
    training = generate_public_training_fixture(family.family_id)

    def hidden_factory(seed: bytes) -> tuple[HiddenFixtureDescriptor, ...]:
        return describe_hidden_fixtures(seed, family_id=family.family_id)

    return create_task_v2(
        validator_hotkey=validator_hotkey,
        engine_image_digest=engine_image_digest,
        generator_source_digest=benchmark_generator_source_digest(),
        benchmark_policy_digest=benchmark_runtime_policy_digest(
            sandbox_policy=sandbox_policy,
            benchmark_policy=benchmark_policy,
            trial_count=trial_count,
            ordered=family.ordered,
        ),
        benchmark_family_id=family.family_id,
        schema_sql=SCHEMA_V2,
        reference_sql=family.sql,
        public_training_fixture=PublicTrainingFixture(
            fixture_id=training.descriptor.fixture_id,
            generator_seed_hex=PUBLIC_TRAINING_SEED.hex(),
            content_digest=training.descriptor.content_digest,
            row_count=training.descriptor.row_count,
        ),
        parameter_ranges=published_parameter_ranges(family.family_id),
        published_statistics=PublishedStatistics(
            row_count_min=min(profile.orders for profile in HOLDOUT_PROFILES),
            row_count_max=max(profile.orders for profile in HOLDOUT_PROFILES),
            selectivity_min_bps=0,
            selectivity_max_bps=10_000,
            data_profiles=(
                "uniform",
                "skewed",
                "correlated",
                "null_heavy",
                "duplicate_heavy",
            ),
        ),
        deadline_unix_ms=deadline_unix_ms,
        hidden_fixture_factory=hidden_factory,
        artifact_budget=artifact_budget,
        artifact_grammar=artifact_grammar,
        entropy=entropy,
    )


def evaluate_bundle_on_committed_holdouts(
    task: PrivateTaskV2,
    bundle: OptimizationBundle,
    *,
    worker_image: str,
    sandbox_policy: SandboxPolicy = DEFAULT_SANDBOX_POLICY,
    benchmark_policy: BenchmarkPolicy = DEFAULT_BENCHMARK_POLICY,
    trial_count: int = 6,
    worker_runner: WorkerRunner | None = None,
) -> HoldoutEvaluationV2:
    """Regenerate, attest, isolate, measure and robustly score one bundle.

    The default runner is the disposable Docker boundary.  Tests may inject a
    direct runner explicitly, but network/localnet evidence must retain the
    default and a digest-pinned image.
    """

    family = _validate_and_regenerate_task(task)
    if bundle.task_id != task.public.task_id:
        raise EvaluationConfigurationError("bundle belongs to another task")
    if bundle.engine_image_digest != task.public.engine_image_digest:
        raise EvaluationConfigurationError("bundle engine differs from task engine")
    if trial_count < benchmark_policy.minimum_trials or trial_count % 2:
        raise EvaluationConfigurationError("trial_count must be even and satisfy the scorer")

    fixtures = generate_hidden_fixtures(
        bytes.fromhex(task.reveal.secret_seed_hex),
        family_id=family.family_id,
    )

    runner = worker_runner or (
        lambda database, request: run_docker_worker(
            database,
            request,
            image=worker_image,
            policy=sandbox_policy,
            require_digest=True,
        )
    )
    evaluations: list[FixtureEvaluationV2] = []
    with tempfile.TemporaryDirectory(prefix="planrace-v2-holdouts-") as directory:
        root = Path(directory)
        for fixture in fixtures:
            database = root / f"{fixture.descriptor.fixture_id}.sqlite3"
            materialize_fixture(fixture, database)
            request = SandboxRequestV2(
                task=task.public,
                reveal=task.reveal,
                fixture=fixture.descriptor,
                bundle=bundle,
                parameters=fixture.parameters,
                ordered=family.ordered,
                trial_count=trial_count,
                benchmark_policy=benchmark_policy,
            )
            result = runner(database, request)
            _verify_worker_echo(request, result)
            score = score_benchmark(
                benchmark_evidence_from_sandbox(result),
                policy=benchmark_policy,
            )
            evaluations.append(
                FixtureEvaluationV2(
                    fixture_id=fixture.descriptor.fixture_id,
                    result=result,
                    score=score,
                )
            )

    return _finalize_holdout_evaluation(
        task,
        bundle,
        family.family_id,
        evaluations,
    )


def evaluate_bundle_from_sandbox_results(
    task: PrivateTaskV2,
    bundle: OptimizationBundle,
    results: Sequence[SandboxResultV2],
    *,
    benchmark_policy: BenchmarkPolicy = DEFAULT_BENCHMARK_POLICY,
    trial_count: int = 6,
) -> HoldoutEvaluationV2:
    """Score already-isolated worker results with the same production gates.

    This is used by the localnet cohort worker, which amortizes container start
    cost by evaluating several committed requests inside one still-disposable
    container. Every result is rebound to its exact task, reveal, fixture and
    artifact before it can reach scoring.
    """

    family = _validate_and_regenerate_task(task)
    fixtures = generate_hidden_fixtures(
        bytes.fromhex(task.reveal.secret_seed_hex), family_id=family.family_id
    )
    if len(results) != len(fixtures):
        raise EvaluationConfigurationError("worker result count does not match holdouts")
    evaluations: list[FixtureEvaluationV2] = []
    for fixture, result in zip(fixtures, results, strict=True):
        request = SandboxRequestV2(
            task=task.public,
            reveal=task.reveal,
            fixture=fixture.descriptor,
            bundle=bundle,
            parameters=fixture.parameters,
            ordered=family.ordered,
            trial_count=trial_count,
            benchmark_policy=benchmark_policy,
        )
        _verify_worker_echo(request, result)
        evaluations.append(
            FixtureEvaluationV2(
                fixture_id=fixture.descriptor.fixture_id,
                result=result,
                score=score_benchmark(
                    benchmark_evidence_from_sandbox(result), policy=benchmark_policy
                ),
            )
        )
    return _finalize_holdout_evaluation(task, bundle, family.family_id, evaluations)


def _finalize_holdout_evaluation(
    task: PrivateTaskV2,
    bundle: OptimizationBundle,
    family_id: str,
    evaluations: Sequence[FixtureEvaluationV2],
) -> HoldoutEvaluationV2:
    exact_passed = all(item.result.correct for item in evaluations)
    compliant = all(item.result.compliant for item in evaluations)
    if not exact_passed:
        return _failed(task, bundle, family_id, evaluations, "exact_result_gate")
    if not compliant:
        return _failed(task, bundle, family_id, evaluations, "artifact_policy_gate")
    if any(not item.score.benchmark_valid for item in evaluations):
        return _failed(task, bundle, family_id, evaluations, "benchmark_invalid")

    # With the v2 grammar, an empty index set is executable-identical to the
    # validator baseline.  Timing noise must never turn that no-op into reward.
    if not bundle.indexes or not any(item.result.used_index_names for item in evaluations):
        return _failed(task, bundle, family_id, evaluations, "no_robust_improvement")

    rewards = [item.score.reward for item in evaluations]
    reward = _robust_holdout_reward(rewards)
    return HoldoutEvaluationV2(
        task_id=task.public.task_id,
        task_commitment=task.public.commitment,
        artifact_digest=bundle.artifact_digest,
        strategy_digest=optimization_strategy_digest(bundle),
        family_id=family_id,
        exact_passed=True,
        compliant=True,
        eligible=reward > 0.0,
        reward=reward,
        failure_code=None if reward > 0.0 else "no_robust_improvement",
        fixture_evaluations=tuple(evaluations),
    )


def evaluate_task_cohort(
    task: PrivateTaskV2,
    submissions: Mapping[str, OptimizationBundle],
    *,
    epoch: int,
    worker_image: str,
    sandbox_policy: SandboxPolicy = DEFAULT_SANDBOX_POLICY,
    benchmark_policy: BenchmarkPolicy = DEFAULT_BENCHMARK_POLICY,
    trial_count: int = 6,
    worker_runner: WorkerRunner | None = None,
) -> CohortEvaluationV2:
    """Evaluate each canonical executable strategy exactly once for one task.

    Metadata-only bundle variants map to the same strategy digest. Their
    identities receive the same evidence digest and unsplit task reward; the
    network aggregator then divides that reward across the duplicate cohort.
    """

    if epoch < 0:
        raise EvaluationConfigurationError("epoch must be non-negative")
    if not submissions:
        raise EvaluationConfigurationError("at least one submission is required")
    if any(not miner_id for miner_id in submissions):
        raise EvaluationConfigurationError("miner IDs must be non-empty")

    by_strategy: dict[str, list[tuple[str, OptimizationBundle]]] = {}
    for miner_id, bundle in sorted(submissions.items()):
        if bundle.task_id != task.public.task_id:
            raise EvaluationConfigurationError("bundle belongs to another task")
        if bundle.engine_image_digest != task.public.engine_image_digest:
            raise EvaluationConfigurationError("bundle engine differs from task engine")
        digest = optimization_strategy_digest(bundle)
        by_strategy.setdefault(digest, []).append((miner_id, bundle))

    evaluations: list[tuple[str, HoldoutEvaluationV2]] = []
    observations: list[EpochObservation] = []
    for strategy_digest, members in sorted(by_strategy.items()):
        canonical_bundle = members[0][1]
        evaluation = evaluate_bundle_on_committed_holdouts(
            task,
            canonical_bundle,
            worker_image=worker_image,
            sandbox_policy=sandbox_policy,
            benchmark_policy=benchmark_policy,
            trial_count=trial_count,
            worker_runner=worker_runner,
        )
        if evaluation.strategy_digest != strategy_digest:
            raise EvaluationConfigurationError("evaluation strategy digest mismatch")
        evidence_digest = holdout_evidence_digest(evaluation)
        evaluations.append((strategy_digest, evaluation))
        for miner_id, _bundle in members:
            observations.append(
                EpochObservation(
                    miner_id=miner_id,
                    epoch=epoch,
                    family=task.public.benchmark_family_id,
                    task_id=task.public.task_id,
                    task_commitment=task.public.commitment,
                    evidence_digest=evidence_digest,
                    reward=evaluation.reward,
                    available=True,
                    correct=evaluation.exact_passed,
                    compliant=evaluation.compliant,
                    strategy_digest=strategy_digest,
                )
            )

    return CohortEvaluationV2(
        task_id=task.public.task_id,
        task_commitment=task.public.commitment,
        unique_strategy_count=len(by_strategy),
        cache_hit_count=len(submissions) - len(by_strategy),
        strategy_evaluations=tuple(evaluations),
        observations=tuple(sorted(observations, key=lambda item: item.miner_id)),
    )


def holdout_evidence_digest(evaluation: HoldoutEvaluationV2) -> str:
    """Hash the validator-owned transcript without metadata-only artifact IDs."""

    fixtures: list[dict[str, Any]] = []
    for item in evaluation.fixture_evaluations:
        result = item.result.model_dump(mode="python", exclude={"artifact_digest"})
        fixtures.append(
            {
                "fixture_id": item.fixture_id,
                "result": _stringify_floats(result),
                "score": _stringify_floats(asdict(item.score)),
            }
        )
    payload = {
        "task_id": evaluation.task_id,
        "task_commitment": evaluation.task_commitment,
        "strategy_digest": evaluation.strategy_digest,
        "family_id": evaluation.family_id,
        "exact_passed": evaluation.exact_passed,
        "compliant": evaluation.compliant,
        "eligible": evaluation.eligible,
        "reward": _number_string(evaluation.reward),
        "failure_code": evaluation.failure_code,
        "fixtures": fixtures,
    }
    return domain_separated_digest("planrace/2:holdout-evidence", payload)


def _number_string(value: float) -> str:
    if not math.isfinite(value):
        raise EvaluationConfigurationError("evidence contains a non-finite measurement")
    return format(value, ".17g")


def _stringify_floats(value: Any) -> Any:
    if isinstance(value, float):
        return _number_string(value)
    if isinstance(value, dict):
        return {str(key): _stringify_floats(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_stringify_floats(item) for item in value]
    return value


def _validate_and_regenerate_task(task: PrivateTaskV2) -> QueryFamily:
    family = next(
        (
            candidate
            for candidate in QUERY_FAMILIES
            if candidate.family_id == task.public.benchmark_family_id
        ),
        None,
    )
    if family is None:
        raise EvaluationConfigurationError("unknown benchmark family")

    def regenerate(seed: bytes) -> tuple[HiddenFixtureDescriptor, ...]:
        return tuple(
            fixture.descriptor
            for fixture in generate_hidden_fixtures(seed, family_id=family.family_id)
        )

    if not audit_task_reveal(task.public, task.reveal, regenerate=regenerate):
        raise EvaluationConfigurationError("task reveal or regenerated fixtures do not verify")
    if task.public.reference_sql.strip() != family.sql.strip():
        raise EvaluationConfigurationError("reference SQL does not match benchmark family")
    if task.public.schema_sql.strip() != SCHEMA_V2.strip():
        raise EvaluationConfigurationError("schema does not match benchmark v2")
    if task.public.parameter_ranges != published_parameter_ranges(family.family_id):
        raise EvaluationConfigurationError("published parameter ranges do not match generator")
    training = generate_public_training_fixture(family.family_id)
    published_training = task.public.public_training_fixture
    if (
        published_training.fixture_id != training.descriptor.fixture_id
        or published_training.generator_seed_hex != PUBLIC_TRAINING_SEED.hex()
        or published_training.content_digest != training.descriptor.content_digest
        or published_training.row_count != training.descriptor.row_count
    ):
        raise EvaluationConfigurationError("public training fixture does not match generator")
    return family


def _verify_worker_echo(request: SandboxRequestV2, result: SandboxResultV2) -> None:
    expected = (
        request.task.task_id,
        request.task.commitment,
        request.fixture.fixture_id,
        request.fixture.content_digest,
        request.reveal.hidden_fixture_merkle_root,
        request.bundle.artifact_digest,
    )
    observed = (
        result.task_id,
        result.task_commitment,
        result.fixture_id,
        result.fixture_content_digest,
        result.hidden_fixture_merkle_root,
        result.artifact_digest,
    )
    if observed != expected:
        raise EvaluationConfigurationError("worker result is not bound to its request")


def _robust_holdout_reward(rewards: Sequence[float]) -> float:
    if not rewards or any(not math.isfinite(value) or value < 0.0 for value in rewards):
        raise EvaluationConfigurationError("invalid holdout rewards")
    ordered = sorted(rewards)
    lower_width = max(1, math.ceil(len(ordered) / 4))
    lower_quartile = statistics.fmean(ordered[:lower_width])
    geometric = math.exp(statistics.fmean(math.log1p(value) for value in ordered)) - 1.0
    return 0.60 * lower_quartile + 0.40 * geometric


def _failed(
    task: PrivateTaskV2,
    bundle: OptimizationBundle,
    family_id: str,
    evaluations: Sequence[FixtureEvaluationV2],
    code: str,
) -> HoldoutEvaluationV2:
    return HoldoutEvaluationV2(
        task_id=task.public.task_id,
        task_commitment=task.public.commitment,
        artifact_digest=bundle.artifact_digest,
        strategy_digest=optimization_strategy_digest(bundle),
        family_id=family_id,
        exact_passed=all(item.result.correct for item in evaluations),
        compliant=all(item.result.compliant for item in evaluations),
        eligible=False,
        reward=0.0,
        failure_code=code,
        fixture_evaluations=tuple(evaluations),
    )
