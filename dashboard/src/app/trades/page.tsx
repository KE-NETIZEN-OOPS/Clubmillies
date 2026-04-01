'use client';

import { useEffect, useState } from 'react';
import GlowCard from '@/components/ui/GlowCard';
import NeonBadge from '@/components/ui/NeonBadge';
import { api, TradeData } from '@/lib/api';
import { formatEAT } from '@/lib/datetime';

export default function TradesPage() {
  const [trades, setTrades] = useState<TradeData[]>([]);
  const [filter, setFilter] = useState('all');

  useEffect(() => { loadTrades(); }, [filter]);

  async function loadTrades() {
    try {
      const params = filter !== 'all' ? `status=${filter.toUpperCase()}` : '';
      setTrades(await api.trades(params));
    } catch (e) { console.error(e); }
  }

  const totalPnl = trades.reduce((sum, t) => sum + (t.pnl || 0), 0);
  const wins = trades.filter((t) => (t.pnl || 0) > 0).length;
  const winRate = trades.length > 0 ? (wins / trades.length * 100) : 0;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Trade History</h1>

      {/* Quick stats */}
      <div className="grid grid-cols-3 gap-4">
        <GlowCard>
          <p className="text-gray-500 text-xs">Total P&L</p>
          <p className={`text-2xl font-bold ${totalPnl >= 0 ? 'text-profit' : 'text-loss'}`}>
            {totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(2)}
          </p>
        </GlowCard>
        <GlowCard>
          <p className="text-gray-500 text-xs">Win Rate</p>
          <p className="text-2xl font-bold text-gold">{winRate.toFixed(1)}%</p>
        </GlowCard>
        <GlowCard>
          <p className="text-gray-500 text-xs">Total Trades</p>
          <p className="text-2xl font-bold">{trades.length}</p>
        </GlowCard>
      </div>

      {/* Filter */}
      <div className="flex gap-2">
        {['all', 'closed', 'open'].map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-4 py-1.5 rounded-lg text-sm transition-all ${
              filter === f ? 'bg-neon-cyan/20 text-neon-cyan border border-neon-cyan/30' : 'text-gray-500 hover:text-white'
            }`}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>

      {/* Table */}
      <GlowCard>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-500 border-b border-white/5">
                <th className="text-left py-3 px-2">Direction</th>
                <th className="text-left py-3 px-2">Entry</th>
                <th className="text-left py-3 px-2">Exit</th>
                <th className="text-left py-3 px-2">Lots</th>
                <th className="text-left py-3 px-2">P&L</th>
                <th className="text-left py-3 px-2">Score</th>
                <th className="text-left py-3 px-2">Reason</th>
                <th className="text-left py-3 px-2">Status</th>
                <th className="text-left py-3 px-2">Opened (EAT)</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t) => (
                <tr key={t.id} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                  <td className="py-2 px-2">
                    <NeonBadge label={t.direction} variant={t.direction === 'BUY' ? 'buy' : 'sell'} />
                  </td>
                  <td className="py-2 px-2 font-mono">${t.entry_price?.toFixed(2)}</td>
                  <td className="py-2 px-2 font-mono">{t.exit_price ? `$${t.exit_price.toFixed(2)}` : '-'}</td>
                  <td className="py-2 px-2">{t.lots}</td>
                  <td className={`py-2 px-2 font-mono font-bold ${(t.pnl || 0) >= 0 ? 'text-profit' : 'text-loss'}`}>
                    {t.pnl !== null ? `${t.pnl >= 0 ? '+' : ''}$${t.pnl.toFixed(2)}` : '-'}
                  </td>
                  <td className="py-2 px-2">{t.confluence_score}/15</td>
                  <td className="py-2 px-2 text-gray-400">{t.close_reason || '-'}</td>
                  <td className="py-2 px-2">
                    <NeonBadge label={t.status} variant={t.status === 'OPEN' ? 'buy' : 'neutral'} />
                  </td>
                  <td className="py-2 px-2 text-gray-500 text-xs">
                    {t.opened_at ? formatEAT(t.opened_at) : '-'}
                  </td>
                </tr>
              ))}
              {trades.length === 0 && (
                <tr><td colSpan={9} className="text-center py-8 text-gray-600">No trades yet</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </GlowCard>
    </div>
  );
}
