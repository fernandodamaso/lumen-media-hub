export type StatusTone = 'success' | 'warning' | 'danger' | 'info';

export type CronStatusView = { label: string; tone: StatusTone };

const STATUS_VIEWS: Record<string, CronStatusView> = {
  ok: { label: 'ok', tone: 'success' },
  fatal: { label: 'failed', tone: 'danger' },
  applied: { label: 'repaired', tone: 'warning' },
  warn: { label: 'warn', tone: 'warning' },
  unparsed: { label: 'unknown', tone: 'info' },
  missing: { label: 'no log', tone: 'info' },
};

export function cronStatusView(status: string | null | undefined): CronStatusView {
  const key = (status || 'ok').toLowerCase();
  return STATUS_VIEWS[key] ?? { label: key, tone: 'info' };
}

export function formatGeneratedAt(iso: string): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

export function formatRunTimestamp(iso: string): string {
  if (!iso) return 'Unknown time';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}
