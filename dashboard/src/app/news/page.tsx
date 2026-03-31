'use client';

import { useEffect, useState } from 'react';
import GlowCard from '@/components/ui/GlowCard';
import NeonBadge from '@/components/ui/NeonBadge';
import { api, NewsData, AnalysisData, TweetData } from '@/lib/api';

export default function NewsPage() {
  const [news, setNews] = useState<NewsData[]>([]);
  const [analyses, setAnalyses] = useState<AnalysisData[]>([]);
  const [tweets, setTweets] = useState<TweetData[]>([]);

  useEffect(() => {
    api.news().then(setNews).catch(console.error);
    api.analyses().then(setAnalyses).catch(console.error);
    api.tweets().then(setTweets).catch(console.error);
  }, []);

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold">News & AI Analysis</h1>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* AI Analyses */}
        <div>
          <h2 className="text-lg font-bold text-gray-300 mb-4">AI Analysis (Claude)</h2>
          <div className="space-y-4">
            {analyses.length === 0 ? (
              <GlowCard><p className="text-gray-600 text-center py-4">No AI analyses yet. Set ANTHROPIC_API_KEY in .env</p></GlowCard>
            ) : (
              analyses.map((a) => (
                <GlowCard key={a.id} glowColor={
                  a.direction === 'bullish' ? 'rgba(0,230,118,0.2)' :
                  a.direction === 'bearish' ? 'rgba(255,51,102,0.2)' : 'rgba(100,100,100,0.1)'
                }>
                  <div className="flex items-center justify-between mb-2">
                    <NeonBadge label={a.source.toUpperCase()} variant="neutral" />
                    <NeonBadge
                      label={a.direction.toUpperCase()}
                      variant={a.direction === 'bullish' ? 'buy' : a.direction === 'bearish' ? 'sell' : 'neutral'}
                    />
                  </div>
                  <div className="mb-2">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs text-gray-500">Confidence</span>
                      <div className="flex-1 h-2 bg-dark-100 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${
                            a.confidence >= 70 ? 'bg-profit' : a.confidence >= 40 ? 'bg-gold' : 'bg-loss'
                          }`}
                          style={{ width: `${a.confidence}%` }}
                        />
                      </div>
                      <span className="text-xs font-bold">{a.confidence}%</span>
                    </div>
                  </div>
                  <p className="text-sm text-gray-400">{a.reasoning}</p>
                  <p className="text-[10px] text-gray-600 mt-2">
                    {new Date(a.created_at).toLocaleString()}
                  </p>
                </GlowCard>
              ))
            )}
          </div>
        </div>

        {/* Economic Calendar */}
        <div>
          <h2 className="text-lg font-bold text-gray-300 mb-4">Economic Calendar</h2>
          <GlowCard>
            {news.length === 0 ? (
              <p className="text-gray-600 text-center py-4">No news events loaded</p>
            ) : (
              <div className="space-y-3">
                {news.map((n) => {
                  const impactColor = n.impact === 'high' ? 'text-loss' : n.impact === 'medium' ? 'text-gold' : 'text-gray-500';
                  const impactBg = n.impact === 'high' ? 'bg-loss/20' : n.impact === 'medium' ? 'bg-gold/20' : 'bg-white/5';
                  return (
                    <div key={n.id} className={`p-3 rounded-lg ${impactBg} border border-white/5`}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-medium text-sm">{n.title}</span>
                        <span className={`text-xs font-bold uppercase ${impactColor}`}>{n.impact}</span>
                      </div>
                      <div className="flex gap-4 text-xs text-gray-500">
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

        {/* Tweets */}
        <div>
          <h2 className="text-lg font-bold text-gray-300 mb-4">Tweets (Market Intel)</h2>
          <GlowCard>
            {tweets.length === 0 ? (
              <p className="text-gray-600 text-center py-4">No tweets loaded</p>
            ) : (
              <div className="space-y-3">
                {tweets.map((t) => (
                  <div key={t.id} className="p-3 rounded-lg bg-white/5 border border-white/5">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs text-gray-500">@{t.author}</span>
                      {t.url ? (
                        <a className="text-xs text-neon-cyan hover:underline" href={t.url} target="_blank" rel="noreferrer">
                          open
                        </a>
                      ) : null}
                    </div>
                    <p className="text-sm text-gray-400 whitespace-pre-wrap">{t.text}</p>
                    <p className="text-[10px] text-gray-600 mt-2">
                      {t.created_at ? new Date(t.created_at).toLocaleString() : (t.fetched_at ? new Date(t.fetched_at).toLocaleString() : '')}
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
