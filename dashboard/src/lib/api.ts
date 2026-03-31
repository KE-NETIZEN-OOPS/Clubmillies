const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

export async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export const api = {
  dashboard: () => fetchApi<DashboardData>('/api/dashboard'),
  accounts: () => fetchApi<AccountData[]>('/api/accounts'),
  createAccount: (data: any) => fetchApi('/api/accounts', { method: 'POST', body: JSON.stringify(data) }),
  updateAccount: (id: number, data: any) => fetchApi(`/api/accounts/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteAccount: (id: number) => fetchApi(`/api/accounts/${id}`, { method: 'DELETE' }),
  toggleAccount: (id: number) => fetchApi(`/api/accounts/${id}/toggle`, { method: 'POST' }),
  trades: (params?: string) => fetchApi<TradeData[]>(`/api/trades${params ? '?' + params : ''}`),
  signals: (params?: string) => fetchApi<SignalData[]>(`/api/signals${params ? '?' + params : ''}`),
  news: () => fetchApi<NewsData[]>('/api/news'),
  analyses: () => fetchApi<AnalysisData[]>('/api/ai-analyses'),
  stats: () => fetchApi<StatsData>('/api/stats'),
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
  symbol: string;
  timeframe: string;
  profile: string;
  risk_per_trade: number;
  max_open_trades: number;
  balance: number;
  equity: number;
  enabled: boolean;
  created_at: string;
}

export interface TradeData {
  id: number;
  account_id: number;
  direction: string;
  entry_price: number;
  exit_price: number | null;
  lots: number;
  sl: number;
  tp: number;
  pnl: number | null;
  confluence_score: number;
  confluence_reasons: string[];
  status: string;
  close_reason: string | null;
  opened_at: string;
  closed_at: string | null;
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
  direction: string;
  confidence: number;
  reasoning: string;
  created_at: string;
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
