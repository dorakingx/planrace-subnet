# Deployment provenance

The production evidence site is https://planrace-subnet.vercel.app.

## Required production record

| Field | Value |
|---|---|
| GitHub repository | `dorakingx/planrace-subnet` |
| Branch / commit | Pending clean protocol v2 integration commit |
| Vercel deployment ID / URL | Pending |
| Production promotion time (UTC) | Pending |
| `gitDirty` | Must be `0` |
| Build command and Node version | Pending final deployment log |
| Evidence manifest SHA-256 | Pending localnet v2 completion |
| Logged-out HTTP verification | Pending |

The previously deployed production was built from a stale dirty tree and is not
accepted as protocol v2 provenance. It must be replaced only after a preview
deployment passes and the exact GitHub SHA is public.

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

Append the final immutable deployment information here; do not overwrite
historical records when later previews or productions are created.
