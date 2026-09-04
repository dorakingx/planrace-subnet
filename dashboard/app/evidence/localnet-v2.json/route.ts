import manifest from '@/evidence/localnet-v2.json';

export const dynamic = 'force-static';

export function GET() {
  return Response.json(manifest, {
    headers: {
      'Cache-Control': 'public, max-age=0, s-maxage=3600',
      'Content-Disposition': 'attachment; filename="localnet-v2.json"',
    },
  });
}
