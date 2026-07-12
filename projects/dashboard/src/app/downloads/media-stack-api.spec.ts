import { normalizeTorrent, summarizeDownloads, normalizeCalendarEvent } from './media-stack-api';

describe('media-stack API boundary', () => {
  it('normalizes qBittorrent DTO state and progress without leaking raw fields', () => {
    const torrent = normalizeTorrent({ hash: 'abc', name: 'Example', state: 'forcedDL', progress: 0.42, size: 100, downloaded: 42, dlspeed: 20, upspeed: 4, eta: 90 });
    expect(torrent).toEqual({ id: 'abc', name: 'Example', state: 'downloading', progress: 42, size: 100, downloaded: 42, downloadRate: 20, uploadRate: 4, eta: 90, category: 'Uncategorized' });
  });

  it.each(['paused', 'pausedDL', 'PAUSEDUP'])('normalizes qBittorrent paused state %s case-insensitively', (state) => {
    const torrent = normalizeTorrent({ hash: 'paused', name: 'Paused', state, progress: .5, size: 100, downloaded: 50, dlspeed: 0, upspeed: 0, eta: 0 });
    expect(torrent.state).toBe('paused');
  });

  it.each([
    ['queuedUP', 'queued'],
    ['checkingUP', 'checking'],
    ['errorUP', 'error'],
  ])('normalizes qBittorrent state %s before upload fallback', (state, expected) => {
    const torrent = normalizeTorrent({ hash: 'state', name: 'State', state, progress: 0, size: 100, downloaded: 0, dlspeed: 0, upspeed: 0, eta: 0 });
    expect(torrent.state).toBe(expected);
  });

  it('groups totals and active downloads from normalized state', () => {
    const downloading = normalizeTorrent({ hash: 'a', name: 'A', state: 'downloading', progress: .5, size: 100, downloaded: 50, dlspeed: 10, upspeed: 2, eta: 30 });
    const seeding = normalizeTorrent({ hash: 'b', name: 'B', state: 'stoppedUP', progress: 1, size: 200, downloaded: 200, dlspeed: 0, upspeed: 3, eta: 0 });
    expect(summarizeDownloads([downloading, seeding])).toEqual({ active: 1, total: 2, downloaded: 250, size: 300, downloadRate: 10, uploadRate: 5 });
  });

  it('normalizes calendar DTO fields into rail view-model values', () => {
    const event = normalizeCalendarEvent({
      title: 'Cowboy Bebop',
      additional: 'S1 E5',
      date: 'Jul 12',
      airDate: '2026-07-12T18:00:00Z',
      hasFile: true,
      kind: 'episode',
    });
    expect(event).toMatchObject({
      time: 'Jul 12',
      kind: 'episode',
      title: 'Cowboy Bebop',
      subtitle: 'S1 E5',
      status: 'available',
    });
  });
});
