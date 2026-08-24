import { DownloadTorrent, TorrentState } from './downloads.models';
import { MediaStackTorrentDto } from '../media-stack/wire/torrents';

export type StatusTone = 'success' | 'warning' | 'danger' | 'info';

type TorrentDtoWithCompletion = Omit<MediaStackTorrentDto, 'completionOn'> & { completionOn?: unknown };

export const mapTorrent = (torrent: TorrentDtoWithCompletion): DownloadTorrent => {
  const progress = clamp(torrent.progress * 100);

  return {
    id: torrent.hash,
    name: torrent.name,
    state: normalizeState(torrent.state),
    progress,
    size: Math.max(0, torrent.size),
    downloaded: Math.max(0, torrent.downloaded),
    downloadRate: Math.max(0, torrent.dlspeed),
    uploadRate: Math.max(0, torrent.upspeed),
    eta: Math.max(0, torrent.eta),
    category: torrent.category ?? 'Uncategorized',
    completed: progress >= 100,
    completedAt: completionIso(torrent.completionOn),
  };
};

function completionIso(completionOn: unknown): string | null {
  if (typeof completionOn !== 'number' || !Number.isInteger(completionOn) || completionOn <= 0) return null;
  const date = new Date(completionOn * 1000);
  return Number.isFinite(date.getTime()) ? date.toISOString() : null;
}

function clamp(value: number): number {
  return Math.round(Math.min(100, Math.max(0, value)) * 10) / 10;
}

function normalizeState(state: string): TorrentState {
  const normalized = state.toLowerCase();
  if (normalized.includes('paused') || normalized.startsWith('stopped')) return 'paused';
  if (normalized.includes('error')) return 'error';
  if (normalized.includes('check')) return 'checking';
  if (normalized === 'downloading' || normalized === 'forceddl') return 'downloading';
  if (normalized.includes('up') || normalized === 'seeding') return 'seeding';
  if (normalized.includes('queued')) return 'queued';
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
type TorrentGroupState = TorrentState | 'completed';

export interface TorrentGroup {
  state: TorrentGroupState;
  label: string;
  torrents: DownloadTorrent[];
}

export function groupTorrents(torrents: DownloadTorrent[]): TorrentGroup[] {
  const operationalGroups = STATE_ORDER.map((state) => ({
    state,
    label: TORRENT_STATE_VIEW[state].label,
    torrents: torrents.filter((torrent) => !torrent.completed && torrent.state === state),
  })).filter((group) => group.torrents.length > 0);
  const completed = torrents.filter((torrent) => torrent.completed);

  return completed.length
    ? [...operationalGroups, { state: 'completed', label: 'Completed', torrents: completed }]
    : operationalGroups;
}

export function torrentDisplayLabel(torrent: DownloadTorrent): string {
  return torrent.completed ? 'Complete' : TORRENT_STATE_VIEW[torrent.state].label;
}

export function torrentDisplayTone(torrent: DownloadTorrent): StatusTone {
  return torrent.completed ? 'success' : TORRENT_STATE_VIEW[torrent.state].tone;
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
