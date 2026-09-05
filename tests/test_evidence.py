import json
from pathlib import Path

import bittensor as bt
import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from planrace.cli import app
from planrace.evidence import (
    EvidenceManifest,
    EvidenceVerificationError,
    canonical_manifest_bytes,
    sign_manifest,
    summarize_manifest,
    verify_manifest,
    verify_manifest_file,
)

ALICE = bt.sp_core.Keypair.create_from_uri("//Alice")
BOB = bt.sp_core.Keypair.create_from_uri("//Bob")
CHARLIE = bt.sp_core.Keypair.create_from_uri("//Charlie")


def unsigned_manifest() -> dict[str, object]:
    digest = "a" * 64
    return {
        "schema_version": "planrace/evidence/1",
        "environment": "localnet",
        "network": "local",
        "netuid": 2,
        "run_id": "local-2-epoch-8",
        "epoch": 8,
        "git_commit": "b" * 40,
        "container_digests": {"subtensor": digest},
        "protocol_version": "planrace/1",
        "validator_hotkeys": [ALICE.ss58_address],
        "miner_hotkeys": [BOB.ss58_address, CHARLIE.ss58_address],
        "task_commitment": digest,
        "task_reveal": {
            "task_id": "task-8",
            "seed": 8,
            "salt": "fixture-only",
            "reveal_digest": digest,
            "verified": True,
        },
        "request_digests": [digest],
        "response_digests": [],
        "authentication": {
            "authenticated_requests": 2,
            "signed_responses": 0,
            "request_protocol": "btauth/1",
            "response_protocol": None,
        },
        "scores": [
            {
                "uid": 1,
                "miner_hotkey": BOB.ss58_address,
                "profile": "honest",
                "accepted": True,
                "correct": True,
                "score": 1.25,
                "failure_code": None,
                "result_hash": digest,
                "reference_hash": digest,
                "median_warm_ms": 1.0,
                "setup_ms": 2.0,
                "plan_cost": 10,
                "baseline_relative_speedup": None,
            },
            {
                "uid": 2,
                "miner_hotkey": CHARLIE.ss58_address,
                "profile": "gaming",
                "accepted": True,
                "correct": False,
                "score": 0.0,
                "failure_code": "result_mismatch",
                "result_hash": None,
                "reference_hash": digest,
                "median_warm_ms": None,
                "setup_ms": None,
                "plan_cost": None,
                "baseline_relative_speedup": None,
            },
        ],
        "weight_plan": {"uids": [1], "weights": [1.0]},
        "extrinsics": [
            {
                "extrinsic_id": "10-0001",
                "block_hash": digest,
                "success": True,
                "message": "Success",
                "fee_tao": 0.0,
            }
        ],
        "readback": {"validator_uid": 0, "last_update": 10, "raw_weights": [[1, 65535]]},
        "timestamps": {
            "observed_at": "2026-01-01T00:00:00Z",
            "signed_at": "2026-01-01T00:01:00Z",
        },
        "known_limitations": ["fixture evidence"],
        "source_artifacts": [{"path": "results/run.json", "sha256": digest}],
    }


def test_signed_manifest_verifies_and_summarizes() -> None:
    manifest = sign_manifest(unsigned_manifest(), ALICE)
    digest = verify_manifest(manifest)
    summary = summarize_manifest(manifest, digest)
    assert summary["validator_count"] == 1
    assert summary["miner_count"] == 2
    assert summary["correctness_passed"] == 1
    assert summary["correctness_failed"] == 1
    assert summary["payload_sha256"] == digest


def test_evidence_v2_uses_explicit_strategy_and_schedule_digests() -> None:
    data = unsigned_manifest()
    data["schema_version"] = "planrace/evidence/2"
    data["protocol_version"] = "planrace/2"
    for score in data["scores"]:  # type: ignore[union-attr]
        score["result_hash"] = None
        score["reference_hash"] = None
        score["strategy_digest"] = "c" * 64
        score["schedule_digest"] = "d" * 64
    manifest = sign_manifest(data, ALICE)
    assert verify_manifest(manifest) == manifest.validator_signature.signed_payload_sha256
    assert all(score.strategy_digest == "c" * 64 for score in manifest.scores)


def test_evidence_v2_rejects_overloaded_result_hash_fields() -> None:
    data = unsigned_manifest()
    data["schema_version"] = "planrace/evidence/2"
    data["protocol_version"] = "planrace/2"
    for score in data["scores"]:  # type: ignore[union-attr]
        score["strategy_digest"] = "c" * 64
        score["schedule_digest"] = "d" * 64
    with pytest.raises(ValidationError, match="cannot overload SQL result hash"):
        sign_manifest(data, ALICE)


def test_canonical_payload_is_independent_of_mapping_order() -> None:
    original = unsigned_manifest()
    reversed_mapping = dict(reversed(list(original.items())))
    assert canonical_manifest_bytes(original) == canonical_manifest_bytes(reversed_mapping)


def test_any_signed_field_tamper_is_rejected() -> None:
    manifest = sign_manifest(unsigned_manifest(), ALICE)
    tampered = manifest.model_dump(mode="json")
    tampered["network"] = "finney"
    with pytest.raises(EvidenceVerificationError, match="digest mismatch"):
        verify_manifest(EvidenceManifest.model_validate_json(json.dumps(tampered)))


def test_signer_must_be_declared_validator() -> None:
    data = unsigned_manifest()
    data["validator_hotkeys"] = [BOB.ss58_address]
    with pytest.raises(EvidenceVerificationError, match="not a declared validator"):
        sign_manifest(data, ALICE)


def test_schema_rejects_unknown_fields_and_bad_weights() -> None:
    data = unsigned_manifest()
    data["unexpected"] = True
    with pytest.raises(ValidationError):
        sign_manifest(data, ALICE)
    data = unsigned_manifest()
    data["weight_plan"] = {"uids": [1, 2], "weights": [0.8, 0.8]}
    with pytest.raises(ValidationError, match="sum to one"):
        sign_manifest(data, ALICE)


def test_cli_verify_summarize_and_tamper_failure(tmp_path: Path) -> None:
    manifest = sign_manifest(unsigned_manifest(), ALICE)
    path = tmp_path / "evidence.json"
    path.write_text(manifest.model_dump_json(indent=2) + "\n")
    loaded, digest = verify_manifest_file(path)
    assert loaded.run_id == manifest.run_id
    assert digest == manifest.validator_signature.signed_payload_sha256

    runner = CliRunner()
    verified = runner.invoke(app, ["evidence", "verify", str(path)])
    assert verified.exit_code == 0
    assert "SIGNATURE VALID; CLAIMS UNVERIFIED local-2-epoch-8" in verified.stdout
    trusted = runner.invoke(
        app,
        ["evidence", "verify", str(path), "--expected-signer", ALICE.ss58_address],
    )
    assert trusted.exit_code == 0
    assert "SIGNATURE VALID; EXPECTED SIGNER" in trusted.stdout
    summarized = runner.invoke(app, ["evidence", "summarize", str(path)])
    assert summarized.exit_code == 0
    assert json.loads(summarized.stdout)["authenticated_requests"] == 2

    tampered = json.loads(path.read_text())
    tampered["epoch"] = 9
    path.write_text(json.dumps(tampered))
    rejected = runner.invoke(app, ["evidence", "verify", str(path)])
    assert rejected.exit_code == 1
    assert "INVALID" in rejected.stderr
