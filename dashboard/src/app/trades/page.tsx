'use client';

import { useEffect, useState } from 'react';
import GlowCard from '@/components/ui/GlowCard';
import NeonBadge from '@/components/ui/NeonBadge';
import { api, TradeData, DashboardData } from '@/lib/api';
import { formatEAT } from '@/lib/datetime';
import { PROFIT_PERIODS } from '@/lib/profit-periods';

export default function TradesPage() {
  const [trades, setTrades] = useState<TradeData[]>([]);
  const [filter, setFilter] = useState('all');
  const [dash, setDash] = useState<DashboardData | null>(null);
  const [profitPeriod, setProfitPeriod] = useState<string>('all');

  useEffect(() => {
    loadTrades();
  }, [filter]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const d = await api.dashboard(profitPeriod);
        if (!cancelled) setDash(d);
      } catch (e) {
        console.error(e);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [profitPeriod]);

  async function loadTrades() {
    try {
      const q = new URLSearchParams();
      q.set('limit', '200');
      if (filter !== 'all') q.set('status', filter.toUpperCase());
      setTrades(await api.trades(q.toString()));
    } catch (e) {
      console.error(e);
    }
  }

  const periodLabel = PROFIT_PERIODS.find((p) => p.value === profitPeriod)?.label ?? 'Period';
  const displayWinRate =
    profitPeriod === 'all' ? dash?.win_rate ?? 0 : dash?.period_win_rate ?? dash?.win_rate ?? 0;
  const displayPnl =
    profitPeriod === 'all' ? dash?.total_pnl ?? 0 : dash?.period_pnl ?? 0;
  const displayClosedCount =
    profitPeriod === 'all' ? dash?.total_trades ?? 0 : dash?.period_trade_count ?? 0;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Trade History</h1>

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-gray-500">Stats window (same as dashboard):</span>
        {PROFIT_PERIODS.map((p) => (
          <button
            key={p.value}
            type="button"
            onClick={() => setProfitPeriod(p.value)}
            className={`text-xs px-2.5 py-1 rounded-lg border transition-colors ${
              profitPeriod === p.value
                ? 'border-neon-cyan/60 bg-neon-cyan/10 text-neon-cyan'
                : 'border-white/10 bg-white/5 text-gray-400 hover:border-white/20'
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>

      {/* Quick stats — from /api/dashboard so win rate & counts match dashboard */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <GlowCard>
          <p className="text-gray-500 text-xs">
            Closed P&amp;L{profitPeriod !== 'all' ? ` (${periodLabel})` : ''}
          </p>
          <p className={`text-2xl font-bold ${displayPnl >= 0 ? 'text-profit' : 'text-loss'}`}>
            {displayPnl >= 0 ? '+' : ''}${displayPnl.toFixed(2)}
          </p>
          {profitPeriod !== 'all' && dash?.total_pnl != null ? (
            <p className="text-[10px] text-gray-600 mt-1">
              All-time: {dash.total_pnl >= 0 ? '+' : ''}${dash.total_pnl.toFixed(2)}
            </p>
          ) : null}
        </GlowCard>
        <GlowCard>
          <p className="text-gray-500 text-xs">
            Win rate{profitPeriod !== 'all' ? ` (${periodLabel})` : ''}
          </p>
          <p className="text-2xl font-bold text-gold">{displayWinRate.toFixed(1)}%</p>
          <p className="text-[10px] text-gray-600 mt-1">
            {displayClosedCount} closed in window · dashboard formula
          </p>
        </GlowCard>
        <GlowCard>
          <p className="text-gray-500 text-xs">Table rows (this view)</p>
          <p className="text-2xl font-bold">
            {trades.filter((t) => t.status === 'CLOSED').length}
            <span className="text-sm text-gray-500 font-normal"> / {trades.length}</span>
          </p>
          <p className="text-[10px] text-gray-600 mt-1">Up to 200 rows by last activity</p>
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
                <th className="text-left py-3 px-2">Closed (EAT)</th>
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
                  <td className="py-2 px-2 text-gray-500 text-xs">
                    {t.closed_at ? formatEAT(t.closed_at) : '—'}
                  </td>
                </tr>
              ))}
              {trades.length === 0 && (
                <tr><td colSpan={10} className="text-center py-8 text-gray-600">No trades yet</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </GlowCard>
    </div>
  );
}
