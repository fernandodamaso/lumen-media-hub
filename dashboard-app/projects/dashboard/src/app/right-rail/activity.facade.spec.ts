import { mediaStackLibraryMutationStub } from '../../testing/media-stack-library-stub';
import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { MEDIA_STACK_API, MediaStackApi } from '../media-stack/media-stack-api';
import { ActivityFeed } from '../activity/activity.models';
import { LibraryListResult } from '../library/library.models';
import { ActivityFacade } from './activity.facade';

const feed: ActivityFeed = {
  ok: true,
  generatedAt: '2026-07-30T00:20:00Z',
  sources: { sonarr: 'ok', radarr: 'ok' },
  items: [
    {
      id: 'sonarr:48211',
      source: 'sonarr',
      kind: 'imported',
      title: 'The ShÅgun Court',
      subtitle: 'S01E07 · 1080p WEB-DL',
      timestamp: '2026-07-30T00:18:41Z',
      href: 'http://sonarr.local/series/shogun-court',
    },
  ],
};

describe('ActivityFacade', () => {
  let api: MockApi;
  let facade: ActivityFacade;

  beforeEach(() => {
    api = new MockApi();
    TestBed.configureTestingModule({
      providers: [ActivityFacade, { provide: MEDIA_STACK_API, useValue: api }],
    });
    facade = TestBed.inject(ActivityFacade);
  });

  it('exposes ready, empty, and error states', async () => {
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('ready');
    expect(facade.items()).toHaveLength(1);
    expect(api.lastLimit).toBe(5);

    api.feed = { ...feed, items: [] };
    await facade.refresh();
    expect(facade.status()).toBe('empty');

    api.failure = true;
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('error');
    expect(facade.error()).toContain('temporarily unavailable');
  });

  it('retains last-good items when a background refresh fails', async () => {
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('ready');

    api.failure = true;
    await facade.refresh();
    expect(facade.status()).toBe('ready');
    expect(facade.items()).toHaveLength(1);
    expect(facade.error()).toContain('Showing last loaded activity');
  });

  it('exposes per-source degradation without failing the feed', async () => {
    api.feed = {
      ...feed,
      sources: { sonarr: 'error', radarr: 'ok' },
    };
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('ready');
    expect(facade.degradedSources()).toEqual(['sonarr']);
  });

  it('does not overlap scheduled polls while one is in flight', async () => {
    vi.useFakeTimers();
    const { promise: deferred, resolve } = Promise.withResolvers<ActivityFeed>();
    api.nextResponse = deferred;

    facade.startPolling(100);
    await vi.advanceTimersByTimeAsync(0);
    expect(api.calls).toBe(1);

    await vi.advanceTimersByTimeAsync(300);
    expect(api.calls).toBe(1);

    api.nextResponse = undefined;
    resolve({ ...feed });
    await Promise.resolve();
    await Promise.resolve();

    await vi.advanceTimersByTimeAsync(100);
    expect(api.calls).toBe(2);

    TestBed.resetTestingModule();
    await vi.advanceTimersByTimeAsync(200);
    expect(api.calls).toBe(2);
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
  feed: ActivityFeed = { ...feed, items: feed.items.map((item) => ({ ...item })) };
  failure = false;
  calls = 0;
  lastLimit?: number;
  nextResponse?: Promise<ActivityFeed>;

  getActivity(limit?: number, signal?: AbortSignal): Promise<ActivityFeed> {
    this.calls++;
    this.lastLimit = limit;
    if (signal?.aborted) {
      return Promise.reject(new DOMException('The operation was aborted.', 'AbortError'));
    }
    if (this.nextResponse) {
      const pending = this.nextResponse;
      return new Promise<ActivityFeed>((resolvePromise, reject) => {
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
            resolvePromise(value);
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
      : Promise.resolve({ ...this.feed, items: this.feed.items.map((item) => ({ ...item })) });
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
  getLibraryStats() {
    return Promise.resolve({ movies: 0, series: 0, availability: 'complete' as const });
  }
  getStorageOverview() {
    return Promise.resolve({ generatedAt: '', volumes: [] });
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
  listCronLogs() {
    return Promise.resolve({ ok: true, currentRuns: [], historyRuns: [] });
  }
  listAiPicks() {
    return Promise.resolve({ ok: true, items: [] });
  }
  submitAiPickFeedback() {
    return Promise.resolve({ ok: true });
  }
  requestMoreAiPicks() {
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
