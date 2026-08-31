import math
import random

from planrace.models import SeedReveal
from planrace.taskgen import generate_workload, verify_reveal
from planrace.weights import plan_weights


def test_weight_normalization_properties_across_random_score_vectors() -> None:
    rng = random.Random(20260831)  # noqa: S311 - deterministic property sampling
    for _ in range(500):
        scores = {uid: rng.random() * 100 if rng.random() > 0.2 else 0.0 for uid in range(20)}
        plan = plan_weights(scores)
        positive = {uid for uid, score in scores.items() if score > 0.0}
        assert plan.planned == bool(positive)
        if plan.planned:
            assert set(plan.uids) == positive
            assert all(weight > 0.0 for weight in plan.weights)
            assert math.isclose(math.fsum(plan.weights), 1.0, abs_tol=1e-12)


def test_any_single_bit_seed_change_breaks_reveal_property() -> None:
    for epoch in range(64):
        workload = generate_workload(epoch)
        assert verify_reveal(workload.task, workload.reveal)
        tampered = SeedReveal(
            task_id=workload.reveal.task_id,
            seed=workload.reveal.seed ^ (1 << (epoch % 32)),
            salt=workload.reveal.salt,
        )
        assert not verify_reveal(workload.task, tampered)
