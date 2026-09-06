import hashlib
import json

import pytest

from planrace.mechanism_simulation import (
    MINER_PROFILES,
    VALIDATOR_SCENARIOS,
    SimulationConfig,
    run_mechanism_simulation,
    verify_evidence_bundle,
    write_evidence_bundle,
)


def small_config() -> SimulationConfig:
    return SimulationConfig(replications=8, epochs=12, trials_per_task=6, root_seed=12345)


def test_adversarial_simulation_is_deterministic_and_fail_closed() -> None:
    first = run_mechanism_simulation(small_config())
    second = run_mechanism_simulation(small_config())
    assert first == second
    assert len(MINER_PROFILES) >= 16
    assert len(VALIDATOR_SCENARIOS) >= 7
    assert first["summary"]["false_acceptance_rate"] == 0.0
    assert first["summary"]["all_fail_safe_no_update_rate"] == 1.0
    assert first["summary"]["max_top1_share"] <= 0.25 + 1e-12
    assert first["summary"]["mean_gaming_weight"] == 0.0
    assert first["summary"]["sybil_strategy_allocation_gain"] == 0.0
    assert first["summary"]["max_abs_sybil_strategy_allocation_gain"] == 0.0
    assert first["summary"]["sybil_allocation_comparison_count"] == 7
    assert first["summary"]["behavior_equivalent_replica_allocation_gain"] >= 0.0
    assert first["summary"]["behavior_equivalent_replica_comparison_count"] == 7
    near_copies = [profile for profile in MINER_PROFILES if "near-copy" in profile.profile_id]
    assert len({profile.strategy_digest for profile in near_copies}) == 2
    assert len({profile.behavior_digest for profile in near_copies}) == 1


def test_duplicate_strategies_are_evaluated_once_and_share_exact_scores() -> None:
    report = run_mechanism_simulation(small_config())
    unique_strategies = len({profile.strategy_digest for profile in MINER_PROFILES})
    summary = report["summary"]
    assert summary["strategy_evaluations"] == 8 * 12 * unique_strategies
    assert summary["duplicate_evaluation_cache_hits"] == 8 * 12 * (
        len(MINER_PROFILES) - unique_strategies
    )
    assert summary["measured_trial_pairs"] > 0
    for row in report["replications"]:
        rewards = row["aggregate_rewards"]
        assert rewards["sybil-copy-a"] == rewards["sybil-copy-b"]


def test_validator_metrics_are_paired_actual_outputs_and_skip_no_update() -> None:
    report = run_mechanism_simulation(small_config())
    summary = report["summary"]
    # Seven active conditions in one cohort produce C(7, 2) actual pairs.
    assert summary["validator_disagreement_pair_count"] == 21
    assert summary["mean_validator_disagreement_tv"] is not None
    assert summary["hardware_rank_pair_count"] == 1
    assert summary["hardware_rank_stability_tau_b"] == pytest.approx(1.0)

    by_scenario = {row["scenario"]: row for row in report["replications"]}
    assert by_scenario["all-fail"]["planned"] is False
    assert by_scenario["all-fail"]["validator_disagreement_tv"] is None
    assert by_scenario["all-fail"]["hardware_pair_tau_b"] is None
    assert by_scenario["all-fail"]["sybil_strategy_allocation_gain"] is None
    assert by_scenario["all-fail"]["behavior_equivalent_replica_allocation_gain"] is None
    assert (
        by_scenario["candidate-measurement-bias"]["aggregate_rewards"]
        != by_scenario["honest"]["aggregate_rewards"]
    )


def test_false_correctness_claim_is_injected_but_not_scored() -> None:
    report = run_mechanism_simulation(small_config())
    by_scenario = {row["scenario"]: row for row in report["replications"]}
    claim = by_scenario["false-accept-claim"]
    honest = by_scenario["honest"]
    assert claim["injected_false_claims"] > 0
    assert claim["accepted_injected_false_claims"] == 0
    # The paired scenario differs only in the ignored miner-owned claim.
    assert claim["aggregate_rewards"] == honest["aggregate_rewards"]
    assert report["summary"]["accepted_injected_false_claims"] == 0


def test_evidence_bundle_hashes_every_output(tmp_path) -> None:  # type: ignore[no-untyped-def]
    report = run_mechanism_simulation(small_config())
    manifest = write_evidence_bundle(report, tmp_path)
    assert manifest["root_seed"] == 12345
    assert len(manifest["seed_commitment"]) == 64
    assert "scripts/run_mechanism_v2.py" in manifest["source_files"]
    for filename, digest in manifest["artifacts"].items():
        assert hashlib.sha256((tmp_path / filename).read_bytes()).hexdigest() == digest
    stored = json.loads((tmp_path / "simulation.json").read_text())
    assert stored["schema_version"] == "planrace-mechanism-simulation/2"
    assert stored["summary"]["exact_strategy_count"] == 19
    assert stored["summary"]["behavior_group_count"] == 18
    assert (tmp_path / "replications.csv").read_text().count("\n") == 9
    assert (tmp_path / "MECHANISM_SIMULATION.json").read_bytes() == (
        tmp_path / "simulation.json"
    ).read_bytes()
    assert (tmp_path / "MECHANISM_SIMULATION.csv").read_bytes() == (
        tmp_path / "replications.csv"
    ).read_bytes()
    verified = verify_evidence_bundle(tmp_path)
    assert verified["config_sha256"] == manifest["config_sha256"]


def test_evidence_bundle_verifier_rejects_tampering(tmp_path) -> None:  # type: ignore[no-untyped-def]
    report = run_mechanism_simulation(small_config())
    write_evidence_bundle(report, tmp_path)
    (tmp_path / "summary.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="artifact digest mismatch"):
        verify_evidence_bundle(tmp_path)
