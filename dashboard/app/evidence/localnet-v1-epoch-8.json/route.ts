import manifest from '@/evidence/localnet-v1-epoch-8.json';

export const dynamic = 'force-static';

export function GET() {
  return Response.json(manifest, {
    headers: {
      'Cache-Control': 'public, max-age=0, s-maxage=3600',
      'Content-Disposition': 'attachment; filename="localnet-v1-epoch-8.json"',
    },
  });
}
