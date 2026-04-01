'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { motion } from 'framer-motion';
import { useSidebar } from '@/components/layout/sidebar-context';

const NAV_ITEMS = [
  { href: '/', label: 'Dashboard', icon: '📊' },
  { href: '/accounts', label: 'Accounts', icon: '👥' },
  { href: '/trades', label: 'Trades', icon: '📋' },
  { href: '/signals', label: 'Signals', icon: '⚡' },
  { href: '/news', label: 'News & AI', icon: '🤖' },
  { href: '/settings', label: 'Settings', icon: '⚙️' },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { collapsed, toggle } = useSidebar();

  return (
    <aside
      className={`fixed left-0 top-0 h-full bg-dark-200/80 backdrop-blur-xl border-r border-neon-cyan/10 z-40 flex flex-col transition-[width] duration-200 ease-out ${
        collapsed ? 'w-[72px]' : 'w-64'
      }`}
    >
      {/* Brand */}
      <div className={`p-4 border-b border-neon-cyan/10 flex items-center gap-2 ${collapsed ? 'flex-col' : ''}`}>
        {!collapsed && (
          <motion.h1
            className="text-2xl font-black tracking-tight flex-1 min-w-0"
            animate={{
              textShadow: [
                '0 0 10px rgba(0, 212, 255, 0.3)',
                '0 0 20px rgba(0, 212, 255, 0.5)',
                '0 0 10px rgba(0, 212, 255, 0.3)',
              ],
            }}
            transition={{ duration: 2, repeat: Infinity }}
          >
            <span className="text-neon-cyan">Club</span>
            <span className="text-gold">Millies</span>
          </motion.h1>
        )}
        <button
          type="button"
          onClick={toggle}
          className="shrink-0 w-9 h-9 rounded-lg border border-white/10 text-gray-400 hover:text-white hover:bg-white/5 text-sm flex items-center justify-center"
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-expanded={!collapsed}
        >
          {collapsed ? '›' : '‹'}
        </button>
      </div>
      {!collapsed && (
        <p className="px-6 pb-3 text-[10px] text-gray-500 italic border-b border-neon-cyan/10">
          Not the best you can get but the best there is
        </p>
      )}

      {/* Navigation */}
      <nav className="flex-1 p-2 space-y-1 overflow-y-auto">
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href;
          return (
            <Link key={item.href} href={item.href} title={item.label}>
              <motion.div
                className={`flex items-center gap-3 px-3 py-3 rounded-xl transition-all text-sm
                  ${active
                    ? 'bg-neon-cyan/10 text-neon-cyan border border-neon-cyan/20 shadow-glow'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                  } ${collapsed ? 'justify-center' : ''}`}
                whileHover={{ x: collapsed ? 0 : 4 }}
                whileTap={{ scale: 0.98 }}
              >
                <span className="text-lg shrink-0">{item.icon}</span>
                {!collapsed && <span className="font-medium truncate">{item.label}</span>}
                {!collapsed && active && (
                  <motion.div
                    className="ml-auto w-2 h-2 rounded-full bg-neon-cyan pulse-dot pulse-dot-green shrink-0"
                    layoutId="nav-indicator"
                  />
                )}
              </motion.div>
            </Link>
          );
        })}
      </nav>

      {/* Status footer */}
      {!collapsed && (
        <div className="p-4 border-t border-neon-cyan/10">
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <div className="w-2 h-2 rounded-full bg-profit pulse-dot pulse-dot-green" />
            <span>Bot Running</span>
          </div>
        </div>
      )}
    </aside>
  );
}
