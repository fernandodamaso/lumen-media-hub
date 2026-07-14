export type TorrentState = 'downloading' | 'seeding' | 'paused' | 'queued' | 'checking' | 'error';

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

export const summarizeDownloads = (torrents: DownloadTorrent[]): DownloadSummary => ({
  active: torrents.filter((torrent) => torrent.state === 'downloading').length,
  total: torrents.length,
  downloaded: torrents.reduce((sum, torrent) => sum + torrent.downloaded, 0),
  size: torrents.reduce((sum, torrent) => sum + torrent.size, 0),
  downloadRate: torrents.reduce((sum, torrent) => sum + torrent.downloadRate, 0),
  uploadRate: torrents.reduce((sum, torrent) => sum + torrent.uploadRate, 0),
});
