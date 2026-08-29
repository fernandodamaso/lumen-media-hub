import { TestBed } from '@angular/core/testing';
import { MEDIA_STACK_API, MediaStackApi } from '../media-stack/media-stack-api';
import { LibraryItem, LibraryListResult, LibraryStats } from './library.models';
import { LibraryItemsFacade } from './library-items.facade';

const movie = (id: string, title: string): LibraryItem => ({
  id,
  title,
  kind: 'movie',
  meta: '2024 · Movie',
  art: 'linear-gradient(145deg, #312e81, #0f172a 70%)',
  overview: '',
  href: null,
  artworkState: 'ok',
  playable: true,
  episodeCount: null,
  played: false,
});

const series = (id: string, title: string): LibraryItem => ({
  id,
  title,
  kind: 'series',
  meta: '2024 · Series',
  art: 'linear-gradient(145deg, #1e3a5f, #0b1220 70%)',
  overview: '',
  href: null,
  artworkState: 'ok',
  playable: true,
  episodeCount: null,
  played: false,
});

describe('LibraryItemsFacade', () => {
  let api: MockApi;
  let facade: LibraryItemsFacade;

  beforeEach(() => {
    api = new MockApi();
    TestBed.configureTestingModule({
      providers: [LibraryItemsFacade, { provide: MEDIA_STACK_API, useValue: api }],
    });
    facade = TestBed.inject(LibraryItemsFacade);
  });

  it('loads items and exposes counts', async () => {
    await Promise.resolve();
    await Promise.resolve();
    expect(facade.status()).toBe('ready');
    expect(facade.items()).toHaveLength(2);
    expect(facade.movieCount()).toBe(1);
    expect(facade.seriesCount()).toBe(1);
    expect(facade.totalCount()).toBe(2);
    expect(facade.availability()).toBe('complete');
  });

  it('sets empty when the library has no items', async () => {
    api.result = { items: [], availability: 'complete' };
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('empty');
    expect(facade.items()).toEqual([]);
  });

  it('retains last-good items when a background refresh fails', async () => {
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('ready');

    api.failure = true;
    await facade.refresh();
    expect(facade.status()).toBe('ready');
    expect(facade.items()).toHaveLength(2);
    expect(facade.error()).toContain('Showing last loaded titles');
  });

  it('keeps empty status when a background refresh fails after an empty load', async () => {
    api.result = { items: [], availability: 'complete' };
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('empty');

    api.failure = true;
    await facade.refresh();
    expect(facade.status()).toBe('empty');
    expect(facade.items()).toEqual([]);
    expect(facade.error()).toContain('Showing last loaded titles');
  });

  it('ignores stale responses when a newer refresh wins the race', async () => {
    const { promise: initialPromise, resolve: resolveInitial } = Promise.withResolvers<LibraryListResult>();
    api.nextResponse = initialPromise;

    const first = facade.refresh({ initial: true });
    expect(facade.refreshing()).toBe(true);

    api.nextResponse = undefined;
    api.result = { items: [movie('new', 'New Title')], availability: 'complete' };
    await facade.refresh();
    expect(facade.items()[0]?.title).toBe('New Title');

    resolveInitial({ items: [movie('stale', 'Stale')], availability: 'complete' });
    await first;

    expect(facade.items()[0]?.title).toBe('New Title');
    expect(facade.refreshing()).toBe(false);
  });

  it('surfaces hard errors on initial load', async () => {
    api.failure = true;
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('error');
    expect(facade.items()).toEqual([]);
    expect(facade.error()).toContain('temporarily unavailable');
  });

  it('ignores aborted refresh failures', async () => {
    await facade.refresh({ initial: true });
    api.failure = true;
    const controller = new AbortController();
    controller.abort();
    await facade.refresh({ signal: controller.signal });
    expect(facade.status()).toBe('ready');
    expect(facade.error()).toBe('');
  });

  it('surfaces partial availability without treating it as an empty library', async () => {
    await facade.refresh({ initial: true });
    api.result = { items: [movie('m1', 'Moonrise')], availability: 'partial' };
    await facade.refresh();
    expect(facade.status()).toBe('ready');
    expect(facade.availability()).toBe('partial');
    expect(facade.error()).toContain('One library source failed');

    api.result = { items: [], availability: 'partial' };
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('error');
    expect(facade.items()).toEqual([]);
  });

  it('prefers authoritative API totals over returned item length', async () => {
    api.result = {
      items: [movie('m1', 'Moonrise'), series('s1', 'Night Watch')],
      availability: 'complete',
      movieCount: 428,
      seriesCount: 76,
    };
    await facade.refresh({ initial: true });
    expect(facade.movieCount()).toBe(428);
    expect(facade.seriesCount()).toBe(76);
    expect(facade.totalCount()).toBe(504);
    expect(facade.items()).toHaveLength(2);
  });
});

class MockApi implements MediaStackApi {
  searchMedia: MediaStackApi['searchMedia'] = () => Promise.resolve({ ok: true, availability: 'available', sources: { jellyseerr: 'fresh' }, items: [] });
  getTvSeasons: MediaStackApi['getTvSeasons'] = (tmdbId) => Promise.resolve({ tmdbId, title: 'Fixture', seasons: [] });
  result: LibraryListResult = {
    items: [movie('m1', 'Moonrise'), series('s1', 'Night Watch')],
    availability: 'complete',
  };
  failure = false;
  nextResponse?: Promise<LibraryListResult>;

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
    return Promise.resolve({ movies: 1, series: 1, availability: 'complete' });
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
    if (this.nextResponse) return this.nextResponse;
    return this.failure
      ? Promise.reject(new Error('offline'))
      : Promise.resolve({ ...this.result, items: [...this.result.items] });
  }
  setLibraryItemPlayed(id: string, played: boolean) {
    return Promise.resolve({ played });
  }
  previewLibraryItemDeletion(id: string) {
    return Promise.resolve({
      previewId: `preview-${id}`,
      title: 'Title',
      kind: 'movie' as const,
      manager: 'Radarr' as const,
      episodeCount: null,
      torrentCount: 0,
      expiresAt: new Date().toISOString(),
    });
  }
  deleteLibraryItem() {
    return Promise.resolve({
      ok: true,
      removed: true,
      torrentCount: 0,
      jellyfinRefresh: 'ok' as const,
      warning: null,
    });
  }
  deleteLibraryItemDirectly() {
    return Promise.resolve({ ok: true, removed: true, mode: 'jellyfin-direct' as const, title: null });
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
    return Promise.resolve({ ok: true, items: [], pending_request_sync: [], generation_request: null });
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
