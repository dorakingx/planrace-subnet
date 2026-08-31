import pytest
from pydantic import ValidationError

from planrace.models import OptimizationArtifact
from planrace.taskgen import generate_workload, verify_reveal


def test_seed_commitment_round_trip() -> None:
    workload = generate_workload(3)
    assert verify_reveal(workload.task, workload.reveal)


def test_artifact_rejects_extra_fields() -> None:
    task = generate_workload(0).task
    with pytest.raises(ValidationError):
        OptimizationArtifact.model_validate(
            {
                "task_id": task.task_id,
                "miner_id": "bad",
                "strategy": "bad",
                "candidate_sql": task.reference_sql,
                "hidden_seed": 1,
            }
        )
