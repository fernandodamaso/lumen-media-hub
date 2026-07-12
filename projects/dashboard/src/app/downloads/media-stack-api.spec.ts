import { normalizeTorrent, summarizeDownloads } from './media-stack-api';

describe('media-stack API boundary', () => {
  it('normalizes qBittorrent DTO state and progress without leaking raw fields', () => {
    const torrent = normalizeTorrent({ hash: 'abc', name: 'Example', state: 'forcedDL', progress: 0.42, size: 100, downloaded: 42, dlspeed: 20, upspeed: 4, eta: 90 });
    expect(torrent).toEqual({ id: 'abc', name: 'Example', state: 'downloading', progress: 42, size: 100, downloaded: 42, downloadRate: 20, uploadRate: 4, eta: 90, category: 'Uncategorized' });
  });

  it.each(['paused', 'pausedDL', 'PAUSEDUP'])('normalizes qBittorrent paused state %s case-insensitively', (state) => {
    const torrent = normalizeTorrent({ hash: 'paused', name: 'Paused', state, progress: .5, size: 100, downloaded: 50, dlspeed: 0, upspeed: 0, eta: 0 });
    expect(torrent.state).toBe('paused');
  });

  it('groups totals and active downloads from normalized state', () => {
    const downloading = normalizeTorrent({ hash: 'a', name: 'A', state: 'downloading', progress: .5, size: 100, downloaded: 50, dlspeed: 10, upspeed: 2, eta: 30 });
    const seeding = normalizeTorrent({ hash: 'b', name: 'B', state: 'stoppedUP', progress: 1, size: 200, downloaded: 200, dlspeed: 0, upspeed: 3, eta: 0 });
    expect(summarizeDownloads([downloading, seeding])).toEqual({ active: 1, total: 2, downloaded: 250, size: 300, downloadRate: 10, uploadRate: 5 });
  });
});
