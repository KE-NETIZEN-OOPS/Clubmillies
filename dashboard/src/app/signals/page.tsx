'use client';

import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import GlowCard from '@/components/ui/GlowCard';
import NeonBadge from '@/components/ui/NeonBadge';
import { api, SignalData } from '@/lib/api';
import { useWebSocket } from '@/lib/websocket';
import { formatEAT } from '@/lib/datetime';

const CONFLUENCE_FACTORS = [
  { key: 'EMA_TREND', label: 'EMA Trend', weight: 1 },
  { key: 'FVG', label: 'Fair Value Gap', weight: 2 },
  { key: 'DEMAND_ZONE', label: 'Demand Zone', weight: 2 },
  { key: 'SUPPLY_ZONE', label: 'Supply Zone', weight: 2 },
  { key: 'LIQ_SWEEP', label: 'Liquidity Sweep', weight: 3 },
  { key: 'SR_REJECT', label: 'S/R Rejection', weight: 2 },
  { key: 'BOS', label: 'Break of Structure', weight: 2 },
  { key: 'FIB', label: 'Fibonacci', weight: 2 },
  { key: 'RSI_OK', label: 'RSI Confirm', weight: 1 },
];

export default function SignalsPage() {
  const [signals, setSignals] = useState<SignalData[]>([]);
  const { events } = useWebSocket();

  useEffect(() => { loadSignals(); }, []);

  async function loadSignals() {
    try {
      setSignals(await api.signals('min_score=5'));
    } catch (e) {
      console.error(e);
    }
  }

  const latestSignal = signals[0];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Live Signals</h1>

      {/* Current Signal */}
      {latestSignal && (
        <GlowCard className="gradient-border" glowColor={
          latestSignal.signal === 'BUY' ? 'rgba(0,230,118,0.3)' :
          latestSignal.signal === 'SELL' ? 'rgba(255,51,102,0.3)' : 'rgba(100,100,100,0.2)'
        }>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold">Current Signal</h2>
            <NeonBadge
              label={latestSignal.signal}
              variant={latestSignal.signal === 'BUY' ? 'buy' : latestSignal.signal === 'SELL' ? 'sell' : 'neutral'}
              size="md"
            />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div><p className="text-gray-500 text-xs">Price</p><p className="font-mono text-xl">${latestSignal.price?.toFixed(2)}</p></div>
            <div><p className="text-gray-500 text-xs">Score</p><p className="text-xl font-bold text-gold">{latestSignal.score}/15</p></div>
            <div><p className="text-gray-500 text-xs">R:R (plan)</p><p className="text-xl font-mono text-neon-cyan">{latestSignal.risk_reward != null ? `1:${latestSignal.risk_reward}` : '—'}</p></div>
            <div><p className="text-gray-500 text-xs">RSI</p><p className="text-xl">{latestSignal.rsi?.toFixed(1) || '-'}</p></div>
          </div>

          {/* Confluence Radar */}
          <h3 className="text-sm font-bold text-gray-400 mb-3">Confluence Breakdown</h3>
          <div className="grid grid-cols-3 gap-2">
            {CONFLUENCE_FACTORS.map((factor) => {
              const active = latestSignal.reasons?.some((r: string) =>
                r.toUpperCase().includes(factor.key.split('_')[0])
              );
              return (
                <div
                  key={factor.key}
                  className={`p-2 rounded-lg text-xs text-center transition-all ${
                    active
                      ? 'bg-profit/20 text-profit border border-profit/30 shadow-glow-profit'
                      : 'bg-white/5 text-gray-600 border border-white/5'
                  }`}
                >
                  <div className="font-bold">{factor.label}</div>
                  <div className="text-[10px] mt-0.5">{active ? `+${factor.weight}` : '0'}</div>
                </div>
              );
            })}
          </div>
        </GlowCard>
      )}

      {/* Signal History */}
      <h2 className="text-lg font-bold text-gray-300">Signal History</h2>
      <GlowCard>
        <div className="space-y-2 max-h-[500px] overflow-y-auto">
          {signals.map((sig, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex items-center gap-4 p-3 rounded-lg hover:bg-white/5 transition-all border-b border-white/5"
            >
              <NeonBadge label={sig.signal} variant={sig.signal === 'BUY' ? 'buy' : sig.signal === 'SELL' ? 'sell' : 'neutral'} />
              <span className="font-mono">${sig.price?.toFixed(2)}</span>
              <div className="flex items-center gap-1">
                <div className="w-16 h-1.5 bg-dark-100 rounded-full overflow-hidden">
                  <div className="h-full bg-gradient-to-r from-neon-cyan to-gold rounded-full" style={{ width: `${(sig.score / 15) * 100}%` }} />
                </div>
                <span className="text-xs text-gray-500">{sig.score}/15</span>
              </div>
              <div className="flex gap-1 flex-wrap flex-1">
                {sig.reasons?.map((r: string, j: number) => (
                  <span key={j} className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-gray-400">{r}</span>
                ))}
              </div>
              <span className="text-xs text-gray-600 shrink-0">
                {sig.created_at ? formatEAT(sig.created_at) : '-'}
              </span>
            </motion.div>
          ))}
        </div>
      </GlowCard>
    </div>
  );
}
