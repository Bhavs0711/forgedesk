/** The API sometimes returns naive UTC timestamps (SQLite); normalise before parsing. */
export function parseDate(s: string): Date {
  return new Date(/(Z|[+-]\d\d:\d\d)$/.test(s) ? s : `${s}Z`);
}

export function duration(seconds: number): string {
  if (seconds < 1) return "0s";
  const s = Math.round(seconds);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m ${r}s`;
  return `${r}s`;
}

export function clock(s: string): string {
  return parseDate(s).toLocaleTimeString([], { hour12: false });
}

export function dateTime(s: string): string {
  return parseDate(s).toLocaleString([], { hour12: false, dateStyle: "short", timeStyle: "short" });
}

export function usd(n: number): string {
  return `$${n.toFixed(n < 1 ? 4 : 2)}`;
}

export function sessionSeconds(s: { started_at: string; ended_at: string | null }, now = Date.now()): number {
  return ((s.ended_at ? parseDate(s.ended_at).getTime() : now) - parseDate(s.started_at).getTime()) / 1000;
}
