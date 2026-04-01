'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { motion } from 'framer-motion';
import GlowCard from '@/components/ui/GlowCard';
import NeonBadge from '@/components/ui/NeonBadge';
import { api, AccountDetailData } from '@/lib/api';

export default function AccountDetailPage() {
  const params = useParams();
  const id = Number(params.id);
  const [data, setData] = useState<AccountDetailData | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    (async () => {
      try {
        setData(await api.account(id));
        setErr(null);
      } catch (e) {
        setErr('Could not load account');
        console.error(e);
      }
    })();
  }, [id]);

  if (err) {
    return (
      <div className="space-y-4">
        <Link href="/accounts" className="text-neon-cyan hover:underline text-sm">
          ← Back to accounts
        </Link>
        <p className="text-gray-400">{err}</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="space-y-4">
        <Link href="/accounts" className="text-neon-cyan hover:underline text-sm">
          ← Back to accounts
        </Link>
        <p className="text-gray-400">Loading…</p>
      </div>
    );
  }

  const demoLabel =
    data.is_demo === true ? 'Demo' : data.is_demo === false ? 'Live' : data.broker_type === 'paper' ? 'Paper' : '—';

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center gap-4">
        <Link href="/accounts" className="text-neon-cyan hover:underline text-sm">
          ← Accounts
        </Link>
        <h1 className="text-2xl font-bold">{data.name}</h1>
        <NeonBadge label={data.profile} variant={data.profile === 'SNIPER' ? 'sniper' : 'aggressive'} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <GlowCard animate>
          <h2 className="text-lg font-semibold mb-4 text-gold">Broker & account</h2>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between gap-4">
              <dt className="text-gray-500">Account # / login</dt>
              <dd className="font-mono text-right">{data.login || '—'}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-gray-500">Environment</dt>
              <dd className="text-right">{demoLabel}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-gray-500">Server</dt>
              <dd className="text-right truncate max-w-[200px]" title={data.server}>
                {data.server || '—'}
              </dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-gray-500">Broker type</dt>
              <dd className="text-right uppercase">{data.broker_type}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-gray-500">Symbol</dt>
              <dd className="text-gold text-right">{data.symbol}</dd>
            </div>
          </dl>
        </GlowCard>

        <GlowCard animate>
          <h2 className="text-lg font-semibold mb-4 text-gold">P/L & ROI</h2>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between gap-4">
              <dt className="text-gray-500">Starting balance</dt>
              <dd className="font-mono">${data.starting_balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-gray-500">Balance / equity</dt>
              <dd className="font-mono">
                ${data.balance.toFixed(2)} / ${data.equity.toFixed(2)}
              </dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-gray-500">Total realized P/L</dt>
              <dd
                className={`font-mono font-medium ${
                  data.stats.total_realized_pnl >= 0 ? 'text-profit' : 'text-loss'
                }`}
              >
                {data.stats.total_realized_pnl >= 0 ? '+' : ''}
                ${data.stats.total_realized_pnl.toFixed(2)}
              </dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-gray-500">ROI vs starting</dt>
              <dd
                className={`font-mono font-medium ${
                  data.stats.roi_vs_starting_balance_pct >= 0 ? 'text-profit' : 'text-loss'
                }`}
              >
                {data.stats.roi_vs_starting_balance_pct >= 0 ? '+' : ''}
                {data.stats.roi_vs_starting_balance_pct}%
              </dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-gray-500">Closed trades</dt>
              <dd className="font-mono">{data.stats.closed_trade_count}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-gray-500">Win rate (closed)</dt>
              <dd className="font-mono">{data.stats.win_rate_pct}%</dd>
            </div>
          </dl>
        </GlowCard>
      </div>

      {data.latest_performance_ai && (
        <GlowCard animate>
          <h2 className="text-lg font-semibold mb-2 text-gold">Latest AI performance note</h2>
          <p className="text-xs text-gray-500 mb-3">
            Updates after each closed trade (metrics + commentary when AI is enabled).
          </p>
          <p className="text-gray-200 leading-relaxed">{data.latest_performance_ai.reasoning}</p>
          {data.latest_performance_ai.metrics && (
            <pre className="mt-4 p-3 rounded-lg bg-black/40 border border-white/10 text-xs overflow-x-auto text-gray-400">
              {JSON.stringify(data.latest_performance_ai.metrics, null, 2)}
            </pre>
          )}
        </GlowCard>
      )}

      {data.open_trades.length > 0 && (
        <GlowCard animate>
          <h2 className="text-lg font-semibold mb-4">Open trades</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b border-white/10">
                  <th className="pb-2 pr-2">Dir</th>
                  <th className="pb-2 pr-2">Entry</th>
                  <th className="pb-2 pr-2">Lots</th>
                  <th className="pb-2 pr-2">MT5 #</th>
                  <th className="pb-2">Opened</th>
                </tr>
              </thead>
              <tbody>
                {data.open_trades.map((t) => (
                  <tr key={t.id} className="border-b border-white/5">
                    <td className="py-2 pr-2">{t.direction}</td>
                    <td className="font-mono py-2 pr-2">{t.entry_price?.toFixed(2)}</td>
                    <td className="py-2 pr-2">{t.lots}</td>
                    <td className="font-mono py-2 pr-2">{t.mt5_position_ticket ?? '—'}</td>
                    <td className="text-gray-500 py-2">{t.opened_at?.slice(0, 16)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </GlowCard>
      )}

      <GlowCard animate>
        <h2 className="text-lg font-semibold mb-4">Closed trades</h2>
        {data.closed_trades.length === 0 ? (
          <p className="text-gray-500 text-sm">No closed trades recorded yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b border-white/10">
                  <th className="pb-2 pr-2">Dir</th>
                  <th className="pb-2 pr-2">Entry</th>
                  <th className="pb-2 pr-2">Exit</th>
                  <th className="pb-2 pr-2">P/L</th>
                  <th className="pb-2 pr-2">Reason</th>
                  <th className="pb-2">Closed</th>
                </tr>
              </thead>
              <tbody>
                {data.closed_trades.map((t) => (
                  <motion.tr
                    key={t.id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="border-b border-white/5"
                  >
                    <td className="py-2 pr-2">{t.direction}</td>
                    <td className="font-mono py-2 pr-2">{t.entry_price?.toFixed(2)}</td>
                    <td className="font-mono py-2 pr-2">{t.exit_price?.toFixed(2) ?? '—'}</td>
                    <td
                      className={`font-mono py-2 pr-2 ${
                        (t.pnl ?? 0) >= 0 ? 'text-profit' : 'text-loss'
                      }`}
                    >
                      {(t.pnl ?? 0) >= 0 ? '+' : ''}
                      ${(t.pnl ?? 0).toFixed(2)}
                    </td>
                    <td className="py-2 pr-2 text-gray-400">{t.close_reason ?? '—'}</td>
                    <td className="text-gray-500 py-2">{t.closed_at?.slice(0, 16) ?? '—'}</td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </GlowCard>
    </div>
  );
}
