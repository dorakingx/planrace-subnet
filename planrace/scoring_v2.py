"""Baseline-relative scoring and robust multi-epoch allocation for PlanRace v2.

The v1 evaluator is retained for replaying historical local-chain evidence.  This
module is the v2 mechanism: every candidate timing is paired with the reference
query on the same worker, correctness and policy compliance are hard gates, and
only a lower-confidence relative improvement can earn reward.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal

from planrace.models_v2 import domain_separated_digest

HORIZONS: tuple[int, ...] = (1, 10, 100, 1_000)
ExecutionOrder = Literal["baseline-first", "candidate-first"]


def _require_finite_non_negative(name: str, value: float) -> None:
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")


def _winsorized_mean(values: Sequence[float], fraction: float) -> float:
    """Return a deterministic winsorized mean without third-party numerics."""

    if not values:
        raise ValueError("at least one value is required")
    if not 0.0 <= fraction < 0.5:
        raise ValueError("winsor fraction must be in [0, 0.5)")
    ordered = sorted(values)
    width = int(len(ordered) * fraction)
    if width == 0:
        return statistics.fmean(ordered)
    lower = ordered[width]
    upper = ordered[-width - 1]
    bounded = [min(upper, max(lower, value)) for value in ordered]
    return statistics.fmean(bounded)


def _robust_standard_error(values: Sequence[float]) -> float:
    """MAD-based standard error, stable in the presence of timing outliers."""

    if len(values) < 2:
        return 0.0
    center = statistics.median(values)
    mad = statistics.median(abs(value - center) for value in values)
    return 1.4826 * mad / math.sqrt(len(values))


@dataclass(frozen=True, slots=True)
class BenchmarkPolicy:
    """Precommitted benchmark parameters; none may change within a task."""

    horizons: tuple[int, ...] = HORIZONS
    horizon_weights: tuple[float, ...] = (0.15, 0.25, 0.30, 0.30)
    minimum_trials: int = 6
    winsor_fraction: float = 0.10
    confidence_z: float = 1.28
    maximum_timeout_rate: float = 0.20
    storage_penalty_at_database_size: float = 0.10

    def __post_init__(self) -> None:
        if not self.horizons or any(horizon < 1 for horizon in self.horizons):
            raise ValueError("horizons must be positive")
        if len(self.horizons) != len(self.horizon_weights):
            raise ValueError("each horizon needs one weight")
        if any(weight < 0.0 or not math.isfinite(weight) for weight in self.horizon_weights):
            raise ValueError("horizon weights must be finite and non-negative")
        if not math.isclose(math.fsum(self.horizon_weights), 1.0, abs_tol=1e-12):
            raise ValueError("horizon weights must sum to one")
        if self.minimum_trials < 2:
            raise ValueError("minimum_trials must be at least two")
        if not 0.0 <= self.winsor_fraction < 0.5:
            raise ValueError("winsor_fraction must be in [0, 0.5)")
        _require_finite_non_negative("confidence_z", self.confidence_z)
        if not 0.0 <= self.maximum_timeout_rate < 1.0:
            raise ValueError("maximum_timeout_rate must be in [0, 1)")
        _require_finite_non_negative(
            "storage_penalty_at_database_size", self.storage_penalty_at_database_size
        )


@dataclass(frozen=True, slots=True)
class InterleavedTrial:
    """A baseline/candidate timing pair collected inside one disposable worker."""

    worker_id: str
    order: ExecutionOrder
    baseline_cold_ms: float
    candidate_cold_ms: float
    baseline_warm_ms: float
    candidate_warm_ms: float
    baseline_timed_out: bool = False
    candidate_timed_out: bool = False

    def __post_init__(self) -> None:
        if not self.worker_id:
            raise ValueError("worker_id is required")
        if self.order not in ("baseline-first", "candidate-first"):
            raise ValueError("invalid execution order")
        for name in (
            "baseline_cold_ms",
            "candidate_cold_ms",
            "baseline_warm_ms",
            "candidate_warm_ms",
        ):
            value = getattr(self, name)
            _require_finite_non_negative(name, value)
            if value == 0.0:
                raise ValueError(f"{name} must be greater than zero")


@dataclass(frozen=True, slots=True)
class BenchmarkEvidence:
    """Validator-owned measurements for one artifact on one hidden task."""

    correct: bool
    compliant: bool
    setup_ms: float
    artifact_storage_bytes: int
    database_bytes: int
    trials: tuple[InterleavedTrial, ...]

    def __post_init__(self) -> None:
        _require_finite_non_negative("setup_ms", self.setup_ms)
        if self.artifact_storage_bytes < 0:
            raise ValueError("artifact_storage_bytes must be non-negative")
        if self.database_bytes <= 0:
            raise ValueError("database_bytes must be positive")


@dataclass(frozen=True, slots=True)
class HorizonScore:
    horizon: int
    relative_speedup: float
    lower_confidence_speedup: float
    relative_savings: float


@dataclass(frozen=True, slots=True)
class BenchmarkScore:
    eligible: bool
    benchmark_valid: bool
    reward: float
    failure_code: str | None
    worker_id: str | None
    timeout_rate: float
    storage_ratio: float
    horizons: tuple[HorizonScore, ...]


DEFAULT_BENCHMARK_POLICY = BenchmarkPolicy()


def score_benchmark(
    evidence: BenchmarkEvidence,
    *,
    policy: BenchmarkPolicy = DEFAULT_BENCHMARK_POLICY,
) -> BenchmarkScore:
    """Score one candidate using paired, same-worker, relative measurements.

    The score is a 0..100 lower-confidence estimate of fractional savings.  A
    baseline-equivalent candidate earns zero; absolute machine speed cancels in
    the ratios.  A broken baseline invalidates the benchmark and must not update
    weights, while candidate failures are a valid zero.
    """

    storage_ratio = evidence.artifact_storage_bytes / evidence.database_bytes
    if len(evidence.trials) < policy.minimum_trials:
        return BenchmarkScore(
            False,
            False,
            0.0,
            "insufficient_trials",
            None,
            0.0,
            storage_ratio,
            (),
        )

    worker_ids = {trial.worker_id for trial in evidence.trials}
    if len(worker_ids) != 1:
        return BenchmarkScore(False, False, 0.0, "mixed_workers", None, 0.0, storage_ratio, ())
    worker_id = next(iter(worker_ids))
    order_counts = Counter(trial.order for trial in evidence.trials)
    if (
        not order_counts["baseline-first"]
        or not order_counts["candidate-first"]
        or abs(order_counts["baseline-first"] - order_counts["candidate-first"]) > 1
    ):
        return BenchmarkScore(
            False,
            False,
            0.0,
            "unbalanced_interleaving",
            worker_id,
            0.0,
            storage_ratio,
            (),
        )
    if any(trial.baseline_timed_out for trial in evidence.trials):
        return BenchmarkScore(
            False,
            False,
            0.0,
            "baseline_timeout",
            worker_id,
            0.0,
            storage_ratio,
            (),
        )

    timeout_rate = statistics.fmean(
        1.0 if trial.candidate_timed_out else 0.0 for trial in evidence.trials
    )
    if not evidence.correct:
        return BenchmarkScore(
            False,
            True,
            0.0,
            "result_mismatch",
            worker_id,
            timeout_rate,
            storage_ratio,
            (),
        )
    if not evidence.compliant:
        return BenchmarkScore(
            False,
            True,
            0.0,
            "policy_rejected",
            worker_id,
            timeout_rate,
            storage_ratio,
            (),
        )
    if timeout_rate > policy.maximum_timeout_rate:
        return BenchmarkScore(
            False,
            True,
            0.0,
            "timeout_rate",
            worker_id,
            timeout_rate,
            storage_ratio,
            (),
        )

    completed = tuple(trial for trial in evidence.trials if not trial.candidate_timed_out)
    if len(completed) < 2:
        return BenchmarkScore(
            False,
            True,
            0.0,
            "candidate_timeout",
            worker_id,
            timeout_rate,
            storage_ratio,
            (),
        )
    completed_orders = Counter(trial.order for trial in completed)
    if (
        not completed_orders["baseline-first"]
        or not completed_orders["candidate-first"]
        or abs(completed_orders["baseline-first"] - completed_orders["candidate-first"]) > 1
    ):
        return BenchmarkScore(
            False,
            True,
            0.0,
            "timeout_order_imbalance",
            worker_id,
            timeout_rate,
            storage_ratio,
            (),
        )

    horizon_scores: list[HorizonScore] = []
    weighted_savings = 0.0
    storage_multiplier = 1.0 + storage_ratio * policy.storage_penalty_at_database_size
    for horizon, horizon_weight in zip(policy.horizons, policy.horizon_weights, strict=True):
        log_speedups = []
        for trial in completed:
            baseline_total = trial.baseline_cold_ms + (horizon - 1) * trial.baseline_warm_ms
            candidate_total = (
                evidence.setup_ms
                + trial.candidate_cold_ms
                + (horizon - 1) * trial.candidate_warm_ms
            ) * storage_multiplier
            log_speedups.append(math.log2(baseline_total / candidate_total))
        center = _winsorized_mean(log_speedups, policy.winsor_fraction)
        lower_bound = center - policy.confidence_z * _robust_standard_error(log_speedups)
        relative_speedup = 2.0**center
        lower_confidence_speedup = 2.0**lower_bound
        relative_savings = max(0.0, min(1.0, 1.0 - 1.0 / lower_confidence_speedup))
        horizon_scores.append(
            HorizonScore(
                horizon=horizon,
                relative_speedup=relative_speedup,
                lower_confidence_speedup=lower_confidence_speedup,
                relative_savings=relative_savings,
            )
        )
        weighted_savings += horizon_weight * relative_savings

    # Intermittent timeouts remain visible and compound across repeated use.
    reliability = (1.0 - timeout_rate) ** 2
    reward = 100.0 * weighted_savings * reliability
    return BenchmarkScore(
        eligible=reward > 0.0,
        benchmark_valid=True,
        reward=reward,
        failure_code=None if reward > 0.0 else "no_relative_improvement",
        worker_id=worker_id,
        timeout_rate=timeout_rate,
        storage_ratio=storage_ratio,
        horizons=tuple(horizon_scores),
    )


def benchmark_evidence_from_sandbox(result: object) -> BenchmarkEvidence:
    """Construct scorer input only from a worker-authored sandbox transcript.

    This is the production bridge that prevents callers from supplying a bare
    ``correct=True`` flag disconnected from exact-result execution.
    """

    from planrace.sandbox_v2 import SandboxResultV2

    if not isinstance(result, SandboxResultV2):
        raise TypeError("result must be a SandboxResultV2")
    trials = tuple(
        InterleavedTrial(
            worker_id=trial.worker_id,
            order=trial.order,
            baseline_cold_ms=trial.baseline_cold_ms,
            candidate_cold_ms=trial.candidate_cold_ms,
            baseline_warm_ms=trial.baseline_warm_ms,
            candidate_warm_ms=trial.candidate_warm_ms,
            baseline_timed_out=trial.baseline_timed_out,
            candidate_timed_out=trial.candidate_timed_out,
        )
        for trial in result.trials
    )
    return BenchmarkEvidence(
        correct=result.correct,
        compliant=result.compliant,
        setup_ms=result.setup_ms,
        artifact_storage_bytes=result.artifact_storage_bytes,
        database_bytes=max(1, result.database_bytes),
        trials=trials,
    )


@dataclass(frozen=True, slots=True)
class EpochObservation:
    miner_id: str
    epoch: int
    family: str
    task_id: str
    task_commitment: str
    evidence_digest: str
    reward: float
    available: bool
    correct: bool
    compliant: bool
    strategy_digest: str
    duplicate_group_size: int = 1

    def __post_init__(self) -> None:
        if not all(
            (
                self.miner_id,
                self.family,
                self.task_id,
                self.task_commitment,
                self.evidence_digest,
                self.strategy_digest,
            )
        ):
            raise ValueError("observation identity, task, evidence, and strategy are required")
        if self.epoch < 0:
            raise ValueError("epoch must be non-negative")
        _require_finite_non_negative("reward", self.reward)
        if self.reward > 100.0:
            raise ValueError("reward cannot exceed 100")
        if self.duplicate_group_size < 1:
            raise ValueError("duplicate_group_size must be positive")


@dataclass(frozen=True, slots=True)
class ScheduledTask:
    epoch: int
    family: str
    task_id: str
    task_commitment: str

    def __post_init__(self) -> None:
        if self.epoch < 0 or not self.family or not self.task_id or not self.task_commitment:
            raise ValueError("scheduled task fields are required")


@dataclass(frozen=True, slots=True)
class AggregationPolicy:
    required_families: tuple[str, ...]
    task_schedule: tuple[ScheduledTask, ...]
    minimum_tasks: int = 12
    minimum_tasks_per_family: int = 2
    minimum_availability: float = 0.75
    minimum_compliance: float = 0.95
    minimum_correctness: float = 0.95
    winsor_fraction: float = 0.10
    confidence_z: float = 1.0
    maximum_weight: float = 0.20
    minimum_distinct_strategies: int = 5

    def __post_init__(self) -> None:
        if not self.required_families or len(set(self.required_families)) != len(
            self.required_families
        ):
            raise ValueError("required_families must be unique and non-empty")
        if not self.task_schedule:
            raise ValueError("a precommitted task_schedule is required")
        task_ids = [task.task_id for task in self.task_schedule]
        task_commitments = [task.task_commitment for task in self.task_schedule]
        epochs = [task.epoch for task in self.task_schedule]
        if (
            len(task_ids) != len(set(task_ids))
            or len(task_commitments) != len(set(task_commitments))
            or len(epochs) != len(set(epochs))
        ):
            raise ValueError("scheduled task IDs, commitments, and epochs must be unique")
        if {task.family for task in self.task_schedule} - set(self.required_families):
            raise ValueError("schedule contains a family outside required_families")
        if self.minimum_tasks < len(self.required_families):
            raise ValueError("minimum_tasks cannot be smaller than the family count")
        if self.minimum_tasks_per_family < 1:
            raise ValueError("minimum_tasks_per_family must be positive")
        if self.minimum_tasks < self.minimum_tasks_per_family * len(self.required_families):
            raise ValueError("minimum_tasks cannot satisfy the per-family quota")
        if self.minimum_tasks > len(self.task_schedule):
            raise ValueError("minimum_tasks cannot exceed the schedule")
        schedule_counts = Counter(task.family for task in self.task_schedule)
        if any(
            schedule_counts[family] < self.minimum_tasks_per_family
            for family in self.required_families
        ):
            raise ValueError("task_schedule cannot satisfy the per-family quota")
        for name in ("minimum_availability", "minimum_compliance", "minimum_correctness"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
        if not 0.0 <= self.winsor_fraction < 0.5:
            raise ValueError("winsor_fraction must be in [0, 0.5)")
        _require_finite_non_negative("confidence_z", self.confidence_z)
        if not 0.0 < self.maximum_weight <= 1.0:
            raise ValueError("maximum_weight must be in (0, 1]")
        if self.minimum_distinct_strategies < 1:
            raise ValueError("minimum_distinct_strategies must be positive")


@dataclass(frozen=True, slots=True)
class MinerAggregate:
    miner_id: str
    eligible: bool
    reward: float
    center: float
    uncertainty: float
    availability: float
    compliance: float
    correctness: float
    task_count: int
    family_scores: tuple[tuple[str, float], ...]
    strategy_digest: str
    failure_code: str | None


def aggregate_miner(
    observations: Sequence[EpochObservation],
    *,
    policy: AggregationPolicy,
) -> MinerAggregate:
    """Aggregate one miner against a closed, precommitted task schedule."""

    if not observations:
        raise ValueError("observations cannot be empty")
    miner_ids = {observation.miner_id for observation in observations}
    if len(miner_ids) != 1:
        raise ValueError("observations must belong to one miner")
    miner_id = next(iter(miner_ids))
    return _aggregate_scheduled_miner(miner_id, observations, policy)


def deduplicate_task_rewards(
    observations: Sequence[EpochObservation],
) -> tuple[EpochObservation, ...]:
    """Evaluate-once accounting for duplicate strategies on each task.

    Validators cache one sandbox score per ``(task commitment, executable
    strategy digest)``.  Every identity in that group must therefore carry the
    same evidence and total reward, which is split without changing group mass.
    """

    task_metadata: dict[str, tuple[int, str, str]] = {}
    groups: dict[tuple[str, str], list[EpochObservation]] = defaultdict(list)
    untouched: list[EpochObservation] = []
    for observation in observations:
        metadata = (observation.epoch, observation.family, observation.task_commitment)
        previous = task_metadata.setdefault(observation.task_id, metadata)
        if previous != metadata:
            raise ValueError("task_id maps to inconsistent schedule metadata")
        if observation.available and observation.compliant and observation.correct:
            groups[(observation.task_commitment, observation.strategy_digest)].append(observation)
        else:
            untouched.append(observation)

    deduplicated = list(untouched)
    for members in groups.values():
        miner_ids = [member.miner_id for member in members]
        if len(miner_ids) != len(set(miner_ids)):
            raise ValueError("duplicate miner observation for one task strategy")
        evidence = {member.evidence_digest for member in members}
        rewards = [member.reward for member in members]
        if len(evidence) != 1 or max(rewards) - min(rewards) > 1e-9:
            raise ValueError("cached duplicate strategy evidence is inconsistent")
        group_size = len(members)
        shared_reward = rewards[0] / group_size
        deduplicated.extend(
            replace(
                member,
                reward=shared_reward,
                duplicate_group_size=group_size,
            )
            for member in members
        )
    return tuple(sorted(deduplicated, key=lambda item: (item.miner_id, item.epoch)))


def aggregate_network(
    observations: Sequence[EpochObservation],
    *,
    miner_ids: Sequence[str],
    policy: AggregationPolicy,
) -> tuple[MinerAggregate, ...]:
    """Secure production aggregation: deduplicate first, then fill omissions."""

    if not miner_ids or len(set(miner_ids)) != len(miner_ids):
        raise ValueError("miner_ids must be unique and non-empty")
    allowed = set(miner_ids)
    if any(observation.miner_id not in allowed for observation in observations):
        raise ValueError("observation belongs to a miner outside the declared roster")
    deduplicated = deduplicate_task_rewards(observations)
    by_miner: dict[str, list[EpochObservation]] = defaultdict(list)
    for observation in deduplicated:
        by_miner[observation.miner_id].append(observation)
    return tuple(
        _aggregate_scheduled_miner(miner_id, by_miner[miner_id], policy) for miner_id in miner_ids
    )


def _aggregate_scheduled_miner(
    miner_id: str,
    observations: Sequence[EpochObservation],
    policy: AggregationPolicy,
) -> MinerAggregate:
    schedule = {task.task_id: task for task in policy.task_schedule}
    by_task: dict[str, EpochObservation] = {}
    for observation in observations:
        scheduled = schedule.get(observation.task_id)
        if scheduled is None:
            raise ValueError("observation is outside the precommitted task schedule")
        if (
            observation.epoch,
            observation.family,
            observation.task_commitment,
        ) != (scheduled.epoch, scheduled.family, scheduled.task_commitment):
            raise ValueError("observation does not match its scheduled task")
        if observation.task_id in by_task:
            raise ValueError("duplicate observation for one scheduled task")
        by_task[observation.task_id] = observation

    available = [observation for observation in observations if observation.available]
    task_count = len(available)
    availability = task_count / len(policy.task_schedule)
    compliance = (
        statistics.fmean(1.0 if observation.compliant else 0.0 for observation in available)
        if available
        else 0.0
    )
    correctness = (
        statistics.fmean(1.0 if observation.correct else 0.0 for observation in available)
        if available
        else 0.0
    )

    by_family: dict[str, list[float]] = defaultdict(list)
    history: list[dict[str, int | str]] = []
    for scheduled in policy.task_schedule:
        scheduled_observation = by_task.get(scheduled.task_id)
        gated_reward = 0.0
        strategy_digest = "missing"
        if scheduled_observation is not None:
            strategy_digest = scheduled_observation.strategy_digest
            if (
                scheduled_observation.available
                and scheduled_observation.compliant
                and scheduled_observation.correct
            ):
                gated_reward = scheduled_observation.reward
        by_family[scheduled.family].append(gated_reward)
        history.append(
            {
                "epoch": scheduled.epoch,
                "task_commitment": scheduled.task_commitment,
                "strategy_digest": strategy_digest,
            }
        )

    family_scores = tuple(
        (
            family,
            max(
                0.0,
                _winsorized_mean(by_family[family], policy.winsor_fraction)
                - policy.confidence_z * _robust_standard_error(by_family[family]),
            ),
        )
        for family in policy.required_families
    )
    score_values = [score for _, score in family_scores]
    center = (
        math.exp(statistics.fmean(math.log(score) for score in score_values))
        if all(score > 0.0 for score in score_values)
        else 0.0
    )
    # Uncertainty is computed on equally weighted family aggregates.  Padding
    # one family with repeated observations cannot shrink the global bound.
    uncertainty = policy.confidence_z * _robust_standard_error(score_values)
    reward = max(0.0, center - uncertainty) * availability * compliance
    strategy_digest = domain_separated_digest("planrace/2:strategy-portfolio", {"history": history})

    failure_code: str | None = None
    if task_count < policy.minimum_tasks:
        failure_code = "insufficient_tasks"
    elif availability < policy.minimum_availability:
        failure_code = "availability_gate"
    elif compliance < policy.minimum_compliance:
        failure_code = "compliance_gate"
    elif correctness < policy.minimum_correctness:
        failure_code = "correctness_gate"
    elif any(score <= 0.0 for score in score_values):
        failure_code = "worst_family_gate"
    elif reward <= 0.0:
        failure_code = "no_robust_improvement"

    return MinerAggregate(
        miner_id=miner_id,
        eligible=failure_code is None,
        reward=reward if failure_code is None else 0.0,
        center=center,
        uncertainty=uncertainty,
        availability=availability,
        compliance=compliance,
        correctness=correctness,
        task_count=task_count,
        family_scores=family_scores,
        strategy_digest=strategy_digest,
        failure_code=failure_code,
    )


@dataclass(frozen=True, slots=True)
class ConcentrationMetrics:
    gini: float
    hhi: float
    top1_share: float
    effective_miners: float


@dataclass(frozen=True, slots=True)
class AllocationResult:
    planned: bool
    reason: str | None
    weights: tuple[tuple[str, float], ...]
    duplicate_groups: tuple[tuple[str, tuple[str, ...]], ...]
    strategy_weights: tuple[tuple[str, float], ...]
    concentration: ConcentrationMetrics


def concentration_metrics(weights: Mapping[str, float]) -> ConcentrationMetrics:
    if any(not math.isfinite(value) or value < 0.0 for value in weights.values()):
        raise ValueError("weights must be finite and non-negative")
    values = sorted(weights.values())
    total = math.fsum(values)
    if not values or total == 0.0:
        return ConcentrationMetrics(0.0, 0.0, 0.0, 0.0)
    normalized = [value / total for value in values]
    count = len(normalized)
    gini_numerator = math.fsum(
        (2 * index - count - 1) * value for index, value in enumerate(normalized, start=1)
    )
    gini = gini_numerator / count
    hhi = math.fsum(value * value for value in normalized)
    return ConcentrationMetrics(
        gini=gini,
        hhi=hhi,
        top1_share=max(normalized),
        effective_miners=1.0 / hhi,
    )


def _capped_normalize(raw: Mapping[str, float], maximum_weight: float) -> dict[str, float]:
    if len(raw) * maximum_weight < 1.0 - 1e-12:
        raise ValueError("not enough recipients to satisfy the concentration cap")
    remaining = dict(raw)
    weights: dict[str, float] = {}
    remaining_mass = 1.0
    while remaining:
        total = math.fsum(remaining.values())
        if total <= 0.0:
            equal = remaining_mass / len(remaining)
            weights.update({miner_id: equal for miner_id in remaining})
            break
        proposed = {
            miner_id: remaining_mass * value / total for miner_id, value in remaining.items()
        }
        capped = [
            miner_id for miner_id, value in proposed.items() if value > maximum_weight + 1e-15
        ]
        if not capped:
            weights.update(proposed)
            break
        for miner_id in sorted(capped):
            weights[miner_id] = maximum_weight
            remaining_mass -= maximum_weight
            del remaining[miner_id]
    # Put floating residue on the smallest weight without violating the cap.
    residue = 1.0 - math.fsum(weights.values())
    if abs(residue) > 1e-15:
        for miner_id in sorted(weights, key=lambda item: (weights[item], item)):
            if weights[miner_id] + residue <= maximum_weight + 1e-12:
                weights[miner_id] += residue
                break
    return weights


def allocate_weights(
    aggregates: Sequence[MinerAggregate],
    *,
    policy: AggregationPolicy,
) -> AllocationResult:
    """Deduplicate strategy rewards, cap concentration, and fail closed."""

    empty_metrics = ConcentrationMetrics(0.0, 0.0, 0.0, 0.0)
    eligible = [
        aggregate for aggregate in aggregates if aggregate.eligible and aggregate.reward > 0
    ]
    if not eligible:
        return AllocationResult(False, "all_failed", (), (), (), empty_metrics)

    by_digest: dict[str, list[MinerAggregate]] = defaultdict(list)
    for aggregate in eligible:
        by_digest[aggregate.strategy_digest].append(aggregate)
    duplicate_groups = tuple(
        (digest, tuple(sorted(member.miner_id for member in members)))
        for digest, members in sorted(by_digest.items())
        if len(members) > 1
    )
    if len(by_digest) < policy.minimum_distinct_strategies:
        return AllocationResult(
            False,
            "insufficient_strategy_diversity",
            (),
            duplicate_groups,
            (),
            empty_metrics,
        )

    # Task-level evaluate-once accounting has already split every duplicated
    # executable strategy in ``aggregate_network``.  Recombine identical full
    # portfolios here before applying the concentration cap, so cloning an
    # identity neither creates reward nor bypasses the strategy-level cap.
    raw_groups = {
        digest: math.fsum(member.reward for member in members)
        for digest, members in by_digest.items()
    }
    try:
        normalized_groups = _capped_normalize(raw_groups, policy.maximum_weight)
    except ValueError:
        return AllocationResult(
            False,
            "insufficient_recipients_for_cap",
            (),
            duplicate_groups,
            (),
            empty_metrics,
        )
    normalized: dict[str, float] = {}
    for digest, members in by_digest.items():
        group_reward = raw_groups[digest]
        for member in members:
            normalized[member.miner_id] = normalized_groups[digest] * member.reward / group_reward
    weights = tuple(sorted(normalized.items()))
    strategy_weights = tuple(sorted(normalized_groups.items()))
    return AllocationResult(
        True,
        None,
        weights,
        duplicate_groups,
        strategy_weights,
        concentration_metrics(dict(strategy_weights)),
    )


def kendall_tau_b(first: Mapping[str, float], second: Mapping[str, float]) -> float:
    """Kendall tau-b for score maps, including deterministic tie handling."""

    keys = sorted(set(first) & set(second))
    if len(keys) < 2:
        raise ValueError("at least two shared items are required")
    concordant = discordant = ties_first = ties_second = 0
    for index, left in enumerate(keys):
        for right in keys[index + 1 :]:
            delta_first = first[left] - first[right]
            delta_second = second[left] - second[right]
            if delta_first == 0.0 and delta_second == 0.0:
                continue
            if delta_first == 0.0:
                ties_first += 1
            elif delta_second == 0.0:
                ties_second += 1
            elif delta_first * delta_second > 0.0:
                concordant += 1
            else:
                discordant += 1
    first_pairs = concordant + discordant + ties_first
    second_pairs = concordant + discordant + ties_second
    denominator = math.sqrt(first_pairs * second_pairs)
    if denominator == 0.0:
        return 1.0
    return (concordant - discordant) / denominator
