import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { readFile } from 'node:fs/promises';

const port = 4317;
const origin = `http://127.0.0.1:${port}`;
const nextBin = new URL('../node_modules/next/dist/bin/next', import.meta.url)
  .pathname;
const server = spawn(
  process.execPath,
  [nextBin, 'start', '--hostname', '127.0.0.1', '--port', String(port)],
  { stdio: ['ignore', 'pipe', 'pipe'] },
);

async function waitUntilReady() {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try {
      const response = await fetch(origin);
      if (response.ok) return;
    } catch {
      // The server socket is expected to be unavailable during startup.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error('Next.js production server did not become ready');
}

try {
  await waitUntilReady();
  const requiredRoutes = [
    '/',
    '/og.png',
    '/favicon.svg',
    '/icon.svg',
    '/robots.txt',
    '/sitemap.xml',
    '/evidence/localnet-v2.json',
    '/evidence/localnet-v2-summary.json',
  ];
  const responses = await Promise.all(
    requiredRoutes.map(async (route) => ({
      route,
      response: await fetch(`${origin}${route}`),
    })),
  );
  for (const { route, response } of responses) {
    assert.equal(response.status, 200, `${route} must return HTTP 200`);
  }

  const home = responses.find(({ route }) => route === '/')?.response;
  assert(home);
  const html = await home.text();
  assert.match(
    html,
    /<link rel="canonical" href="https:\/\/planrace-subnet\.vercel\.app"/,
  );
  assert.match(html, /LOCALNET EVIDENCE/);
  assert.match(html, /TESTNET PENDING/);
  assert.doesNotMatch(html, /TESTNET VERIFIED/);
  assert.equal(home.headers.get('x-content-type-options'), 'nosniff');
  assert.equal(home.headers.get('x-frame-options'), 'DENY');
  assert.match(
    home.headers.get('content-security-policy') ?? '',
    /object-src 'none'/,
  );

  const raw = responses.find(
    ({ route }) => route === '/evidence/localnet-v2.json',
  )?.response;
  assert(raw);
  assert.match(raw.headers.get('content-disposition') ?? '', /attachment/);
  const rawManifest = await raw.text();
  const sourceManifest = await readFile('evidence/localnet-v2.json', 'utf8');
  assert.equal(
    rawManifest,
    sourceManifest,
    'downloaded signed manifest must preserve the committed UTF-8 bytes',
  );
  const evidence = JSON.parse(rawManifest);
  assert.match(evidence.schema_version, /^planrace\/evidence\/[12]$/);
  assert.match(
    evidence.validator_signature.signed_payload_sha256,
    /^[0-9a-f]{64}$/,
  );

  process.stdout.write(
    `Smoke verified ${requiredRoutes.length} production routes.\n`,
  );
} finally {
  server.kill('SIGTERM');
}
