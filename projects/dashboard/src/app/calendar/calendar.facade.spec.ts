import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import {
  CALENDAR_LINK_BASES,
  MEDIA_STACK_API,
  MediaStackApi,
  MediaStackArrLibraryDto,
  MediaStackCalendarEventDto,
  MediaStackTorrentDto,
} from '../downloads/media-stack-api';
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
        title: 'Night Transit',
        additional: 'Premiere',
        date: 'Jul 15',
        hasFile: false,
        kind: 'movie',
      },
      {
        title: 'Cowboy Bebop',
        additional: 'S1 E5',
        date: 'Jul 12',
        airDate: '2026-07-12T18:00:00Z',
        hasFile: false,
        kind: 'episode',
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
  events: MediaStackCalendarEventDto[] = [
    {
      title: 'Night Transit',
      additional: 'Premiere',
      date: 'Jul 15',
      airDate: '2026-07-15T12:00:00Z',
      hasFile: false,
      kind: 'movie',
    },
    {
      title: 'Cowboy Bebop',
      additional: 'S1 E5',
      date: 'Jul 12',
      airDate: '2026-07-12T18:00:00Z',
      hasFile: false,
      kind: 'episode',
    },
    {
      title: 'Dune',
      additional: 'Theatrical',
      date: 'Jul 13',
      airDate: '2026-07-13T00:00:00Z',
      hasFile: true,
      kind: 'movie',
    },
  ];
  library: MediaStackArrLibraryDto = {
    ok: true,
    series: { 'cowboy bebop': 'cowboy-bebop' },
    movies: { dune: 'dune-2021' },
  };
  calendarCalls = 0;
  failure = false;

  listTorrents(): Promise<MediaStackTorrentDto[]> {
    return Promise.resolve([]);
  }
  pauseAll(): Promise<void> {
    return Promise.resolve();
  }
  resumeAll(): Promise<void> {
    return Promise.resolve();
  }
  listCalendarEvents(): Promise<MediaStackCalendarEventDto[]> {
    this.calendarCalls++;
    return this.failure ? Promise.reject(new Error('offline')) : Promise.resolve(this.events.map((event) => ({ ...event })));
  }
  getArrLibrary(): Promise<MediaStackArrLibraryDto> {
    return this.failure
      ? Promise.reject(new Error('offline'))
      : Promise.resolve({
          ok: this.library.ok,
          series: { ...this.library.series },
          movies: { ...this.library.movies },
        });
  }
}
