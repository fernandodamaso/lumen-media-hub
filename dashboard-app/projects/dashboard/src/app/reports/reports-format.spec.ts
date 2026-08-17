import type { MediaStackCronLogsDto } from '../media-stack/wire/cron';
import type { AutomationProblem, AutomationService } from '../automation/automation.models';
import {
  buildServiceHealthReportView,
  cronStatusView,
  formatGeneratedAt,
  formatRunTimestamp,
  mapCronLogs,
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

  it('maps current vs history and resolves older actionables after a quiet success', () => {
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
          current: { timestamp: '2026-07-12T12:00:00Z', status: 'ok', detail: 'Checked 1, no repairs needed' },
          history: [
            { timestamp: '2026-07-12T11:00:00Z', status: 'ok', detail: 'Summary: 1 file(s) can be freed (~0.88 GiB), 1 file(s) kept' },
            { timestamp: '2026-07-12T11:30:00Z', status: 'fatal', detail: 'Timeout', fatal: 'Timeout' },
          ],
        },
      ],
    };
    const logs = mapCronLogs(dto);
    expect(logs.currentRuns).toHaveLength(1);
    expect(logs.currentRuns[0].triage).toBe('quiet');
    // Both older actionable rows (positive dry-run + fatal) resolved by the newer success.
    expect(logs.historyRuns).toHaveLength(2);
    expect(logs.historyRuns.map((run) => run.triage)).toEqual(['actionable', 'actionable']);
    expect(logs.historyRuns.every((run) => run.resolved)).toBe(true);
  });

  it('does not resolve history when the current run is still fatal', () => {
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
          current: { timestamp: '2026-07-12T12:00:00Z', status: 'fatal', detail: 'Disk full', fatal: 'Disk full' },
          history: [{ timestamp: '2026-07-12T11:00:00Z', status: 'ok', detail: 'Checked 1, no repairs needed' }],
        },
      ],
    };
    const logs = mapCronLogs(dto);
    expect(logs.currentRuns[0].triage).toBe('actionable');
    expect(logs.historyRuns[0].triage).toBe('quiet');
    expect(logs.historyRuns[0].resolved).toBe(false);
  });

  it('carries missing and unparsed current sentinels as actionable current rows', () => {
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
          mtime: null,
          current: { status: 'missing', detail: 'No log file yet' },
          history: [],
        },
        {
          id: 'weekly-validate',
          title: 'Weekly validate',
          file: 'weekly-validate.log',
          format: 'text',
          schedule: '0 4 * * 0',
          exists: true,
          current: { status: 'unparsed', detail: 'No recent runs' },
          history: [],
        },
      ],
    };
    const logs = mapCronLogs(dto);
    expect(logs.currentRuns).toHaveLength(2);
    expect(logs.currentRuns[0]).toMatchObject({
      jobId: 'watchdog',
      status: 'missing',
      triage: 'actionable',
      detail: 'No log file yet',
    });
    expect(logs.currentRuns[1]).toMatchObject({
      jobId: 'weekly-validate',
      status: 'unparsed',
      triage: 'actionable',
      detail: 'No recent runs',
    });
    expect(logs.historyRuns).toHaveLength(0);
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

describe('buildServiceHealthReportView', () => {
  const services: AutomationService[] = [
    { id: 'sonarr', name: 'Sonarr', status: 'healthy', detail: 'OK', latencyMs: 20 },
    { id: 'prowlarr', name: 'Prowlarr', status: 'degraded', detail: '1 indexer disabled', latencyMs: 350 },
    { id: 'sabnzbd', name: 'SABnzbd', status: 'down', detail: 'Last seen 18m ago' },
  ];
  const problems: AutomationProblem[] = [
    { id: 'p1', summary: 'SABnzbd unreachable', serviceId: 'sabnzbd', severity: 'actionable' },
    { id: 'p2', summary: '1 indexer(s) disabled', serviceId: 'prowlarr', severity: 'warning' },
    { id: 'p3', summary: '4 Sonarr episode(s) missing', serviceId: 'sonarr', severity: 'warning' },
    { id: 'p4', summary: 'Disk space low', serviceId: null, severity: 'actionable' },
  ];

  it('shows active services and relevant problems without a selection', () => {
    const view = buildServiceHealthReportView(services, problems, null);
    expect(view.services.map((service) => service.id)).toEqual(['prowlarr', 'sabnzbd']);
    expect(view.problems.map((problem) => problem.id)).toEqual(['p1', 'p2', 'p4']);
    expect(view.noIssuesMessage).toBeNull();
  });

  it('filters to a selected degraded service and its problems', () => {
    const view = buildServiceHealthReportView(services, problems, 'prowlarr');
    expect(view.services).toEqual([services[1]]);
    expect(view.problems).toEqual([problems[1]]);
    expect(view.noIssuesMessage).toBeNull();
  });

  it('shows healthy recovery without leftover warning problems', () => {
    const view = buildServiceHealthReportView(services, problems, 'sonarr');
    expect(view.services).toEqual([services[0]]);
    expect(view.problems).toEqual([]);
    expect(view.noIssuesMessage).toBe('No current live issues.');
  });

  it('preserves service detail when no structured problem exists', () => {
    const view = buildServiceHealthReportView(
      [{ id: 'radarr', name: 'Radarr', status: 'down', detail: 'Connection refused' }],
      [],
      'radarr',
    );
    expect(view.services[0]?.detail).toBe('Connection refused');
    expect(view.problems).toEqual([]);
  });

  it('falls back to active issues for unknown service ids', () => {
    const view = buildServiceHealthReportView(services, problems, 'missing-service');
    expect(view.unknownServiceNotice).toBe('Unknown service. Showing all current issues.');
    expect(view.services.map((service) => service.id)).toEqual(['prowlarr', 'sabnzbd']);
  });

  it('shows an all-clear message when nothing is degraded or down', () => {
    const view = buildServiceHealthReportView(
      [{ id: 'sonarr', name: 'Sonarr', status: 'healthy', detail: 'OK', latencyMs: 20 }],
      [],
      null,
    );
    expect(view.services).toEqual([]);
    expect(view.problems).toEqual([]);
    expect(view.noIssuesMessage).toBe('No current live issues.');
  });
});
