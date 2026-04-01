const API_BASE = (process.env.NEXT_PUBLIC_API_URL || '').replace(/\/$/, '');

export async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const pathNorm = path.startsWith('/') ? path : `/${path}`;
  const url = `${API_BASE}${pathNorm}`;
  let res: Response;
  try {
    const { headers: optHeaders, ...rest } = options || {};
    const mergedHeaders: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(typeof optHeaders === 'object' && optHeaders !== null && !(optHeaders instanceof Headers)
        ? (optHeaders as Record<string, string>)
        : {}),
    };
    res = await fetch(url, { ...rest, headers: mergedHeaders });
  } catch (e) {
    const baseHint =
      typeof window !== 'undefined' && !API_BASE
        ? ' Configure NEXT_PUBLIC_API_URL to your API base URL (e.g. https://api.yourdomain.com) in the dashboard env and redeploy.'
        : '';
    const msg = e instanceof Error ? e.message : String(e);
    throw new Error(`${msg}${baseHint}`);
  }
  if (!res.ok) {
    let detail = '';
    try {
      const j = await res.json();
      detail = typeof (j as { detail?: unknown }).detail === 'string'
        ? (j as { detail: string }).detail
        : JSON.stringify(j);
    } catch {
      detail = await res.text();
    }
    throw new Error(detail || `API error: ${res.status}`);
  }
  return res.json();
}

export const api = {
  dashboard: (period?: string) =>
    fetchApi<DashboardData>(
      `/api/dashboard${period && period !== 'all' ? `?period=${encodeURIComponent(period)}` : ''}`
    ),
  live: () => fetchApi<LiveSnapshot>('/api/live'),
  accounts: () => fetchApi<AccountData[]>('/api/accounts'),
  account: (id: number, period?: string) =>
    fetchApi<AccountDetailData>(
      `/api/accounts/${id}${period && period !== 'all' ? `?period=${encodeURIComponent(period)}` : ''}`
    ),
  createAccount: (data: any) => fetchApi('/api/accounts', { method: 'POST', body: JSON.stringify(data) }),
  updateAccount: (id: number, data: any) => fetchApi(`/api/accounts/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteAccount: (id: number) => fetchApi(`/api/accounts/${id}`, { method: 'DELETE' }),
  toggleAccount: (id: number) => fetchApi(`/api/accounts/${id}/toggle`, { method: 'POST' }),
  trades: (params?: string) => fetchApi<TradeData[]>(`/api/trades${params ? '?' + params : ''}`),
  signals: (params?: string) => fetchApi<SignalData[]>(`/api/signals${params ? '?' + params : ''}`),
  news: () => fetchApi<NewsData[]>('/api/news'),
  analyzeNews: (id: number) =>
    fetchApi<{ analysis: NewsAnalysisResult; event: Record<string, unknown> }>(
      `/api/news/${id}/analyze`,
      { method: 'POST' }
    ),
  analyses: (params?: string) => {
    const q =
      !params ? '' : params.startsWith('?') ? params : `?${params}`;
    return fetchApi<AnalysisData[]>(`/api/ai-analyses${q}`);
  },
  tweets: () => fetchApi<TweetData[]>('/api/tweets'),
  stats: () => fetchApi<StatsData>('/api/stats'),
  intelConfig: () =>
    fetchApi<IntelConfig>('/api/intel/config'),
  fetchIntelTweets: (query?: string) =>
    fetchApi<IntelFetchResult>('/api/intel/fetch-tweets', {
      method: 'POST',
      body: JSON.stringify({ query: query?.trim() || null }),
    }),
  intelSummary: (limit?: number) =>
    fetchApi<IntelSummaryData>(
      `/api/intel/summary${limit != null ? `?limit=${encodeURIComponent(String(limit))}` : ''}`
    ),
};

// Types
export interface DashboardData {
  total_balance: number;
  total_equity: number;
  today_pnl: number;
  total_pnl: number;
  period?: string;
  period_pnl?: number;
  period_trade_count?: number;
  period_win_rate?: number;
  total_trades: number;
  today_trades: number;
  win_rate: number;
  active_accounts: number;
  total_accounts: number;
  accounts: AccountData[];
  recent_signals: SignalData[];
}

export interface AccountData {
  id: number;
  name: string;
  broker_type: string;
  login?: string;
  server?: string;
  symbol: string;
  timeframe: string;
  profile: string;
  risk_per_trade: number;
  max_open_trades: number;
  balance: number;
  equity: number;
  starting_balance?: number;
  is_demo?: boolean | null;
  enabled: boolean;
  created_at: string;
}

export interface AccountDetailData {
  id: number;
  name: string;
  broker_type: string;
  login: string;
  server: string;
  is_demo: boolean | null;
  symbol: string;
  timeframe: string;
  profile: string;
  risk_per_trade: number;
  max_open_trades: number;
  balance: number;
  equity: number;
  starting_balance: number;
  enabled: boolean;
  period?: string;
  stats: {
    total_realized_pnl: number;
    total_realized_pnl_all_time?: number;
    closed_trade_count: number;
    open_trade_count: number;
    win_count: number;
    loss_count?: number;
    win_rate_pct: number;
    roi_vs_starting_balance_pct: number;
    best_trade?: number;
    worst_trade?: number;
    avg_risk_reward?: number | null;
    profit_factor?: number | null;
  };
  closed_trades: TradeData[];
  open_trades: TradeData[];
  latest_performance_ai: {
    id: number;
    direction: string;
    confidence: number;
    reasoning: string;
    metrics?: Record<string, unknown> | null;
    created_at: string | null;
  } | null;
}

export interface TradeData {
  id: number;
  account_id?: number;
  direction: string;
  entry_price: number;
  exit_price: number | null;
  lots: number;
  sl: number;
  tp: number;
  pnl: number | null;
  confluence_score?: number;
  confluence_reasons?: string[];
  status: string;
  close_reason: string | null;
  opened_at: string;
  closed_at: string | null;
  mt5_position_ticket?: number | null;
  risk_reward?: number | null;
}

export interface SignalData {
  id?: number;
  account_id?: number;
  signal: string;
  score: number;
  max_score?: number;
  reasons: string[];
  price: number;
  sl?: number | null;
  tp?: number | null;
  rsi?: number;
  atr?: number;
  risk_reward?: number | null;
  created_at: string | null;
}

export interface NewsAnalysisResult {
  direction?: string;
  confidence?: number;
  reasoning?: string;
  verdict?: string;
}

export interface NewsData {
  id: number;
  title: string;
  currency: string;
  impact: string;
  forecast: string;
  previous: string;
  actual: string;
  event_time: string;
}

export interface AnalysisData {
  id: number;
  source: string;
  account_id?: number | null;
  trade_id?: number | null;
  direction: string;
  confidence: number;
  reasoning: string;
  metrics?: Record<string, unknown> | null;
  created_at: string;
}

export interface TweetData {
  id: number;
  tweet_id: string;
  author: string;
  text: string;
  url?: string | null;
  created_at: string | null;
  fetched_at: string | null;
  /** Per-post gold/XAU intel from last fetch (Claude) */
  ai_direction?: string | null;
  ai_confidence?: number | null;
  ai_reasoning?: string | null;
}

export interface IntelConfig {
  default_query: string;
  sociavault_configured: boolean;
}

export interface IntelFetchResult {
  query: string;
  sociavault_requests: number;
  tweets_found: number;
  tweets_new_rows: number;
  tweets: Array<{
    tweet_id: string;
    author: string;
    text: string;
    url: string | null;
    source: string;
  }>;
  analysis: {
    direction: string;
    confidence: number;
    reasoning: string;
  };
}

export interface IntelSummaryData {
  counts: { bullish: number; bearish: number; neutral: number; unknown: number };
  total_posts: number;
  tagged_posts: number;
  net_bias: string;
  net_summary_line: string;
  batch_analysis: {
    direction: string;
    confidence: number;
    reasoning: string;
    created_at: string | null;
  } | null;
  tweets: TweetData[];
}

export interface LiveSnapshot {
  spot_xauusd: number | null;
  /** "mt5" = broker mid tick; "yahoo" = fallback quote */
  spot_source?: string | null;
  source?: string;
  open_trades: Array<{
    id: number;
    account_id: number;
    account_name?: string | null;
    direction: string;
    entry_price: number;
    lots: number;
    sl: number;
    tp: number;
    confluence_score: number | null;
    unrealized_pnl: number | null;
    opened_at: string | null;
    mt5_position_ticket?: number | null;
    symbol?: string | null;
    source?: string;
  }>;
  total_unrealized_pnl: number;
  updated_at: string;
}

export interface StatsData {
  total_trades: number;
  winners: number;
  losers: number;
  win_rate: number;
  total_pnl: number;
  avg_win: number;
  avg_loss: number;
  profit_factor: number;
  best_trade: number;
  worst_trade: number;
}
