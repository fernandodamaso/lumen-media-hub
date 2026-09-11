import { CleanupCandidate, CleanupReason, GIB } from './cleanup.models';

export function formatCleanupBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return '—';
  if (bytes >= 1024 ** 4) return `${trim(bytes / 1024 ** 4)} TiB`;
  if (bytes >= GIB) return `${trim(bytes / GIB)} GB`;
  if (bytes >= 1024 ** 2) return `${trim(bytes / 1024 ** 2)} MB`;
  return `${Math.round(bytes)} B`;
}

export function formatCandidateMeta(candidate: CleanupCandidate, generatedAt: string): string {
  const generated = Date.parse(generatedAt);
  const played = Date.parse(candidate.lastPlayedAt);
  const days = Number.isFinite(generated) && Number.isFinite(played)
    ? Math.max(0, Math.floor((generated - played) / 86_400_000))
    : null;
  const kind = candidate.mediaKind === 'movie' ? 'Movie' : candidate.subtitle;
  return days === null ? kind : `${kind} · ${days} days since play`;
}

export function formatCleanupReason(reason: CleanupReason): string {
  switch (reason.code) {
    case 'watched_movie_expired':
      return `Matches the configured ${reason.evidence['retentionDays'] ?? 0}-day movie rule.`;
    case 'watched_episode_expired':
      return `Outside the latest ${reason.evidence['keepLatestPerSeries'] ?? 0} available episodes after the configured retention window.`;
    case 'large_watched_file_stale':
      return `Watched file is at least ${formatCleanupBytes(reason.evidence['minimumBytes'] ?? 0)} and has been idle ${reason.evidence['idleDays'] ?? 0}+ days.`;
  }
}

export function formatCandidateReason(candidate: CleanupCandidate): string {
  return candidate.reasons.map(formatCleanupReason).join(' ');
}

function trim(value: number): string {
  if (value >= 100) return Math.round(value).toString();
  return value.toFixed(1).replace(/\.0$/, '');
}
