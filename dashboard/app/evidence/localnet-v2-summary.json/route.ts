import summary from '@/evidence/localnet-v2-summary.json';

export const dynamic = 'force-static';

export function GET() {
  return Response.json(summary, {
    headers: {
      'Cache-Control': 'public, max-age=0, s-maxage=3600',
      'Content-Disposition': 'attachment; filename="localnet-v2-summary.json"',
    },
  });
}
