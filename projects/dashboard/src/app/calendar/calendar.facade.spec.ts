import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { MEDIA_STACK_API, MediaStackApi } from '../media-stack/media-stack-api';
import { ArrLibrary, CALENDAR_LINK_BASES, CalendarEvent } from './calendar.models';
import { LibraryItem } from '../library/library.models';
import { CalendarFacade, SCHEDULED_REFRESH_TIMEOUT_MS } from './calendar.facade';

describe('CalendarFacade', () => {
  let api: MockApi;
  let facade: CalendarFacade;

  beforeEach(() => {
    api = new MockApi();
    TestBed.configureTestingModule({
      providers: [
        CalendarFacade,
        { provide: MEDIA_STACK_API, useValue: api },
        {
          provide: CALENDAR_LINK_BASES,
          useValue: {
            sonarrBase: 'https://sonarr.example/',
            radarrBase: 'https://radarr.example/',
          },
        },
      ],
    });
    facade = TestBed.inject(CalendarFacade);
  });

  it('loads mixed events in airDate order and attaches destinations', async () => {
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('ready');
    expect(facade.events().map((event) => event.title)).toEqual([
      'Cowboy Bebop',
      'Dune',
      'Night Transit',
    ]);
    expect(facade.events()[0].href).toBe('https://sonarr.example/series/cowboy-bebop');
    expect(facade.events()[1].href).toBe('https://radarr.example/movie/dune-2021');
    expect(facade.events()[2].href).toBeNull();
  });

  it('keeps undated events after dated ones', async () => {
    api.events = [
      {
        id: 'Night Transit-Premiere-Jul 15',
        time: 'Jul 15',
        kind: 'movie',
        title: 'Night Transit',
        subtitle: 'Premiere',
        status: 'pending',
        airDate: '',
      },
      {
        id: 'Cowboy Bebop-S1 E5-2026-07-12T18:00:00Z',
        time: 'Jul 12',
        kind: 'episode',
        title: 'Cowboy Bebop',
        subtitle: 'S1 E5',
        status: 'pending',
        airDate: '2026-07-12T18:00:00Z',
      },
    ];
    await facade.refresh({ initial: true });
    expect(facade.events().map((event) => event.title)).toEqual(['Cowboy Bebop', 'Night Transit']);
  });

  it('exposes empty and error states', async () => {
    api.events = [];
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('empty');

    api.failure = true;
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('error');
    expect(facade.error()).toContain('temporarily unavailable');
  });

  it('retains last-good events when a background refresh fails', async () => {
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('ready');
    expect(facade.events()).toHaveLength(3);

    api.failure = true;
    await facade.refresh();
    expect(facade.status()).toBe('ready');
    expect(facade.events()).toHaveLength(3);
    expect(facade.error()).toContain('Showing last loaded schedule');
  });

  it('ignores stale responses when a newer refresh wins the race', async () => {
    const { promise: initialPromise, resolve: resolveInitial } =
      Promise.withResolvers<CalendarEvent[]>();
    api.nextResponse = initialPromise;

    const first = facade.refresh({ initial: true });
    expect(facade.refreshing()).toBe(true);

    api.nextResponse = undefined;
    api.events = [
      {
        id: 'Newer-S1 E1-2026-07-12T18:00:00Z',
        time: 'Jul 12',
        kind: 'episode',
        title: 'Newer',
        subtitle: 'S1 E1',
        status: 'pending',
        airDate: '2026-07-12T18:00:00Z',
      },
    ];
    await facade.refresh();
    expect(facade.events()[0]?.title).toBe('Newer');

    resolveInitial([
      {
        id: 'Stale-S1 E1-2026-07-12T18:00:00Z',
        time: 'Jul 12',
        kind: 'episode',
        title: 'Stale',
        subtitle: 'S1 E1',
        status: 'pending',
        airDate: '2026-07-12T18:00:00Z',
      },
    ]);
    await first;

    expect(facade.events()[0]?.title).toBe('Newer');
    expect(facade.refreshing()).toBe(false);
  });

  it('keeps events usable when arr library lookup fails', async () => {
    api.libraryFailure = true;
    await facade.refresh({ initial: true });
    expect(facade.status()).toBe('ready');
    expect(facade.events().map((event) => event.title)).toEqual([
      'Cowboy Bebop',
      'Dune',
      'Night Transit',
    ]);
    expect(facade.events().every((event) => event.href === null)).toBe(true);
  });

  it('resolves colliding titles using event kind', async () => {
    api.events = [
      {
        id: 'Fargo-Theatrical-2026-07-13T00:00:00Z',
        time: 'Jul 13',
        kind: 'movie',
        title: 'Fargo',
        subtitle: 'Theatrical',
        status: 'available',
        airDate: '2026-07-13T00:00:00Z',
      },
      {
        id: 'Fargo-S1 E1-2026-07-12T18:00:00Z',
        time: 'Jul 12',
        kind: 'episode',
        title: 'Fargo',
        subtitle: 'S1 E1',
        status: 'pending',
        airDate: '2026-07-12T18:00:00Z',
      },
    ];
    api.library = {
      ok: true,
      series: { fargo: 'fargo' },
      movies: { fargo: 'fargo-1996' },
    };
    await facade.refresh({ initial: true });
    expect(facade.events()[0].href).toBe('https://sonarr.example/series/fargo');
    expect(facade.events()[1].href).toBe('https://radarr.example/movie/fargo-1996');
  });

  it('does not overlap scheduled polls while one is in flight', async () => {
    vi.useFakeTimers();
    const { promise: deferred, resolve } = Promise.withResolvers<CalendarEvent[]>();
    api.nextResponse = deferred;

    facade.startPolling(100);
    await vi.advanceTimersByTimeAsync(0);
    expect(api.calendarCalls).toBe(1);

    await vi.advanceTimersByTimeAsync(300);
    expect(api.calendarCalls).toBe(1);

    api.nextResponse = undefined;
    resolve(api.events.map((event) => ({ ...event })));
    await Promise.resolve();
    await Promise.resolve();

    await vi.advanceTimersByTimeAsync(100);
    expect(api.calendarCalls).toBe(2);

    TestBed.resetTestingModule();
    await vi.advanceTimersByTimeAsync(200);
    expect(api.calendarCalls).toBe(2);
    vi.useRealTimers();
  });

  it('ignores a superseded hung poll timeout after a newer refresh wins', async () => {
    vi.useFakeTimers();
    const { promise: deferred } = Promise.withResolvers<CalendarEvent[]>();
    api.nextResponse = deferred;

    facade.startPolling(SCHEDULED_REFRESH_TIMEOUT_MS + 1_000);
    await vi.advanceTimersByTimeAsync(0);
    expect(api.calendarCalls).toBe(1);
    expect(facade.refreshing()).toBe(true);

    api.nextResponse = undefined;
    api.events = [
      {
        id: 'From-manual-2026-07-12T18:00:00Z',
        time: 'Jul 12',
        kind: 'episode',
        title: 'From manual',
        subtitle: 'S1 E1',
        status: 'pending',
        airDate: '2026-07-12T18:00:00Z',
      },
    ];
    await facade.refresh();
    expect(facade.status()).toBe('ready');
    expect(facade.events()[0]?.title).toBe('From manual');
    expect(facade.error()).toBe('');
    expect(facade.refreshing()).toBe(false);

    await vi.advanceTimersByTimeAsync(SCHEDULED_REFRESH_TIMEOUT_MS);
    expect(facade.status()).toBe('ready');
    expect(facade.events()[0]?.title).toBe('From manual');
    expect(facade.error()).toBe('');
    expect(facade.refreshing()).toBe(false);

    TestBed.resetTestingModule();
    vi.useRealTimers();
  });

  it('does not commit a de-linked schedule when ARR enrichment aborts mid-refresh', async () => {
    vi.useFakeTimers();
    facade.startPolling(SCHEDULED_REFRESH_TIMEOUT_MS + 1_000);
    await vi.advanceTimersByTimeAsync(0);
    await Promise.resolve();
    await Promise.resolve();
    expect(facade.status()).toBe('ready');
    const priorTitles = facade.events().map((event) => event.title);
    expect(priorTitles[0]).toBe('Cowboy Bebop');

    const { promise: hungLibrary } = Promise.withResolvers<ArrLibrary>();
    api.nextLibrary = hungLibrary;
    api.events = [
      {
        id: 'Aborted-S1 E1-2026-07-12T18:00:00Z',
        time: 'Jul 12',
        kind: 'episode',
        title: 'Aborted Enrichment',
        subtitle: 'S1 E1',
        status: 'pending',
        airDate: '2026-07-12T18:00:00Z',
      },
    ];

    await vi.advanceTimersByTimeAsync(SCHEDULED_REFRESH_TIMEOUT_MS + 1_000);
    expect(api.calendarCalls).toBe(2);
    expect(facade.refreshing()).toBe(true);

    await vi.advanceTimersByTimeAsync(SCHEDULED_REFRESH_TIMEOUT_MS);
    expect(facade.status()).toBe('ready');
    expect(facade.events().map((event) => event.title)).toEqual(priorTitles);
    expect(facade.error()).toBe(
      'Could not refresh calendar. Showing last loaded schedule.',
    );
    expect(facade.events().some((event) => event.title === 'Aborted Enrichment')).toBe(false);

    TestBed.resetTestingModule();
    vi.useRealTimers();
  });

  it('enriches event art from library posters by title and keeps gradients when unmatched', async () => {
    api.libraryItems = [
      {
        id: 'jf-1',
        title: 'Cowboy Bebop',
        kind: 'series',
        meta: '1998 · Series',
        art: 'url("https://jellyfin.example/bebop.jpg") center / cover no-repeat',
        overview: '',
        href: null,
        artworkState: 'ok',
        playable: true,
      },
    ];
    api.events = api.events.map((event) => ({
      ...event,
      art: 'linear-gradient(145deg, #111, #000 70%)',
    }));
    await facade.refresh({ initial: true });
    const byTitle = new Map(facade.events().map((event) => [event.title, event.art]));
    expect(byTitle.get('Cowboy Bebop')).toBe(
      'url("https://jellyfin.example/bebop.jpg") center / cover no-repeat',
    );
    expect(byTitle.get('Dune')).toContain('linear-gradient');
  });

  it('keeps gradient art when library item load fails without aborting', async () => {
    api.libraryItemsFailure = true;
    api.events = [
      {
        id: 'Cowboy Bebop-S1 E5-2026-07-12T18:00:00Z',
        time: 'Jul 12',
        kind: 'episode',
        title: 'Cowboy Bebop',
        subtitle: 'S1 E5',
        status: 'pending',
        airDate: '2026-07-12T18:00:00Z',
        art: 'linear-gradient(145deg, #111, #000 70%)',
      },
    ];
    await facade.refresh({ initial: true });
    expect(facade.events()[0]?.art).toContain('linear-gradient');
  });

  it('refreshes on one interval and stops polling when destroyed', async () => {
    vi.useFakeTimers();
    facade.startPolling(100);
    await vi.advanceTimersByTimeAsync(0);
    expect(api.calendarCalls).toBe(1);
    facade.startPolling(100);
    await vi.advanceTimersByTimeAsync(200);
    expect(api.calendarCalls).toBe(3);
    TestBed.resetTestingModule();
    await vi.advanceTimersByTimeAsync(200);
    expect(api.calendarCalls).toBe(3);
    vi.useRealTimers();
  });
});

class MockApi implements MediaStackApi {
  events: CalendarEvent[] = [
    {
      id: 'Night Transit-Premiere-2026-07-15T12:00:00Z',
      time: 'Jul 15',
      kind: 'movie',
      title: 'Night Transit',
      subtitle: 'Premiere',
      status: 'pending',
      airDate: '2026-07-15T12:00:00Z',
    },
    {
      id: 'Cowboy Bebop-S1 E5-2026-07-12T18:00:00Z',
      time: 'Jul 12',
      kind: 'episode',
      title: 'Cowboy Bebop',
      subtitle: 'S1 E5',
      status: 'pending',
      airDate: '2026-07-12T18:00:00Z',
    },
    {
      id: 'Dune-Theatrical-2026-07-13T00:00:00Z',
      time: 'Jul 13',
      kind: 'movie',
      title: 'Dune',
      subtitle: 'Theatrical',
      status: 'available',
      airDate: '2026-07-13T00:00:00Z',
    },
  ];
  library: ArrLibrary = {
    ok: true,
    series: { 'cowboy bebop': 'cowboy-bebop' },
    movies: { dune: 'dune-2021' },
  };
  calendarCalls = 0;
  failure = false;
  libraryFailure = false;
  libraryItems: LibraryItem[] = [];
  libraryItemsFailure = false;
  nextResponse?: Promise<CalendarEvent[]>;
  nextLibrary?: Promise<ArrLibrary>;
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
  getStorageOverview() {
    return Promise.resolve({ generatedAt: '', volumes: [] });
  }
  listCalendarEvents(signal?: AbortSignal): Promise<CalendarEvent[]> {
    this.calendarCalls++;
    this.lastSignal = signal;
    if (signal?.aborted) {
      return Promise.reject(new DOMException('The operation was aborted.', 'AbortError'));
    }
    if (this.nextResponse) {
      const pending = this.nextResponse;
      return new Promise<CalendarEvent[]>((resolve, reject) => {
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
            reject(error);
          },
        );
      });
    }
    return this.failure
      ? Promise.reject(new Error('offline'))
      : Promise.resolve(this.events.map((event) => ({ ...event })));
  }
  getArrLibrary(signal?: AbortSignal): Promise<ArrLibrary> {
    if (signal?.aborted) {
      return Promise.reject(new DOMException('The operation was aborted.', 'AbortError'));
    }
    if (this.nextLibrary) {
      const pending = this.nextLibrary;
      return new Promise<ArrLibrary>((resolve, reject) => {
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
            reject(error);
          },
        );
      });
    }
    return this.libraryFailure || this.failure
      ? Promise.reject(new Error('offline'))
      : Promise.resolve({
          ok: this.library.ok,
          series: { ...this.library.series },
          movies: { ...this.library.movies },
        });
  }
  listLibraryItems(_filter?: unknown, signal?: AbortSignal) {
    if (signal?.aborted) {
      return Promise.reject(new DOMException('The operation was aborted.', 'AbortError'));
    }
    return this.libraryItemsFailure
      ? Promise.reject(new Error('library offline'))
      : Promise.resolve({ items: this.libraryItems.map((item) => ({ ...item })), availability: 'complete' as const });
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
    return Promise.resolve({ ok: true, runs: [] });
  }
}
