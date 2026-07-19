import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { MEDIA_STACK_API, MediaStackApi } from '../media-stack/media-stack-api';
import { AutomationSummary } from './automation.models';
import { ServiceHealthFacade } from './service-health.facade';

const healthySummary: AutomationSummary = {
  generatedAt: '2026-07-12T18:00:00Z',
  services: [{ id: 'sonarr', name: 'Sonarr', status: 'healthy', detail: 'OK', latencyMs: 20 }],
  preview: [],
  problems: [],
  availability: { services: 'present', preview: 'empty', problems: 'empty' },
};

const emptySummary: AutomationSummary = {
  generatedAt: '2026-07-12T19:00:00Z',
  services: [],
  preview: [],
  problems: [],
  availability: { services: 'empty', preview: 'empty', problems: 'empty' },
};

describe('ServiceHealthFacade', () => {
  let api: MockApi;
  let facade: ServiceHealthFacade;

  beforeEach(() => {
    api = new MockApi();
    TestBed.configureTestingModule({
      providers: [ServiceHealthFacade, { provide: MEDIA_STACK_API, useValue: api }],
    });
    facade = TestBed.inject(ServiceHealthFacade);
  });

  it('loads ready and empty states without inventing freshness', async () => {
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('ready');
    expect(facade.services()).toHaveLength(1);
    expect(facade.generatedAt()).toBe('2026-07-12T18:00:00Z');
    expect(facade.error()).toBe('');

    api.summary = emptySummary;
    await facade.refresh();
    expect(facade.status()).toBe('empty');
    expect(facade.generatedAt()).toBe('2026-07-12T19:00:00Z');
  });

  it('surfaces exclusive error on initial load failure', async () => {
    api.failure = true;
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('error');
    expect(facade.summary()).toBeNull();
    expect(facade.error()).toContain('temporarily unavailable');
  });

  it('retains last-good summary when a background refresh fails', async () => {
    await facade.refresh({ initial: true });
    const prior = facade.summary();
    api.failure = true;
    await facade.refresh();
    expect(facade.status()).toBe('ready');
    expect(facade.summary()).toEqual(prior);
    expect(facade.error()).toContain('Showing last loaded status');
  });

  it('ignores stale responses when a newer refresh wins the race', async () => {
    const { promise: initialPromise, resolve: resolveInitial } =
      Promise.withResolvers<AutomationSummary>();
    api.nextResponse = initialPromise;

    const first = facade.refresh({ initial: true });
    expect(facade.refreshing()).toBe(true);

    api.nextResponse = undefined;
    api.summary = {
      ...healthySummary,
      generatedAt: '2026-07-12T20:00:00Z',
      services: [{ id: 'radarr', name: 'Radarr', status: 'healthy', detail: 'OK', latencyMs: 10 }],
    };
    await facade.refresh();
    expect(facade.services()[0]?.id).toBe('radarr');
    expect(facade.generatedAt()).toBe('2026-07-12T20:00:00Z');

    resolveInitial(structuredClone(healthySummary));
    await first;

    expect(facade.services()[0]?.id).toBe('radarr');
    expect(facade.refreshing()).toBe(false);
  });

  it('does not overlap scheduled polls while one is in flight', async () => {
    vi.useFakeTimers();
    const { promise: deferred, resolve } = Promise.withResolvers<AutomationSummary>();
    api.nextResponse = deferred;

    facade.startPolling(100);
    await vi.advanceTimersByTimeAsync(0);
    expect(api.summaryCalls).toBe(1);

    await vi.advanceTimersByTimeAsync(300);
    expect(api.summaryCalls).toBe(1);

    api.nextResponse = undefined;
    resolve(structuredClone(healthySummary));
    await Promise.resolve();
    await Promise.resolve();

    await vi.advanceTimersByTimeAsync(100);
    expect(api.summaryCalls).toBe(2);

    TestBed.resetTestingModule();
    await vi.advanceTimersByTimeAsync(200);
    expect(api.summaryCalls).toBe(2);
    vi.useRealTimers();
  });

  it('ignores late resolutions after destroy', async () => {
    vi.useFakeTimers();
    const { promise: deferred, resolve } = Promise.withResolvers<AutomationSummary>();
    api.nextResponse = deferred;

    facade.startPolling(100);
    await vi.advanceTimersByTimeAsync(0);
    expect(api.summaryCalls).toBe(1);
    expect(facade.status()).toBe('loading');

    TestBed.resetTestingModule();
    resolve({
      ...healthySummary,
      generatedAt: '2026-07-12T21:00:00Z',
    });
    await Promise.resolve();
    await Promise.resolve();

    expect(facade.status()).toBe('loading');
    expect(facade.summary()).toBeNull();
    await vi.advanceTimersByTimeAsync(500);
    expect(api.summaryCalls).toBe(1);
    vi.useRealTimers();
  });
});

class MockApi implements MediaStackApi {
  summary: AutomationSummary = structuredClone(healthySummary);
  nextResponse?: Promise<AutomationSummary>;
  failure = false;
  summaryCalls = 0;

  getAutomationSummary(): Promise<AutomationSummary> {
    this.summaryCalls++;
    if (this.failure) return Promise.reject(new Error('offline'));
    if (this.nextResponse) return this.nextResponse;
    return Promise.resolve(structuredClone(this.summary));
  }

  listCronLogs() {
    return Promise.resolve({ ok: true, generatedAt: '2026-07-12T18:00:00Z', runs: [] });
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
    return Promise.resolve({ movies: 0, series: 0 });
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
    return Promise.resolve([]);
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
