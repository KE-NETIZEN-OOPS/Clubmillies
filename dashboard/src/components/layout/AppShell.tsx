'use client';

import Sidebar from '@/components/layout/Sidebar';
import { SidebarProvider, useSidebar } from '@/components/layout/sidebar-context';

function MainPanel({ children }: { children: React.ReactNode }) {
  const { collapsed } = useSidebar();
  return (
    <main
      className={`min-h-screen relative z-10 transition-[margin] duration-200 ease-out ${
        collapsed ? 'ml-[72px]' : 'ml-64'
      }`}
    >
      <div className="p-8">{children}</div>
    </main>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <SidebarProvider>
      <Sidebar />
      <MainPanel>{children}</MainPanel>
    </SidebarProvider>
  );
}
