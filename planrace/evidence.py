"""Signed, tamper-evident evidence manifests for completed PlanRace runs."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, Final, Literal

import bittensor as bt
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

EVIDENCE_SCHEMA_VERSION: Final = "planrace/evidence/2"
EVIDENCE_SIGNATURE_DOMAINS: Final = {
    "planrace/evidence/1": b"planrace-evidence-manifest/v1\x00",
    "planrace/evidence/2": b"planrace-evidence-manifest/v2\x00",
}

DigestHex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
GitCommit = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
HexSignature = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{128}$")]
NonEmptyText = Annotated[str, StringConstraints(min_length=1, max_length=4096)]
Hotkey = Annotated[str, StringConstraints(min_length=40, max_length=64)]


class EvidenceVerificationError(ValueError):
    """Raised when a manifest is malformed or its signature does not verify."""


class EvidenceModel(BaseModel):
    """Strict base class for signed evidence values."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class TaskRevealEvidence(EvidenceModel):
    task_id: NonEmptyText
    seed: Annotated[int, Field(ge=0)] | None
    salt: NonEmptyText | None
    reveal_digest: DigestHex
    verified: bool


class AuthenticationEvidence(EvidenceModel):
    authenticated_requests: Annotated[int, Field(ge=0)]
    signed_responses: Annotated[int, Field(ge=0)]
    request_protocol: NonEmptyText
    response_protocol: NonEmptyText | None


class ScoreEvidence(EvidenceModel):
    uid: Annotated[int, Field(ge=0)]
    miner_hotkey: Hotkey
    profile: NonEmptyText
    accepted: bool
    correct: bool
    score: Annotated[float, Field(ge=0.0)]
    failure_code: NonEmptyText | None
    result_hash: DigestHex | None
    reference_hash: DigestHex | None
    strategy_digest: DigestHex | None = None
    schedule_digest: DigestHex | None = None
    median_warm_ms: Annotated[float, Field(ge=0.0)] | None
    setup_ms: Annotated[float, Field(ge=0.0)] | None
    plan_cost: Annotated[int, Field(ge=0)] | None
    baseline_relative_speedup: Annotated[float, Field(gt=0.0)] | None


class WeightPlanEvidence(EvidenceModel):
    uids: tuple[Annotated[int, Field(ge=0)], ...]
    weights: tuple[Annotated[float, Field(ge=0.0, le=1.0)], ...]

    @field_validator("weights")
    @classmethod
    def weights_are_normalized(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if value and abs(sum(value) - 1.0) > 1e-9:
            raise ValueError("non-empty weight plans must sum to one")
        return value


class ExtrinsicEvidence(EvidenceModel):
    extrinsic_id: NonEmptyText
    block_hash: DigestHex
    success: bool
    message: NonEmptyText
    fee_tao: Annotated[float, Field(ge=0.0)]


class ReadbackEvidence(EvidenceModel):
    validator_uid: Annotated[int, Field(ge=0)]
    last_update: Annotated[int, Field(ge=0)]
    raw_weights: tuple[tuple[Annotated[int, Field(ge=0)], Annotated[int, Field(ge=0)]], ...]


class TimestampEvidence(EvidenceModel):
    observed_at: NonEmptyText
    signed_at: NonEmptyText


class SourceArtifactEvidence(EvidenceModel):
    path: NonEmptyText
    sha256: DigestHex


class ValidatorSignature(EvidenceModel):
    algorithm: Literal["sr25519"]
    signer_hotkey: Hotkey
    signed_payload_sha256: DigestHex
    signature_hex: HexSignature


class EvidenceManifest(EvidenceModel):
    """Portable evidence for one completed validator run.

    The signature covers every field except ``validator_signature`` using
    :data:`EVIDENCE_SIGNATURE_DOMAIN` followed by canonical UTF-8 JSON.
    """

    schema_version: Literal["planrace/evidence/1", "planrace/evidence/2"] = EVIDENCE_SCHEMA_VERSION
    environment: Literal["localnet", "testnet"]
    network: NonEmptyText
    netuid: Annotated[int, Field(ge=1)]
    run_id: NonEmptyText
    epoch: Annotated[int, Field(ge=0)]
    git_commit: GitCommit
    container_digests: dict[NonEmptyText, DigestHex]
    protocol_version: NonEmptyText
    validator_hotkeys: tuple[Hotkey, ...]
    miner_hotkeys: tuple[Hotkey, ...]
    task_commitment: DigestHex
    task_reveal: TaskRevealEvidence
    request_digests: tuple[DigestHex, ...]
    response_digests: tuple[DigestHex, ...]
    authentication: AuthenticationEvidence
    scores: tuple[ScoreEvidence, ...]
    weight_plan: WeightPlanEvidence
    extrinsics: tuple[ExtrinsicEvidence, ...]
    readback: ReadbackEvidence
    timestamps: TimestampEvidence
    known_limitations: tuple[NonEmptyText, ...]
    source_artifacts: tuple[SourceArtifactEvidence, ...]
    validator_signature: ValidatorSignature

    @field_validator("validator_hotkeys", "miner_hotkeys")
    @classmethod
    def identities_are_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("at least one identity is required")
        if len(value) != len(set(value)):
            raise ValueError("identities must be unique")
        return value

    @model_validator(mode="after")
    def score_hashes_match_schema_semantics(self) -> EvidenceManifest:
        for score in self.scores:
            if self.schema_version == "planrace/evidence/2":
                if self.protocol_version != "planrace/2":
                    raise ValueError("evidence/2 is reserved for protocol v2")
                if score.result_hash is not None or score.reference_hash is not None:
                    raise ValueError("evidence/2 cannot overload SQL result hash fields")
                if score.strategy_digest is None or score.schedule_digest is None:
                    raise ValueError("evidence/2 scores require strategy and schedule digests")
            elif score.strategy_digest is not None or score.schedule_digest is not None:
                raise ValueError("evidence/1 scores cannot contain v2 strategy digest fields")
        return self


def canonical_manifest_bytes(data: EvidenceManifest | Mapping[str, Any]) -> bytes:
    """Return the canonical JSON payload used for evidence signatures."""

    if isinstance(data, EvidenceManifest):
        payload = data.model_dump(mode="json", exclude={"validator_signature"})
    else:
        payload = dict(data)
        payload.pop("validator_signature", None)
    try:
        encoded = json.dumps(
            _normalize_json_numbers(payload),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as error:
        raise EvidenceVerificationError(f"manifest is not canonicalizable: {error}") from error
    return encoded.encode("utf-8")


def _normalize_json_numbers(value: Any) -> Any:
    """Match JSON.stringify's finite-number representation for signed payloads."""

    if isinstance(value, float):
        if not math.isfinite(value):
            raise EvidenceVerificationError("manifest numbers must be finite")
        return int(value) if value.is_integer() else value
    if isinstance(value, dict):
        return {key: _normalize_json_numbers(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_json_numbers(item) for item in value]
    return value


def signature_payload(data: EvidenceManifest | Mapping[str, Any]) -> bytes:
    """Return the domain-separated bytes signed by a validator."""

    schema_version = (
        data.schema_version if isinstance(data, EvidenceManifest) else data.get("schema_version")
    )
    domain = EVIDENCE_SIGNATURE_DOMAINS.get(str(schema_version))
    if domain is None:
        raise EvidenceVerificationError("unsupported evidence signature domain")
    return domain + canonical_manifest_bytes(data)


def sign_manifest(data: Mapping[str, Any], keypair: bt.Keypair) -> EvidenceManifest:
    """Validate and sign an unsigned manifest mapping with a validator keypair."""

    unsigned = dict(data)
    unsigned.pop("validator_signature", None)
    unsigned["validator_signature"] = {
        "algorithm": "sr25519",
        "signer_hotkey": keypair.ss58_address,
        "signed_payload_sha256": "0" * 64,
        "signature_hex": "0" * 128,
    }
    validated = EvidenceManifest.model_validate_json(
        json.dumps(unsigned, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    )
    payload = signature_payload(validated)
    signed = validated.model_dump(mode="json")
    signed["validator_signature"] = {
        "algorithm": "sr25519",
        "signer_hotkey": keypair.ss58_address,
        "signed_payload_sha256": hashlib.sha256(payload).hexdigest(),
        "signature_hex": keypair.sign(payload).hex(),
    }
    manifest = EvidenceManifest.model_validate_json(
        json.dumps(signed, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    )
    verify_manifest(manifest)
    return manifest


def _verify_signature(
    signed_data: EvidenceManifest | Mapping[str, Any],
    manifest: EvidenceManifest,
    *,
    expected_signer: str | None = None,
) -> str:
    """Verify a validated manifest without changing its signed JSON shape."""
    signature = manifest.validator_signature
    if expected_signer is not None and signature.signer_hotkey != expected_signer:
        raise EvidenceVerificationError("manifest signer does not match expected signer")
    if signature.signer_hotkey not in manifest.validator_hotkeys:
        raise EvidenceVerificationError("manifest signer is not a declared validator hotkey")
    payload = signature_payload(signed_data)
    digest = hashlib.sha256(payload).hexdigest()
    if digest != signature.signed_payload_sha256:
        raise EvidenceVerificationError("signed payload digest mismatch")
    try:
        verifier = bt.sp_core.Keypair(ss58_address=signature.signer_hotkey)
        verified = verifier.verify(payload, bytes.fromhex(signature.signature_hex))
    except (TypeError, ValueError) as error:
        raise EvidenceVerificationError(f"invalid validator signature: {error}") from error
    if not verified:
        raise EvidenceVerificationError("validator signature verification failed")
    return digest


def verify_manifest(manifest: EvidenceManifest, *, expected_signer: str | None = None) -> str:
    """Verify the signer binding, payload digest, and sr25519 signature.

    Returns the signed payload's SHA-256 digest when verification succeeds.
    """

    return _verify_signature(manifest, manifest, expected_signer=expected_signer)


def load_manifest(path: Path) -> EvidenceManifest:
    """Load a strict JSON manifest without accepting unknown fields."""

    try:
        raw = path.read_bytes()
    except OSError as error:
        raise EvidenceVerificationError(f"cannot read manifest: {error}") from error
    try:
        return EvidenceManifest.model_validate_json(raw)
    except (ValueError, TypeError) as error:
        raise EvidenceVerificationError(f"manifest schema validation failed: {error}") from error


def verify_manifest_file(
    path: Path, *, expected_signer: str | None = None
) -> tuple[EvidenceManifest, str]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise EvidenceVerificationError(f"cannot read manifest: {error}") from error
    try:
        signed_data = json.loads(raw)
        if not isinstance(signed_data, dict):
            raise TypeError("manifest root must be an object")
        manifest = EvidenceManifest.model_validate_json(raw)
    except (ValueError, TypeError) as error:
        raise EvidenceVerificationError(f"manifest schema validation failed: {error}") from error
    digest = _verify_signature(signed_data, manifest, expected_signer=expected_signer)
    return manifest, digest


def summarize_manifest(manifest: EvidenceManifest, digest: str | None = None) -> dict[str, Any]:
    """Produce stable, machine-readable headline metrics for a verified run."""

    payload_digest = digest or verify_manifest(manifest)
    correct = sum(score.correct for score in manifest.scores)
    return {
        "environment": manifest.environment,
        "network": manifest.network,
        "netuid": manifest.netuid,
        "run_id": manifest.run_id,
        "epoch": manifest.epoch,
        "protocol_version": manifest.protocol_version,
        "git_commit": manifest.git_commit,
        "validator_count": len(manifest.validator_hotkeys),
        "miner_count": len(manifest.miner_hotkeys),
        "authenticated_requests": manifest.authentication.authenticated_requests,
        "signed_responses": manifest.authentication.signed_responses,
        "correctness_passed": correct,
        "correctness_failed": len(manifest.scores) - correct,
        "weight_recipients": len(manifest.weight_plan.uids),
        "extrinsic_count": len(manifest.extrinsics),
        "payload_sha256": payload_digest,
        "signer_hotkey": manifest.validator_signature.signer_hotkey,
    }
