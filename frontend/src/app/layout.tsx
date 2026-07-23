import type { Metadata } from 'next';
import { IBM_Plex_Sans, JetBrains_Mono } from 'next/font/google';

import { AuthProvider } from '@/lib/auth-context';

import './globals.css';

// Plex for the interface and JetBrains for anything machine-written: the pair
// reads as instrumentation rather than as a website, which is what a review
// surface is. JetBrains Mono in particular holds up at the 12.5px the code
// viewer runs at.
const plexSans = IBM_Plex_Sans({
  variable: '--font-plex-sans',
  subsets: ['latin', 'latin-ext'],
  weight: ['400', '500', '600'],
});
const jetbrainsMono = JetBrains_Mono({
  variable: '--font-jetbrains-mono',
  subsets: ['latin', 'latin-ext'],
  weight: ['400', '500'],
});

export const metadata: Metadata = {
  title: 'Code Review Agent',
  description:
    'Çok ajanlı yapay zeka destekli kod inceleme ve güvenlik analizi. ' +
    'Her bulgu statik analizle çapraz doğrulanır.',
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="tr"
      className={`${plexSans.variable} ${jetbrainsMono.variable} h-full antialiased`}
    >
      <body className="bg-background flex min-h-full flex-col">
        <a
          href="#main"
          className="focus:bg-accent focus:text-accent-contrast sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:px-3 focus:py-2 focus:font-medium"
        >
          İçeriğe geç
        </a>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
