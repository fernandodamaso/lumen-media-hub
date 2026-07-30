import { TestBed } from '@angular/core/testing';
import { MEDIA_STACK_API, MediaStackApi } from '../media-stack/media-stack-api';
import { WatchNextItem, WatchNextResult } from './watch-next.models';
import { WatchNextFacade } from './watch-next.facade';

const episode = (id: string, title: string, progressPercent = 0): WatchNextItem => ({
  id,
  parentId: 'series-1',
  title,
  subtitle: 'S01E01 · Pilot',
  kind: 'episode',
  art: 'linear-gradient(145deg, #1e3a5f, #0b1220 70%)',
  artworkState: 'ok',
  href: null,
  playable: true,
  progressPercent,
  year: null,
  rating: null,
  genres: [],
  overview: null,
  runtimeTicks: null,
  positionTicks: null,
  backdropUrl: null,
  thumbUrl: null,
});

const movie = (id: string, title: string, progressPercent = 10): WatchNextItem => ({
  id,
  parentId: null,
  title,
  subtitle: '',
  kind: 'movie',
  art: 'linear-gradient(145deg, #312e81, #0f172a 70%)',
  artworkState: 'ok',
  href: null,
  playable: true,
  progressPercent,
  year: null,
  rating: null,
  genres: [],
  overview: null,
  runtimeTicks: null,
  positionTicks: null,
  backdropUrl: null,
  thumbUrl: null,
});

describe('WatchNextFacade', () => {
  let api: MockApi;
  let facade: WatchNextFacade;

  beforeEach(() => {
    api = new MockApi();
    TestBed.configureTestingModule({
      providers: [WatchNextFacade, { provide: MEDIA_STACK_API, useValue: api }],
    });
    facade = TestBed.inject(WatchNextFacade);
  });

  it('loads items and exposes movie and episode collections', async () => {
    await Promise.resolve();
    await Promise.resolve();
    expect(facade.status()).toBe('ready');
    expect(facade.items()).toHaveLength(2);
    expect(facade.movieCount()).toBe(1);
    expect(facade.seriesCount()).toBe(1);
    expect(facade.movies()[0]?.kind).toBe('movie');
    expect(facade.series()[0]?.kind).toBe('episode');
  });

  it('sets empty when there are no watch-next items', async () => {
    api.result = { items: [] };
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

  it('enters error when the initial load fails', async () => {
    api.failure = true;
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [WatchNextFacade, { provide: MEDIA_STACK_API, useValue: api }],
    });
    const failingFacade = TestBed.inject(WatchNextFacade);
    await Promise.resolve();
    await Promise.resolve();
    expect(failingFacade.status()).toBe('error');
    expect(failingFacade.error()).toContain('temporarily unavailable');
  });

  it('enters error when a refresh fails after an empty load', async () => {
    api.result = { items: [] };
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('empty');

    api.failure = true;
    await facade.refresh();
    expect(facade.status()).toBe('error');
    expect(facade.error()).toContain('temporarily unavailable');
  });

  it('ignores stale responses', async () => {
    let resolveSlow: ((value: WatchNextResult) => void) | undefined;
    const slow = new Promise<WatchNextResult>((resolve) => {
      resolveSlow = resolve;
    });
    api.nextResponse = slow;
    const first = facade.refresh({ initial: true });
    api.result = { items: [movie('m2', 'Later')] };
    api.nextResponse = undefined;
    await facade.refresh({ initial: true });
    resolveSlow?.({ items: [episode('old', 'Stale')] });
    await first;
    expect(facade.items()[0]?.title).toBe('Later');
  });
});

class MockApi implements MediaStackApi {
  result: WatchNextResult = { items: [movie('m1', 'Moonrise'), episode('e1', 'Night Watch')] };
  failure = false;
  nextResponse?: Promise<WatchNextResult>;

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
  listLibraryItems() {
    return Promise.resolve({ items: [], availability: 'complete' as const });
  }
  listWatchNext(): Promise<WatchNextResult> {
    if (this.nextResponse) return this.nextResponse;
    return this.failure
      ? Promise.reject(new Error('offline'))
      : Promise.resolve({ items: [...this.result.items] });
  }
  getActivity() {
    return Promise.resolve({
      ok: true,
      generatedAt: '',
      sources: { sonarr: 'ok' as const, radarr: 'ok' as const },
      items: [],
    });
  }
  getLibraryStats() {
    return Promise.resolve({ movies: 0, series: 0, availability: 'complete' as const });
  }
  getStorageOverview() {
    return Promise.resolve({ generatedAt: '', volumes: [] });
  }
  getAutomationSummary() {
    return Promise.resolve({
      generatedAt: '',
      services: [],
      preview: [],
      problems: [],
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
    return Promise.resolve({ ok: true, runs: [] });
  }
}
