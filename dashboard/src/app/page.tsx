'use client';

import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import GlowCard from '@/components/ui/GlowCard';
import AnimatedCounter from '@/components/ui/AnimatedCounter';
import NeonBadge from '@/components/ui/NeonBadge';
import FloatingButton from '@/components/ui/FloatingButton';
import { api, DashboardData, LiveSnapshot } from '@/lib/api';
import { useWebSocket } from '@/lib/websocket';
import { formatEAT, formatEATTime } from '@/lib/datetime';

const PROFIT_PERIODS = [
  { value: 'all', label: 'All time' },
  { value: 'today', label: 'Today' },
  { value: 'week', label: 'Week' },
  { value: 'month', label: '1 month' },
  { value: '3m', label: '3 months' },
  { value: '6m', label: '6 months' },
  { value: 'year', label: '1 year' },
] as const;

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [live, setLive] = useState<LiveSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [profitPeriod, setProfitPeriod] = useState<string>('all');
  const { events, connected } = useWebSocket();

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 10000);
    return () => clearInterval(interval);
  }, [profitPeriod]);

  useEffect(() => {
    let cancelled = false;
    async function pollLive() {
      try {
        const L = await api.live();
        if (!cancelled) setLive(L);
      } catch {
        /* optional endpoint */
      }
    }
    pollLive();
    const t = setInterval(pollLive, 4000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);

  async function loadData() {
    try {
      const d = await api.dashboard(profitPeriod);
      setData(d);
    } catch (e) {
      console.error('Dashboard load error:', e);
    } finally {
      setLoading(false);
    }
  }

  const periodLabel = PROFIT_PERIODS.find((p) => p.value === profitPeriod)?.label ?? 'Period';
  const displayTotalPnl =
    profitPeriod === 'all' ? data?.total_pnl ?? 0 : data?.period_pnl ?? data?.total_pnl ?? 0;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <motion.div
          className="text-4xl font-black"
          animate={{ opacity: [0.3, 1, 0.3] }}
          transition={{ duration: 1.5, repeat: Infinity }}
        >
          <span className="text-neon-cyan">Club</span>
          <span className="text-gold">Millies</span>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <motion.h1
            className="text-3xl font-black"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
          >
            Welcome to <span className="text-neon-cyan neon-text">Club</span>
            <span className="text-gold neon-text-gold">Millies</span>
          </motion.h1>
          <p className="text-gray-500 mt-1 text-sm italic">
            Not the best you can get but the best there is
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${connected ? 'bg-profit pulse-dot pulse-dot-green' : 'bg-loss'}`} />
          <span className="text-xs text-gray-500">{connected ? 'Live' : 'Disconnected'}</span>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-gray-500">P&amp;L window:</span>
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

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <GlowCard animate className="gradient-border">
          <p className="text-gray-500 text-sm mb-1">Total Balance</p>
          <AnimatedCounter value={data?.total_balance || 0} prefix="$" className="text-3xl font-bold text-white" />
          <p className="text-xs text-gray-600 mt-2">{data?.active_accounts || 0} active accounts</p>
        </GlowCard>

        <GlowCard animate glowColor={
          (data?.today_pnl || 0) >= 0 ? 'rgba(0, 230, 118, 0.3)' : 'rgba(255, 51, 102, 0.3)'
        }>
          <p className="text-gray-500 text-sm mb-1">Today P&L</p>
          <AnimatedCounter
            value={data?.today_pnl || 0}
            prefix={((data?.today_pnl || 0) >= 0) ? '+$' : '-$'}
            className={`text-3xl font-bold ${(data?.today_pnl || 0) >= 0 ? 'text-profit' : 'text-loss'}`}
          />
          <p className="text-xs text-gray-600 mt-2">{data?.today_trades || 0} trades today</p>
        </GlowCard>

        <GlowCard animate glowColor="rgba(255, 159, 28, 0.3)">
          <p className="text-gray-500 text-sm mb-1">Win Rate</p>
          <AnimatedCounter value={data?.win_rate || 0} suffix="%" className="text-3xl font-bold text-gold" />
          <p className="text-xs text-gray-600 mt-2">{data?.total_trades || 0} total trades</p>
        </GlowCard>

        <GlowCard animate>
          <p className="text-gray-500 text-sm mb-1">
            {profitPeriod === 'all' ? 'Total P&L' : `P&L (${periodLabel})`}
          </p>
          <AnimatedCounter
            value={displayTotalPnl}
            prefix={(displayTotalPnl >= 0) ? '+$' : '-$'}
            className={`text-3xl font-bold ${displayTotalPnl >= 0 ? 'text-profit' : 'text-loss'}`}
          />
          <p className="text-xs text-gray-600 mt-2">
            {profitPeriod !== 'all' && data?.total_pnl != null ? (
              <>All-time: {data.total_pnl >= 0 ? '+' : ''}${data.total_pnl.toFixed(2)} · </>
            ) : null}
            {profitPeriod !== 'all' && data?.period_trade_count != null ? (
              <>{data.period_trade_count} closed in window · </>
            ) : null}
            {profitPeriod !== 'all' && data?.period_win_rate != null ? (
              <>{data.period_win_rate}% win (window)</>
            ) : (
              profitPeriod === 'all' && 'All closed trades'
            )}
          </p>
        </GlowCard>
      </div>

      {/* Accounts + Recent Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Accounts */}
        <div className="lg:col-span-2 space-y-4">
          <h2 className="text-lg font-bold text-gray-300">Active Accounts</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {data?.accounts?.map((acc) => (
              <GlowCard key={acc.id} glowColor={acc.enabled ? 'rgba(0, 230, 118, 0.2)' : 'rgba(100,100,100,0.2)'}>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${acc.enabled ? 'bg-profit pulse-dot pulse-dot-green' : 'bg-gray-600'}`} />
                    <span className="font-bold">{acc.name}</span>
                  </div>
                  <NeonBadge
                    label={acc.profile}
                    variant={acc.profile === 'SNIPER' ? 'sniper' : 'aggressive'}
                  />
                </div>
                <div className="space-y-1">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">Balance</span>
                    <span className="font-mono">${acc.balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">Equity</span>
                    <span className="font-mono">${acc.equity.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">Symbol</span>
                    <span className="text-gold">{acc.symbol}</span>
                  </div>
                </div>
              </GlowCard>
            ))}
          </div>
        </div>

        {/* Live Feed */}
        <div>
          <h2 className="text-lg font-bold text-gray-300 mb-4">Live Feed</h2>
          {live && (
            <GlowCard className="mb-4 space-y-2">
              <div className="flex justify-between text-xs text-gray-500">
                <span>Spot XAU/USD (ref.)</span>
                <span className="font-mono text-gold">
                  {live.spot_xauusd != null ? `$${live.spot_xauusd.toFixed(2)}` : '—'}
                </span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-gray-500">Open positions</span>
                <span
                  className={`font-mono ${
                    (live.total_unrealized_pnl || 0) >= 0 ? 'text-profit' : 'text-loss'
                  }`}
                >
                  Σ unrealized:{' '}
                  {(live.total_unrealized_pnl || 0) >= 0 ? '+' : ''}
                  ${(live.total_unrealized_pnl || 0).toFixed(2)}
                </span>
              </div>
              <div className="max-h-[120px] overflow-y-auto space-y-1 border-t border-white/5 pt-2">
                {live.open_trades.length === 0 ? (
                  <p className="text-gray-600 text-[10px]">No open trades</p>
                ) : (
                  live.open_trades.map((ot) => (
                    <div key={ot.id} className="text-[10px] flex justify-between gap-2">
                      <span className="truncate">
                        {ot.account_name ?? `Acc ${ot.account_id}`}{' '}
                        {ot.symbol ? `· ${ot.symbol}` : ''} {ot.direction} @{' '}
                        {ot.entry_price?.toFixed(2)}
                      </span>
                      <span
                        className={
                          ot.unrealized_pnl == null
                            ? 'text-gray-600'
                            : ot.unrealized_pnl >= 0
                              ? 'text-profit'
                              : 'text-loss'
                        }
                      >
                        {ot.unrealized_pnl == null
                          ? '—'
                          : `${ot.unrealized_pnl >= 0 ? '+' : ''}$${ot.unrealized_pnl.toFixed(2)}`}
                      </span>
                    </div>
                  ))
                )}
              </div>
              <p className="text-[9px] text-gray-600">
                Updated {formatEATTime(live.updated_at)} EAT ·{' '}
                {live.source === 'mt5'
                  ? 'MT5 positions + live profit'
                  : 'DB open trades · est. P/L via Yahoo GC=F'}
              </p>
            </GlowCard>
          )}
          <GlowCard className="max-h-[400px] overflow-y-auto space-y-3">
            {events.length === 0 ? (
              <p className="text-gray-600 text-sm text-center py-8">Waiting for events...</p>
            ) : (
              events
                .filter((ev) => {
                  if (ev.type !== 'signal.generated') return true;
                  const sc = (ev.data as { score?: number })?.score ?? 0;
                  return sc >= 5;
                })
                .slice(0, 20)
                .map((ev, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="flex items-start gap-2 text-xs border-b border-white/5 pb-2"
                >
                  <span className="text-neon-cyan shrink-0">
                    {ev.type === 'trade.opened' ? '🟢' :
                     ev.type === 'trade.closed' ? (ev.data.pnl > 0 ? '✅' : '❌') :
                     ev.type === 'signal.generated' ? '⚡' :
                     ev.type === 'ai.analysis' ? '🤖' : '📌'}
                  </span>
                  <div>
                    <span className="text-gray-300">
                      {ev.type === 'trade.opened' && `${ev.data.direction} @ $${ev.data.price?.toFixed(2)} (${ev.data.score}/15)`}
                      {ev.type === 'trade.closed' && `Closed ${ev.data.direction} | ${ev.data.pnl > 0 ? '+' : ''}$${ev.data.pnl?.toFixed(2)} (${ev.data.reason})`}
                      {ev.type === 'signal.generated' && `Signal: ${ev.data.signal} @ $${ev.data.price?.toFixed(2)}`}
                      {ev.type === 'ai.analysis' && `AI: ${ev.data.direction} (${ev.data.confidence}%)`}
                    </span>
                    <span className="text-gray-600 ml-2">
                      {formatEATTime(ev.timestamp)}
                    </span>
                  </div>
                </motion.div>
              ))
            )}
          </GlowCard>
        </div>
      </div>

      {/* Recent Signals */}
      <div>
        <h2 className="text-lg font-bold text-gray-300 mb-4">Recent Signals</h2>
        <GlowCard>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-500 border-b border-white/5">
                  <th className="text-left py-2">Signal</th>
                  <th className="text-left py-2">Price</th>
                  <th className="text-left py-2">SL</th>
                  <th className="text-left py-2">TP</th>
                  <th className="text-left py-2">Score</th>
                  <th className="text-left py-2">Reasons</th>
                  <th className="text-left py-2">R:R</th>
                  <th className="text-left py-2">Time (EAT)</th>
                </tr>
              </thead>
              <tbody>
                {data?.recent_signals?.map((sig, i) => (
                  <tr key={i} className="border-b border-white/5">
                    <td className="py-2">
                      <NeonBadge
                        label={sig.signal}
                        variant={sig.signal === 'BUY' ? 'buy' : sig.signal === 'SELL' ? 'sell' : 'neutral'}
                      />
                    </td>
                    <td className="py-2 font-mono">${sig.price?.toFixed(2)}</td>
                    <td className="py-2 font-mono text-loss">{sig.sl ? `$${sig.sl.toFixed(2)}` : '-'}</td>
                    <td className="py-2 font-mono text-profit">{sig.tp ? `$${sig.tp.toFixed(2)}` : '-'}</td>
                    <td className="py-2">
                      <div className="flex items-center gap-2">
                        <div className="w-20 h-2 bg-dark-100 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-gradient-to-r from-neon-cyan to-gold rounded-full"
                            style={{ width: `${(sig.score / 15) * 100}%` }}
                          />
                        </div>
                        <span className="text-xs text-gray-400">{sig.score}/15</span>
                      </div>
                    </td>
                    <td className="py-2">
                      <div className="flex gap-1 flex-wrap">
                        {sig.reasons?.map((r: string, j: number) => (
                          <span key={j} className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-gray-400">{r}</span>
                        ))}
                      </div>
                    </td>
                    <td className="py-2 font-mono text-xs text-gray-400">
                      {sig.risk_reward != null ? `1:${sig.risk_reward}` : '—'}
                    </td>
                    <td className="py-2 text-gray-500 text-xs">
                      {sig.created_at ? formatEAT(sig.created_at) : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </GlowCard>
      </div>

      {/* Floating action button */}
      <FloatingButton onClick={loadData}>
        <span className="text-xl">🔄</span>
      </FloatingButton>
    </div>
  );
}
