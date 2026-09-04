# Verifiable evidence manifests

PlanRace publishes one signed `EvidenceManifest` per completed validator run.
The manifest is an integrity envelope around the run metadata, identities, task
commit/reveal evidence, transport digests, score components, weight plan,
extrinsics, readback, timestamps, and known limitations. The strict Pydantic
model is in [`planrace/evidence.py`](planrace/evidence.py); its generated JSON
Schema is [`schemas/evidence-manifest-v1.schema.json`](schemas/evidence-manifest-v1.schema.json).

## Signature format

Schema version `planrace/evidence/1` uses the following deterministic encoding:

1. Remove the top-level `validator_signature` object.
2. Reject non-finite numbers and encode integral floats as JSON integers.
3. Recursively order every object by Unicode key order. Preserve array order.
4. Encode compact UTF-8 JSON with no insignificant whitespace.
5. Prefix the bytes with `planrace-evidence-manifest/v1` and one null byte.
6. Sign those bytes with the validator's sr25519 hotkey.

`validator_signature.signed_payload_sha256` is the SHA-256 of the complete
domain-separated payload. The signer must also appear in
`validator_hotkeys`. Unknown schema fields are rejected.

## Verify or summarize

From a bootstrapped repository:

```bash
uv run planrace evidence verify dashboard/evidence/localnet-v1-epoch-8.json
uv run planrace evidence summarize dashboard/evidence/localnet-v1-epoch-8.json
```

`verify` exits non-zero if schema validation, signer binding, payload digest, or
signature verification fails. Changing a signed field therefore invalidates
the manifest. `summarize` performs the same verification before emitting JSON
headline metrics.

The dashboard independently performs the same canonicalization and sr25519
verification in Node before every production build. Its validator/miner counts,
correctness totals, authenticated-request count, and weight-recipient count are
derived from the verified manifest rather than constants in the page source.

## Current evidence and limits

The current public manifest is a reconstruction of the committed epoch-8
localnet result, signed after the run by Bittensor's public `//Alice` development
identity. This establishes tamper evidence for the reconstruction; it is not an
in-band epoch signature and must not be interpreted as testnet evidence. Because
the local development key is public, it cannot establish exclusive operator
attribution; the manifest records this limitation explicitly. The
manifest records that v1 authenticated requests but did not sign responses,
did not retain raw roundtrip bytes, and did not measure same-worker baseline
performance. Those gaps stay visible in both the raw evidence and dashboard.

A signature establishes payload integrity and signer possession. It does not by
itself prove that observations are complete or true. Review the listed source
artifacts, chain identifiers, readback, and `known_limitations` before relying
on a run. Testnet evidence must be emitted and signed in-band by the dedicated
testnet validator; local development keys are never suitable for funds.
