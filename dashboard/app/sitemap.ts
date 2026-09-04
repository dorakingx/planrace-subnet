import type { MetadataRoute } from 'next';

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: 'https://planrace-subnet.vercel.app',
      lastModified: new Date('2026-09-01T00:00:00Z'),
      changeFrequency: 'weekly',
      priority: 1,
    },
  ];
}
