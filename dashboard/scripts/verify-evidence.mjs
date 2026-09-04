import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

import { verifyEvidence } from './evidence.mjs';

const manifestPath = resolve(
  process.env.PLANRACE_EVIDENCE_MANIFEST ?? 'evidence/localnet-v2.json',
);
const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
const { digest } = await verifyEvidence(manifest);

process.stdout.write(
  `VERIFIED ${manifest.run_id} sha256:${digest} signer:${manifest.validator_signature.signer_hotkey}\n`,
);
