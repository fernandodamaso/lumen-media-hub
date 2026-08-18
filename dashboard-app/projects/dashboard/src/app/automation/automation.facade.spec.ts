import { mediaStackLibraryMutationStub } from '../../testing/media-stack-library-stub';
import { TestBed } from '@angular/core/testing';
import { computed, signal } from '@angular/core';
import { vi } from 'vitest';
import { MEDIA_STACK_API, MediaStackApi } from '../media-stack/media-stack-api';
import { CronLogs, CronRun } from '../reports/reports.models';
import { AutomationFacade, SCHEDULED_REFRESH_TIMEOUT_MS } from './automation.facade';
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

  it('mirrors service health summary and health independently of run state', () => {
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
      generatedAt: '2026-07-14T12:00:00Z',
      currentRuns: [cronRun('Cleanup', '2026-07-14T12:00:00Z')],
      historyRuns: [],
    };
    expect(facade.status()).toBe('loading');
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('ready');
    expect(facade.tasks()).toHaveLength(1);
    expect(facade.refreshing()).toBe(false);
  });

  it('reports empty when cron logs return no runs', async () => {
    api.cronLogs = { ok: true, generatedAt: '2026-07-14T12:00:00Z', currentRuns: [], historyRuns: [] };
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('empty');
    expect(facade.tasks()).toEqual([]);
  });

  it('computes latestRuns as the three most recent current jobs', async () => {
    api.cronLogs = {
      ok: true,
      generatedAt: '2026-07-14T13:00:00Z',
      currentRuns: [
        cronRun('Watchdog', '2026-07-14T11:00:00Z'),
        cronRun('Cleanup', '2026-07-14T10:00:00Z'),
        cronRun('Metadata', '2026-07-14T13:00:00Z'),
      ],
      historyRuns: [],
    };
    await facade.refresh({ initial: true });
    expect(facade.latestRuns()).toHaveLength(3);
    expect(facade.latestRuns().map((run) => run.jobTitle)).toEqual(['Metadata', 'Watchdog', 'Cleanup']);
  });

  it('surfaces exclusive error on initial failure and recovers', async () => {
    api.cronFailure = true;
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('error');
    expect(facade.error()).toContain('temporarily unavailable');

    api.cronFailure = false;
    api.cronLogs = {
      ok: true,
      generatedAt: '2026-07-14T12:00:00Z',
      currentRuns: [cronRun('watchdog', '2026-07-14T12:00:00Z')],
      historyRuns: [],
    };
    await facade.refresh();
    expect(facade.status()).toBe('ready');
  });

  it('treats soft ok:false as load/refresh failure and retains last-good on background failure', async () => {
    api.cronLogs = { ok: false, error: 'backend offline', currentRuns: [], historyRuns: [] };
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('error');
    expect(facade.tasks()).toEqual([]);
    expect(facade.error()).toBe('backend offline');

    api.cronLogs = {
      ok: true,
      generatedAt: '2026-07-14T12:00:00Z',
      currentRuns: [cronRun('Cleanup', '2026-07-14T12:00:00Z')],
      historyRuns: [],
    };
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('ready');

    api.cronLogs = { ok: false, error: 'backend offline', currentRuns: [], historyRuns: [] };
    await facade.refresh();
    expect(facade.status()).toBe('ready');
    expect(facade.tasks()).toHaveLength(1);
    expect(facade.error()).toContain('Showing last loaded history');
  });

  it('retains prior runs when a transport refresh fails after a successful load', async () => {
    api.cronLogs = {
      ok: true,
      generatedAt: '2026-07-14T12:00:00Z',
      currentRuns: [cronRun('Cleanup', '2026-07-14T12:00:00Z')],
      historyRuns: [],
    };
    await facade.refresh({ initial: true });
    const prior = facade.tasks();
    expect(facade.status()).toBe('ready');
    api.cronFailure = true;
    await facade.refresh();
    expect(facade.tasks()).toEqual(prior);
    expect(facade.status()).toBe('ready');
    expect(facade.error()).toContain('Showing last loaded history');
  });

  it('ignores stale responses when a newer refresh wins the race', async () => {
    const { promise: initialPromise, resolve: resolveInitial } = Promise.withResolvers<CronLogs>();
    api.nextResponse = initialPromise;

    const first = facade.refresh({ initial: true });
    expect(facade.refreshing()).toBe(true);

    api.nextResponse = undefined;
    api.cronLogs = {
      ok: true,
      generatedAt: '2026-07-14T13:00:00Z',
      currentRuns: [cronRun('Newer', '2026-07-14T13:00:00Z')],
      historyRuns: [],
    };
    await facade.refresh();
    expect(facade.tasks()[0]?.jobTitle).toBe('Newer');

    resolveInitial({
      ok: true,
      generatedAt: '2026-07-14T12:00:00Z',
      currentRuns: [cronRun('Stale', '2026-07-14T12:00:00Z')],
      historyRuns: [],
    });
    await first;

    expect(facade.tasks()[0]?.jobTitle).toBe('Newer');
    expect(facade.refreshing()).toBe(false);
  });

  it('does not overlap scheduled polls while one is in flight and stops on destroy', async () => {
    vi.useFakeTimers();
    const { promise: deferred, resolve } = Promise.withResolvers<CronLogs>();
    api.nextResponse = deferred;

    facade.startPolling(100);
    await vi.advanceTimersByTimeAsync(0);
    expect(api.cronCalls).toBe(1);

    facade.startPolling(100);
    await vi.advanceTimersByTimeAsync(300);
    expect(api.cronCalls).toBe(1);

    api.nextResponse = undefined;
    resolve({
      ok: true,
      generatedAt: '2026-07-14T12:00:00Z',
      currentRuns: [cronRun('Cleanup', '2026-07-14T12:00:00Z')],
      historyRuns: [],
    });
    await Promise.resolve();
    await Promise.resolve();

    await vi.advanceTimersByTimeAsync(100);
    expect(api.cronCalls).toBe(2);

    TestBed.resetTestingModule();
    await vi.advanceTimersByTimeAsync(200);
    expect(api.cronCalls).toBe(2);
    vi.useRealTimers();
  });

  it('recovers scheduled polling after a hung refresh times out', async () => {
    vi.useFakeTimers();
    const { promise: deferred } = Promise.withResolvers<CronLogs>();
    api.nextResponse = deferred;

    facade.startPolling(SCHEDULED_REFRESH_TIMEOUT_MS + 1_000);
    await vi.advanceTimersByTimeAsync(0);
    expect(api.cronCalls).toBe(1);
    expect(facade.refreshing()).toBe(true);

    await vi.advanceTimersByTimeAsync(SCHEDULED_REFRESH_TIMEOUT_MS);
    expect(facade.refreshing()).toBe(false);
    expect(facade.status()).toBe('error');
    expect(facade.error()).toContain('temporarily unavailable');

    api.nextResponse = undefined;
    await vi.advanceTimersByTimeAsync(1_000);
    expect(api.cronCalls).toBe(2);
    expect(facade.status()).toBe('empty');
    expect(facade.refreshing()).toBe(false);

    TestBed.resetTestingModule();
    vi.useRealTimers();
  });

  it('aborts the active listCronLogs signal when a scheduled refresh times out', async () => {
    vi.useFakeTimers();
    const { promise: deferred } = Promise.withResolvers<CronLogs>();
    api.nextResponse = deferred;

    facade.startPolling(SCHEDULED_REFRESH_TIMEOUT_MS + 1_000);
    await vi.advanceTimersByTimeAsync(0);
    expect(api.cronCalls).toBe(1);
    expect(api.lastSignal?.aborted).toBe(false);

    await vi.advanceTimersByTimeAsync(SCHEDULED_REFRESH_TIMEOUT_MS);
    expect(api.lastSignal?.aborted).toBe(true);
    expect(api.cronCalls).toBe(1);

    api.nextResponse = undefined;
    await vi.advanceTimersByTimeAsync(1_000);
    expect(api.cronCalls).toBe(2);

    TestBed.resetTestingModule();
    vi.useRealTimers();
  });

  it('does not let a timed-out poll stamp failure over a newer successful refresh', async () => {
    vi.useFakeTimers();
    const { promise: deferred } = Promise.withResolvers<CronLogs>();
    api.nextResponse = deferred;

    facade.startPolling(SCHEDULED_REFRESH_TIMEOUT_MS + 1_000);
    await vi.advanceTimersByTimeAsync(0);
    expect(api.cronCalls).toBe(1);
    const hungSignal = api.lastSignal;

    api.nextResponse = undefined;
    api.cronLogs = {
      ok: true,
      generatedAt: '2026-07-14T13:00:00Z',
      currentRuns: [cronRun('Manual', '2026-07-14T13:00:00Z')],
      historyRuns: [],
    };
    await facade.refresh();
    expect(facade.status()).toBe('ready');
    expect(facade.tasks()[0]?.jobTitle).toBe('Manual');
    expect(facade.error()).toBe('');

    await vi.advanceTimersByTimeAsync(SCHEDULED_REFRESH_TIMEOUT_MS);
    expect(hungSignal?.aborted).toBe(true);
    expect(facade.status()).toBe('ready');
    expect(facade.tasks()[0]?.jobTitle).toBe('Manual');
    expect(facade.error()).toBe('');

    TestBed.resetTestingModule();
    vi.useRealTimers();
  });

  it('aborts an active refresh on destroy and ignores a late resolution', async () => {
    vi.useFakeTimers();
    const { promise: deferred, resolve } = Promise.withResolvers<CronLogs>();
    api.nextResponse = deferred;

    facade.startPolling(100);
    await vi.advanceTimersByTimeAsync(0);
    expect(api.cronCalls).toBe(1);
    expect(facade.status()).toBe('loading');
    const signal = api.lastSignal;

    TestBed.resetTestingModule();
    expect(signal?.aborted).toBe(true);

    resolve({
      ok: true,
      generatedAt: '2026-07-14T12:00:00Z',
      currentRuns: [cronRun('Late', '2026-07-14T12:00:00Z')],
      historyRuns: [],
    });
    await Promise.resolve();
    await Promise.resolve();

    expect(facade.status()).toBe('loading');
    expect(facade.tasks()).toEqual([]);
    await vi.advanceTimersByTimeAsync(500);
    expect(api.cronCalls).toBe(1);
    vi.useRealTimers();
  });

  it('keeps run refresh failures independent from service-health state', async () => {
    health.summary.set({
      generatedAt: '2026-07-12T18:00:00Z',
      services: [{ id: 'sonarr', name: 'Sonarr', status: 'healthy', detail: 'OK', latencyMs: 20 }],
      preview: [],
      problems: [],
      availability: { services: 'present', preview: 'empty', problems: 'empty' },
    });
    health.status.set('ready');

    api.cronFailure = true;
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('error');
    expect(facade.summary()?.services[0]?.id).toBe('sonarr');
    expect(health.status()).toBe('ready');
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
  refreshing = signal(false);
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
  setLibraryItemPlayed = mediaStackLibraryMutationStub.setLibraryItemPlayed;
  previewLibraryItemDeletion = mediaStackLibraryMutationStub.previewLibraryItemDeletion;
  deleteLibraryItem = mediaStackLibraryMutationStub.deleteLibraryItem;
  cronFailure = false;
  cronLogs: CronLogs = { ok: true, generatedAt: '2026-07-14T12:00:00Z', currentRuns: [], historyRuns: [] };
  nextResponse?: Promise<CronLogs>;
  cronCalls = 0;
  lastSignal?: AbortSignal;

  listCronLogs(signal?: AbortSignal) {
    this.cronCalls++;
    this.lastSignal = signal;
    if (signal?.aborted) {
      return Promise.reject(new DOMException('The operation was aborted.', 'AbortError'));
    }
    if (this.cronFailure) return Promise.reject(new Error('offline'));
    if (this.nextResponse) return abortable(this.nextResponse, signal);
    return Promise.resolve(structuredClone(this.cronLogs));
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
  listWatchNext() {
    return Promise.resolve({ items: [] });
  }
  listRecentlyAvailable() {
    return Promise.resolve({ items: [] });
  }
  getActivity() {
    return Promise.resolve({
      ok: true,
      generatedAt: '',
      sources: { sonarr: 'ok' as const, radarr: 'ok' as const },
      items: [],
    });
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

function abortable<T>(pending: Promise<T>, signal?: AbortSignal): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    let settled = false;
    const onAbort = () => {
      if (settled) return;
      settled = true;
      reject(new DOMException('The operation was aborted.', 'AbortError'));
    };
    signal?.addEventListener('abort', onAbort, { once: true });
    void pending.then(
      (value) => {
        if (settled) return;
        settled = true;
        signal?.removeEventListener('abort', onAbort);
        resolve(value);
      },
      (error: unknown) => {
        if (settled) return;
        settled = true;
        signal?.removeEventListener('abort', onAbort);
        reject(error instanceof Error ? error : new Error(String(error)));
      },
    );
  });
}
