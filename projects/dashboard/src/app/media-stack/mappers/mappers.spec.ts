import { mapAutomationSummary } from './automation';
import { mapCalendarEvent } from './calendar';
import { flattenCronRuns, mapCronRun } from './cron';
import { mapLibraryItem } from './library';
import { mapTorrent } from './torrents';
import { DEFAULT_LIBRARY_ART } from '../../library/library.models';
import type { MediaStackCronLogsDto } from '../wire/cron';

describe('media-stack wire mappers', () => {
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

  it.each(['paused', 'pausedDL', 'PAUSEDUP'])('maps qBittorrent paused state %s case-insensitively', (state) => {
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
    ['queuedUP', 'queued'],
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

  it('maps calendar DTO fields into rail domain values', () => {
    const event = mapCalendarEvent({
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

  it('maps library DTO meta and artwork state', () => {
    const present = mapLibraryItem({
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

    const missing = mapLibraryItem({
      id: 'jf-missing',
      title: 'Night Transit',
      kind: 'movie',
      year: 2026,
    });
    expect(missing?.artworkState).toBe('missing');
    expect(missing?.art).toBe(DEFAULT_LIBRARY_ART);
    expect(missing?.meta).toBe('2026 · Movie');

    const failed = mapLibraryItem({
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
      mapLibraryItem({
        id: 'jf-season',
        title: 'Season 1',
        kind: 'Season',
      }),
    ).toBeNull();
    expect(
      mapLibraryItem({
        id: 'jf-folder',
        title: 'Collections',
        kind: 'Folder',
      }),
    ).toBeNull();
  });

  it('sizes remote poster URLs to cover the 2:3 art host', () => {
    const item = mapLibraryItem({
      id: 'jf-poster',
      title: 'Afterlight',
      kind: 'movie',
      posterUrl: 'https://jellyfin.example/Items/jf-poster/Images/Primary',
    });
    expect(item?.art).toBe(
      'url("https://jellyfin.example/Items/jf-poster/Images/Primary") center / cover no-repeat',
    );
  });

  it('maps a healthy automation summary DTO into a domain summary', () => {
    const summary = mapAutomationSummary({
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

  it.each(['broken', 'OFFLINE', '', undefined as unknown as string])(
    'clamps unknown or missing automation status %j to unknown',
    (status) => {
      const summary = mapAutomationSummary({
        generatedAt: '',
        services: [{ id: 'x', name: 'X', status }],
      });
      expect(summary.services[0].status).toBe('unknown');
    },
  );

  it('defaults missing problem severity to info', () => {
    const summary = mapAutomationSummary({
      generatedAt: '',
      problems: [{ id: 'x', summary: 'X', severity: undefined as unknown as string }],
    });
    expect(summary.problems[0].severity).toBe('info');
  });

  it('marks null sections with unavailable flag as unavailable', () => {
    const summary = mapAutomationSummary({
      generatedAt: '',
      services: null,
      preview: [],
      unavailable: { services: true },
    });
    expect(summary.availability).toEqual({ services: 'unavailable', preview: 'empty', problems: 'unavailable' });
  });

  it('marks undefined/null sections without flag as unavailable', () => {
    const summary = mapAutomationSummary({
      generatedAt: '',
    });
    expect(summary.availability).toEqual({
      services: 'unavailable',
      preview: 'unavailable',
      problems: 'unavailable',
    });
  });

  it('defaults missing generatedAt and string fields to empty values', () => {
    const summary = mapAutomationSummary({
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

  it('maps a cron run while preserving contract status', () => {
    const run = mapCronRun(
      { id: 'watchdog', title: 'Watchdog' },
      { timestamp: '2026-07-12T10:00:00Z', status: 'fatal', detail: 'Disk full', fatal: 'Disk full', exitCode: 1 },
      0,
    );
    expect(run).toMatchObject({
      jobId: 'watchdog',
      jobTitle: 'Watchdog',
      status: 'fatal',
      triage: 'actionable',
      timestamp: '2026-07-12T10:00:00Z',
      detail: 'Disk full',
      fatal: 'Disk full',
      exitCode: 1,
    });
  });

  it('flattens nested cron logs into triage rows', () => {
    const dto: MediaStackCronLogsDto = {
      ok: true,
      generatedAt: '2026-07-12T12:00:00Z',
      logs: [
        {
          id: 'watchdog',
          title: 'Watchdog',
          file: 'watchdog.log',
          format: 'ndjson',
          schedule: '*/15 * * * *',
          exists: true,
          runs: [
            { timestamp: '2026-07-12T11:00:00Z', status: 'ok', detail: 'Checked 1, no repairs needed' },
            { timestamp: '2026-07-12T11:15:00Z', status: 'fatal', detail: 'Timeout', fatal: 'Timeout' },
          ],
        },
      ],
    };
    const runs = flattenCronRuns(dto);
    expect(runs).toHaveLength(2);
    expect(runs.map((run) => run.triage)).toEqual(['quiet', 'actionable']);
  });

  it('preserves job entries that have no nested runs', () => {
    const dto: MediaStackCronLogsDto = {
      ok: true,
      generatedAt: '2026-07-12T12:00:00Z',
      logs: [
        {
          id: 'watchdog',
          title: 'Watchdog',
          file: 'watchdog.log',
          format: 'ndjson',
          schedule: '*/15 * * * *',
          exists: false,
          summary: 'Log file missing',
          lastStatus: 'missing',
          mtime: null,
        },
        {
          id: 'weekly-validate',
          title: 'Weekly validate',
          file: 'weekly-validate.log',
          format: 'text',
          schedule: '0 4 * * 0',
          exists: true,
          runs: [],
        },
      ],
    };
    const runs = flattenCronRuns(dto);
    expect(runs).toHaveLength(2);
    expect(runs[0]).toMatchObject({
      jobId: 'watchdog',
      status: 'missing',
      triage: 'actionable',
      detail: 'Log file missing',
    });
    expect(runs[1]).toMatchObject({
      jobId: 'weekly-validate',
      status: 'unparsed',
      triage: 'actionable',
      detail: 'No recent runs',
    });
  });
});
