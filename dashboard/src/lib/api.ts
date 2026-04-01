const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

export async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
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
  dashboard: () => fetchApi<DashboardData>('/api/dashboard'),
  live: () => fetchApi<LiveSnapshot>('/api/live'),
  accounts: () => fetchApi<AccountData[]>('/api/accounts'),
  account: (id: number) => fetchApi<AccountDetailData>(`/api/accounts/${id}`),
  createAccount: (data: any) => fetchApi('/api/accounts', { method: 'POST', body: JSON.stringify(data) }),
  updateAccount: (id: number, data: any) => fetchApi(`/api/accounts/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteAccount: (id: number) => fetchApi(`/api/accounts/${id}`, { method: 'DELETE' }),
  toggleAccount: (id: number) => fetchApi(`/api/accounts/${id}/toggle`, { method: 'POST' }),
  trades: (params?: string) => fetchApi<TradeData[]>(`/api/trades${params ? '?' + params : ''}`),
  signals: (params?: string) => fetchApi<SignalData[]>(`/api/signals${params ? '?' + params : ''}`),
  news: () => fetchApi<NewsData[]>('/api/news'),
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
};

// Types
export interface DashboardData {
  total_balance: number;
  total_equity: number;
  today_pnl: number;
  total_pnl: number;
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
  stats: {
    total_realized_pnl: number;
    closed_trade_count: number;
    open_trade_count: number;
    win_count: number;
    win_rate_pct: number;
    roi_vs_starting_balance_pct: number;
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
  created_at: string | null;
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

export interface LiveSnapshot {
  spot_xauusd: number | null;
  open_trades: Array<{
    id: number;
    account_id: number;
    direction: string;
    entry_price: number;
    lots: number;
    sl: number;
    tp: number;
    confluence_score: number;
    unrealized_pnl: number | null;
    opened_at: string | null;
    mt5_position_ticket?: number | null;
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
