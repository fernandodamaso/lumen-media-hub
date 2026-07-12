import { InjectionToken } from '@angular/core';

export type TorrentState = 'downloading' | 'seeding' | 'paused' | 'queued' | 'checking' | 'error';

/** Raw qBittorrent-shaped data stays behind this boundary. */
export interface MediaStackTorrentDto {
  hash: string;
  name: string;
  state: string;
  progress: number;
  size: number;
  downloaded: number;
  dlspeed: number;
  upspeed: number;
  eta: number;
  category?: string;
}

export interface MediaStackApi {
  listTorrents(): Promise<MediaStackTorrentDto[]>;
  pauseAll(): Promise<void>;
  resumeAll(): Promise<void>;
}

export const MEDIA_STACK_API = new InjectionToken<MediaStackApi>('MEDIA_STACK_API');
export const MEDIA_STACK_API_MODE = new InjectionToken<'mock' | 'http'>('MEDIA_STACK_API_MODE');

export interface DownloadTorrent {
  id: string;
  name: string;
  state: TorrentState;
  progress: number;
  size: number;
  downloaded: number;
  downloadRate: number;
  uploadRate: number;
  eta: number;
  category: string;
}

export interface DownloadSummary {
  active: number;
  total: number;
  downloaded: number;
  size: number;
  downloadRate: number;
  uploadRate: number;
}

export const normalizeTorrent = (torrent: MediaStackTorrentDto): DownloadTorrent => ({
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

export const summarizeDownloads = (torrents: DownloadTorrent[]): DownloadSummary => ({
  active: torrents.filter((torrent) => torrent.state === 'downloading').length,
  total: torrents.length,
  downloaded: torrents.reduce((sum, torrent) => sum + torrent.downloaded, 0),
  size: torrents.reduce((sum, torrent) => sum + torrent.size, 0),
  downloadRate: torrents.reduce((sum, torrent) => sum + torrent.downloadRate, 0),
  uploadRate: torrents.reduce((sum, torrent) => sum + torrent.uploadRate, 0),
});

function clamp(value: number): number {
  return Math.round(Math.min(100, Math.max(0, value)) * 10) / 10;
}

function normalizeState(state: string): TorrentState {
  if (state === 'downloading' || state === 'forcedDL') return 'downloading';
  if (state.includes('UP') || state === 'seeding') return 'seeding';
  if (state.includes('PAUSED')) return 'paused';
  if (state.includes('QUEUED') || state === 'queued') return 'queued';
  if (state.includes('CHECK')) return 'checking';
  if (state.includes('ERROR')) return 'error';
  return 'queued';
}
