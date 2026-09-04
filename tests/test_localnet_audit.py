from scripts.audit_localnet_v2 import _readback_matches


def test_u16_weights_match_normalized_chain_readback() -> None:
    submitted = [[4, 32_767], [5, 65_535], [12, 32_767]]
    total = sum(weight for _, weight in submitted)
    readback = {"0": {str(uid): weight / total for uid, weight in submitted}}
    assert _readback_matches(readback, submitted)


def test_chain_readback_rejects_changed_uid_or_weight() -> None:
    submitted = [[4, 32_767], [5, 65_535]]
    assert not _readback_matches({"0": {"4": 0.5, "6": 0.5}}, submitted)
    assert not _readback_matches({"0": {"4": 0.6, "5": 0.4}}, submitted)
