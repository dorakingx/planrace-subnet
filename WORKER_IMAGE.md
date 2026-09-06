# Published validator worker

The public PlanRace protocol-v2 validation worker is immutable, multi-platform,
and anonymously pullable:

```text
ghcr.io/dorakingx/planrace-validator-worker@sha256:051d1cf58f127e5c7faa3945ad134027bc6931076a30791056c29aa82d3725b0
```

| Field | Verified value |
|---|---|
| Source commit | `c2a87e76f8442fa4d645dc3dfddbeab176b13b3d` |
| Publish workflow | `publish-worker.yml`, run `34030499429` |
| Manifest digest | `sha256:051d1cf58f127e5c7faa3945ad134027bc6931076a30791056c29aa82d3725b0` |
| linux/amd64 digest | `sha256:46a6f73e59ffabed24eafa5c21adc0f8ed489fa714e0016d5cb8d9f12ccc54bb` |
| linux/arm64 digest | `sha256:7194caa1b100f6e4fb41db3f8fff9f94bede6aac21d39d018d29c7e379cab5d7` |
| Runtime | Python `3.12.13`, SQLite `3.46.1`, non-root UID/GID `65532:65532` |
| Base | Official Python manifest `sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36` |
| Supply chain | Hash-locked Python wheels, OCI SBOM, BuildKit provenance, GitHub build attestation |

The [public package](https://github.com/dorakingx/planrace-subnet/pkgs/container/planrace-validator-worker)
was built for both target architectures in GitHub Actions. The workflow and all
third-party actions are commit-pinned.

## Independent verification

Inspect the anonymous registry manifest:

```bash
docker buildx imagetools inspect \
  ghcr.io/dorakingx/planrace-validator-worker@sha256:051d1cf58f127e5c7faa3945ad134027bc6931076a30791056c29aa82d3725b0
```

Verify the GitHub attestation against the exact repository, workflow, and
source commit:

```bash
gh attestation verify \
  oci://ghcr.io/dorakingx/planrace-validator-worker@sha256:051d1cf58f127e5c7faa3945ad134027bc6931076a30791056c29aa82d3725b0 \
  --repo dorakingx/planrace-subnet \
  --signer-workflow dorakingx/planrace-subnet/.github/workflows/publish-worker.yml \
  --source-digest c2a87e76f8442fa4d645dc3dfddbeab176b13b3d \
  --deny-self-hosted-runners
```

The delivery audit also pulled the public digest and executed it with no
network and a read-only root. It confirmed UID `65532`, Python `3.12.13`,
SQLite `3.46.1`, and worker imports. CI independently rebuilds the Dockerfile on
every pull request and `main` push and checks invalid input exits silently with
the bounded fail-closed code `70`.

## Evidence boundary

This digest is the required worker reference for the future testnet run. It
does not retroactively replace the local Docker content ID in the signed
30-epoch localnet evidence, and it does not prove host isolation, testnet
execution, or transaction finality. The testnet manifest must bind this exact
registry digest and separately record chain and protocol evidence.
