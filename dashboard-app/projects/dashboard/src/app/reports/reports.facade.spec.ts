import { mediaStackLibraryMutationStub } from '../../testing/media-stack-library-stub';
import { TestBed } from '@angular/core/testing';
import { MEDIA_STACK_API, MediaStackApi } from '../media-stack/media-stack-api';
import { CronLogs, CronRun } from './reports.models';
import { ReportsFacade } from './reports.facade';

const mixedRuns: CronRun[] = [
  {
    id: 'watchdog-2026-07-12T11:45:00Z-0',
    jobId: 'watchdog',
    jobTitle: 'Watchdog',
    status: 'fatal',
    triage: 'actionable',
    timestamp: '2026-07-12T11:45:00Z',
    detail: 'Disk full',
    fatal: 'Disk full',
    applied: null,
    exitCode: 1,
    schedule: '*/15 * * * *',
  },
  {
    id: 'watchdog-2026-07-12T11:30:00Z-1',
    jobId: 'watchdog',
    jobTitle: 'Watchdog',
    status: 'ok',
    triage: 'quiet',
    timestamp: '2026-07-12T11:30:00Z',
    detail: 'Checked 1, no repairs needed',
    fatal: null,
    applied: null,
    exitCode: 0,
    schedule: '*/15 * * * *',
  },
];

const mixedLogs: CronLogs = {
  ok: true,
  generatedAt: '2026-07-12T12:00:00Z',
  currentRuns: mixedRuns,
  historyRuns: [],
};

const allClearLogs: CronLogs = {
  ok: true,
  generatedAt: '2026-07-12T13:00:00Z',
  currentRuns: [
    {
      id: 'weekly-validate-2026-07-06T04:00:00Z-0',
      jobId: 'weekly-validate',
      jobTitle: 'Weekly validate',
      status: 'ok',
      triage: 'quiet',
      timestamp: '2026-07-06T04:00:00Z',
      detail: 'Completed',
      fatal: null,
      applied: null,
      exitCode: 0,
      schedule: '0 4 * * 0',
    },
  ],
  historyRuns: [],
};

describe('ReportsFacade', () => {
  let api: MockApi;
  let facade: ReportsFacade;

  beforeEach(() => {
    api = new MockApi();
    TestBed.configureTestingModule({
      providers: [ReportsFacade, { provide: MEDIA_STACK_API, useValue: api }],
    });
    facade = TestBed.inject(ReportsFacade);
  });

  it('loads mixed, all-clear, and empty states', async () => {
    await facade.load();
    expect(facade.status()).toBe('mixed');
    expect(facade.currentRuns()[0]?.status).toBe('fatal');
    expect(facade.summary()).toMatchObject({ kind: 'mixed', affectedJobs: 1, healthyJobs: 1 });
    expect(facade.generatedAt()).toBe('2026-07-12T12:00:00Z');
    expect(facade.error()).toBe('');

    api.response = allClearLogs;
    await facade.refresh();
    expect(facade.status()).toBe('allClear');
    expect(facade.summary().affectedJobs).toBe(0);
    expect(facade.generatedAt()).toBe('2026-07-12T13:00:00Z');

    api.response = { ok: true, generatedAt: '2026-07-12T14:00:00Z', currentRuns: [], historyRuns: [] };
    await facade.refresh();
    expect(facade.status()).toBe('empty');
    expect(facade.currentRuns()).toEqual([]);
  });

  it('surfaces error on initial load failure with empty runs', async () => {
    api.failure = true;
    await facade.load();
    expect(facade.status()).toBe('error');
    expect(facade.currentRuns()).toEqual([]);
    expect(facade.error()).toContain('temporarily unavailable');
  });

  it('treats soft ok:false envelopes as load/refresh failures', async () => {
    api.response = { ok: false, error: 'backend offline', currentRuns: [], historyRuns: [] };
    await facade.load();
    expect(facade.status()).toBe('error');
    expect(facade.currentRuns()).toEqual([]);

    api.response = structuredClone(mixedLogs);
    await facade.load();
    expect(facade.status()).toBe('mixed');

    api.response = { ok: false, error: 'backend offline', currentRuns: [], historyRuns: [], generatedAt: '2026-07-12T99:00:00Z' };
    await facade.refresh();
    expect(facade.status()).toBe('mixed');
    expect(facade.generatedAt()).toBe('2026-07-12T12:00:00Z');
    expect(facade.error()).toContain('Showing last loaded history');
  });

  it('retains prior data when refresh fails after a successful load', async () => {
    await facade.load();
    const priorRuns = facade.currentRuns();
    const priorGeneratedAt = facade.generatedAt();
    const priorStatus = facade.status();

    api.failure = true;
    await facade.refresh();

    expect(facade.currentRuns()).toEqual(priorRuns);
    expect(facade.generatedAt()).toBe(priorGeneratedAt);
    expect(facade.status()).toBe(priorStatus);
    expect(facade.status()).not.toBe('error');
    expect(facade.error()).toContain('Showing last loaded history');
  });

  it('clears refresh error and updates generatedAt on successful refresh', async () => {
    await facade.load();
    api.failure = true;
    await facade.refresh();
    expect(facade.error()).toBeTruthy();

    api.failure = false;
    api.response = {
      ...allClearLogs,
      generatedAt: '2026-07-12T15:30:00Z',
    };
    await facade.refresh();
    expect(facade.error()).toBe('');
    expect(facade.generatedAt()).toBe('2026-07-12T15:30:00Z');
    expect(facade.status()).toBe('allClear');
  });

  it('ignores stale responses when a newer refresh wins the race', async () => {
    const { promise: initialPromise, resolve: resolveInitial } = Promise.withResolvers<CronLogs>();
    api.nextResponse = initialPromise;

    const loadPromise = facade.load();
    expect(facade.refreshing()).toBe(true);

    api.nextResponse = undefined;
    api.response = allClearLogs;
    await facade.refresh();
    expect(facade.status()).toBe('allClear');
    expect(facade.generatedAt()).toBe('2026-07-12T13:00:00Z');

    resolveInitial(structuredClone(mixedLogs));
    await loadPromise;

    expect(facade.status()).toBe('allClear');
    expect(facade.generatedAt()).toBe('2026-07-12T13:00:00Z');
    expect(facade.refreshing()).toBe(false);
  });
});

class MockApi implements MediaStackApi {
  setLibraryItemPlayed = mediaStackLibraryMutationStub.setLibraryItemPlayed;
  previewLibraryItemDeletion = mediaStackLibraryMutationStub.previewLibraryItemDeletion;
  deleteLibraryItem = mediaStackLibraryMutationStub.deleteLibraryItem;
  response: CronLogs = structuredClone(mixedLogs);
  nextResponse?: Promise<CronLogs>;
  failure = false;
  listCalls = 0;

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
  runQueueHygiene(_mode: 'observe' | 'auto') {
    return Promise.reject(new Error('not implemented'));
  }

  getAutomationSummary() {
    return Promise.resolve({
      generatedAt: '',
      services: [],
      preview: [],
      problems: [],
      queueHygiene: null,
      availability: { services: 'empty' as const, preview: 'empty' as const, problems: 'empty' as const },
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
  listCronLogs(): Promise<CronLogs> {
    this.listCalls++;
    if (this.failure) return Promise.reject(new Error('offline'));
    if (this.nextResponse) return this.nextResponse;
    return Promise.resolve(structuredClone(this.response));
  }
}
