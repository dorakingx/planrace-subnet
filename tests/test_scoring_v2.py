import math
from dataclasses import replace
from typing import Any, cast

import pytest

from planrace.scoring_v2 import (
    AggregationPolicy,
    BenchmarkEvidence,
    BenchmarkPolicy,
    EpochObservation,
    InterleavedTrial,
    MinerAggregate,
    ScheduledTask,
    aggregate_miner,
    aggregate_network,
    allocate_weights,
    concentration_metrics,
    kendall_tau_b,
    score_benchmark,
)

FAMILIES = ("joins", "aggregates", "range", "skew")


def task_schedule() -> tuple[ScheduledTask, ...]:
    return tuple(
        ScheduledTask(
            epoch=epoch,
            family=FAMILIES[epoch % len(FAMILIES)],
            task_id=f"task-{epoch}",
            task_commitment=f"sha256:{epoch + 1:064x}",
        )
        for epoch in range(12)
    )


def trials(
    *,
    scale: float = 1.0,
    candidate_scale: float = 0.5,
    worker_id: str = "worker-a",
    count: int = 10,
    candidate_timeouts: int = 0,
) -> tuple[InterleavedTrial, ...]:
    return tuple(
        InterleavedTrial(
            worker_id=worker_id,
            order="baseline-first" if index % 2 == 0 else "candidate-first",
            baseline_cold_ms=80.0 * scale,
            candidate_cold_ms=80.0 * scale * candidate_scale,
            baseline_warm_ms=20.0 * scale,
            candidate_warm_ms=20.0 * scale * candidate_scale,
            candidate_timed_out=index < candidate_timeouts,
        )
        for index in range(count)
    )


def evidence(
    *,
    trial_values: tuple[InterleavedTrial, ...] | None = None,
    correct: bool = True,
    compliant: bool = True,
    setup_ms: float = 0.0,
    storage_bytes: int = 0,
) -> BenchmarkEvidence:
    return BenchmarkEvidence(
        correct=correct,
        compliant=compliant,
        setup_ms=setup_ms,
        artifact_storage_bytes=storage_bytes,
        database_bytes=1_000_000,
        trials=trial_values or trials(),
    )


def test_same_worker_relative_score_is_hardware_scale_invariant() -> None:
    fast = score_benchmark(evidence(setup_ms=4.0))
    slow = score_benchmark(evidence(trial_values=trials(scale=3.0), setup_ms=12.0))
    assert fast.eligible and slow.eligible
    assert slow.reward == pytest.approx(fast.reward)
    assert [item.horizon for item in fast.horizons] == [1, 10, 100, 1_000]


def test_setup_and_storage_are_charged_at_every_horizon() -> None:
    no_overhead = score_benchmark(evidence())
    overhead = score_benchmark(evidence(setup_ms=80.0, storage_bytes=1_000_000))
    assert overhead.reward < no_overhead.reward
    assert overhead.horizons[0].relative_savings == 0.0
    assert overhead.horizons[-1].relative_savings > 0.0
    assert overhead.storage_ratio == 1.0


def test_correctness_compliance_and_timeout_fail_closed() -> None:
    wrong = score_benchmark(evidence(correct=False))
    rejected = score_benchmark(evidence(compliant=False))
    timed_out = score_benchmark(evidence(trial_values=trials(candidate_timeouts=3)))
    assert (wrong.reward, wrong.failure_code) == (0.0, "result_mismatch")
    assert (rejected.reward, rejected.failure_code) == (0.0, "policy_rejected")
    assert (timed_out.reward, timed_out.failure_code) == (0.0, "timeout_rate")


def test_mixed_worker_and_broken_baseline_invalidate_measurement() -> None:
    mixed = list(trials())
    mixed[-1] = InterleavedTrial(
        worker_id="worker-b",
        order=mixed[-1].order,
        baseline_cold_ms=80.0,
        candidate_cold_ms=40.0,
        baseline_warm_ms=20.0,
        candidate_warm_ms=10.0,
    )
    mixed_score = score_benchmark(evidence(trial_values=tuple(mixed)))
    broken = list(trials())
    original = broken[0]
    broken[0] = InterleavedTrial(
        worker_id=original.worker_id,
        order=original.order,
        baseline_cold_ms=original.baseline_cold_ms,
        candidate_cold_ms=original.candidate_cold_ms,
        baseline_warm_ms=original.baseline_warm_ms,
        candidate_warm_ms=original.candidate_warm_ms,
        baseline_timed_out=True,
    )
    baseline_score = score_benchmark(evidence(trial_values=tuple(broken)))
    assert not mixed_score.benchmark_valid
    assert mixed_score.failure_code == "mixed_workers"
    assert not baseline_score.benchmark_valid
    assert baseline_score.failure_code == "baseline_timeout"


def test_winsorization_contains_one_timing_outlier() -> None:
    clean = score_benchmark(evidence())
    noisy = list(trials())
    outlier = noisy[0]
    noisy[0] = InterleavedTrial(
        worker_id=outlier.worker_id,
        order=outlier.order,
        baseline_cold_ms=outlier.baseline_cold_ms,
        candidate_cold_ms=outlier.candidate_cold_ms * 100,
        baseline_warm_ms=outlier.baseline_warm_ms,
        candidate_warm_ms=outlier.candidate_warm_ms * 100,
    )
    robust = score_benchmark(
        evidence(trial_values=tuple(noisy)),
        policy=BenchmarkPolicy(winsor_fraction=0.10),
    )
    assert robust.reward == pytest.approx(clean.reward)


def observations(
    miner_id: str,
    *,
    reward: float = 40.0,
    available: bool = True,
    compliant: bool = True,
    correct: bool = True,
    digest: str | None = None,
) -> list[EpochObservation]:
    schedule = task_schedule()
    strategy_digest = digest or f"digest-{miner_id}"
    return [
        EpochObservation(
            miner_id=miner_id,
            epoch=task.epoch,
            family=task.family,
            task_id=task.task_id,
            task_commitment=task.task_commitment,
            evidence_digest=f"evidence-{task.epoch}-{strategy_digest}",
            reward=reward,
            available=available,
            compliant=compliant,
            correct=correct,
            strategy_digest=strategy_digest,
        )
        for task in schedule
    ]


def aggregation_policy() -> AggregationPolicy:
    return AggregationPolicy(
        required_families=FAMILIES,
        task_schedule=task_schedule(),
        minimum_tasks=12,
    )


def test_multi_epoch_gates_and_fixed_family_quota() -> None:
    policy = replace(aggregation_policy(), minimum_tasks=8)
    eligible = aggregate_miner(observations("good"), policy=policy)
    offline = observations("offline")
    offline[:4] = [
        replace(
            item,
            available=False,
            correct=False,
            compliant=False,
        )
        for item in offline[:4]
    ]
    unavailable = aggregate_miner(offline, policy=policy)
    assert eligible.eligible
    assert eligible.reward == pytest.approx(40.0)
    assert not unavailable.eligible
    assert unavailable.failure_code == "availability_gate"
    assert dict(unavailable.family_scores)["joins"] < 40.0


def aggregate(miner_id: str, reward: float, digest: str) -> MinerAggregate:
    return MinerAggregate(
        miner_id=miner_id,
        eligible=True,
        reward=reward,
        center=reward,
        uncertainty=0.0,
        availability=1.0,
        compliance=1.0,
        correctness=1.0,
        task_count=12,
        family_scores=tuple((family, reward) for family in FAMILIES),
        strategy_digest=digest,
        failure_code=None,
    )


def test_duplicate_identities_split_task_rewards_without_strategy_gain() -> None:
    policy = aggregation_policy()
    other_ids = [f"miner-{index}" for index in range(6)]
    other_observations = [
        observation for miner_id in other_ids for observation in observations(miner_id, reward=10.0)
    ]
    single_aggregates = aggregate_network(
        [*other_observations, *observations("copy-a", reward=10.0, digest="shared")],
        miner_ids=[*other_ids, "copy-a"],
        policy=policy,
    )
    duplicated_aggregates = aggregate_network(
        [
            *other_observations,
            *observations("copy-a", reward=10.0, digest="shared"),
            *observations("copy-b", reward=10.0, digest="shared"),
        ],
        miner_ids=[*other_ids, "copy-a", "copy-b"],
        policy=policy,
    )
    single = allocate_weights(single_aggregates, policy=policy)
    duplicated = allocate_weights(duplicated_aggregates, policy=policy)
    assert single.planned and duplicated.planned
    single_weights = dict(single.weights)
    duplicate_weights = dict(duplicated.weights)
    assert duplicate_weights["copy-a"] + duplicate_weights["copy-b"] == pytest.approx(
        single_weights["copy-a"]
    )
    assert max(duplicate_weights.values()) <= policy.maximum_weight
    assert duplicated.concentration.top1_share <= policy.maximum_weight
    assert sum(
        aggregate.reward
        for aggregate in duplicated_aggregates
        if aggregate.miner_id in {"copy-a", "copy-b"}
    ) == pytest.approx(
        next(aggregate.reward for aggregate in single_aggregates if aggregate.miner_id == "copy-a")
    )


def test_inconsistent_cached_duplicate_evidence_is_rejected() -> None:
    policy = aggregation_policy()
    copy_a = observations("copy-a", reward=10.0, digest="shared")
    copy_b = observations("copy-b", reward=10.0, digest="shared")
    copy_b[0] = replace(copy_b[0], evidence_digest="forged-evidence", reward=100.0)
    with pytest.raises(ValueError, match="cached duplicate strategy evidence"):
        aggregate_network(
            [*copy_a, *copy_b],
            miner_ids=["copy-a", "copy-b"],
            policy=policy,
        )


def test_all_failed_is_safe_no_update() -> None:
    failed = MinerAggregate(
        miner_id="failed",
        eligible=False,
        reward=0.0,
        center=0.0,
        uncertainty=0.0,
        availability=0.0,
        compliance=0.0,
        correctness=0.0,
        task_count=12,
        family_scores=(),
        strategy_digest="failed-strategy",
        failure_code="availability_gate",
    )
    allocation = allocate_weights([failed], policy=aggregation_policy())
    assert not allocation.planned
    assert allocation.reason == "all_failed"
    assert allocation.weights == ()


def test_kendall_tau_b_tracks_stable_and_reversed_ranks() -> None:
    first = {"a": 3.0, "b": 2.0, "c": 1.0}
    assert kendall_tau_b(first, first) == 1.0
    assert math.isclose(kendall_tau_b(first, {"a": 1.0, "b": 2.0, "c": 3.0}), -1.0)


@pytest.mark.parametrize(
    "overrides",
    [
        {"horizons": ()},
        {"horizons": (0,), "horizon_weights": (1.0,)},
        {"horizons": (1,), "horizon_weights": (0.5, 0.5)},
        {"horizon_weights": (-0.1, 0.3, 0.4, 0.4)},
        {"horizon_weights": (0.1, 0.2, 0.3, 0.3)},
        {"minimum_trials": 1},
        {"winsor_fraction": 0.5},
        {"confidence_z": float("nan")},
        {"maximum_timeout_rate": 1.0},
        {"storage_penalty_at_database_size": -1.0},
    ],
)
def test_benchmark_policy_rejects_unsafe_parameters(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        BenchmarkPolicy(**overrides)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("worker_id", ""),
        ("order", "not-an-order"),
        ("baseline_cold_ms", 0.0),
        ("candidate_cold_ms", -1.0),
    ],
)
def test_interleaved_trial_rejects_invalid_measurements(field: str, value: object) -> None:
    kwargs: dict[str, object] = {
        "worker_id": "worker",
        "order": "baseline-first",
        "baseline_cold_ms": 10.0,
        "candidate_cold_ms": 5.0,
        "baseline_warm_ms": 4.0,
        "candidate_warm_ms": 2.0,
    }
    kwargs[field] = value
    with pytest.raises(ValueError):
        InterleavedTrial(**cast(Any, kwargs))


@pytest.mark.parametrize(
    "overrides",
    [
        {"setup_ms": -1.0},
        {"artifact_storage_bytes": -1},
        {"database_bytes": 0},
    ],
)
def test_benchmark_evidence_rejects_invalid_costs(overrides: dict[str, Any]) -> None:
    kwargs: dict[str, Any] = {
        "correct": True,
        "compliant": True,
        "setup_ms": 0.0,
        "artifact_storage_bytes": 0,
        "database_bytes": 100,
        "trials": trials(),
    }
    kwargs.update(overrides)
    with pytest.raises(ValueError):
        BenchmarkEvidence(**kwargs)


def test_measurement_structure_and_intermittent_timeout_paths() -> None:
    too_few = score_benchmark(evidence(trial_values=trials(count=2)))
    one_order = tuple(
        InterleavedTrial(
            worker_id="worker",
            order="baseline-first",
            baseline_cold_ms=10.0,
            candidate_cold_ms=5.0,
            baseline_warm_ms=4.0,
            candidate_warm_ms=2.0,
        )
        for _ in range(6)
    )
    unbalanced = score_benchmark(evidence(trial_values=one_order))
    almost_all_timeout = score_benchmark(
        evidence(trial_values=trials(candidate_timeouts=9)),
        policy=BenchmarkPolicy(maximum_timeout_rate=0.95),
    )
    timeout_imbalanced_values = list(trials())
    for index in (0, 2):
        old = timeout_imbalanced_values[index]
        timeout_imbalanced_values[index] = InterleavedTrial(
            worker_id=old.worker_id,
            order=old.order,
            baseline_cold_ms=old.baseline_cold_ms,
            candidate_cold_ms=old.candidate_cold_ms,
            baseline_warm_ms=old.baseline_warm_ms,
            candidate_warm_ms=old.candidate_warm_ms,
            candidate_timed_out=True,
        )
    timeout_imbalanced = score_benchmark(evidence(trial_values=tuple(timeout_imbalanced_values)))
    one_timeout = score_benchmark(evidence(trial_values=trials(candidate_timeouts=1)))
    baseline_equivalent = score_benchmark(evidence(trial_values=trials(candidate_scale=1.0)))
    assert too_few.failure_code == "insufficient_trials"
    assert unbalanced.failure_code == "unbalanced_interleaving"
    assert almost_all_timeout.failure_code == "candidate_timeout"
    assert timeout_imbalanced.failure_code == "timeout_order_imbalance"
    assert 0.0 < one_timeout.reward < score_benchmark(evidence()).reward
    assert baseline_equivalent.failure_code == "no_relative_improvement"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"miner_id": ""},
        {"epoch": -1},
        {"reward": -1.0},
        {"reward": 101.0},
    ],
)
def test_epoch_observation_validation(kwargs: dict[str, Any]) -> None:
    values: dict[str, Any] = {
        "miner_id": "miner",
        "epoch": 0,
        "family": "joins",
        "task_id": "task-0",
        "task_commitment": f"sha256:{1:064x}",
        "evidence_digest": "evidence",
        "reward": 1.0,
        "available": True,
        "correct": True,
        "compliant": True,
        "strategy_digest": "digest",
    }
    values.update(kwargs)
    with pytest.raises(ValueError):
        EpochObservation(**values)


@pytest.mark.parametrize(
    "overrides",
    [
        {"required_families": ()},
        {"required_families": ("joins", "joins")},
        {"task_schedule": ()},
        {"minimum_tasks": 2},
        {"minimum_availability": 1.1},
        {"minimum_compliance": -0.1},
        {"minimum_correctness": 1.1},
        {"winsor_fraction": 0.5},
        {"confidence_z": -1.0},
        {"maximum_weight": 0.0},
        {"minimum_distinct_strategies": 0},
    ],
)
def test_aggregation_policy_validation(overrides: dict[str, Any]) -> None:
    values: dict[str, Any] = {
        "required_families": FAMILIES,
        "task_schedule": task_schedule(),
    }
    values.update(overrides)
    with pytest.raises(ValueError):
        AggregationPolicy(**values)


def test_aggregation_rejects_bad_sets_and_exercises_each_gate() -> None:
    policy = aggregation_policy()
    with pytest.raises(ValueError, match="cannot be empty"):
        aggregate_miner([], policy=policy)
    mixed = observations("a")
    mixed[-1] = replace(mixed[-1], miner_id="b", strategy_digest="digest-b")
    with pytest.raises(ValueError, match="one miner"):
        aggregate_miner(mixed, policy=policy)

    insufficient = aggregate_miner(observations("short")[:8], policy=policy)
    specialist_values = observations("specialist")
    specialist_values = [
        item if item.family == "joins" else replace(item, reward=0.0) for item in specialist_values
    ]
    specialist = aggregate_miner(specialist_values, policy=policy)
    bad_compliance = observations("noncompliant")
    item = bad_compliance[0]
    bad_compliance[0] = replace(item, compliant=False)
    compliance = aggregate_miner(bad_compliance, policy=policy)
    bad_correctness = observations("incorrect")
    item = bad_correctness[0]
    bad_correctness[0] = replace(item, correct=False)
    correctness = aggregate_miner(bad_correctness, policy=policy)
    no_gain = aggregate_miner(observations("no-gain", reward=0.0), policy=policy)
    unstable_rewards = {"joins": 0.01, "aggregates": 0.02, "range": 50.0, "skew": 100.0}
    unstable = aggregate_miner(
        [replace(item, reward=unstable_rewards[item.family]) for item in observations("unstable")],
        policy=policy,
    )
    rotating_observations = observations("rotating")
    rotating_observations[-1] = replace(
        rotating_observations[-1],
        strategy_digest="different-executable-strategy",
        evidence_digest="different-executable-evidence",
    )
    rotating = aggregate_miner(rotating_observations, policy=policy)
    with pytest.raises(ValueError, match="duplicate observation"):
        aggregate_miner(
            [*observations("duplicated"), observations("duplicated")[0]],
            policy=policy,
        )
    outside = replace(observations("outside")[0], task_id="not-scheduled")
    with pytest.raises(ValueError, match="outside the precommitted"):
        aggregate_miner([outside], policy=policy)
    mismatch = replace(observations("mismatch")[0], family="skew")
    with pytest.raises(ValueError, match="does not match"):
        aggregate_miner([mismatch], policy=policy)
    assert insufficient.failure_code == "insufficient_tasks"
    assert insufficient.availability == pytest.approx(8 / 12)
    assert specialist.failure_code == "worst_family_gate"
    assert specialist.reward == 0.0
    assert compliance.failure_code == "compliance_gate"
    assert correctness.failure_code == "correctness_gate"
    assert no_gain.failure_code == "worst_family_gate"
    assert unstable.failure_code == "no_robust_improvement"
    assert rotating.eligible
    assert rotating.reward == pytest.approx(40.0)


def test_concentration_and_allocation_edge_cases() -> None:
    assert concentration_metrics({}).top1_share == 0.0
    with pytest.raises(ValueError):
        concentration_metrics({"bad": float("nan")})

    low_diversity = allocate_weights(
        [aggregate("only", 10.0, "one")],
        policy=aggregation_policy(),
    )
    impossible_cap = allocate_weights(
        [aggregate("only", 10.0, "one")],
        policy=AggregationPolicy(
            required_families=FAMILIES,
            task_schedule=task_schedule(),
            minimum_distinct_strategies=1,
            maximum_weight=0.20,
        ),
    )
    capped = allocate_weights(
        [
            aggregate("star", 100.0, "star"),
            *[aggregate(f"peer-{index}", 1.0, f"peer-{index}") for index in range(5)],
        ],
        policy=aggregation_policy(),
    )
    assert low_diversity.reason == "insufficient_strategy_diversity"
    assert impossible_cap.reason == "insufficient_recipients_for_cap"
    assert capped.planned
    assert dict(capped.strategy_weights)["star"] == pytest.approx(0.20)
    assert math.fsum(dict(capped.strategy_weights).values()) == pytest.approx(1.0)


def test_kendall_tau_validation_and_all_ties() -> None:
    with pytest.raises(ValueError):
        kendall_tau_b({"one": 1.0}, {"one": 1.0})
    assert kendall_tau_b({"a": 1.0, "b": 1.0}, {"a": 1.0, "b": 1.0}) == 1.0
