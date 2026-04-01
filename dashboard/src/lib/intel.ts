import type { IntelSummaryData, TweetData } from '@/lib/api';

export function xPostUrl(t: TweetData): string {
  if (t.url && /^https?:\/\//i.test(t.url)) return t.url;
  return `https://x.com/i/web/status/${encodeURIComponent(t.tweet_id)}`;
}

export const INTEL_DIR_SHORT: Record<string, string> = {
  bullish: 'BULL',
  bearish: 'BEAR',
  neutral: 'NEUT',
};

/** Mirrors server logic in GET /api/intel/summary when that route is unavailable (older API deploy). */
export function computeIntelSummaryFromTweets(tweets: TweetData[]): IntelSummaryData {
  const counts = { bullish: 0, bearish: 0, neutral: 0, unknown: 0 };
  for (const t of tweets) {
    const d = (t.ai_direction ?? '').trim().toLowerCase();
    if (d === 'bullish') counts.bullish += 1;
    else if (d === 'bearish') counts.bearish += 1;
    else if (d === 'neutral') counts.neutral += 1;
    else counts.unknown += 1;
  }
  const tagged = counts.bullish + counts.bearish + counts.neutral;
  let net_bias: string;
  let net_summary_line: string;
  if (tagged === 0) {
    net_bias = 'unknown';
    net_summary_line =
      'No posts have per-post AI tags yet. Run Fetch intel with ANTHROPIC_API_KEY set on the API server.';
  } else {
    const b = counts.bullish;
    const br = counts.bearish;
    const n = counts.neutral;
    if (b > br && b > n) net_bias = 'bullish';
    else if (br > b && br > n) net_bias = 'bearish';
    else if (n >= b && n >= br) net_bias = 'neutral';
    else net_bias = 'mixed';
    net_summary_line = `In this list, ${b} post(s) lean bullish, ${br} bearish, ${n} neutral (among ${tagged} with tags). Net: ${net_bias}.`;
  }
  return {
    counts,
    total_posts: tweets.length,
    tagged_posts: tagged,
    net_bias,
    net_summary_line,
    batch_analysis: null,
    tweets,
  };
}
