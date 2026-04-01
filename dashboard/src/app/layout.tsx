import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import '../styles/globals.css';
import AppShell from '@/components/layout/AppShell';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'ClubMillies — Gold Trading Bot',
  description: 'Not the best you can get but the best there is',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} min-h-screen`}>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
