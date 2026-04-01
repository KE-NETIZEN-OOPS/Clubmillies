import type { TweetData } from '@/lib/api';

export function xPostUrl(t: TweetData): string {
  if (t.url && /^https?:\/\//i.test(t.url)) return t.url;
  return `https://x.com/i/web/status/${encodeURIComponent(t.tweet_id)}`;
}

export const INTEL_DIR_SHORT: Record<string, string> = {
  bullish: 'BULL',
  bearish: 'BEAR',
  neutral: 'NEUT',
};
