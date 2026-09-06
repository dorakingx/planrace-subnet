# Deployment provenance

The production evidence site is https://planrace-subnet.vercel.app.

## Verified production record (2026-09-05)

| Field | Value |
|---|---|
| GitHub repository | `dorakingx/planrace-subnet` |
| Branch / commit | `main` / `50e378281a2deffb906d368302c264d44497c92a` |
| Preview deployment | `dpl_5UKpTxYdNhskbUH85VrWponn7j4a` / `planrace-subnet-2tal729bu-doraking.vercel.app` |
| Production deployment | `dpl_6CxN3ZqYYm7sArcfEwWNDHQDpuYD` / `planrace-subnet-4fm0teujb-doraking.vercel.app` |
| Canonical production URL | `https://planrace-subnet.vercel.app` |
| Production promotion time (UTC) | `2026-09-05T00:00:45Z` |
| `gitDirty` | `0` before the preview build |
| Build command and Node version | `npm run build:vercel`; Node.js `24.x` |
| Evidence manifest file SHA-256 | `0d4eb50214326c035fc0d9e82513ff0a58f0f867549fbe27d783f5cdcf09fc25` |
| Signed payload SHA-256 | `741b61e619054aa6a5b834938cd41f1a0eabe1ef9d1397a8913cd9dffc777001` |
| Logged-out HTTP verification | Passed for `/`, v2 manifest/summary, robots, sitemap, icons, and OG image |

The record above replaced the earlier stale deployment. The clean preview was
verified first, then that same build artifact was promoted to production. The
Vercel Git integration root directory is `dashboard`; subsequent pushes must
also complete as Git-linked deployments before they replace this baseline.

## Public acceptance checklist

- `/`, `/robots.txt`, `/sitemap.xml`, `/icon.svg` or configured favicon, and the
  OG image return HTTP 200 without login;
- canonical metadata points to the production URL;
- no browser console errors, broken internal links, or mobile overflow;
- keyboard navigation, contrast, and security headers are checked;
- rendered localnet values equal the committed signed manifest;
- testnet remains visibly pending until a separate signed testnet manifest is
  committed;
- GitHub commit equals deployment metadata and the source tree is clean.

Append later immutable deployment information here; do not overwrite historical
records when later previews or productions are created.

## Git-linked production record (2026-09-05)

After correcting the Vercel project root directory to `dashboard`, the GitHub
integration built and deployed the following clean checkout without a manual
promotion step.

| Field | Value |
|---|---|
| Branch / commit | `main` / `d5ce868c1204f1cb63ebbf56af040e9044837bff` |
| Production deployment | `dpl_3JB3i2sG3kyHFAznCQwSh4iukqie` / `planrace-subnet-6o98x9opd-doraking.vercel.app` |
| Canonical production URL | `https://planrace-subnet.vercel.app` |
| Deployment creation time (UTC) | `2026-09-05T00:17:01Z` |
| Git source metadata | GitHub repository `dorakingx/planrace-subnet`, branch `main`, matching full SHA |
| `gitDirty` | Not emitted for the provider-controlled Git checkout; Vercel cloned the exact SHA |
| Vercel project root | `dashboard` |
| Build result | Ready; evidence verification passed; build log had no warning, error, or failure |
| Logged-out HTTP verification | Eight public routes passed with expected headers and signed v2 values |

## Submission-package production record (2026-09-07 JST)

PR #1 integrated the published submission receipts, interim media and full
proposal checkpoint link. Its CI run `34046171321` passed all jobs before merge:
306 Python tests, 85% coverage, three browser E2E tests, source/evidence audits,
dependency and secret scans, and worker-image checks. The merged file tree was
verified identical to the tested PR head.

| Field | Value |
|---|---|
| Branch / commit | `main` / `c602a21eef392264439607999af6eced66a55505` |
| Tested PR head | `32be37d85c6c96500c659620675eb4a3526f4320` |
| Production deployment | `dpl_E7Y24aoSWhg5vgj9fTeLVzeMFMBb` / `planrace-subnet-3bekv3iz5-doraking.vercel.app` |
| Canonical alias | `https://planrace-subnet.vercel.app` |
| Source / status | Provider-controlled Git checkout / READY |
| Build log | Cloned `main` at `c602a21`; evidence signature check and Next.js build passed |
| Build-to-ready interval | 26.853 seconds, from provider timestamps |
| `gitDirty` | Not emitted for provider Git checkout; do not synthesize a `0` metadata field |
| Public route checks | Eight HTTP 200 responses, canonical metadata, security headers and explicit testnet-pending labels |
| Downloaded manifest SHA-256 | `4e6ed9471fa6adae6e0cafc69446aa24296657b24160c8b151932824a56ffdb3`; exact committed byte match |
| Bounded runtime-error check | No project error clusters reported from `2026-09-06T16:46:20Z` to the observation shortly after deployment |

This is a historical verified record, not an assertion that future main commits
or deployments have passed the same checks. The separate post-merge CI has run
ID `34046510708`; consult that run for its final state. No drains or continuous
monitoring coverage were established by the short runtime-error query. The
dashboard continues to show localnet evidence, not a public testnet run.
