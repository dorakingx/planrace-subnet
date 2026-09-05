"""Deterministic adversarial simulation for the PlanRace v2 mechanism."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import platform
import random
import re
import sqlite3
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, cast

from planrace.scoring_v2 import (
    AggregationPolicy,
    AllocationResult,
    BenchmarkEvidence,
    BenchmarkPolicy,
    EpochObservation,
    InterleavedTrial,
    MinerAggregate,
    ScheduledTask,
    aggregate_network,
    allocate_weights,
    kendall_tau_b,
    score_benchmark,
)

WORKLOAD_FAMILIES: tuple[str, ...] = ("joins", "aggregates", "range", "skew")
Category = Literal["honest", "gaming", "sybil"]


@dataclass(frozen=True, slots=True)
class MinerProfile:
    profile_id: str
    category: Category
    strategy_key: str
    cold_speedup: float
    warm_speedup: float
    setup_fraction: float
    storage_ratio: float
    availability: float = 0.99
    compliance: float = 1.0
    correctness: float = 1.0
    timeout_probability: float = 0.0
    timing_noise: float = 0.04
    family_multipliers: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    behavior_key: str | None = None

    @property
    def strategy_digest(self) -> str:
        return hashlib.sha256(self.strategy_key.encode()).hexdigest()

    @property
    def behavior_digest(self) -> str:
        return hashlib.sha256((self.behavior_key or self.strategy_key).encode()).hexdigest()


MINER_PROFILES: tuple[MinerProfile, ...] = (
    MinerProfile(
        "covering-join",
        "honest",
        "covering-join-v2",
        2.20,
        4.00,
        1.50,
        0.40,
        family_multipliers=(1.30, 0.90, 1.00, 0.90),
    ),
    MinerProfile(
        "partial-index",
        "honest",
        "partial-index-v2",
        1.80,
        2.80,
        0.80,
        0.20,
        family_multipliers=(1.15, 0.95, 1.15, 0.85),
    ),
    MinerProfile(
        "aggregate-advisor",
        "honest",
        "aggregate-advisor-v2",
        2.00,
        2.30,
        0.05,
        0.00,
        family_multipliers=(0.90, 1.35, 0.95, 0.90),
    ),
    MinerProfile("balanced-index", "honest", "balanced-index-v2", 1.70, 2.40, 0.50, 0.15),
    MinerProfile("cold-specialist", "honest", "cold-specialist-v2", 2.60, 1.15, 0.30, 0.10),
    MinerProfile("warm-specialist", "honest", "warm-specialist-v2", 1.15, 4.20, 1.00, 0.45),
    MinerProfile("low-storage", "honest", "low-storage-v2", 1.45, 1.70, 0.15, 0.03),
    MinerProfile("robust-generalist", "honest", "robust-generalist-v2", 1.65, 2.00, 0.35, 0.12),
    MinerProfile(
        "noisy-search", "honest", "noisy-search-v2", 2.10, 3.00, 0.90, 0.25, timing_noise=0.12
    ),
    MinerProfile("conservative", "honest", "conservative-v2", 1.25, 1.35, 0.05, 0.01),
    MinerProfile("high-setup-star", "honest", "high-setup-star-v2", 1.80, 5.00, 3.00, 0.70),
    MinerProfile(
        "timeout-prone",
        "honest",
        "timeout-prone-v2",
        2.50,
        5.50,
        0.70,
        0.30,
        availability=0.94,
        timeout_probability=0.10,
    ),
    MinerProfile(
        "constant-answer", "gaming", "constant-answer-v2", 100.0, 100.0, 0.0, 0.0, correctness=0.0
    ),
    MinerProfile("wrong-fast", "gaming", "wrong-fast-v2", 20.0, 20.0, 0.0, 0.0, correctness=0.0),
    MinerProfile(
        "fixture-memorizer", "gaming", "fixture-memorizer-v2", 8.0, 12.0, 0.0, 0.0, correctness=0.0
    ),
    MinerProfile(
        "malformed-bundle", "gaming", "malformed-bundle-v2", 5.0, 5.0, 0.0, 0.0, compliance=0.0
    ),
    MinerProfile("sybil-copy-a", "sybil", "shared-copy-v2", 1.65, 2.00, 0.35, 0.12),
    MinerProfile("sybil-copy-b", "sybil", "shared-copy-v2", 1.65, 2.00, 0.35, 0.12),
    MinerProfile(
        "sybil-near-copy-a",
        "sybil",
        "near-copy-asc-v2",
        1.65,
        2.00,
        0.35,
        0.12,
        behavior_key="near-copy-equivalent-plan-v2",
    ),
    MinerProfile(
        "sybil-near-copy-b",
        "sybil",
        "near-copy-desc-v2",
        1.65,
        2.00,
        0.35,
        0.12,
        behavior_key="near-copy-equivalent-plan-v2",
    ),
)


@dataclass(frozen=True, slots=True)
class ValidatorScenario:
    scenario_id: str
    hardware_scale: float = 1.0
    order_bias: float = 0.0
    outlier_probability: float = 0.0
    candidate_bias_multipliers: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    false_accept_claim: bool = False
    all_fail: bool = False


VALIDATOR_SCENARIOS: tuple[ValidatorScenario, ...] = (
    ValidatorScenario("honest"),
    ValidatorScenario("fast-worker", hardware_scale=0.55),
    ValidatorScenario("slow-worker", hardware_scale=2.40),
    ValidatorScenario("order-bias", order_bias=0.16),
    ValidatorScenario("timing-outliers", outlier_probability=0.08),
    ValidatorScenario(
        "candidate-measurement-bias",
        candidate_bias_multipliers=(0.60, 1.55, 0.75, 1.45),
    ),
    ValidatorScenario("false-accept-claim", false_accept_claim=True),
    ValidatorScenario("all-fail", all_fail=True),
)


@dataclass(frozen=True, slots=True)
class SimulationConfig:
    replications: int = 512
    epochs: int = 24
    trials_per_task: int = 10
    root_seed: int = 20_260_901

    def __post_init__(self) -> None:
        if self.replications < 1 or self.epochs < 1 or self.trials_per_task < 2:
            raise ValueError("replications, epochs, and trials_per_task must be positive")


DEFAULT_SIMULATION_CONFIG = SimulationConfig()


@dataclass(frozen=True, slots=True)
class StrategyEpochEvaluation:
    """One validator-owned evaluation cached by canonical strategy digest."""

    available: bool
    compliant: bool
    measured_correct: bool
    miner_claimed_correct: bool
    reward: float
    invalid: bool
    false_acceptance: bool
    injected_false_claim: bool
    accepted_injected_false_claim: bool
    trial_pairs: int


def _noise(rng: random.Random, sigma: float) -> float:
    return math.exp(rng.gauss(0.0, sigma))


def _expected_profile_score(profile: MinerProfile) -> float:
    if profile.correctness == 0.0 or profile.compliance == 0.0:
        return 0.0
    horizon_weights = (0.15, 0.25, 0.30, 0.30)
    horizons = (1, 10, 100, 1_000)
    family_scores = []
    for family_index in range(len(WORKLOAD_FAMILIES)):
        multiplier = profile.family_multipliers[family_index]
        cold_speedup = max(0.05, profile.cold_speedup * multiplier)
        warm_speedup = max(0.05, profile.warm_speedup * multiplier)
        savings = 0.0
        for horizon, weight in zip(horizons, horizon_weights, strict=True):
            baseline = 80.0 + (horizon - 1) * 24.0
            candidate = (
                80.0 * profile.setup_fraction
                + 80.0 / cold_speedup
                + (horizon - 1) * 24.0 / warm_speedup
            ) * (1.0 + profile.storage_ratio * 0.10)
            savings += weight * max(0.0, 1.0 - candidate / baseline)
        family_scores.append(savings)
    return (
        100.0
        * sum(family_scores)
        / len(family_scores)
        * profile.availability
        * profile.compliance
        * profile.correctness
    )


def _make_trials(
    *,
    rng: random.Random,
    profile: MinerProfile,
    scenario: ValidatorScenario,
    family_index: int,
    worker_id: str,
    trial_count: int,
) -> tuple[InterleavedTrial, ...]:
    base_cold = 80.0 * scenario.hardware_scale
    base_warm = 24.0 * scenario.hardware_scale
    family_multiplier = profile.family_multipliers[family_index]
    candidate_bias = scenario.candidate_bias_multipliers[family_index]
    candidate_cold = (
        base_cold / max(0.05, profile.cold_speedup * family_multiplier) * candidate_bias
    )
    candidate_warm = (
        base_warm / max(0.05, profile.warm_speedup * family_multiplier) * candidate_bias
    )
    start_with_baseline = rng.random() < 0.5
    trials = []
    for trial_index in range(trial_count):
        baseline_first = (trial_index % 2 == 0) == start_with_baseline
        order: Literal["baseline-first", "candidate-first"] = (
            "baseline-first" if baseline_first else "candidate-first"
        )
        first_multiplier = 1.0 + scenario.order_bias
        second_multiplier = max(0.10, 1.0 - scenario.order_bias)
        baseline_order_multiplier = first_multiplier if baseline_first else second_multiplier
        candidate_order_multiplier = second_multiplier if baseline_first else first_multiplier
        baseline_outlier = 1.0
        candidate_outlier = 1.0
        if rng.random() < scenario.outlier_probability:
            if rng.random() < 0.5:
                baseline_outlier = rng.uniform(4.0, 12.0)
            else:
                candidate_outlier = rng.uniform(4.0, 12.0)
        trials.append(
            InterleavedTrial(
                worker_id=worker_id,
                order=order,
                baseline_cold_ms=(
                    base_cold * baseline_order_multiplier * baseline_outlier * _noise(rng, 0.025)
                ),
                candidate_cold_ms=(
                    candidate_cold
                    * candidate_order_multiplier
                    * candidate_outlier
                    * _noise(rng, profile.timing_noise)
                ),
                baseline_warm_ms=(
                    base_warm * baseline_order_multiplier * baseline_outlier * _noise(rng, 0.025)
                ),
                candidate_warm_ms=(
                    candidate_warm
                    * candidate_order_multiplier
                    * candidate_outlier
                    * _noise(rng, profile.timing_noise)
                ),
                candidate_timed_out=rng.random() < profile.timeout_probability,
            )
        )
    return tuple(trials)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _total_variation(first: dict[str, float], second: dict[str, float]) -> float:
    keys = set(first) | set(second)
    return 0.5 * math.fsum(abs(first.get(key, 0.0) - second.get(key, 0.0)) for key in keys)


def _profile_evaluation_signature(profile: MinerProfile) -> tuple[object, ...]:
    """Fields that must agree when two identities claim one strategy digest."""

    return (
        profile.cold_speedup,
        profile.warm_speedup,
        profile.setup_fraction,
        profile.storage_ratio,
        profile.availability,
        profile.compliance,
        profile.correctness,
        profile.timeout_probability,
        profile.timing_noise,
        profile.family_multipliers,
        profile.behavior_key,
    )


def _simulation_task_schedule(epochs: int) -> tuple[ScheduledTask, ...]:
    tasks: list[ScheduledTask] = []
    for epoch in range(epochs):
        family = WORKLOAD_FAMILIES[epoch % len(WORKLOAD_FAMILIES)]
        task_payload = f"planrace-mechanism-v2:epoch:{epoch}:family:{family}".encode()
        task_hash = hashlib.sha256(task_payload).hexdigest()
        tasks.append(
            ScheduledTask(
                epoch=epoch,
                family=family,
                task_id=task_hash[:32],
                task_commitment="sha256:" + task_hash,
            )
        )
    return tuple(tasks)


def _evidence_digest(
    task: ScheduledTask,
    strategy_digest: str,
    evaluation: StrategyEpochEvaluation,
) -> str:
    validator_owned = {
        "task_commitment": task.task_commitment,
        "strategy_digest": strategy_digest,
        "available": evaluation.available,
        "compliant": evaluation.compliant,
        "measured_correct": evaluation.measured_correct,
        "reward": evaluation.reward,
        "trial_pairs": evaluation.trial_pairs,
    }
    encoded = json.dumps(
        validator_owned,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _evaluate_strategy_epoch(
    *,
    rng: random.Random,
    profile: MinerProfile,
    scenario: ValidatorScenario,
    family_index: int,
    database_bytes: int,
    worker_id: str,
    trial_count: int,
    benchmark_policy: BenchmarkPolicy,
) -> StrategyEpochEvaluation:
    available = not scenario.all_fail and rng.random() < profile.availability
    compliant = available and rng.random() < profile.compliance
    measured_correct = compliant and rng.random() < profile.correctness
    miner_claimed_correct = available and (scenario.false_accept_claim or measured_correct)
    reward = 0.0
    false_acceptance = False
    trial_pairs = 0
    if available:
        setup_ms = 80.0 * scenario.hardware_scale * profile.setup_fraction
        trials = _make_trials(
            rng=rng,
            profile=profile,
            scenario=scenario,
            family_index=family_index,
            worker_id=worker_id,
            trial_count=trial_count,
        )
        trial_pairs = len(trials)
        evidence = BenchmarkEvidence(
            # This is validator-measured exact-result correctness. The miner's
            # claim above is deliberately never supplied to the scorer.
            correct=measured_correct,
            compliant=compliant,
            setup_ms=setup_ms,
            artifact_storage_bytes=int(database_bytes * profile.storage_ratio),
            database_bytes=database_bytes,
            trials=trials,
        )
        benchmark_score = score_benchmark(evidence, policy=benchmark_policy)
        reward = benchmark_score.reward
        false_acceptance = (not measured_correct or not compliant) and benchmark_score.eligible

    invalid = available and (not measured_correct or not compliant)
    injected_false_claim = (
        scenario.false_accept_claim and miner_claimed_correct and not measured_correct
    )
    return StrategyEpochEvaluation(
        available=available,
        compliant=compliant,
        measured_correct=measured_correct,
        miner_claimed_correct=miner_claimed_correct,
        reward=reward,
        invalid=invalid,
        false_acceptance=false_acceptance,
        injected_false_claim=injected_false_claim,
        accepted_injected_false_claim=injected_false_claim and false_acceptance,
        trial_pairs=trial_pairs,
    )


def _duplicate_strategy_gains(
    observations: list[EpochObservation],
    miner_ids: tuple[str, ...],
    aggregates: list[MinerAggregate],
    *,
    allocation: AllocationResult,
    policy: AggregationPolicy,
) -> tuple[float, ...]:
    """Compare each duplicated strategy's mass with a single-identity control."""

    if not allocation.planned:
        return ()
    profile_groups: dict[str, list[str]] = defaultdict(list)
    for profile in MINER_PROFILES:
        profile_groups[profile.behavior_digest].append(profile.profile_id)
    duplicated = {
        digest: sorted(members) for digest, members in profile_groups.items() if len(members) > 1
    }
    aggregate_by_id = {aggregate.miner_id: aggregate for aggregate in aggregates}
    observed_strategy_weights = dict(allocation.strategy_weights)
    gains: list[float] = []
    for _task_strategy_digest, members in sorted(duplicated.items()):
        representative = members[0]
        removed_ids = set(members[1:])
        control_miner_ids = tuple(miner_id for miner_id in miner_ids if miner_id not in removed_ids)
        control_observations = [
            observation for observation in observations if observation.miner_id not in removed_ids
        ]
        control_aggregates = list(
            aggregate_network(
                control_observations,
                miner_ids=control_miner_ids,
                policy=policy,
            )
        )
        control = allocate_weights(control_aggregates, policy=policy)
        if not control.planned:
            continue
        portfolio_digest = aggregate_by_id[representative].behavior_digest
        gain = observed_strategy_weights.get(portfolio_digest, 0.0) - dict(
            control.strategy_weights
        ).get(portfolio_digest, 0.0)
        gains.append(0.0 if gain <= 1e-12 else gain)
    return tuple(gains)


def run_mechanism_simulation(
    config: SimulationConfig = DEFAULT_SIMULATION_CONFIG,
) -> dict[str, Any]:
    """Run deterministic multi-epoch simulations across miners and attacks."""

    benchmark_policy = BenchmarkPolicy(
        minimum_trials=config.trials_per_task,
        winsor_fraction=0.10,
        maximum_timeout_rate=0.20,
    )
    task_schedule = _simulation_task_schedule(config.epochs)
    aggregation_policy = AggregationPolicy(
        required_families=WORKLOAD_FAMILIES,
        task_schedule=task_schedule,
        minimum_tasks=max(12, min(config.epochs, 24)),
        maximum_weight=0.25,
        minimum_distinct_strategies=5,
    )
    expected_scores = {
        profile.profile_id: _expected_profile_score(profile) for profile in MINER_PROFILES
    }
    profile_by_id = {profile.profile_id: profile for profile in MINER_PROFILES}
    miner_ids = tuple(profile.profile_id for profile in MINER_PROFILES)
    canonical_profiles: dict[str, MinerProfile] = {}
    for profile in MINER_PROFILES:
        representative = canonical_profiles.setdefault(profile.strategy_digest, profile)
        if _profile_evaluation_signature(profile) != _profile_evaluation_signature(representative):
            raise ValueError(
                "profiles sharing a strategy digest must share evaluation characteristics"
            )
    rows: list[dict[str, Any]] = []
    profile_reward_values: dict[str, list[float]] = defaultdict(list)
    profile_weight_values: dict[str, list[float]] = defaultdict(list)
    profile_failures: dict[str, Counter[str]] = defaultdict(Counter)
    total_invalid_attempts = 0
    total_false_acceptances = 0
    total_strategy_evaluations = 0
    total_duplicate_cache_hits = 0
    total_trial_pairs = 0
    total_injected_false_claims = 0
    total_accepted_injected_false_claims = 0

    for replication in range(config.replications):
        scenario = VALIDATOR_SCENARIOS[replication % len(VALIDATOR_SCENARIOS)]
        cohort = replication // len(VALIDATOR_SCENARIOS)
        # The disclosed deterministic PRNG is evidence replay machinery, not a
        # source for protocol secrets or production task generation. Conditions
        # in one cohort share random draws so cross-validator comparisons are
        # paired rather than comparisons of unrelated samples.
        rng = random.Random(config.root_seed + cohort * 1_000_003)  # noqa: S311
        observations: dict[str, list[EpochObservation]] = defaultdict(list)
        replication_invalid_attempts = 0
        replication_false_acceptances = 0
        replication_strategy_evaluations = 0
        replication_duplicate_cache_hits = 0
        replication_trial_pairs = 0
        replication_injected_false_claims = 0
        replication_accepted_injected_false_claims = 0

        for epoch in range(config.epochs):
            scheduled_task = task_schedule[epoch]
            family = scheduled_task.family
            family_index = WORKLOAD_FAMILIES.index(family)
            database_bytes = 16_000_000 + family_index * 2_000_000
            evaluation_cache: dict[str, StrategyEpochEvaluation] = {}
            for profile in MINER_PROFILES:
                evaluation = evaluation_cache.get(profile.strategy_digest)
                if evaluation is None:
                    evaluation = _evaluate_strategy_epoch(
                        rng=rng,
                        profile=profile,
                        scenario=scenario,
                        family_index=family_index,
                        database_bytes=database_bytes,
                        worker_id=f"cohort-{cohort}-scenario-{scenario.scenario_id}-epoch-{epoch}",
                        trial_count=config.trials_per_task,
                        benchmark_policy=benchmark_policy,
                    )
                    evaluation_cache[profile.strategy_digest] = evaluation
                    replication_strategy_evaluations += 1
                    replication_trial_pairs += evaluation.trial_pairs
                    replication_invalid_attempts += int(evaluation.invalid)
                    replication_false_acceptances += int(evaluation.false_acceptance)
                    replication_injected_false_claims += int(evaluation.injected_false_claim)
                    replication_accepted_injected_false_claims += int(
                        evaluation.accepted_injected_false_claim
                    )
                else:
                    replication_duplicate_cache_hits += 1
                observations[profile.profile_id].append(
                    EpochObservation(
                        miner_id=profile.profile_id,
                        epoch=epoch,
                        family=family,
                        reward=evaluation.reward,
                        available=evaluation.available,
                        correct=evaluation.measured_correct,
                        compliant=evaluation.compliant,
                        task_id=scheduled_task.task_id,
                        task_commitment=scheduled_task.task_commitment,
                        evidence_digest=_evidence_digest(
                            scheduled_task,
                            profile.strategy_digest,
                            evaluation,
                        ),
                        strategy_digest=profile.strategy_digest,
                        behavior_digest=profile.behavior_digest,
                    )
                )

        network_observations = [
            observation
            for profile in MINER_PROFILES
            for observation in observations[profile.profile_id]
        ]
        aggregates = list(
            aggregate_network(
                network_observations,
                miner_ids=miner_ids,
                policy=aggregation_policy,
            )
        )
        allocation = allocate_weights(aggregates, policy=aggregation_policy)
        duplicate_gains = _duplicate_strategy_gains(
            network_observations,
            miner_ids,
            aggregates,
            allocation=allocation,
            policy=aggregation_policy,
        )
        aggregate_scores = {aggregate.miner_id: aggregate.reward for aggregate in aggregates}
        weights = dict(allocation.weights)
        for aggregate in aggregates:
            profile_reward_values[aggregate.miner_id].append(aggregate.reward)
            profile_weight_values[aggregate.miner_id].append(weights.get(aggregate.miner_id, 0.0))
            if aggregate.failure_code:
                profile_failures[aggregate.miner_id][aggregate.failure_code] += 1

        rank_stability = (
            kendall_tau_b(expected_scores, aggregate_scores) if allocation.planned else None
        )
        category_weights = {
            category: math.fsum(
                weights.get(profile.profile_id, 0.0)
                for profile in MINER_PROFILES
                if profile.category == category
            )
            for category in ("honest", "gaming", "sybil")
        }
        winner = (
            min(weights, key=lambda miner_id: (-weights[miner_id], miner_id)) if weights else None
        )
        winner_category = profile_by_id[winner].category if winner else None
        safe_no_update = scenario.all_fail and not allocation.planned
        rows.append(
            {
                "replication": replication,
                "cohort": cohort,
                "scenario": scenario.scenario_id,
                "planned": allocation.planned,
                "reason": allocation.reason,
                "winner": winner,
                "winner_category": winner_category,
                "false_acceptances": replication_false_acceptances,
                "invalid_attempts": replication_invalid_attempts,
                "gini": allocation.concentration.gini,
                "hhi": allocation.concentration.hhi,
                "top1_share": allocation.concentration.top1_share,
                "effective_miners": allocation.concentration.effective_miners,
                "rank_stability_tau_b": rank_stability,
                # Populated from paired validator outputs after every cohort is
                # complete. No-update rows remain explicitly null.
                "validator_disagreement_tv": None,
                "hardware_pair_tau_b": None,
                "honest_weight": category_weights["honest"],
                "gaming_weight": category_weights["gaming"],
                "sybil_weight": category_weights["sybil"],
                "safe_no_update": safe_no_update,
                "strategy_evaluations": replication_strategy_evaluations,
                "duplicate_cache_hits": replication_duplicate_cache_hits,
                "trial_pairs": replication_trial_pairs,
                "injected_false_claims": replication_injected_false_claims,
                "accepted_injected_false_claims": (replication_accepted_injected_false_claims),
                "sybil_strategy_allocation_gain": (
                    _mean(list(duplicate_gains)) if duplicate_gains else None
                ),
                "weights": weights,
                "strategy_weights": dict(allocation.strategy_weights),
                "aggregate_rewards": aggregate_scores,
            }
        )
        total_invalid_attempts += replication_invalid_attempts
        total_false_acceptances += replication_false_acceptances
        total_strategy_evaluations += replication_strategy_evaluations
        total_duplicate_cache_hits += replication_duplicate_cache_hits
        total_trial_pairs += replication_trial_pairs
        total_injected_false_claims += replication_injected_false_claims
        total_accepted_injected_false_claims += replication_accepted_injected_false_claims

    cohort_rows: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        cohort_rows[int(row["cohort"])].append(row)
    validator_pair_disagreements: list[float] = []
    hardware_pair_taus: list[float] = []
    row_disagreements: dict[int, list[float]] = defaultdict(list)
    for values in cohort_rows.values():
        planned = [
            row
            for row in values
            if row["scenario"] != "all-fail"
            and bool(row["planned"])
            and bool(row["strategy_weights"])
        ]
        for index, first in enumerate(planned):
            for second in planned[index + 1 :]:
                disagreement = _total_variation(
                    dict(first["strategy_weights"]),
                    dict(second["strategy_weights"]),
                )
                validator_pair_disagreements.append(disagreement)
                row_disagreements[int(first["replication"])].append(disagreement)
                row_disagreements[int(second["replication"])].append(disagreement)
        for row in planned:
            disagreements = row_disagreements[int(row["replication"])]
            row["validator_disagreement_tv"] = _mean(disagreements) if disagreements else None

        by_scenario = {str(row["scenario"]): row for row in values}
        fast = by_scenario.get("fast-worker")
        slow = by_scenario.get("slow-worker")
        if fast and slow and bool(fast["planned"]) and bool(slow["planned"]):
            paired_tau = kendall_tau_b(
                dict(fast["aggregate_rewards"]),
                dict(slow["aggregate_rewards"]),
            )
            hardware_pair_taus.append(paired_tau)
            fast["hardware_pair_tau_b"] = paired_tau
            slow["hardware_pair_tau_b"] = paired_tau

    active_rows = [row for row in rows if row["scenario"] != "all-fail"]
    all_fail_rows = [row for row in rows if row["scenario"] == "all-fail"]
    active_rank_values = [
        float(row["rank_stability_tau_b"])
        for row in active_rows
        if row["rank_stability_tau_b"] is not None
    ]
    sybil_gain_values = [
        float(row["sybil_strategy_allocation_gain"])
        for row in active_rows
        if row["sybil_strategy_allocation_gain"] is not None
    ]
    scenario_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        scenario_rows[str(row["scenario"])].append(row)
    scenario_summary = {}
    for scenario_id, values in sorted(scenario_rows.items()):
        tau_values = [
            float(row["rank_stability_tau_b"])
            for row in values
            if row["rank_stability_tau_b"] is not None
        ]
        disagreement_values = [
            float(row["validator_disagreement_tv"])
            for row in values
            if row["validator_disagreement_tv"] is not None
        ]
        scenario_summary[scenario_id] = {
            "replications": len(values),
            "planned_rate": _mean([float(row["planned"]) for row in values]),
            "false_acceptance_rate": (
                sum(int(row["false_acceptances"]) for row in values)
                / max(1, sum(int(row["invalid_attempts"]) for row in values))
            ),
            "mean_tau_b": _mean(tau_values) if tau_values else None,
            "mean_cross_validator_disagreement_tv": (
                _mean(disagreement_values) if disagreement_values else None
            ),
            "mean_top1_share": _mean([float(row["top1_share"]) for row in values]),
            "mean_gaming_weight": _mean([float(row["gaming_weight"]) for row in values]),
            "injected_false_claims": sum(int(row["injected_false_claims"]) for row in values),
            "accepted_injected_false_claims": sum(
                int(row["accepted_injected_false_claims"]) for row in values
            ),
        }
    profile_summary = {
        profile.profile_id: {
            "category": profile.category,
            "strategy_digest": profile.strategy_digest,
            "mean_aggregate_reward": _mean(profile_reward_values[profile.profile_id]),
            "mean_weight": _mean(profile_weight_values[profile.profile_id]),
            "gate_failures": dict(sorted(profile_failures[profile.profile_id].items())),
        }
        for profile in MINER_PROFILES
    }
    summary = {
        "replications": config.replications,
        "epochs_per_replication": config.epochs,
        "miner_profile_count": len(MINER_PROFILES),
        "validator_scenario_count": len(VALIDATOR_SCENARIOS),
        "invalid_attempts": total_invalid_attempts,
        "false_acceptances": total_false_acceptances,
        "false_acceptance_rate": total_false_acceptances / max(1, total_invalid_attempts),
        "honest_winner_rate": _mean(
            [float(row["winner_category"] == "honest") for row in active_rows]
        ),
        "all_fail_safe_no_update_rate": _mean(
            [float(row["safe_no_update"]) for row in all_fail_rows]
        ),
        "strategy_evaluations": total_strategy_evaluations,
        "duplicate_evaluation_cache_hits": total_duplicate_cache_hits,
        "measured_trial_pairs": total_trial_pairs,
        "injected_false_claims": total_injected_false_claims,
        "accepted_injected_false_claims": total_accepted_injected_false_claims,
        "mean_gini": _mean([float(row["gini"]) for row in active_rows]),
        "mean_hhi": _mean([float(row["hhi"]) for row in active_rows]),
        "mean_top1_share": _mean([float(row["top1_share"]) for row in active_rows]),
        "max_top1_share": max((float(row["top1_share"]) for row in active_rows), default=0.0),
        "mean_rank_stability_tau_b": (_mean(active_rank_values) if active_rank_values else None),
        "hardware_rank_stability_tau_b": (
            _mean(hardware_pair_taus) if hardware_pair_taus else None
        ),
        "hardware_rank_pair_count": len(hardware_pair_taus),
        "mean_validator_disagreement_tv": (
            _mean(validator_pair_disagreements) if validator_pair_disagreements else None
        ),
        "validator_disagreement_pair_count": len(validator_pair_disagreements),
        "mean_honest_weight": _mean([float(row["honest_weight"]) for row in active_rows]),
        "mean_gaming_weight": _mean([float(row["gaming_weight"]) for row in active_rows]),
        "mean_sybil_weight": _mean([float(row["sybil_weight"]) for row in active_rows]),
        "sybil_strategy_allocation_gain": (max(sybil_gain_values) if sybil_gain_values else None),
        "mean_sybil_strategy_allocation_gain": (
            _mean(sybil_gain_values) if sybil_gain_values else None
        ),
        "max_abs_sybil_strategy_allocation_gain": (
            max((abs(value) for value in sybil_gain_values), default=0.0)
            if sybil_gain_values
            else None
        ),
        "sybil_allocation_comparison_count": len(sybil_gain_values),
        "scenario_metrics": scenario_summary,
        "profile_metrics": profile_summary,
    }
    return {
        "schema_version": "planrace-mechanism-simulation/2",
        "config": asdict(config),
        "benchmark_policy": asdict(benchmark_policy),
        "aggregation_policy": asdict(aggregation_policy),
        "profiles": [
            asdict(profile) | {"strategy_digest": profile.strategy_digest}
            for profile in MINER_PROFILES
        ],
        "validator_scenarios": [asdict(scenario) for scenario in VALIDATOR_SCENARIOS],
        "summary": summary,
        "replications": rows,
    }


def _canonical_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commit(repo_root: Path) -> str:
    result = subprocess.run(
        ["/usr/bin/git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _git_dirty(repo_root: Path) -> bool:
    result = subprocess.run(
        ["/usr/bin/git", "status", "--porcelain"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def write_evidence_bundle(report: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    """Write stable JSON/CSV artifacts and a hash manifest."""

    output_dir.mkdir(parents=True, exist_ok=True)
    repo_root = Path(__file__).resolve().parents[1]
    simulation_path = output_dir / "simulation.json"
    summary_path = output_dir / "summary.json"
    replications_path = output_dir / "replications.csv"
    profiles_path = output_dir / "profile-rewards.csv"
    publication_json_path = output_dir / "MECHANISM_SIMULATION.json"
    publication_csv_path = output_dir / "MECHANISM_SIMULATION.csv"
    simulation_payload = _canonical_json(report)
    simulation_path.write_text(simulation_payload, encoding="utf-8")
    publication_json_path.write_text(simulation_payload, encoding="utf-8")
    summary_path.write_text(_canonical_json(report["summary"]), encoding="utf-8")

    replication_fields = (
        "replication",
        "cohort",
        "scenario",
        "planned",
        "reason",
        "winner",
        "winner_category",
        "false_acceptances",
        "invalid_attempts",
        "gini",
        "hhi",
        "top1_share",
        "effective_miners",
        "rank_stability_tau_b",
        "validator_disagreement_tv",
        "hardware_pair_tau_b",
        "honest_weight",
        "gaming_weight",
        "sybil_weight",
        "safe_no_update",
        "strategy_evaluations",
        "duplicate_cache_hits",
        "trial_pairs",
        "injected_false_claims",
        "accepted_injected_false_claims",
        "sybil_strategy_allocation_gain",
    )
    replication_buffer = io.StringIO(newline="")
    replication_writer = csv.DictWriter(
        replication_buffer, fieldnames=replication_fields, lineterminator="\n"
    )
    replication_writer.writeheader()
    for row in report["replications"]:
        replication_writer.writerow({field: row[field] for field in replication_fields})
    replication_payload = replication_buffer.getvalue()
    replications_path.write_text(replication_payload, encoding="utf-8")
    publication_csv_path.write_text(replication_payload, encoding="utf-8")

    profile_buffer = io.StringIO(newline="")
    profile_fields = (
        "profile_id",
        "category",
        "strategy_digest",
        "mean_aggregate_reward",
        "mean_weight",
        "gate_failures_json",
    )
    profile_writer = csv.DictWriter(profile_buffer, fieldnames=profile_fields, lineterminator="\n")
    profile_writer.writeheader()
    for profile_id, metrics in report["summary"]["profile_metrics"].items():
        profile_writer.writerow(
            {
                "profile_id": profile_id,
                "category": metrics["category"],
                "strategy_digest": metrics["strategy_digest"],
                "mean_aggregate_reward": metrics["mean_aggregate_reward"],
                "mean_weight": metrics["mean_weight"],
                "gate_failures_json": json.dumps(metrics["gate_failures"], sort_keys=True),
            }
        )
    profiles_path.write_text(profile_buffer.getvalue(), encoding="utf-8")

    source_paths = (
        repo_root / "planrace" / "scoring_v2.py",
        repo_root / "planrace" / "mechanism_simulation.py",
        repo_root / "scripts" / "run_mechanism_v2.py",
    )
    lock_path = repo_root / "uv.lock"
    config_payload = _canonical_json(report["config"]).encode()
    seed = int(report["config"]["root_seed"])
    manifest = {
        "schema_version": "planrace-mechanism-evidence/2",
        "reproduction_command": "uv run python scripts/run_mechanism_v2.py",
        "root_seed": seed,
        "seed_commitment": hashlib.sha256(f"planrace-mechanism-v2:{seed}".encode()).hexdigest(),
        "config_sha256": hashlib.sha256(config_payload).hexdigest(),
        "source_git_base_commit": _git_commit(repo_root),
        "source_tree_dirty": _git_dirty(repo_root),
        "source_files": {str(path.relative_to(repo_root)): _sha256(path) for path in source_paths},
        "dependency_lock": {"path": "uv.lock", "sha256": _sha256(lock_path)},
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "sqlite": sqlite3.sqlite_version,
            "byteorder": sys.byteorder,
        },
        "artifacts": {
            path.name: _sha256(path)
            for path in (
                simulation_path,
                summary_path,
                replications_path,
                profiles_path,
                publication_json_path,
                publication_csv_path,
            )
        },
    }
    (output_dir / "manifest.json").write_text(_canonical_json(manifest), encoding="utf-8")
    return manifest


def verify_evidence_bundle(
    output_dir: Path,
    *,
    repo_root: Path | None = None,
    require_clean_source: bool = False,
) -> dict[str, Any]:
    """Verify every mechanism artifact, source, seed, and configuration hash."""

    root = repo_root or Path(__file__).resolve().parents[1]
    manifest = cast(
        dict[str, Any],
        json.loads((output_dir / "manifest.json").read_text(encoding="utf-8")),
    )
    if manifest.get("schema_version") != "planrace-mechanism-evidence/2":
        raise ValueError("unsupported mechanism evidence schema")
    if require_clean_source and manifest.get("source_tree_dirty") is not False:
        raise ValueError("mechanism evidence was generated from a dirty source tree")
    if require_clean_source and _git_dirty(root):
        raise ValueError("current mechanism source tree is dirty")
    source_commit = str(manifest.get("source_git_base_commit", ""))
    if re.fullmatch(r"[0-9a-f]{40}", source_commit) is None:
        raise ValueError("invalid mechanism source commit")
    commit_check = subprocess.run(  # noqa: S603 - fixed git binary and validated full SHA
        ["/usr/bin/git", "cat-file", "-e", f"{source_commit}^{{commit}}"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if commit_check.returncode != 0:
        raise ValueError("mechanism source commit is not present in repository history")
    seed = int(manifest["root_seed"])
    expected_seed = hashlib.sha256(f"planrace-mechanism-v2:{seed}".encode()).hexdigest()
    if manifest.get("seed_commitment") != expected_seed:
        raise ValueError("mechanism seed commitment mismatch")

    simulation = cast(
        dict[str, Any],
        json.loads((output_dir / "simulation.json").read_text(encoding="utf-8")),
    )
    config_digest = hashlib.sha256(_canonical_json(simulation["config"]).encode()).hexdigest()
    if manifest.get("config_sha256") != config_digest:
        raise ValueError("mechanism configuration digest mismatch")
    for filename, expected in manifest["artifacts"].items():
        path = (output_dir / filename).resolve()
        if (
            not path.is_relative_to(output_dir.resolve())
            or not path.is_file()
            or _sha256(path) != expected
        ):
            raise ValueError(f"mechanism artifact digest mismatch: {filename}")
    for filename, expected in manifest["source_files"].items():
        path = root / filename
        if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"unsafe or missing mechanism source path: {filename}")
        if _sha256(path) != expected:
            raise ValueError(f"mechanism source digest mismatch: {filename}")
    lock = manifest["dependency_lock"]
    lock_path = (root / lock["path"]).resolve()
    if (
        not lock_path.is_relative_to(root.resolve())
        or not lock_path.is_file()
        or _sha256(lock_path) != lock["sha256"]
    ):
        raise ValueError("mechanism dependency lock digest mismatch")
    if (output_dir / "MECHANISM_SIMULATION.json").read_bytes() != (
        output_dir / "simulation.json"
    ).read_bytes():
        raise ValueError("mechanism JSON publication alias mismatch")
    if (output_dir / "MECHANISM_SIMULATION.csv").read_bytes() != (
        output_dir / "replications.csv"
    ).read_bytes():
        raise ValueError("mechanism CSV publication alias mismatch")
    config = SimulationConfig(**simulation["config"])
    regenerated = run_mechanism_simulation(config)
    with tempfile.TemporaryDirectory(prefix="planrace-mechanism-verify-") as directory:
        regenerated_root = Path(directory)
        regenerated_manifest = write_evidence_bundle(regenerated, regenerated_root)
        for filename in regenerated_manifest["artifacts"]:
            if (regenerated_root / filename).read_bytes() != (output_dir / filename).read_bytes():
                raise ValueError(
                    f"mechanism artifact does not reproduce from seed and config: {filename}"
                )
    return manifest
