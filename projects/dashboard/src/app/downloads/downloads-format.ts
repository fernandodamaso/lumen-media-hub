import { TorrentState } from './downloads.models';

export type StatusTone = 'success' | 'warning' | 'danger' | 'info';

export const TORRENT_STATE_VIEW: Record<TorrentState, { label: string; tone: StatusTone }> = {
  downloading: { label: 'Downloading', tone: 'info' },
  seeding: { label: 'Seeding', tone: 'success' },
  paused: { label: 'Paused', tone: 'warning' },
  queued: { label: 'Queued', tone: 'warning' },
  checking: { label: 'Checking', tone: 'warning' },
  error: { label: 'Error', tone: 'danger' },
};

export function formatBytes(bytes: number): string {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
}

export function formatRate(bytes: number): string {
  return `${formatBytes(bytes)}/s`;
}

export function formatEta(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return minutes >= 60 ? `${Math.floor(minutes / 60)}h ${minutes % 60}m` : `${minutes}m`;
}
