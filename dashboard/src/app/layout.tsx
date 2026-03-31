import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import '../styles/globals.css';
import Sidebar from '@/components/layout/Sidebar';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'ClubMillies — Gold Trading Bot',
  description: 'Not the best you can get but the best there is',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} min-h-screen`}>
        <Sidebar />
        <main className="ml-64 min-h-screen relative z-10">
          <div className="p-8">
            {children}
          </div>
        </main>
      </body>
    </html>
  );
}
