import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export const metadata: Metadata = {
  metadataBase: new URL('https://planrace-subnet.vercel.app'),
  title: {
    default: 'PlanRace — Verified Query Optimization Market',
    template: '%s · PlanRace',
  },
  description:
    'A Bittensor subnet where miners compete on faster query artifacts and validators check exact results before awarding weight.',
  alternates: {
    canonical: '/',
  },
  applicationName: 'PlanRace',
  category: 'technology',
  icons: {
    icon: '/favicon.svg',
  },
  openGraph: {
    title: 'PlanRace — Faster queries. Truth first.',
    description: 'A verified query-optimization market on Bittensor.',
    type: 'website',
    url: '/',
    siteName: 'PlanRace',
    images: ['/og.png'],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'PlanRace — Faster queries. Truth first.',
    description: 'A verified query-optimization market on Bittensor.',
    images: ['/og.png'],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
