import pytest

from planrace.weights import WeightPlan, plan_weights, submit_weight_plan


def test_scores_normalize_in_uid_order_and_drop_zero() -> None:
    plan = plan_weights({9: 3.0, 2: 1.0, 7: 0.0})
    assert plan.planned
    assert plan.uids == (2, 9)
    assert plan.weights == (0.25, 0.75)


def test_no_positive_scores_fail_closed() -> None:
    assert not plan_weights({1: 0.0}).planned


@pytest.mark.parametrize("scores", [{-1: 1.0}, {1: -1.0}, {1: float("nan")}])
def test_invalid_scores_fail(scores: dict[int, float]) -> None:
    with pytest.raises(ValueError):
        plan_weights(scores)


def test_dry_run_never_calls_setter_and_mainnet_always_fails() -> None:
    calls = []
    plan = WeightPlan(True, None, (1,), (1.0,))

    def setter(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append((args, kwargs))

    assert (
        submit_weight_plan(
            plan,
            network="test",
            netuid=2,
            wallet_name="validator",
            hotkey_name="default",
            dry_run=True,
            setter=setter,
        )
        is None
    )
    assert not calls
    with pytest.raises(ValueError, match="mainnet"):
        submit_weight_plan(
            plan,
            network="finney",
            netuid=2,
            wallet_name="validator",
            hotkey_name="default",
            setter=setter,
        )


def test_explicit_local_submission_uses_v11_shape() -> None:
    calls = []
    plan = WeightPlan(True, None, (1, 3), (0.4, 0.6))

    def setter(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append((args, kwargs))
        return "ok"

    result = submit_weight_plan(
        plan,
        network="local",
        netuid=2,
        wallet_name="validator",
        hotkey_name="default",
        dry_run=False,
        setter=setter,
    )
    assert result == "ok"
    assert calls == [
        (
            (2, [0.4, 0.6]),
            {"uids": [1, 3], "wallet": "validator", "hotkey": "default", "network": "local"},
        )
    ]
