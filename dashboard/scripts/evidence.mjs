import { createHash } from 'node:crypto';

import { cryptoWaitReady, signatureVerify } from '@polkadot/util-crypto';

export const EVIDENCE_SIGNATURE_DOMAIN = Buffer.from(
  'planrace-evidence-manifest/v1\0',
  'utf8',
);

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function canonicalValue(value) {
  if (Array.isArray(value)) {
    return value.map(canonicalValue);
  }
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, canonicalValue(value[key])]),
    );
  }
  if (typeof value === 'number') {
    assert(Number.isFinite(value), 'manifest numbers must be finite');
  }
  return value;
}

export function canonicalManifestBytes(manifest) {
  const { validator_signature: _signature, ...unsigned } = manifest;
  return Buffer.from(JSON.stringify(canonicalValue(unsigned)), 'utf8');
}

export function signaturePayload(manifest) {
  return Buffer.concat([
    EVIDENCE_SIGNATURE_DOMAIN,
    canonicalManifestBytes(manifest),
  ]);
}

function validateHeadlineSchema(manifest) {
  assert(
    manifest.schema_version === 'planrace/evidence/1',
    'unsupported evidence schema',
  );
  assert(
    manifest.environment === 'localnet' || manifest.environment === 'testnet',
    'invalid environment',
  );
  assert(
    Number.isInteger(manifest.netuid) && manifest.netuid > 0,
    'invalid netuid',
  );
  assert(
    Array.isArray(manifest.validator_hotkeys),
    'validators must be an array',
  );
  assert(manifest.validator_hotkeys.length > 0, 'validator list is empty');
  assert(Array.isArray(manifest.miner_hotkeys), 'miners must be an array');
  assert(manifest.miner_hotkeys.length > 0, 'miner list is empty');
  assert(Array.isArray(manifest.scores), 'scores must be an array');
  assert(
    Array.isArray(manifest.known_limitations),
    'limitations must be an array',
  );
  assert(
    typeof manifest.validator_signature?.signature_hex === 'string',
    'validator signature is missing',
  );
}

export async function verifyEvidence(manifest) {
  validateHeadlineSchema(manifest);
  const signature = manifest.validator_signature;
  assert(signature.algorithm === 'sr25519', 'unsupported signature algorithm');
  assert(
    manifest.validator_hotkeys.includes(signature.signer_hotkey),
    'signer is not a declared validator',
  );
  const payload = signaturePayload(manifest);
  const digest = createHash('sha256').update(payload).digest('hex');
  assert(
    digest === signature.signed_payload_sha256,
    'signed payload digest mismatch',
  );
  assert(await cryptoWaitReady(), 'sr25519 verifier did not initialize');
  const verification = signatureVerify(
    payload,
    `0x${signature.signature_hex}`,
    signature.signer_hotkey,
  );
  assert(
    verification.isValid && verification.crypto === 'sr25519',
    'validator signature verification failed',
  );
  return { digest, manifest };
}
