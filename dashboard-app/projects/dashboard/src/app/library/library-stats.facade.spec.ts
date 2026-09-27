import { mediaStackLibraryMutationStub } from '../../testing/media-stack-library-stub';
import { TestBed } from '@angular/core/testing';
import { MEDIA_STACK_API, MediaStackApi } from '../media-stack/media-stack-api';
import { LibraryListResult, LibraryStats } from './library.models';
import { LibraryStatsFacade } from './library-stats.facade';

const stats: LibraryStats = { movies: 428, series: 76, availability: 'complete' };

describe('LibraryStatsFacade', () => {
  let api: MockApi;
  let facade: LibraryStatsFacade;

  beforeEach(() => {
    api = new MockApi();
    TestBed.configureTestingModule({
      providers: [LibraryStatsFacade, { provide: MEDIA_STACK_API, useValue: api }],
    });
    facade = TestBed.inject(LibraryStatsFacade);
  });

  it('loads valid counts including zeros', async () => {
    await Promise.resolve();
    await Promise.resolve();
    expect(facade.status()).toBe('ready');
    expect(facade.stats()).toEqual(stats);
    expect(facade.availability()).toBe('complete');

    api.items = { movies: 0, series: 0, availability: 'complete' };
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('ready');
    expect(facade.stats()).toEqual({ movies: 0, series: 0, availability: 'complete' });
  });

  it('retains last-good totals when a background refresh fails', async () => {
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('ready');
    expect(facade.stats()?.movies).toBe(428);

    api.failure = true;
    await facade.refresh();
    expect(facade.status()).toBe('ready');
    expect(facade.stats()?.movies).toBe(428);
    expect(facade.error()).toContain('Showing last loaded counts');
  });

  it('ignores stale responses when a newer refresh wins the race', async () => {
    const { promise: initialPromise, resolve: resolveInitial } = Promise.withResolvers<LibraryStats>();
    api.nextResponse = initialPromise;

    const first = facade.refresh({ initial: true });
    expect(facade.refreshing()).toBe(true);

    api.nextResponse = undefined;
    api.items = { movies: 10, series: 2, availability: 'complete' };
    await facade.refresh();
    expect(facade.stats()?.movies).toBe(10);

    resolveInitial({ movies: 999, series: 999, availability: 'complete' });
    await first;

    expect(facade.stats()?.movies).toBe(10);
    expect(facade.refreshing()).toBe(false);
  });

  it('surfaces hard errors on initial load', async () => {
    api.failure = true;
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('error');
    expect(facade.stats()).toBeNull();
    expect(facade.error()).toContain('temporarily unavailable');
  });
});

class MockApi implements MediaStackApi {
  searchMedia: MediaStackApi['searchMedia'] = () => Promise.resolve({ ok: true, availability: 'available', sources: { jellyseerr: 'fresh' }, items: [] });
  getTvSeasons: MediaStackApi['getTvSeasons'] = (tmdbId) => Promise.resolve({ tmdbId, title: 'Fixture', seasons: [] });
  setLibraryItemPlayed = mediaStackLibraryMutationStub.setLibraryItemPlayed;
  previewLibraryItemDeletion = mediaStackLibraryMutationStub.previewLibraryItemDeletion;
  deleteLibraryItem = mediaStackLibraryMutationStub.deleteLibraryItem;
  deleteLibraryItemDirectly = mediaStackLibraryMutationStub.deleteLibraryItemDirectly;
  items: LibraryStats = { ...stats };
  listCalls = 0;
  failure = false;
  nextResponse?: Promise<LibraryStats>;

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
  getLibraryStats(): Promise<LibraryStats> {
    this.listCalls++;
    if (this.nextResponse) return this.nextResponse;
    return this.failure ? Promise.reject(new Error('offline')) : Promise.resolve({ ...this.items });
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
  listCronLogs() {
    return Promise.resolve({ ok: true, currentRuns: [], historyRuns: [] });
  }
}
