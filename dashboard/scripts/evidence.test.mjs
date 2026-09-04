import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import test from 'node:test';

import {
  canonicalManifestBytes,
  signaturePayload,
  verifyEvidence,
} from './evidence.mjs';

const manifest = JSON.parse(
  await readFile(resolve('evidence/localnet-v2.json'), 'utf8'),
);

void test('committed localnet manifest has a valid validator signature', async () => {
  const verified = await verifyEvidence(manifest);
  assert.equal(
    verified.digest,
    manifest.validator_signature.signed_payload_sha256,
  );
});

void test('canonical encoding does not depend on object insertion order', () => {
  const reversed = Object.fromEntries(Object.entries(manifest).reverse());
  assert.deepEqual(
    canonicalManifestBytes(reversed),
    canonicalManifestBytes(manifest),
  );
  assert.deepEqual(signaturePayload(reversed), signaturePayload(manifest));
});

void test('changing any signed evidence makes verification fail', async () => {
  const tampered = structuredClone(manifest);
  tampered.netuid += 1;
  await assert.rejects(verifyEvidence(tampered), /digest mismatch/);
});

void test('undeclared validator signer is rejected before display', async () => {
  const tampered = structuredClone(manifest);
  tampered.validator_hotkeys = [manifest.miner_hotkeys[0]];
  await assert.rejects(verifyEvidence(tampered), /not a declared validator/);
});
