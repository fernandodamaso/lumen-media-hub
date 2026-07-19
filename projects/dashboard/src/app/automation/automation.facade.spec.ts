import { TestBed } from '@angular/core/testing';
import { computed, signal } from '@angular/core';
import { vi } from 'vitest';
import { MEDIA_STACK_API, MediaStackApi } from '../media-stack/media-stack-api';
import { CronLogs, CronRun } from '../reports/reports.models';
import { AutomationFacade } from './automation.facade';
import { AutomationSummary, summarizeAutomationHealth } from './automation.models';
import { ServiceHealthFacade, ServiceHealthStatus } from './service-health.facade';

describe('AutomationFacade', () => {
  let api: MockApi;
  let health: MockServiceHealthFacade;
  let facade: AutomationFacade;

  beforeEach(() => {
    api = new MockApi();
    health = new MockServiceHealthFacade();
    TestBed.configureTestingModule({
      providers: [
        AutomationFacade,
        { provide: MEDIA_STACK_API, useValue: api },
        { provide: ServiceHealthFacade, useValue: health },
      ],
    });
    facade = TestBed.inject(AutomationFacade);
  });

  it('starts in loading state', () => {
    expect(facade.status()).toBe('loading');
    expect(facade.latestRuns()).toEqual([]);
  });

  it('mirrors service health summary and health', () => {
    const summary: AutomationSummary = {
      generatedAt: '2026-07-12T18:00:00Z',
      services: [{ id: 'sonarr', name: 'Sonarr', status: 'healthy', detail: 'OK', latencyMs: 20 }],
      preview: [],
      problems: [],
      availability: { services: 'present', preview: 'empty', problems: 'empty' },
    };
    health.summary.set(summary);
    expect(facade.summary()).toBe(summary);
    expect(facade.health()).toEqual({ overall: 'healthy', actionableCount: 0 });
  });

  it('moves from loading to ready when cron logs have runs', async () => {
    api.cronLogs = {
      ok: true,
      runs: [
        {
          id: 'cleanup-1',
          jobId: 'cleanup',
          jobTitle: 'Cleanup',
          status: 'ok',
          triage: 'quiet',
          timestamp: '2026-07-14T12:00:00Z',
          detail: '',
          fatal: null,
          applied: null,
          exitCode: null,
          schedule: 'Hourly',
        },
      ],
    };
    expect(facade.status()).toBe('loading');
    await facade.refresh();
    expect(facade.status()).toBe('ready');
    expect(facade.tasks()).toHaveLength(1);
  });

  it('reports empty when cron logs return no runs', async () => {
    api.cronLogs = { ok: true, runs: [] };
    await facade.refresh();
    expect(facade.status()).toBe('empty');
    expect(facade.tasks()).toEqual([]);
  });

  it('computes latestRuns as the three most recent unique jobs', async () => {
    api.cronLogs = {
      ok: true,
      runs: [
        cronRun('Watchdog', '2026-07-14T11:00:00Z'),
        cronRun('Watchdog', '2026-07-14T12:00:00Z'),
        cronRun('Cleanup', '2026-07-14T10:00:00Z'),
        cronRun('Metadata', '2026-07-14T09:00:00Z'),
        cronRun('Metadata', '2026-07-14T13:00:00Z'),
      ],
    };
    await facade.refresh();
    expect(facade.latestRuns()).toHaveLength(3);
    expect(facade.latestRuns().map((run) => run.jobTitle)).toEqual(['Metadata', 'Watchdog', 'Cleanup']);
  });

  it('reports error and preserves recoverability', async () => {
    api.cronFailure = true;
    await facade.refresh();
    expect(facade.status()).toBe('error');
    expect(facade.error()).toContain('temporarily unavailable');

    api.cronFailure = false;
    api.cronLogs = {
      ok: true,
      runs: [cronRun('watchdog', new Date().toISOString())],
    };
    await facade.refresh();
    expect(facade.status()).toBe('ready');
  });

  it('refreshes on one interval and stops polling when destroyed', async () => {
    vi.useFakeTimers();
    facade.startPolling(100);
    await vi.advanceTimersByTimeAsync(0);
    expect(api.cronCalls).toBe(1);
    facade.startPolling(100);
    await vi.advanceTimersByTimeAsync(200);
    expect(api.cronCalls).toBe(3);
    TestBed.resetTestingModule();
    await vi.advanceTimersByTimeAsync(200);
    expect(api.cronCalls).toBe(3);
    vi.useRealTimers();
  });
});

function cronRun(jobTitle: string, timestamp: string): CronRun {
  return {
    id: `${jobTitle.toLowerCase()}-${timestamp}`,
    jobId: jobTitle.toLowerCase(),
    jobTitle,
    status: 'ok',
    triage: 'quiet',
    timestamp,
    detail: '',
    fatal: null,
    applied: null,
    exitCode: null,
    schedule: 'Monitoring',
  };
}

class MockServiceHealthFacade {
  status = signal<ServiceHealthStatus>('loading');
  summary = signal<AutomationSummary | null>(null);
  error = signal('');
  services = computed(() => this.summary()?.services ?? []);
  problems = computed(() => this.summary()?.problems ?? []);
  generatedAt = computed(() => this.summary()?.generatedAt ?? '');
  health = computed(() => {
    const summary = this.summary();
    return summary ? summarizeAutomationHealth(summary) : { overall: 'unknown' as const, actionableCount: 0 };
  });
  startPolling = vi.fn();
  refresh = vi.fn();
}

class MockApi implements MediaStackApi {
  cronFailure = false;
  cronLogs: CronLogs = { ok: true, runs: [] };
  cronCalls = 0;

  listCronLogs() {
    this.cronCalls++;
    return this.cronFailure
      ? Promise.reject(new Error('offline'))
      : Promise.resolve(structuredClone(this.cronLogs));
  }

  getAutomationSummary(): Promise<AutomationSummary> {
    return Promise.reject(new Error('not used'));
  }

  listTorrents() {
    return Promise.resolve([]);
  }
  pauseAll() {
    return Promise.resolve();
  }
  resumeAll() {
    return Promise.resolve();
  }
  pauseTorrent() {
    return Promise.resolve();
  }
  resumeTorrent() {
    return Promise.resolve();
  }
  getLibraryStats() {
    return Promise.resolve({ movies: 0, series: 0, availability: 'complete' as const });
  }
  getStorageOverview() {
    return Promise.resolve({ generatedAt: '', volumes: [] });
  }
  listCalendarEvents() {
    return Promise.resolve([]);
  }
  getArrLibrary() {
    return Promise.resolve({ ok: true, series: {}, movies: {} });
  }
  listLibraryItems() {
    return Promise.resolve({ items: [], availability: 'complete' as const });
  }
  listHermesRecommendations() {
    return Promise.resolve({ ok: true, items: [] });
  }
  submitHermesFeedback() {
    return Promise.resolve({ ok: true });
  }
  requestHermesMore() {
    return Promise.resolve({ ok: true });
  }
  listJellyseerrDiscover() {
    return Promise.resolve({ ok: true, items: [] });
  }
  listTraktDiscover() {
    return Promise.resolve({ ok: true, items: [] });
  }
  requestMedia() {
    return Promise.resolve({ ok: true });
  }
}
