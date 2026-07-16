import type { MediaStackCronLogsDto } from '../media-stack/wire/cron';
import {
  cronStatusView,
  flattenCronRuns,
  formatGeneratedAt,
  formatRunTimestamp,
  mapCronRun,
} from './reports-format';

describe('reports format / cron mapping', () => {
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

  it.each([
    ['ok', 'ok', 'success'],
    ['fatal', 'failed', 'danger'],
    ['warn', 'warn', 'warning'],
    ['applied', 'repaired', 'success'],
    ['unparsed', 'unknown', 'info'],
    ['missing', 'no log', 'info'],
  ] as const)('maps status %s to label/tone', (status, label, tone) => {
    expect(cronStatusView(status)).toEqual({ label, tone });
  });

  it('falls back for unknown statuses without inventing failure tones', () => {
    expect(cronStatusView('custom')).toEqual({ label: 'custom', tone: 'info' });
    expect(cronStatusView('')).toEqual({ label: 'ok', tone: 'success' });
  });

  it('formats timestamps for display', () => {
    expect(formatGeneratedAt('')).toBe('');
    expect(formatRunTimestamp('')).toBe('Unknown time');
    expect(formatGeneratedAt('not-a-date')).toBe('not-a-date');
    expect(formatGeneratedAt('2026-07-12T12:00:00Z')).toBeTruthy();
    expect(formatRunTimestamp('2026-07-12T12:00:00Z')).toBeTruthy();
  });
});
