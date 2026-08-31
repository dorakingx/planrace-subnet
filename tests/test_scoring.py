from planrace.miners import baseline_miner, gaming_miner, indexed_miner
from planrace.models import OptimizationArtifact
from planrace.scoring import evaluate_artifact
from planrace.taskgen import generate_workload


def test_wrong_fast_query_gets_zero() -> None:
    workload = generate_workload(0)
    result = evaluate_artifact(workload, gaming_miner(workload.task))
    assert not result.correct
    assert result.score == 0.0
    assert result.failure_code == "result_mismatch"


def test_correct_artifacts_share_exact_hash() -> None:
    workload = generate_workload(1)
    indexed = evaluate_artifact(workload, indexed_miner(workload.task))
    baseline = evaluate_artifact(workload, baseline_miner(workload.task))
    assert indexed.correct and baseline.correct
    assert indexed.result_hash == indexed.reference_hash
    assert indexed.result_hash == baseline.result_hash


def test_task_mismatch_fails_closed() -> None:
    workload = generate_workload(0)
    artifact = OptimizationArtifact(
        task_id="other-task",
        miner_id="wrong-task",
        strategy="identity-v1",
        candidate_sql=workload.task.reference_sql,
    )
    result = evaluate_artifact(workload, artifact)
    assert result.score == 0.0
    assert result.failure_code == "task_mismatch"
