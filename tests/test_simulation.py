from planrace.simulation import simulate


def test_honest_miner_wins_multiple_epochs() -> None:
    result = simulate(3)
    assert result["winner"] == "honest-indexed"
    assert result["mean_scores"]["gaming-fast-wrong"] == 0.0
    assert len(result["epochs"]) == 3


def test_simulation_rejects_empty_run() -> None:
    try:
        simulate(0)
    except ValueError as error:
        assert "positive" in str(error)
    else:
        raise AssertionError("zero epochs must fail")
