import {
  formatEta,
  formatRate,
  formatRateParts,
  groupTorrents,
  mapTorrent,
  torrentDisplayLabel,
  torrentDisplayTone,
  TORRENT_STATE_VIEW,
} from './downloads-format';
import { DownloadTorrent } from './downloads.models';

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
      completed: false,
      completedAt: null,
    });
  });

  it('maps normalized completion and completionOn seconds to the domain', () => {
    expect(
      mapTorrent({
        hash: 'complete',
        name: 'Complete',
        state: 'queuedUP',
        progress: 1,
        size: 100,
        downloaded: 100,
        dlspeed: 0,
        upspeed: 4,
        eta: 0,
        completionOn: 1_720_000_000,
      }),
    ).toMatchObject({
      state: 'seeding',
      progress: 100,
      completed: true,
      completedAt: '2024-07-03T09:46:40.000Z',
    });
  });

  it.each(['queuedUP', 'stalledUP', 'uploading'])('keeps %s as operational seeding when complete', (state) => {
    expect(
      mapTorrent({
        hash: state,
        name: 'Complete',
        state,
        progress: 1,
        size: 100,
        downloaded: 100,
        dlspeed: 0,
        upspeed: 0,
        eta: 0,
      }),
    ).toMatchObject({ state: 'seeding', completed: true });
  });

  it('keeps a completed paused torrent operationally paused', () => {
    expect(
      mapTorrent({
        hash: 'paused',
        name: 'Complete but paused',
        state: 'pausedUP',
        progress: 1,
        size: 100,
        downloaded: 100,
        dlspeed: 0,
        upspeed: 0,
        eta: 0,
      }),
    ).toMatchObject({ state: 'paused', completed: true });
  });

  it('leaves incomplete torrents incomplete when completionOn is missing', () => {
    expect(
      mapTorrent({
        hash: 'queued',
        name: 'Incomplete',
        state: 'queuedDL',
        progress: 0.5,
        size: 100,
        downloaded: 50,
        dlspeed: 0,
        upspeed: 0,
        eta: 60,
      }),
    ).toMatchObject({ state: 'queued', progress: 50, completed: false, completedAt: null });
  });

  it.each([undefined, null, 0, -1, Number.NaN, Number.POSITIVE_INFINITY, Number.MAX_SAFE_INTEGER, 'not-a-timestamp'])
    ('returns null for an unknown or invalid completionOn value: %s', (completionOn) => {
      expect(
        mapTorrent({
          hash: 'invalid-time',
          name: 'Invalid completion time',
          state: 'stalledUP',
          progress: 1,
          size: 100,
          downloaded: 100,
          dlspeed: 0,
          upspeed: 0,
          eta: 0,
          completionOn,
        }),
      ).toMatchObject({ completed: true, completedAt: null });
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

  it('uses completion for display label and tone without changing operational state', () => {
    const torrent: DownloadTorrent = {
      id: 'paused-complete',
      name: 'Paused complete',
      state: 'paused',
      progress: 100,
      size: 100,
      downloaded: 100,
      downloadRate: 0,
      uploadRate: 0,
      eta: 0,
      category: 'Movies',
      completed: true,
      completedAt: null,
    };

    expect(torrentDisplayLabel(torrent)).toBe('Complete');
    expect(torrentDisplayTone(torrent)).toBe('success');
    expect(torrent.state).toBe('paused');
  });

  it('uses the operational state for incomplete display', () => {
    const torrent: DownloadTorrent = {
      id: 'paused-active',
      name: 'Paused active',
      state: 'paused',
      progress: 50,
      size: 100,
      downloaded: 50,
      downloadRate: 0,
      uploadRate: 0,
      eta: 60,
      category: 'Movies',
      completed: false,
      completedAt: null,
    };

    expect(torrentDisplayLabel(torrent)).toBe('Paused');
    expect(torrentDisplayTone(torrent)).toBe('warning');
  });

  it('groups completed torrents separately while preserving their operational state', () => {
    const completedPaused: DownloadTorrent = {
      id: 'complete-paused',
      name: 'Complete paused',
      state: 'paused',
      progress: 100,
      size: 100,
      downloaded: 100,
      downloadRate: 0,
      uploadRate: 0,
      eta: 0,
      category: 'Movies',
      completed: true,
      completedAt: null,
    };
    const activePaused: DownloadTorrent = { ...completedPaused, id: 'active-paused', completed: false, progress: 50 };

    expect(groupTorrents([completedPaused, activePaused])).toEqual([
      { state: 'paused', label: 'Paused', torrents: [activePaused] },
      { state: 'completed', label: 'Completed', torrents: [completedPaused] },
    ]);
    expect(completedPaused.state).toBe('paused');
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
