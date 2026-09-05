import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

export const dynamic = 'force-static';

export function GET() {
  // A signed manifest is a byte-sensitive artifact. Response.json() parses and
  // reserializes numbers, which can change IEEE-754 spellings and invalidate
  // the sr25519 signature. Emit the committed UTF-8 source verbatim.
  const manifest = readFileSync(
    resolve(process.cwd(), 'evidence/localnet-v2.json'),
    'utf8',
  );
  return new Response(manifest, {
    headers: {
      'Cache-Control': 'public, max-age=0, s-maxage=3600',
      'Content-Disposition': 'attachment; filename="localnet-v2.json"',
      'Content-Type': 'application/json; charset=utf-8',
    },
  });
}
