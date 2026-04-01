'use client';

import { useEffect, useState } from 'react';
import GlowCard from '@/components/ui/GlowCard';

const INTEL_KEY = 'clubmillies_intel_query';

export default function SettingsPage() {
  const [intelQuery, setIntelQuery] = useState('');

  useEffect(() => {
    try {
      const s = localStorage.getItem(INTEL_KEY);
      if (s) setIntelQuery(s);
    } catch {
      /* ignore */
    }
  }, []);

  function persistIntel(q: string) {
    setIntelQuery(q);
    try {
      localStorage.setItem(INTEL_KEY, q);
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-2xl font-bold">Settings</h1>

      <GlowCard>
        <h2 className="text-lg font-bold mb-4">API Keys</h2>
        <p className="text-sm text-gray-500 mb-4">
          Configure these in your <code className="text-neon-cyan">.env</code> file on the server.
        </p>
        <div className="space-y-3">
          <div className="flex items-center justify-between p-3 rounded-lg bg-white/5">
            <div>
              <p className="font-medium">Telegram Bot</p>
              <p className="text-xs text-gray-500">Trade alerts & commands</p>
            </div>
            <span className="text-xs px-2 py-1 rounded bg-profit/20 text-profit">Active</span>
          </div>
          <div className="flex items-center justify-between p-3 rounded-lg bg-white/5">
            <div>
              <p className="font-medium">Anthropic (Claude AI)</p>
              <p className="text-xs text-gray-500">News & tweet analysis</p>
            </div>
            <span className="text-xs px-2 py-1 rounded bg-gold/20 text-gold">Set in .env</span>
          </div>
          <div className="flex items-center justify-between p-3 rounded-lg bg-white/5">
            <div>
              <p className="font-medium">Twitter/X API</p>
              <p className="text-xs text-gray-500">Market intelligence from key accounts</p>
            </div>
            <span className="text-xs px-2 py-1 rounded bg-gold/20 text-gold">Set in .env</span>
          </div>
        </div>
      </GlowCard>

      <GlowCard>
        <h2 className="text-lg font-bold mb-4">Strategy Profiles</h2>
        <div className="space-y-3">
          <div className="p-4 rounded-lg border border-neon-cyan/20 bg-neon-cyan/5">
            <div className="flex items-center justify-between mb-2">
              <span className="font-bold text-neon-cyan">SNIPER</span>
              <span className="text-xs text-gray-400">~85% Win Rate</span>
            </div>
            <div className="grid grid-cols-3 gap-2 text-xs text-gray-400">
              <div>Confluence: 7/15</div>
              <div>SL: 2.5x ATR</div>
              <div>TP: 0.6x ATR</div>
            </div>
          </div>
          <div className="p-4 rounded-lg border border-gold/20 bg-gold/5">
            <div className="flex items-center justify-between mb-2">
              <span className="font-bold text-gold">AGGRESSIVE</span>
              <span className="text-xs text-gray-400">~83% Win Rate</span>
            </div>
            <div className="grid grid-cols-3 gap-2 text-xs text-gray-400">
              <div>Confluence: 5/15</div>
              <div>SL: 2.5x ATR</div>
              <div>TP: 0.6x ATR</div>
            </div>
          </div>
        </div>
      </GlowCard>

      <GlowCard>
        <h2 className="text-lg font-bold mb-2">X / Twitter search (SociaVault)</h2>
        <p className="text-sm text-gray-500 mb-3">
          Default query for <span className="text-gray-400">News → Market intel → Fetch new tweets</span>.
          Stored in this browser only. Backend fallback: <code className="text-neon-cyan">INTEL_DEFAULT_QUERY</code> in{' '}
          <code className="text-gray-500">.env</code>.
        </p>
        <textarea
          className="w-full min-h-[88px] bg-dark-100 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder:text-gray-600 focus:border-neon-cyan/40 outline-none resize-y"
          value={intelQuery}
          onChange={(e) => persistIntel(e.target.value)}
          placeholder='e.g. gold OR XAUUSD OR DXY OR "us dollar index"'
        />
      </GlowCard>

      <GlowCard>
        <h2 className="text-lg font-bold mb-2">About</h2>
        <div className="text-center py-4">
          <p className="text-2xl font-black">
            <span className="text-neon-cyan">Club</span>
            <span className="text-gold">Millies</span>
          </p>
          <p className="text-sm text-gray-500 italic mt-1">Not the best you can get but the best there is</p>
          <p className="text-xs text-gray-600 mt-4">v1.0.0 — Multi-Confluence Gold Trading Bot</p>
        </div>
      </GlowCard>
    </div>
  );
}
