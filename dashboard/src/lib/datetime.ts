/** East Africa Time (Nairobi) — all user-facing dates should use this. */
const EAT = 'Africa/Nairobi';

export function formatEAT(
  iso: string | null | undefined,
  options: Intl.DateTimeFormatOptions = {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }
): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString('en-KE', { timeZone: EAT, ...options });
}

export function formatEATTime(iso: string | null | undefined): string {
  return formatEAT(iso, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
