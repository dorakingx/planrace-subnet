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
  title: 'PlanRace — Verified Query Optimization Market',
  description:
    'A Bittensor subnet where miners compete on faster SQL artifacts and validators prove exact results before awarding weight.',
  openGraph: {
    title: 'PlanRace — Faster queries. Truth first.',
    description: 'A verified query-optimization market on Bittensor.',
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
