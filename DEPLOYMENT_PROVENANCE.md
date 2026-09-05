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
