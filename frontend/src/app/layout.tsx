import type { Metadata } from 'next';
import '../styles/globals.css';
import { LanguageProvider } from '@/contexts/LanguageContext';

export const metadata: Metadata = {
  title: 'PaperPulse - Discover Trending Research Papers',
  description: 'A platform to discover and understand trending research papers',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh">
      <body>
        <LanguageProvider>
          {children}
        </LanguageProvider>
      </body>
    </html>
  );
}
