import {
  flattenCronRuns,
  isQuietRun,
  normalizeTorrent,
  summarizeDownloads,
  normalizeCalendarEvent,
  normalizeCronRun,
  normalizeLibraryItem,
  resolveJellyfinItemLink,
  DEFAULT_LIBRARY_ART,
  normalizeAutomationSummary,
  summarizeAutomationHealth,
  prioritizeCronRuns,
  summarizeCronHealth,
  AutomationSummary,
  type CronRun,
  type MediaStackCronLogsDto,
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

describe('cron log triage helpers', () => {
  const job = { id: 'watchdog', title: 'Watchdog' };

  it('classifies clean success as quiet and failures as actionable', () => {
    expect(isQuietRun({ status: 'ok', detail: 'Checked 3, no repairs needed' })).toBe(true);
    expect(isQuietRun({ status: ' OK ', detail: 'Checked 3, no repairs needed' })).toBe(true);
    expect(isQuietRun({ status: 'ok', detail: '' })).toBe(true);
    expect(isQuietRun({ status: 'fatal', detail: 'Disk full', fatal: 'Disk full' })).toBe(false);
    expect(isQuietRun({ status: 'warn', detail: 'Stale metadata found' })).toBe(false);
    expect(isQuietRun({ status: 'ok', applied: 2, detail: 'Applied 2 repairs' })).toBe(false);
    expect(isQuietRun({ status: 'ok', detail: '2.1 GB can be freed' })).toBe(false);
    expect(isQuietRun({ status: 'ok', detail: 'No stale entries; blocker: Radarr offline' })).toBe(false);
    expect(isQuietRun({ status: 'ok', detail: 'No stale cleanup: 2 GB can be freed' })).toBe(false);
    expect(isQuietRun({ status: 'ok', detail: 'No stale metadata found' })).toBe(true);
    expect(isQuietRun({ exitCode: 1, detail: '' })).toBe(false);
    expect(isQuietRun({ exitCode: 0, detail: '' })).toBe(true);
  });

  it('normalizes a run while preserving contract status', () => {
    const run = normalizeCronRun(
      job,
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

  it('prioritizes actionable failures before quiet successes', () => {
    const quietOlder: CronRun = {
      id: 'q1',
      jobId: 'weekly-validate',
      jobTitle: 'Weekly validate',
      status: 'ok',
      triage: 'quiet',
      timestamp: '2026-07-12T09:00:00Z',
      detail: 'Completed',
      fatal: null,
      applied: null,
      exitCode: 0,
    };
    const quietNewer: CronRun = {
      id: 'q2',
      jobId: 'hardlink-cleanup',
      jobTitle: 'Hardlink cleanup',
      status: 'ok',
      triage: 'quiet',
      timestamp: '2026-07-12T11:00:00Z',
      detail: 'Nothing to check',
      fatal: null,
      applied: null,
      exitCode: 0,
    };
    const warn: CronRun = {
      id: 'w1',
      jobId: 'stale-metadata',
      jobTitle: 'Stale metadata',
      status: 'warn',
      triage: 'actionable',
      timestamp: '2026-07-12T10:00:00Z',
      detail: 'Stale entries found',
      fatal: null,
      applied: null,
      exitCode: 0,
    };
    const fatal: CronRun = {
      id: 'f1',
      jobId: 'watchdog',
      jobTitle: 'Watchdog',
      status: 'fatal',
      triage: 'actionable',
      timestamp: '2026-07-12T08:00:00Z',
      detail: 'Disk full',
      fatal: 'Disk full',
      applied: null,
      exitCode: 1,
    };

    expect(prioritizeCronRuns([quietOlder, quietNewer, warn, fatal]).map((run) => run.id)).toEqual([
      'f1',
      'w1',
      'q2',
      'q1',
    ]);
  });

  it('summarizes empty, all-clear, and mixed health without manufacturing alerts', () => {
    expect(summarizeCronHealth([])).toEqual({ kind: 'empty', total: 0, actionable: 0, quiet: 0 });

    const quiet: CronRun = {
      id: 'q',
      jobId: 'watchdog',
      jobTitle: 'Watchdog',
      status: 'ok',
      triage: 'quiet',
      timestamp: '2026-07-12T11:00:00Z',
      detail: 'Checked 1, no repairs needed',
      fatal: null,
      applied: null,
      exitCode: 0,
    };
    expect(summarizeCronHealth([quiet])).toEqual({ kind: 'allClear', total: 1, actionable: 0, quiet: 1 });

    const fatal: CronRun = { ...quiet, id: 'f', status: 'fatal', triage: 'actionable', detail: 'Boom', fatal: 'Boom' };
    expect(summarizeCronHealth([quiet, fatal])).toEqual({ kind: 'mixed', total: 2, actionable: 1, quiet: 1 });
  });
});
