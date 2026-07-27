import { DownloadTorrent, TorrentState } from './downloads.models';
import { MediaStackTorrentDto } from '../media-stack/wire/torrents';

export type StatusTone = 'success' | 'warning' | 'danger' | 'info';

export const mapTorrent = (torrent: MediaStackTorrentDto): DownloadTorrent => ({
  id: torrent.hash,
  name: torrent.name,
  state: normalizeState(torrent.state),
  progress: clamp(torrent.progress * 100),
  size: Math.max(0, torrent.size),
  downloaded: Math.max(0, torrent.downloaded),
  downloadRate: Math.max(0, torrent.dlspeed),
  uploadRate: Math.max(0, torrent.upspeed),
  eta: Math.max(0, torrent.eta),
  category: torrent.category ?? 'Uncategorized',
});

function clamp(value: number): number {
  return Math.round(Math.min(100, Math.max(0, value)) * 10) / 10;
}

function normalizeState(state: string): TorrentState {
  const normalized = state.toLowerCase();
  if (normalized.includes('paused')) return 'paused';
  if (normalized.includes('error')) return 'error';
  if (normalized.includes('check')) return 'checking';
  if (normalized.includes('queued')) return 'queued';
  if (normalized === 'downloading' || normalized === 'forceddl') return 'downloading';
  if (normalized.includes('up') || normalized === 'seeding') return 'seeding';
  return 'queued';
}

export const TORRENT_STATE_VIEW: Record<TorrentState, { label: string; tone: StatusTone }> = {
  downloading: { label: 'Downloading', tone: 'info' },
  seeding: { label: 'Seeding', tone: 'success' },
  paused: { label: 'Paused', tone: 'warning' },
  queued: { label: 'Queued', tone: 'warning' },
  checking: { label: 'Checking', tone: 'warning' },
  error: { label: 'Error', tone: 'danger' },
};

const STATE_ORDER: TorrentState[] = ['error', 'downloading', 'queued', 'checking', 'paused', 'seeding'];

export interface TorrentGroup {
  state: TorrentState;
  label: string;
  torrents: DownloadTorrent[];
}

export function groupTorrents(torrents: DownloadTorrent[]): TorrentGroup[] {
  return STATE_ORDER.map((state) => ({
    state,
    label: TORRENT_STATE_VIEW[state].label,
    torrents: torrents.filter((torrent) => torrent.state === state),
  })).filter((group) => group.torrents.length > 0);
}

function byteParts(bytes: number): { value: string; unit: string } {
  if (!bytes) return { value: '0', unit: 'B' };
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return {
    value: (bytes / 1024 ** index).toFixed(index ? 1 : 0),
    unit: units[index],
  };
}

export function formatBytes(bytes: number): string {
  const p = byteParts(bytes);
  return `${p.value} ${p.unit}`;
}

export function formatRate(bytes: number): string {
  return `${formatBytes(bytes)}/s`;
}

export function formatRateParts(bytes: number): { value: string; unit: string } {
  const p = byteParts(bytes);
  return { value: p.value, unit: `${p.unit}/s` };
}

export function formatEta(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return minutes >= 60 ? `${Math.floor(minutes / 60)}h ${minutes % 60}m` : `${minutes}m`;
}

export function torrentArt(name: string): string {
  const hue = stringHash(name) % 360;
  const hue2 = (hue + 40) % 360;
  return `linear-gradient(145deg, hsl(${hue} 60% 32%), hsl(${hue2} 55% 22%))`;
}

function stringHash(value: string): number {
  let hash = 0;
  for (let i = 0; i < value.length; i++) {
    hash = (hash << 5) - hash + value.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}
