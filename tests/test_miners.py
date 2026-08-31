from planrace.miners import baseline_miner, gaming_miner, indexed_miner
from planrace.taskgen import generate_workload


def test_reference_profiles_keep_task_identity() -> None:
    task = generate_workload(0).task
    artifacts = [miner(task) for miner in (indexed_miner, baseline_miner, gaming_miner)]
    assert all(artifact.task_id == task.task_id for artifact in artifacts)
    assert len({artifact.miner_id for artifact in artifacts}) == 3
