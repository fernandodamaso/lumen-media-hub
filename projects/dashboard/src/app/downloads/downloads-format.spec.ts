import { formatEta, TORRENT_STATE_VIEW } from './downloads-format';

describe('downloads format helpers', () => {
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
});
