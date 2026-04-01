/** Same window labels/values as `/api/dashboard?period=` — keep in sync with dashboard UI. */
export const PROFIT_PERIODS = [
  { value: 'all', label: 'All time' },
  { value: 'today', label: 'Today' },
  { value: 'week', label: 'Week' },
  { value: 'month', label: '1 month' },
  { value: '3m', label: '3 months' },
  { value: '6m', label: '6 months' },
  { value: 'year', label: '1 year' },
] as const;
