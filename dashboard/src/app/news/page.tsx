'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import GlowCard from '@/components/ui/GlowCard';
import NeonBadge from '@/components/ui/NeonBadge';
import { api, NewsData, AnalysisData } from '@/lib/api';
import { formatEAT } from '@/lib/datetime';

const SOURCE_LABEL: Record<string, string> = {
  news: 'Economic news',
  news_calendar: 'Calendar deep-dive (on-demand)',
  twitter: 'Twitter / headlines batch',
  market: 'Market snapshot',
  trade_close: 'Performance (after each close)',
};

export default function NewsPage() {
  const [news, setNews] = useState<NewsData[]>([]);
  const [analyses, setAnalyses] = useState<AnalysisData[]>([]);
  const [analyzingId, setAnalyzingId] = useState<number | null>(null);
  const [analyzeErr, setAnalyzeErr] = useState<string | null>(null);

  function isGarbageAnalysis(a: AnalysisData): boolean {
    const r = (a.reasoning || '').toLowerCase();
    return r.includes('no module named') && r.includes('anthropic');
  }

  useEffect(() => {
    function refresh() {
      api.news().then(setNews).catch(console.error);
      api.analyses('limit=40').then(setAnalyses).catch(console.error);
    }
    refresh();
    const t = setInterval(refresh, 45_000);
    return () => clearInterval(t);
  }, []);

  const grouped = useMemo(() => {
    const g: Record<string, AnalysisData[]> = {};
    for (const a of analyses) {
      if (isGarbageAnalysis(a)) continue;
      const k = a.source || 'other';
      if (!g[k]) g[k] = [];
      g[k].push(a);
    }
    for (const k of Object.keys(g)) {
      g[k].sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
    }
    return g;
  }, [analyses]);

  async function analyzeEvent(id: number) {
    setAnalyzeErr(null);
    setAnalyzingId(id);
    try {
      await api.analyzeNews(id);
      setAnalyses(await api.analyses('limit=40'));
    } catch (e) {
      setAnalyzeErr(e instanceof Error ? e.message : String(e));
    } finally {
      setAnalyzingId(null);
    }
  }

  const order = ['trade_close', 'market', 'news', 'news_calendar', 'twitter', 'other'];
  const keysToShow = [
    ...order.filter((k) => grouped[k]?.length),
    ...Object.keys(grouped).filter((k) => !order.includes(k)),
  ];

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">News & AI Analysis</h1>
        <p className="text-sm text-gray-500 mt-1 max-w-3xl">
          AI runs and economic calendar while this page is open. X / market intel lives on{' '}
          <Link href="/intel" className="text-neon-cyan/90 hover:text-neon-cyan underline underline-offset-2">
            Market intel
          </Link>
          .
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-8 gap-4 items-start">
        {/* AI Analyses — scrollable compact list */}
        <div className="xl:col-span-5 min-w-0">
          <div className="flex items-center justify-between mb-2 gap-2">
            <h2 className="text-lg font-bold text-gray-300">AI Analysis (Claude)</h2>
            <button
              type="button"
              onClick={() => api.analyses('limit=40').then(setAnalyses).catch(console.error)}
              className="text-xs px-2 py-1 rounded-lg border border-white/10 text-gray-400 hover:text-white"
            >
              Refresh
            </button>
          </div>
          <div className="max-h-[min(68vh,560px)] overflow-y-auto rounded-xl border border-white/10 bg-dark-100/40 pr-1">
            {analyses.filter((a) => !isGarbageAnalysis(a)).length === 0 ? (
              <div className="p-4 text-center text-gray-600 text-sm">
                No AI analyses yet. Set <code className="text-neon-cyan">ANTHROPIC_API_KEY</code> on the{' '}
                <strong>API server</strong> and <code className="text-gray-500">pip install anthropic</code>.
              </div>
            ) : (
              <div className="space-y-2 p-2">
                {keysToShow.map((key) => (
                  <div key={key} className="mb-4 last:mb-0">
                    <h3 className="text-[10px] font-semibold text-gold mb-1.5 uppercase tracking-wider px-1">
                      {SOURCE_LABEL[key] || key}
                    </h3>
                    <div className="space-y-2">
                      {grouped[key].map((a) => (
                        <div
                          key={a.id}
                          className={`rounded-lg border p-3 text-left ${
                            a.direction === 'bullish'
                              ? 'border-profit/25 bg-profit/5'
                              : a.direction === 'bearish'
                                ? 'border-loss/25 bg-loss/5'
                                : 'border-white/10 bg-white/[0.03]'
                          }`}
                        >
                          <div className="flex items-center justify-between gap-2 mb-1.5">
                            <span className="text-[10px] text-gray-500 uppercase">{a.source}</span>
                            <NeonBadge
                              label={a.direction.toUpperCase()}
                              variant={
                                a.direction === 'bullish'
                                  ? 'buy'
                                  : a.direction === 'bearish'
                                    ? 'sell'
                                    : 'neutral'
                              }
                            />
                          </div>
                          <div className="flex items-center gap-2 mb-1.5">
                            <span className="text-[10px] text-gray-500 shrink-0">Confidence</span>
                            <div className="flex-1 h-1.5 bg-dark-100 rounded-full overflow-hidden min-w-0">
                              <div
                                className={`h-full rounded-full ${
                                  a.confidence >= 70
                                    ? 'bg-profit'
                                    : a.confidence >= 40
                                      ? 'bg-gold'
                                      : 'bg-loss'
                                }`}
                                style={{ width: `${Math.min(100, a.confidence)}%` }}
                              />
                            </div>
                            <span className="text-[10px] font-bold tabular-nums">{a.confidence}%</span>
                          </div>
                          <p className="text-xs text-gray-300 leading-snug line-clamp-6">{a.reasoning}</p>
                          {a.metrics && (
                            <details className="mt-1.5 text-[10px] text-gray-600">
                              <summary className="cursor-pointer text-gray-500">Metrics</summary>
                              <pre className="mt-1 p-2 rounded bg-black/40 overflow-x-auto whitespace-pre-wrap max-h-32 overflow-y-auto">
                                {JSON.stringify(a.metrics, null, 2)}
                              </pre>
                            </details>
                          )}
                          <p className="text-[10px] text-gray-600 mt-1.5">{formatEAT(a.created_at)} EAT</p>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Economic Calendar */}
        <div className="xl:col-span-3 min-w-0">
          <h2 className="text-lg font-bold text-gray-300 mb-4">Economic Calendar</h2>
          {analyzeErr && (
            <p className="text-xs text-loss mb-2 whitespace-pre-wrap">{analyzeErr}</p>
          )}
          <GlowCard>
            {news.length === 0 ? (
              <p className="text-gray-600 text-center py-4">No events loaded yet (wait for monitor)</p>
            ) : (
              <div className="space-y-3 max-h-[70vh] overflow-y-auto pr-1">
                {news.map((n) => {
                  const impactColor =
                    n.impact === 'high'
                      ? 'text-loss'
                      : n.impact === 'medium'
                        ? 'text-gold'
                        : 'text-gray-500';
                  const impactBg =
                    n.impact === 'high'
                      ? 'bg-loss/20'
                      : n.impact === 'medium'
                        ? 'bg-gold/20'
                        : 'bg-white/5';
                  return (
                    <div key={n.id} className={`p-3 rounded-lg ${impactBg} border border-white/5`}>
                      <div className="flex items-center justify-between mb-1 gap-2">
                        <span className="font-medium text-sm leading-tight">{n.title}</span>
                        <span className={`text-xs font-bold uppercase shrink-0 ${impactColor}`}>
                          {n.impact}
                        </span>
                      </div>
                      <div className="flex gap-4 text-xs text-gray-500 flex-wrap">
                        <span>{n.currency}</span>
                        <span>Forecast: {n.forecast || '-'}</span>
                        <span>Previous: {n.previous || '-'}</span>
                        {n.actual && <span className="text-white font-bold">Actual: {n.actual}</span>}
                      </div>
                      <p className="text-[10px] text-gray-600 mt-1">
                        {formatEAT(n.event_time)} EAT
                      </p>
                      <button
                        type="button"
                        onClick={() => analyzeEvent(n.id)}
                        disabled={analyzingId === n.id}
                        className="mt-2 text-xs px-2 py-1 rounded-lg border border-neon-cyan/30 text-neon-cyan hover:bg-neon-cyan/10 disabled:opacity-40"
                      >
                        {analyzingId === n.id ? 'Analyzing…' : 'AI: analyze this event'}
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </GlowCard>

          <GlowCard className="mt-4 p-4 border-neon-cyan/15">
            <p className="text-sm font-semibold text-gray-200 mb-1">Market intel (X)</p>
            <p className="text-xs text-gray-500 leading-relaxed mb-3">
              Batch bias, per-post counts, and full-width posts — moved off this page so calendar and AI stay readable.
            </p>
            <Link
              href="/intel"
              className="inline-flex items-center justify-center w-full py-2.5 rounded-xl text-sm font-medium bg-neon-cyan/15 text-neon-cyan border border-neon-cyan/40 hover:bg-neon-cyan/25"
            >
              Open Market intel
            </Link>
          </GlowCard>
        </div>
      </div>
    </div>
  );
}
