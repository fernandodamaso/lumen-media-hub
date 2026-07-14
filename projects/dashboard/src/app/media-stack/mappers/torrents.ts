import { DownloadTorrent, TorrentState } from '../../downloads/downloads.models';
import { MediaStackTorrentDto } from '../wire/torrents';

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
