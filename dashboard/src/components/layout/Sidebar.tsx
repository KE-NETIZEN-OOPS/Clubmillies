'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { motion } from 'framer-motion';

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

  return (
    <aside className="fixed left-0 top-0 h-full w-64 bg-dark-200/80 backdrop-blur-xl border-r border-neon-cyan/10 z-40 flex flex-col">
      {/* Brand */}
      <div className="p-6 border-b border-neon-cyan/10">
        <motion.h1
          className="text-2xl font-black tracking-tight"
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
        <p className="text-[10px] text-gray-500 mt-1 italic">
          Not the best you can get but the best there is
        </p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4 space-y-1">
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href;
          return (
            <Link key={item.href} href={item.href}>
              <motion.div
                className={`flex items-center gap-3 px-4 py-3 rounded-xl transition-all text-sm
                  ${active
                    ? 'bg-neon-cyan/10 text-neon-cyan border border-neon-cyan/20 shadow-glow'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                  }`}
                whileHover={{ x: 4 }}
                whileTap={{ scale: 0.98 }}
              >
                <span className="text-lg">{item.icon}</span>
                <span className="font-medium">{item.label}</span>
                {active && (
                  <motion.div
                    className="ml-auto w-2 h-2 rounded-full bg-neon-cyan pulse-dot pulse-dot-green"
                    layoutId="nav-indicator"
                  />
                )}
              </motion.div>
            </Link>
          );
        })}
      </nav>

      {/* Status footer */}
      <div className="p-4 border-t border-neon-cyan/10">
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <div className="w-2 h-2 rounded-full bg-profit pulse-dot pulse-dot-green" />
          <span>Bot Running</span>
        </div>
      </div>
    </aside>
  );
}
