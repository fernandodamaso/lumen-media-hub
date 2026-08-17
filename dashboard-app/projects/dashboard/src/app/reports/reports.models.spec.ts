import { CronRun, isQuietRun, prioritizeCronRuns, summarizeCronHealth } from './reports.models';

describe('reports.models cron triage helpers', () => {
  it('classifies clean success as quiet and failures as actionable', () => {
    expect(isQuietRun({ status: 'ok', detail: 'Checked 3, no repairs needed' })).toBe(true);
    expect(isQuietRun({ status: ' OK ', detail: 'Checked 3, no repairs needed' })).toBe(true);
    expect(isQuietRun({ status: 'ok', detail: '' })).toBe(true);
    expect(isQuietRun({ status: 'fatal', detail: 'Disk full', fatal: 'Disk full' })).toBe(false);
    expect(isQuietRun({ status: 'warn', detail: 'Stale metadata found' })).toBe(false);
    expect(isQuietRun({ status: 'ok', applied: 2, detail: 'Applied 2 repairs' })).toBe(false);
    expect(isQuietRun({ status: 'ok', detail: '2.1 GB can be freed' })).toBe(false);
    expect(isQuietRun({ status: 'ok', detail: '0 file(s) can be freed (~0 GiB), 2 file(s) kept' })).toBe(true);
    expect(isQuietRun({ status: 'ok', detail: '0 bytes can be freed' })).toBe(true);
    // Unparseable freeable-space phrase stays actionable.
    expect(isQuietRun({ status: 'ok', detail: 'several files can be freed' })).toBe(false);
    // Successful Weekly Validate blocks end with "Phase completed: …" and are quiet.
    expect(isQuietRun({ status: 'ok', detail: 'Phase completed: 6 (Tasks 19-20)' })).toBe(true);
    expect(isQuietRun({ status: 'ok', detail: 'No stale entries; blocker: Radarr offline' })).toBe(false);
    expect(isQuietRun({ status: 'ok', detail: 'No stale cleanup: 2 GB can be freed' })).toBe(false);
    expect(isQuietRun({ status: 'ok', detail: 'No stale metadata found' })).toBe(true);
    expect(isQuietRun({ status: 'ok', detail: 'All services are healthy' })).toBe(true);
    expect(isQuietRun({ status: 'ok', detail: 'All services are healthy; fail reported' })).toBe(false);
    expect(isQuietRun({ exitCode: 1, detail: '' })).toBe(false);
    expect(isQuietRun({ exitCode: 0, detail: '' })).toBe(true);
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
    expect(summarizeCronHealth([])).toEqual({ kind: 'empty', totalJobs: 0, affectedJobs: 0, healthyJobs: 0 });

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
    expect(summarizeCronHealth([quiet])).toEqual({ kind: 'allClear', totalJobs: 1, affectedJobs: 0, healthyJobs: 1 });

    const fatal: CronRun = { ...quiet, id: 'f', status: 'fatal', triage: 'actionable', detail: 'Boom', fatal: 'Boom' };
    expect(summarizeCronHealth([quiet, fatal])).toEqual({ kind: 'mixed', totalJobs: 2, affectedJobs: 1, healthyJobs: 1 });
  });
});
