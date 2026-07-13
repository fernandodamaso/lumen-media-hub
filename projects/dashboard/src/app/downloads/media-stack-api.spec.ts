import {
  normalizeTorrent,
  summarizeDownloads,
  normalizeCalendarEvent,
  normalizeLibraryItem,
  resolveJellyfinItemLink,
  DEFAULT_LIBRARY_ART,
  normalizeAutomationSummary,
  summarizeAutomationHealth,
  AutomationSummary,
} from './media-stack-api';

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

  it('normalizes library DTO meta and artwork state', () => {
    const present = normalizeLibraryItem({
      id: 'jf-dune',
      title: 'Dune',
      kind: 'movie',
      year: 2021,
      overview: 'Desert power.',
      posterUrl: 'linear-gradient(145deg, #8b5a2b, #1a1a1a 70%)',
    });
    expect(present).toMatchObject({
      id: 'jf-dune',
      title: 'Dune',
      kind: 'movie',
      meta: '2021 · Movie',
      artworkState: 'ok',
      playable: true,
      href: null,
    });
    expect(present?.art).toContain('gradient');

    const missing = normalizeLibraryItem({
      id: 'jf-missing',
      title: 'Night Transit',
      kind: 'movie',
      year: 2026,
    });
    expect(missing?.artworkState).toBe('missing');
    expect(missing?.art).toBe(DEFAULT_LIBRARY_ART);
    expect(missing?.meta).toBe('2026 · Movie');

    const failed = normalizeLibraryItem({
      id: 'jf-failed',
      title: 'Broken Art',
      kind: 'series',
      posterUrl: 'http://example.invalid/poster.jpg',
      artworkState: 'failed',
    });
    expect(failed?.artworkState).toBe('failed');
    expect(failed?.art).toBe(DEFAULT_LIBRARY_ART);
    expect(failed?.meta).toBe('Series');
  });

  it('drops unknown library kinds instead of coercing them to movie', () => {
    expect(
      normalizeLibraryItem({
        id: 'jf-season',
        title: 'Season 1',
        kind: 'Season',
      }),
    ).toBeNull();
    expect(
      normalizeLibraryItem({
        id: 'jf-folder',
        title: 'Collections',
        kind: 'Folder',
      }),
    ).toBeNull();
  });

  it('sizes remote poster URLs to cover the 2:3 art host', () => {
    const item = normalizeLibraryItem({
      id: 'jf-poster',
      title: 'Afterlight',
      kind: 'movie',
      posterUrl: 'https://jellyfin.example/Items/jf-poster/Images/Primary',
    });
    expect(item?.art).toBe(
      'url("https://jellyfin.example/Items/jf-poster/Images/Primary") center / cover no-repeat',
    );
  });

  it('resolves Jellyfin detail links when configured and playable', () => {
    expect(
      resolveJellyfinItemLink({ id: 'jf-dune', playable: true }, { jellyfinBase: 'http://localhost:8096/' }),
    ).toBe('http://localhost:8096/web/index.html#!/details?id=jf-dune');
    expect(resolveJellyfinItemLink({ id: 'jf-dune', playable: false })).toBeNull();
    expect(resolveJellyfinItemLink({ id: '', playable: true })).toBeNull();
    expect(resolveJellyfinItemLink({ id: 'unknown', playable: true })).toBeNull();
  });

  it('normalizes a healthy automation summary DTO into a domain summary', () => {
    const summary = normalizeAutomationSummary({
      generatedAt: '2026-07-12T18:00:00Z',
      services: [{ id: 'sonarr', name: 'Sonarr', status: 'healthy', detail: 'OK' }],
      preview: [{ id: 'p1', title: 'Dune', when: 'Jul 13', kind: 'movie' }],
      problems: [{ id: 'x1', summary: 'Disk low', serviceId: 'radarr', severity: 'actionable' }],
    });
    expect(summary.generatedAt).toBe('2026-07-12T18:00:00Z');
    expect(summary.services).toHaveLength(1);
    expect(summary.services[0].status).toBe('healthy');
    expect(summary.availability).toEqual({ services: 'present', preview: 'present', problems: 'present' });
  });

  it.each(['broken', 'OFFLINE', '', undefined as unknown as string])('clamps unknown or missing automation status %j to unknown', (status) => {
    const summary = normalizeAutomationSummary({
      generatedAt: '',
      services: [{ id: 'x', name: 'X', status }],
    });
    expect(summary.services[0].status).toBe('unknown');
  });

  it('defaults missing problem severity to info', () => {
    const summary = normalizeAutomationSummary({
      generatedAt: '',
      problems: [{ id: 'x', summary: 'X', severity: undefined as unknown as string }],
    });
    expect(summary.problems[0].severity).toBe('info');
  });

  it('marks null sections with unavailable flag as unavailable', () => {
    const summary = normalizeAutomationSummary({
      generatedAt: '',
      services: null,
      preview: [],
      unavailable: { services: true },
    });
    expect(summary.availability).toEqual({ services: 'unavailable', preview: 'empty', problems: 'unavailable' });
  });

  it('marks undefined/null sections without flag as unavailable', () => {
    const summary = normalizeAutomationSummary({
      generatedAt: '',
    });
    expect(summary.availability).toEqual({ services: 'unavailable', preview: 'unavailable', problems: 'unavailable' });
  });

  it('defaults missing generatedAt and string fields to empty values', () => {
    const summary = normalizeAutomationSummary({
      generatedAt: undefined as unknown as string,
      services: [{ id: undefined as unknown as string, name: undefined as unknown as string, status: 'down' }],
      preview: [{ id: undefined as unknown as string, title: undefined as unknown as string }],
      problems: [{ id: undefined as unknown as string, summary: undefined as unknown as string }],
    });
    expect(summary.generatedAt).toBe('');
    expect(summary.services[0]).toEqual({ id: '', name: '', status: 'down', detail: '' });
    expect(summary.preview[0]).toEqual({ id: '', title: '', when: '', kind: '' });
    expect(summary.problems[0]).toEqual({ id: '', summary: '', serviceId: null, severity: 'info' });
  });

  it('summarizes overall health as worst service status and counts actionable problems', () => {
    const summary: AutomationSummary = {
      generatedAt: '',
      services: [
        { id: 'a', name: 'A', status: 'healthy', detail: '' },
        { id: 'b', name: 'B', status: 'down', detail: '' },
        { id: 'c', name: 'C', status: 'degraded', detail: '' },
      ],
      preview: [],
      problems: [
        { id: 'p1', summary: '', serviceId: null, severity: 'actionable' },
        { id: 'p2', summary: '', serviceId: null, severity: 'actionable' },
        { id: 'p3', summary: '', serviceId: null, severity: 'warning' },
      ],
      availability: { services: 'present', preview: 'empty', problems: 'present' },
    };
    expect(summarizeAutomationHealth(summary)).toEqual({ overall: 'down', actionableCount: 2 });
  });

  it('summarizes empty services as unknown with zero actionables', () => {
    const summary: AutomationSummary = {
      generatedAt: '',
      services: [],
      preview: [],
      problems: [],
      availability: { services: 'empty', preview: 'empty', problems: 'empty' },
    };
    expect(summarizeAutomationHealth(summary)).toEqual({ overall: 'unknown', actionableCount: 0 });
  });
});
