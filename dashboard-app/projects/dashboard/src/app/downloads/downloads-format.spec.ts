import { formatEta, formatRate, formatRateParts, mapTorrent, TORRENT_STATE_VIEW } from './downloads-format';

describe('downloads format / torrent mapping', () => {
  it('maps qBittorrent DTO state and progress without leaking raw fields', () => {
    const torrent = mapTorrent({
      hash: 'abc',
      name: 'Example',
      state: 'forcedDL',
      progress: 0.42,
      size: 100,
      downloaded: 42,
      dlspeed: 20,
      upspeed: 4,
      eta: 90,
    });
    expect(torrent).toEqual({
      id: 'abc',
      name: 'Example',
      state: 'downloading',
      progress: 42,
      size: 100,
      downloaded: 42,
      downloadRate: 20,
      uploadRate: 4,
      eta: 90,
      category: 'Uncategorized',
    });
  });

  it.each(['paused', 'pausedDL', 'PAUSEDUP', 'stoppedDL', 'stoppedUP'])(
    'maps qBittorrent paused/stopped state %s case-insensitively',
    (state) => {
    const torrent = mapTorrent({
      hash: 'paused',
      name: 'Paused',
      state,
      progress: 0.5,
      size: 100,
      downloaded: 50,
      dlspeed: 0,
      upspeed: 0,
      eta: 0,
    });
    expect(torrent.state).toBe('paused');
  });

  it.each([
    ['queuedUP', 'seeding'],
    ['checkingUP', 'checking'],
    ['errorUP', 'error'],
  ])('maps qBittorrent state %s before upload fallback', (state, expected) => {
    const torrent = mapTorrent({
      hash: 'state',
      name: 'State',
      state,
      progress: 0,
      size: 100,
      downloaded: 0,
      dlspeed: 0,
      upspeed: 0,
      eta: 0,
    });
    expect(torrent.state).toBe(expected);
  });

  it('formats short ETAs in seconds and longer ones in minutes or hours', () => {
    expect(formatEta(30)).toBe('30s');
    expect(formatEta(90)).toBe('1m');
    expect(formatEta(3660)).toBe('1h 1m');
  });

  it('maps error torrents to a danger tone', () => {
    expect(TORRENT_STATE_VIEW.error).toEqual({ label: 'Error', tone: 'danger' });
    expect(TORRENT_STATE_VIEW.downloading.tone).toBe('info');
    expect(TORRENT_STATE_VIEW.seeding.tone).toBe('success');
  });

  it.each([
    [0, '0', 'B/s'],
    [500 * 1024, '500.0', 'KB/s'],
    [10 * 1024 * 1024, '10.0', 'MB/s'],
    [5 * 1024 * 1024 * 1024, '5.0', 'GB/s'],
  ])('formatRateParts(%d) returns { value: %s, unit: %s } consistent with formatRate', (bytes, value, unit) => {
    const parts = formatRateParts(bytes);
    expect(parts).toEqual({ value, unit });
    expect(formatRate(bytes)).toBe(`${value} ${unit}`);
  });
});
