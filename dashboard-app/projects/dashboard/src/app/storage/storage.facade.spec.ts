import { mediaStackLibraryMutationStub } from '../../testing/media-stack-library-stub';
import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { MEDIA_STACK_API, MediaStackApi } from '../media-stack/media-stack-api';
import { LibraryListResult } from '../library/library.models';
import { StorageOverview } from './storage.models';
import { SCHEDULED_REFRESH_TIMEOUT_MS, StorageFacade } from './storage.facade';

const overview: StorageOverview = {
  generatedAt: '2026-07-13T12:00:00Z',
  volumes: [
    { id: 'media', label: 'Media library', kind: 'library', usedBytes: 10, totalBytes: 20 },
  ],
};

describe('StorageFacade', () => {
  let api: MockApi;
  let facade: StorageFacade;

  beforeEach(() => {
    api = new MockApi();
    TestBed.configureTestingModule({
      providers: [StorageFacade, { provide: MEDIA_STACK_API, useValue: api }],
    });
    facade = TestBed.inject(StorageFacade);
  });

  it('polls and exposes populated, empty, and error states', async () => {
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('ready');
    expect(facade.volumes()).toHaveLength(1);
    expect(facade.volumes()[0].usedBytes).toBe(10);

    api.overview = { generatedAt: '', volumes: [] };
    await facade.refresh();
    expect(facade.status()).toBe('empty');

    api.failure = true;
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('error');
    expect(facade.error()).toContain('temporarily unavailable');
  });

  it('treats zero-capacity volumes as valid empty capacity', async () => {
    api.overview = {
      generatedAt: '2026-07-13T12:00:00Z',
      volumes: [{ id: 'empty', label: 'Empty', kind: 'cache', usedBytes: 0, totalBytes: 0 }],
    };
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('ready');
    expect(facade.volumes()[0]).toMatchObject({ usedBytes: 0, totalBytes: 0 });
  });

  it('retains last-good volumes when a background refresh fails', async () => {
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('ready');

    api.failure = true;
    await facade.refresh();
    expect(facade.status()).toBe('ready');
    expect(facade.volumes()).toHaveLength(1);
    expect(facade.error()).toContain('Showing last loaded capacity');
  });

  it('ignores stale responses when a newer refresh wins the race', async () => {
    const { promise: initialPromise, resolve: resolveInitial } =
      Promise.withResolvers<StorageOverview>();
    api.nextResponse = initialPromise;

    const first = facade.refresh({ initial: true });
    expect(facade.refreshing()).toBe(true);

    api.nextResponse = undefined;
    api.overview = {
      generatedAt: 'newer',
      volumes: [{ id: 'newer', label: 'Newer', kind: 'library', usedBytes: 1, totalBytes: 2 }],
    };
    await facade.refresh();
    expect(facade.volumes()[0]?.id).toBe('newer');

    resolveInitial({
      generatedAt: 'stale',
      volumes: [{ id: 'stale', label: 'Stale', kind: 'library', usedBytes: 9, totalBytes: 9 }],
    });
    await first;

    expect(facade.volumes()[0]?.id).toBe('newer');
    expect(facade.refreshing()).toBe(false);
  });

  it('does not overlap scheduled polls while one is in flight', async () => {
    vi.useFakeTimers();
    const { promise: deferred, resolve } = Promise.withResolvers<StorageOverview>();
    api.nextResponse = deferred;

    facade.startPolling(100);
    await vi.advanceTimersByTimeAsync(0);
    expect(api.listCalls).toBe(1);

    await vi.advanceTimersByTimeAsync(300);
    expect(api.listCalls).toBe(1);

    api.nextResponse = undefined;
    resolve({ ...overview });
    await Promise.resolve();
    await Promise.resolve();

    await vi.advanceTimersByTimeAsync(100);
    expect(api.listCalls).toBe(2);

    TestBed.resetTestingModule();
    await vi.advanceTimersByTimeAsync(200);
    expect(api.listCalls).toBe(2);
    vi.useRealTimers();
  });

  it('recovers scheduled polling after a hung refresh times out', async () => {
    vi.useFakeTimers();
    const { promise: deferred } = Promise.withResolvers<StorageOverview>();
    api.nextResponse = deferred;

    facade.startPolling(SCHEDULED_REFRESH_TIMEOUT_MS + 1_000);
    await vi.advanceTimersByTimeAsync(0);
    expect(api.listCalls).toBe(1);
    expect(facade.refreshing()).toBe(true);

    await vi.advanceTimersByTimeAsync(SCHEDULED_REFRESH_TIMEOUT_MS);
    expect(facade.refreshing()).toBe(false);
    expect(facade.status()).toBe('error');
    expect(facade.error()).toContain('temporarily unavailable');

    api.nextResponse = undefined;
    await vi.advanceTimersByTimeAsync(1_000);
    expect(api.listCalls).toBe(2);
    expect(facade.status()).toBe('ready');

    TestBed.resetTestingModule();
    vi.useRealTimers();
  });

  it('ignores a superseded hung poll timeout after a newer refresh wins', async () => {
    vi.useFakeTimers();
    const { promise: deferred } = Promise.withResolvers<StorageOverview>();
    api.nextResponse = deferred;

    facade.startPolling(SCHEDULED_REFRESH_TIMEOUT_MS + 1_000);
    await vi.advanceTimersByTimeAsync(0);
    expect(api.listCalls).toBe(1);
    expect(facade.refreshing()).toBe(true);

    api.nextResponse = undefined;
    api.overview = {
      generatedAt: 'from-manual',
      volumes: [{ id: 'manual', label: 'Manual', kind: 'library', usedBytes: 3, totalBytes: 9 }],
    };
    await facade.refresh();
    expect(facade.status()).toBe('ready');
    expect(facade.volumes()[0]?.id).toBe('manual');
    expect(facade.error()).toBe('');
    expect(facade.refreshing()).toBe(false);

    await vi.advanceTimersByTimeAsync(SCHEDULED_REFRESH_TIMEOUT_MS);
    expect(facade.status()).toBe('ready');
    expect(facade.volumes()[0]?.id).toBe('manual');
    expect(facade.error()).toBe('');
    expect(facade.refreshing()).toBe(false);

    TestBed.resetTestingModule();
    vi.useRealTimers();
  });
});

class MockApi implements MediaStackApi {
  searchMedia: MediaStackApi['searchMedia'] = () => Promise.resolve({ ok: true, availability: 'available', sources: { jellyseerr: 'fresh' }, items: [] });
  getTvSeasons: MediaStackApi['getTvSeasons'] = (tmdbId) => Promise.resolve({ tmdbId, title: 'Fixture', seasons: [] });
  setLibraryItemPlayed = mediaStackLibraryMutationStub.setLibraryItemPlayed;
  previewLibraryItemDeletion = mediaStackLibraryMutationStub.previewLibraryItemDeletion;
  deleteLibraryItem = mediaStackLibraryMutationStub.deleteLibraryItem;
  deleteLibraryItemDirectly = mediaStackLibraryMutationStub.deleteLibraryItemDirectly;
  overview: StorageOverview = { ...overview, volumes: overview.volumes.map((v) => ({ ...v })) };
  listCalls = 0;
  failure = false;
  nextResponse?: Promise<StorageOverview>;
  lastSignal?: AbortSignal;

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
  getStorageOverview(signal?: AbortSignal): Promise<StorageOverview> {
    this.listCalls++;
    this.lastSignal = signal;
    if (signal?.aborted) {
      return Promise.reject(new DOMException('The operation was aborted.', 'AbortError'));
    }
    if (this.nextResponse) {
      const pending = this.nextResponse;
      return new Promise<StorageOverview>((resolve, reject) => {
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
    return this.failure
      ? Promise.reject(new Error('offline'))
      : Promise.resolve({
          ...this.overview,
          volumes: this.overview.volumes.map((volume) => ({ ...volume })),
        });
  }
  listCalendarEvents() {
    return Promise.resolve([]);
  }
  getArrLibrary() {
    return Promise.resolve({ ok: true, series: {}, movies: {} });
  }
  listLibraryItems(): Promise<LibraryListResult> {
    return Promise.resolve({ items: [], availability: 'complete' });
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
  listCronLogs() {
    return Promise.resolve({ ok: true, currentRuns: [], historyRuns: [] });
  }
}
