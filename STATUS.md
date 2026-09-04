# Status

Updated: 2026-09-01 (Asia/Tokyo)

## Protocol v2 hardening phase

- Baseline audit completed on `hardening/protocol-v2`; see
  [BASELINE_AUDIT.md](BASELINE_AUDIT.md).
- The existing `planrace/1` implementation and local-chain evidence are being
  preserved as historical v1 evidence.
- P0 work now in progress: opaque CSPRNG task creation, true holdout
  commit/reveal, structured optimization bundles, signed miner responses,
  disposable sandbox workers, canonical exact-result semantics, and
  baseline-relative scoring.
- Public status remains **LOCALNET EVIDENCE / TESTNET PENDING**.
- HackQuest still shows `QECForge` with no checkpoint. It will not be updated or
  posted until every checkpoint P0 gate is evidenced and independently
  reviewed.
- No dedicated testnet wallet, testnet netuid, test TAO, or testnet deployment
  exists yet.
- Current Vercel production provenance is known-bad (`gitDirty=1`, stale Git
  SHA) and must be replaced by a clean deployment after integration.

## Complete

- repository created under `dorakingx` as public;
- zero-base idea reselection and pivot decision;
- protocol v1 models;
- historical v1 commit/reveal fixture generation;
- bounded SQL/index admission;
- exact result oracle and scorer;
- three reference miner profiles;
- multi-epoch local simulation;
- receiver-bound Bittensor v11 request authentication;
- official Subtensor localnet with three registered neurons;
- endpoint publication and verified local-chain weight update;
- CI-enforced unit, integration, property, and branch-coverage checks;
- public Vercel evidence dashboard and reproducible demo UI.

## In progress

- Protocol v2 P0 hardening and adversarial verification.
- Evidence-manifest-driven dashboard and clean deployment provenance.
- Localnet v2 scale-out before any testnet claim.
- HackQuest checkpoint package and testnet deployment after the P0 gates.

## Not complete

- Bittensor testnet registration/funding/weights;
- HackQuest checkpoint post;
- clean Protocol v2 evidence-dashboard deployment/video;
- final submission and release tag.

The project is not presented as production-ready and the hackathon Goal is not complete yet.
