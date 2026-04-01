'use client';

import { useEffect, useMemo, useState } from 'react';
import GlowCard from '@/components/ui/GlowCard';
import NeonBadge from '@/components/ui/NeonBadge';
import { api, NewsData, AnalysisData, TweetData } from '@/lib/api';
import { motion } from 'framer-motion';
import { formatEAT } from '@/lib/datetime';

const INTEL_KEY = 'clubmillies_intel_query';

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
  const [tweets, setTweets] = useState<TweetData[]>([]);
  const [intelQuery, setIntelQuery] = useState('');
  const [intelReady, setIntelReady] = useState(false);
  const [intelLoading, setIntelLoading] = useState(false);
  const [intelError, setIntelError] = useState<string | null>(null);
  const [intelLast, setIntelLast] = useState<string | null>(null);
  const [analyzingId, setAnalyzingId] = useState<number | null>(null);
  const [analyzeErr, setAnalyzeErr] = useState<string | null>(null);

  function isGarbageAnalysis(a: AnalysisData): boolean {
    const r = (a.reasoning || '').toLowerCase();
    return r.includes('no module named') && r.includes('anthropic');
  }

  useEffect(() => {
    let saved = '';
    try {
      saved = localStorage.getItem(INTEL_KEY) || '';
    } catch {
      /* ignore */
    }
    api
      .intelConfig()
      .then((c) => {
        setIntelQuery(saved || c.default_query || '');
        setIntelReady(c.sociavault_configured);
      })
      .catch(console.error);
  }, []);

  useEffect(() => {
    function refresh() {
      api.news().then(setNews).catch(console.error);
      api.analyses('limit=40').then(setAnalyses).catch(console.error);
      api.tweets().then(setTweets).catch(console.error);
    }
    refresh();
    const t = setInterval(refresh, 45_000);
    return () => clearInterval(t);
  }, []);

  async function handleFetchIntel() {
    setIntelError(null);
    setIntelLoading(true);
    try {
      const r = await api.fetchIntelTweets(intelQuery.trim() || undefined);
      setIntelLast(
        `Found ${r.tweets_found} posts (${r.tweets_new_rows} new in DB). ` +
          `${r.sociavault_requests} SociaVault request · AI: ${r.analysis.direction} (${r.analysis.confidence}%)`
      );
      const [tList, aList] = await Promise.all([
        api.tweets(),
        api.analyses('limit=40'),
      ]);
      setTweets(tList);
      setAnalyses(aList);
    } catch (e) {
      setIntelError(e instanceof Error ? e.message : String(e));
    } finally {
      setIntelLoading(false);
    }
  }

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
          AI cards show <span className="text-gray-400">direction + confidence bars</span> because each
          run is scored for bullish / bearish bias. Performance summaries include a JSON metrics block
          for ROI — that is intentional for transparency. Economic events use a public calendar JSON
          (not ForexFactory HTML) to avoid 403 blocks. This page refreshes every 45s while open.
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 items-start">
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
        <div className="xl:col-span-4 min-w-0">
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
        </div>

        {/* Intel (tweets + news headlines) */}
        <div className="xl:col-span-3 min-w-0">
          <h2 className="text-lg font-bold text-gray-300 mb-4">Market intel</h2>
          <p className="text-xs text-gray-600 mb-3">
            Google News + account RSS still fill in the background.{' '}
            <span className="text-gold">X search via SociaVault is manual only</span> (one API credit per
            button click). Set <code className="text-gray-400">SOCIAVAULT_API_KEY</code> and optional{' '}
            <code className="text-gray-400">INTEL_DEFAULT_QUERY</code> in the backend{' '}
            <code className="text-gray-400">.env</code>.
          </p>
          <div className="mb-3 space-y-2">
            <label className="text-xs text-gray-500 block">X / Twitter search query (one request per fetch)</label>
            <textarea
              className="w-full min-h-[72px] bg-dark-100 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder:text-gray-600 focus:border-neon-cyan/40 outline-none resize-y"
              value={intelQuery}
              onChange={(e) => {
                const v = e.target.value;
                setIntelQuery(v);
                try {
                  localStorage.setItem(INTEL_KEY, v);
                } catch {
                  /* ignore */
                }
              }}
              placeholder='e.g. gold OR XAUUSD OR DXY OR war'
              disabled={intelLoading}
            />
            <motion.button
              type="button"
              onClick={() => handleFetchIntel()}
              disabled={!intelReady || intelLoading}
              className="w-full py-2.5 rounded-xl font-medium text-sm bg-neon-cyan/20 text-neon-cyan border border-neon-cyan/40 hover:shadow-glow disabled:opacity-40 disabled:cursor-not-allowed transition-all"
              whileTap={{ scale: intelReady && !intelLoading ? 0.98 : 1 }}
            >
              {intelLoading ? 'Fetching…' : 'Fetch new tweets'}
            </motion.button>
            {!intelReady && (
              <p className="text-xs text-loss">
                SociaVault is not configured (add SOCIAVAULT_API_KEY to the API server .env and restart).
              </p>
            )}
            {intelError && <p className="text-xs text-loss whitespace-pre-wrap">{intelError}</p>}
            {intelLast && !intelError && (
              <p className="text-xs text-profit/90 border border-profit/20 rounded-lg p-2 bg-profit/5">{intelLast}</p>
            )}
          </div>
          <GlowCard>
            {tweets.length === 0 ? (
              <p className="text-gray-600 text-center py-4">
                No items yet. Add Google News queries or fix Twitter API / RSS bridges.
              </p>
            ) : (
              <div className="space-y-3 max-h-[70vh] overflow-y-auto">
                {tweets.map((t) => (
                  <div key={t.id} className="p-3 rounded-lg bg-white/5 border border-white/5">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs text-gray-500">@{t.author}</span>
                      {t.url ? (
                        <a
                          className="text-xs text-neon-cyan hover:underline"
                          href={t.url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          open
                        </a>
                      ) : null}
                    </div>
                    <p className="text-sm text-gray-400 whitespace-pre-wrap">{t.text}</p>
                    <p className="text-[10px] text-gray-600 mt-2">
                      {t.created_at
                        ? formatEAT(t.created_at)
                        : t.fetched_at
                          ? formatEAT(t.fetched_at)
                          : ''}{' '}
                      EAT
                    </p>
                  </div>
                ))}
              </div>
            )}
          </GlowCard>
        </div>
      </div>
    </div>
  );
}
