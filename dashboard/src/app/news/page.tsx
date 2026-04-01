'use client';

import { useEffect, useMemo, useState } from 'react';
import GlowCard from '@/components/ui/GlowCard';
import NeonBadge from '@/components/ui/NeonBadge';
import { api, NewsData, AnalysisData, TweetData } from '@/lib/api';
import { motion } from 'framer-motion';

const SOURCE_LABEL: Record<string, string> = {
  news: 'Economic news',
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

  useEffect(() => {
    api.news().then(setNews).catch(console.error);
    api.analyses('limit=40').then(setAnalyses).catch(console.error);
    api.tweets().then(setTweets).catch(console.error);
    api
      .intelConfig()
      .then((c) => {
        setIntelQuery(c.default_query || '');
        setIntelReady(c.sociavault_configured);
      })
      .catch(console.error);
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
      const k = a.source || 'other';
      if (!g[k]) g[k] = [];
      g[k].push(a);
    }
    return g;
  }, [analyses]);

  const order = ['trade_close', 'market', 'news', 'twitter', 'other'];
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
          (not ForexFactory HTML) to avoid 403 blocks.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* AI Analyses — grouped by source */}
        <div>
          <h2 className="text-lg font-bold text-gray-300 mb-4">AI Analysis (Claude)</h2>
          <div className="space-y-6">
            {analyses.length === 0 ? (
              <GlowCard>
                <p className="text-gray-600 text-center py-4">
                  No AI analyses yet. Set <code className="text-neon-cyan">ANTHROPIC_API_KEY</code> in
                  .env
                </p>
              </GlowCard>
            ) : (
              keysToShow.map((key) => (
                  <div key={key}>
                    <h3 className="text-xs font-semibold text-gold mb-2 uppercase tracking-wider">
                      {SOURCE_LABEL[key] || key}
                    </h3>
                    <div className="space-y-3">
                      {grouped[key].map((a) => (
                        <GlowCard
                          key={a.id}
                          glowColor={
                            a.direction === 'bullish'
                              ? 'rgba(0,230,118,0.2)'
                              : a.direction === 'bearish'
                                ? 'rgba(255,51,102,0.2)'
                                : 'rgba(100,100,100,0.1)'
                          }
                        >
                          <div className="flex items-center justify-between mb-2">
                            <NeonBadge label={(a.source || 'ai').toUpperCase()} variant="neutral" />
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
                          <div className="mb-2">
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-xs text-gray-500">Confidence</span>
                              <div className="flex-1 h-2 bg-dark-100 rounded-full overflow-hidden">
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
                              <span className="text-xs font-bold">{a.confidence}%</span>
                            </div>
                          </div>
                          <p className="text-sm text-gray-300 leading-relaxed">{a.reasoning}</p>
                          {a.metrics && (
                            <details className="mt-2 text-[10px] text-gray-600">
                              <summary className="cursor-pointer text-gray-500">Metrics JSON</summary>
                              <pre className="mt-1 p-2 rounded bg-black/40 overflow-x-auto whitespace-pre-wrap">
                                {JSON.stringify(a.metrics, null, 2)}
                              </pre>
                            </details>
                          )}
                          <p className="text-[10px] text-gray-600 mt-2">
                            {new Date(a.created_at).toLocaleString()}
                          </p>
                        </GlowCard>
                      ))}
                    </div>
                  </div>
                ))
            )}
          </div>
        </div>

        {/* Economic Calendar */}
        <div>
          <h2 className="text-lg font-bold text-gray-300 mb-4">Economic Calendar</h2>
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
                        {new Date(n.event_time).toLocaleString()}
                      </p>
                    </div>
                  );
                })}
              </div>
            )}
          </GlowCard>
        </div>

        {/* Intel (tweets + news headlines) */}
        <div>
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
              onChange={(e) => setIntelQuery(e.target.value)}
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
                        ? new Date(t.created_at).toLocaleString()
                        : t.fetched_at
                          ? new Date(t.fetched_at).toLocaleString()
                          : ''}
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
