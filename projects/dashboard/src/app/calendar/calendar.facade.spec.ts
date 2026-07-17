import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { MEDIA_STACK_API, MediaStackApi } from '../media-stack/media-stack-api';
import { ArrLibrary, CALENDAR_LINK_BASES, CalendarEvent } from './calendar.models';
import { CalendarFacade } from './calendar.facade';

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
    await facade.refresh();
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
    await facade.refresh();
    expect(facade.events().map((event) => event.title)).toEqual(['Cowboy Bebop', 'Night Transit']);
  });

  it('exposes empty and error states', async () => {
    api.events = [];
    await facade.refresh();
    expect(facade.status()).toBe('empty');

    api.failure = true;
    await facade.refresh();
    expect(facade.status()).toBe('error');
    expect(facade.error()).toContain('temporarily unavailable');
  });

  it('keeps events usable when arr library lookup fails', async () => {
    api.libraryFailure = true;
    await facade.refresh();
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
    await facade.refresh();
    expect(facade.events()[0].href).toBe('https://sonarr.example/series/fargo');
    expect(facade.events()[1].href).toBe('https://radarr.example/movie/fargo-1996');
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
  listCalendarEvents(): Promise<CalendarEvent[]> {
    this.calendarCalls++;
    return this.failure
      ? Promise.reject(new Error('offline'))
      : Promise.resolve(this.events.map((event) => ({ ...event })));
  }
  getArrLibrary(): Promise<ArrLibrary> {
    return this.libraryFailure || this.failure
      ? Promise.reject(new Error('offline'))
      : Promise.resolve({
          ok: this.library.ok,
          series: { ...this.library.series },
          movies: { ...this.library.movies },
        });
  }
  listLibraryItems() {
    return Promise.resolve([]);
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
