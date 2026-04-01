'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import GlowCard from '@/components/ui/GlowCard';
import NeonBadge from '@/components/ui/NeonBadge';
import { api, IntelSummaryData, TweetData } from '@/lib/api';
import { xPostUrl, INTEL_DIR_SHORT, computeIntelSummaryFromTweets } from '@/lib/intel';
import { formatEAT } from '@/lib/datetime';
import { motion } from 'framer-motion';

const INTEL_KEY = 'clubmillies_intel_query';

function CountPill({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: 'profit' | 'loss' | 'gold' | 'muted';
}) {
  const toneCls =
    tone === 'profit'
      ? 'border-profit/30 bg-profit/10 text-profit'
      : tone === 'loss'
        ? 'border-loss/30 bg-loss/10 text-loss'
        : tone === 'gold'
          ? 'border-gold/30 bg-gold/10 text-gold'
          : 'border-white/10 bg-white/[0.04] text-gray-400';
  return (
    <div className={`rounded-xl border px-4 py-3 ${toneCls}`}>
      <p className="text-[10px] uppercase tracking-wider opacity-80">{label}</p>
      <p className="text-2xl font-bold tabular-nums mt-0.5">{value}</p>
    </div>
  );
}

export default function IntelPage() {
  const [summary, setSummary] = useState<IntelSummaryData | null>(null);
  const [summaryErr, setSummaryErr] = useState<string | null>(null);
  const [summaryNotice, setSummaryNotice] = useState<string | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(true);

  const [intelQuery, setIntelQuery] = useState('');
  const [intelReady, setIntelReady] = useState(false);
  const [intelLoading, setIntelLoading] = useState(false);
  const [intelError, setIntelError] = useState<string | null>(null);
  const [intelLast, setIntelLast] = useState<string | null>(null);

  const [modalTweet, setModalTweet] = useState<TweetData | null>(null);

  const loadSummary = useCallback(async () => {
    setSummaryErr(null);
    setSummaryLoading(true);
    try {
      const s = await api.intelSummary(300);
      setSummary(s);
    } catch (e) {
      setSummaryErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSummaryLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  useEffect(() => {
    const t = setInterval(loadSummary, 60_000);
    return () => clearInterval(t);
  }, [loadSummary]);

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
    if (!modalTweet) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setModalTweet(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [modalTweet]);

  async function handleFetchIntel() {
    setIntelError(null);
    setIntelLoading(true);
    try {
      const r = await api.fetchIntelTweets(intelQuery.trim() || undefined);
      setIntelLast(
        `Found ${r.tweets_found} posts (${r.tweets_new_rows} new). ` +
          `AI: ${r.analysis.direction} (${r.analysis.confidence}%)`
      );
      await loadSummary();
      try {
        await api.analyses('limit=40');
      } catch (ae) {
        console.warn('AI analyses refresh failed after intel fetch:', ae);
      }
    } catch (e) {
      setIntelError(e instanceof Error ? e.message : String(e));
    } finally {
      setIntelLoading(false);
    }
  }

  const c = summary?.counts;
  const tagged = summary?.tagged_posts ?? 0;
  const total = summary?.total_posts ?? 0;

  return (
    <div className="space-y-8 max-w-6xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Market intel</h1>
          <p className="text-sm text-gray-500 mt-1 max-w-2xl">
            Aggregate bias from stored X posts (per-post AI tags), plus the latest batch analysis from your last fetch.
          </p>
        </div>
        <Link
          href="/news"
          className="text-sm text-neon-cyan/90 hover:text-neon-cyan border border-neon-cyan/30 rounded-lg px-3 py-2 self-start sm:self-auto"
        >
          ← News & AI Analysis
        </Link>
      </div>

      {summaryLoading && !summary ? (
        <p className="text-sm text-gray-500">Loading summary…</p>
      ) : null}
      {summaryErr ? (
        <p className="text-sm text-loss whitespace-pre-wrap">{summaryErr}</p>
      ) : null}
      {summaryNotice && !summaryErr ? (
        <p className="text-xs text-gold/90 border border-gold/25 rounded-lg px-3 py-2 bg-gold/5 whitespace-pre-wrap">
          {summaryNotice}
        </p>
      ) : null}

      {summary ? (
        <div className="space-y-6">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <CountPill label="Bullish" value={c!.bullish} tone="profit" />
            <CountPill label="Bearish" value={c!.bearish} tone="loss" />
            <CountPill label="Neutral" value={c!.neutral} tone="gold" />
            <CountPill label="Unknown / untagged" value={c!.unknown} tone="muted" />
          </div>

          <GlowCard className="p-5">
            <div className="flex flex-wrap items-center gap-3 mb-3">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Conclusion</span>
              {summary.net_bias ? (
                <NeonBadge
                  label={summary.net_bias.toUpperCase()}
                  variant={
                    summary.net_bias === 'bullish'
                      ? 'buy'
                      : summary.net_bias === 'bearish'
                        ? 'sell'
                        : 'neutral'
                  }
                />
              ) : null}
              <span className="text-xs text-gray-500">
                {tagged} tagged / {total} posts in window
              </span>
            </div>
            <p className="text-base text-gray-200 leading-relaxed">{summary.net_summary_line}</p>
          </GlowCard>

          {summary.batch_analysis ? (
            <GlowCard className="p-5 border-neon-cyan/15">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                Latest batch analysis (full fetch)
              </p>
              <div className="flex flex-wrap items-center gap-2 mb-3">
                <NeonBadge
                  label={summary.batch_analysis.direction.toUpperCase()}
                  variant={
                    summary.batch_analysis.direction === 'bullish'
                      ? 'buy'
                      : summary.batch_analysis.direction === 'bearish'
                        ? 'sell'
                        : 'neutral'
                  }
                />
                <span className="text-xs text-gray-400 tabular-nums">
                  {summary.batch_analysis.confidence}% confidence
                </span>
                {summary.batch_analysis.created_at ? (
                  <span className="text-[10px] text-gray-600">
                    {formatEAT(summary.batch_analysis.created_at)} EAT
                  </span>
                ) : null}
              </div>
              <p className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap">
                {summary.batch_analysis.reasoning}
              </p>
            </GlowCard>
          ) : (
            <p className="text-sm text-gray-600">
              No batch analysis row yet — run <strong>Fetch intel</strong> after the API is configured.
            </p>
          )}
        </div>
      ) : null}

      <div>
        <h2 className="text-lg font-bold text-gray-300 mb-3">Fetch &amp; refresh</h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
          <div className="space-y-2">
            <textarea
              aria-label="Intel search keywords"
              className="w-full min-h-[88px] bg-dark-100 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder:text-gray-600 focus:border-neon-cyan/40 outline-none resize-y"
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
              {intelLoading ? 'Fetching…' : 'Fetch intel'}
            </motion.button>
            {!intelReady && (
              <p className="text-xs text-gray-500">Manual intel fetch is not available (API not configured).</p>
            )}
            {intelError && <p className="text-xs text-loss whitespace-pre-wrap">{intelError}</p>}
            {intelLast && !intelError && (
              <p className="text-xs text-profit/90 border border-profit/20 rounded-lg p-2 bg-profit/5 break-words">
                {intelLast}
              </p>
            )}
          </div>
          <div className="text-xs text-gray-500 leading-relaxed border border-white/10 rounded-xl p-4 bg-dark-100/40">
            <p>
              Per-post direction counts drive the <strong>Conclusion</strong> above. After a fetch, open any row below for full text
              and AI impact notes.
            </p>
          </div>
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between gap-2 mb-3">
          <h2 className="text-lg font-bold text-gray-300">Posts</h2>
          <button
            type="button"
            onClick={() => loadSummary()}
            className="text-xs px-2 py-1 rounded-lg border border-white/10 text-gray-400 hover:text-white"
          >
            Refresh summary
          </button>
        </div>

        {summaryLoading && !summary ? (
          <p className="text-sm text-gray-500">Loading posts…</p>
        ) : summary && summary.tweets.length === 0 ? (
          <GlowCard>
            <p className="text-gray-600 text-center py-8 text-sm">
              No intel posts loaded yet — configure the intel API and use Fetch.
            </p>
          </GlowCard>
        ) : summary && summary.tweets.length > 0 ? (
          <div className="rounded-xl border border-white/10 overflow-hidden bg-dark-100/30">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm min-w-[640px]">
                <thead>
                  <tr className="border-b border-white/10 text-[10px] uppercase tracking-wider text-gray-500">
                    <th className="px-4 py-3 font-semibold w-[140px]">Author</th>
                    <th className="px-4 py-3 font-semibold w-[100px]">Bias</th>
                    <th className="px-4 py-3 font-semibold">Post</th>
                    <th className="px-4 py-3 font-semibold w-[120px]">Time (EAT)</th>
                    <th className="px-4 py-3 font-semibold w-[72px] text-right">X</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.tweets.map((t) => (
                    <tr
                      key={t.id}
                      className="border-b border-white/5 hover:bg-white/[0.03] align-top"
                    >
                      <td className="px-4 py-3 text-xs text-gray-400">
                        <button
                          type="button"
                          onClick={() => setModalTweet(t)}
                          className="text-left text-neon-cyan/90 hover:underline break-all"
                        >
                          @{t.author}
                        </button>
                      </td>
                      <td className="px-4 py-3">
                        {t.ai_direction ? (
                          <NeonBadge
                            label={
                              INTEL_DIR_SHORT[t.ai_direction.toLowerCase()] ??
                              t.ai_direction.toUpperCase().slice(0, 4)
                            }
                            variant={
                              t.ai_direction === 'bullish'
                                ? 'buy'
                                : t.ai_direction === 'bearish'
                                  ? 'sell'
                                  : 'neutral'
                            }
                            size="sm"
                          />
                        ) : (
                          <span className="text-[10px] text-gray-600">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <button
                          type="button"
                          onClick={() => setModalTweet(t)}
                          className="text-left w-full text-gray-200 hover:text-white"
                        >
                          <p className="text-xs leading-snug line-clamp-3 break-words">{t.text}</p>
                          {t.ai_reasoning ? (
                            <p className="text-[11px] text-gray-500 mt-1.5 line-clamp-2 break-words">
                              <span className="text-gold/80">Impact </span>
                              {t.ai_reasoning}
                            </p>
                          ) : null}
                        </button>
                      </td>
                      <td className="px-4 py-3 text-[11px] text-gray-500 tabular-nums whitespace-nowrap">
                        {t.created_at
                          ? formatEAT(t.created_at)
                          : t.fetched_at
                            ? formatEAT(t.fetched_at)
                            : '—'}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <a
                          href={xPostUrl(t)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-neon-cyan/80 hover:text-neon-cyan"
                        >
                          Open
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </div>

      {modalTweet ? (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          onClick={() => setModalTweet(null)}
        >
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            className="max-w-lg w-full max-h-[min(85vh,640px)] overflow-y-auto rounded-2xl border border-neon-cyan/20 bg-dark-200 p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-2 mb-3">
              <div>
                <p className="text-xs text-gray-500">@{modalTweet.author}</p>
                <p className="text-[10px] text-gray-600 mt-0.5">id {modalTweet.tweet_id}</p>
              </div>
              <button
                type="button"
                onClick={() => setModalTweet(null)}
                className="text-gray-500 hover:text-white text-sm px-2 py-0.5 rounded-lg border border-white/10"
              >
                Close
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <p className="text-[10px] font-semibold text-gray-500 uppercase mb-1">Post</p>
                <p className="text-sm text-gray-200 whitespace-pre-wrap leading-relaxed">{modalTweet.text}</p>
              </div>
              {modalTweet.ai_reasoning ? (
                <div>
                  <p className="text-[10px] font-semibold text-gold uppercase mb-1">Gold / XAU — market impact (AI)</p>
                  <div className="flex items-center gap-2 mb-2">
                    {modalTweet.ai_direction ? (
                      <NeonBadge
                        label={modalTweet.ai_direction.toUpperCase()}
                        variant={
                          modalTweet.ai_direction === 'bullish'
                            ? 'buy'
                            : modalTweet.ai_direction === 'bearish'
                              ? 'sell'
                              : 'neutral'
                        }
                      />
                    ) : null}
                    {modalTweet.ai_confidence != null ? (
                      <span className="text-xs text-gray-400">Confidence {modalTweet.ai_confidence}%</span>
                    ) : null}
                  </div>
                  <p className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap">
                    {modalTweet.ai_reasoning}
                  </p>
                </div>
              ) : summary?.batch_analysis ? (
                <div>
                  <p className="text-[10px] font-semibold text-gray-500 uppercase mb-1">
                    Batch intel (latest fetch — all posts)
                  </p>
                  <div className="flex items-center gap-2 mb-2">
                    <NeonBadge
                      label={summary.batch_analysis.direction.toUpperCase()}
                      variant={
                        summary.batch_analysis.direction === 'bullish'
                          ? 'buy'
                          : summary.batch_analysis.direction === 'bearish'
                            ? 'sell'
                            : 'neutral'
                      }
                    />
                    <span className="text-xs text-gray-400">{summary.batch_analysis.confidence}%</span>
                  </div>
                  <p className="text-sm text-gray-400 leading-relaxed whitespace-pre-wrap">
                    {summary.batch_analysis.reasoning}
                  </p>
                  <p className="text-[10px] text-gray-600 mt-2">
                    Per-post impact fills after the next successful <strong>Fetch intel</strong> (Claude returns one row per post).
                  </p>
                </div>
              ) : (
                <p className="text-xs text-gray-500">
                  No AI text yet. Set <code className="text-neon-cyan">ANTHROPIC_API_KEY</code> on the API server, restart it, then use{' '}
                  <strong>Fetch intel</strong>.
                </p>
              )}
              <a
                href={xPostUrl(modalTweet)}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center justify-center w-full py-2.5 rounded-xl text-sm font-medium bg-neon-cyan/15 text-neon-cyan border border-neon-cyan/40 hover:bg-neon-cyan/25"
              >
                Open post on X
              </a>
            </div>
          </motion.div>
        </div>
      ) : null}
    </div>
  );
}
