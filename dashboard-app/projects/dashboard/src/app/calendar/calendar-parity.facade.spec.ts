import { TestBed } from '@angular/core/testing';

import { CALENDAR_LINK_BASES, CalendarEventCollection } from './calendar.models';
import { CalendarFacade } from './calendar.facade';
import { MEDIA_STACK_API, MediaStackApi } from '../media-stack/media-stack-api';

function eventFeed(): CalendarEventCollection {
  const events = [
    {
      id: 'radarr:movie:22',
      time: 'Aug 27',
      kind: 'movie' as const,
      title: 'Alpha Movie',
      subtitle: 'Digital release',
      status: 'monitored' as const,
      airDate: '2026-08-27T20:00:00Z',
      movieId: 22,
    },
    {
      id: 'sonarr:episode:11',
      time: 'Aug 27',
      kind: 'episode' as const,
      title: 'Zulu Show',
      subtitle: 'S1 E1',
      status: 'monitored' as const,
      airDate: '2026-08-27T20:00:00Z',
      episodeId: 11,
      seriesId: 42,
    },
  ] as CalendarEventCollection;
  events.sources = { sonarr: 'error', radarr: 'ok' };
  return events;
}

describe('CalendarFacade combined source parity', () => {
  it('keeps healthy provider events while exposing degraded source state', async () => {
    const feed = eventFeed();
    const api = {
      listCalendarEvents: () => Promise.resolve(feed),
      getArrLibrary: () => Promise.resolve({ ok: true, series: {}, movies: {} }),
      listLibraryItems: () => Promise.resolve({ items: [], availability: 'complete' }),
    } as unknown as MediaStackApi;

    TestBed.configureTestingModule({
      providers: [
        CalendarFacade,
        { provide: MEDIA_STACK_API, useValue: api },
        { provide: CALENDAR_LINK_BASES, useValue: { sonarrBase: '', radarrBase: '' } },
      ],
    });

    const facade = TestBed.inject(CalendarFacade);
    await facade.refresh({ initial: true });

    expect(facade.status()).toBe('ready');
    expect(facade.events().map((event) => event.kind)).toEqual(['episode', 'movie']);
    expect(facade.degradedSources()).toEqual(['sonarr']);
  });

  it('does not classify an intentionally unconfigured provider as degraded', async () => {
    const feed = eventFeed();
    feed.sources = { sonarr: 'ok', radarr: 'unconfigured' };
    const api = {
      listCalendarEvents: () => Promise.resolve(feed),
      getArrLibrary: () => Promise.resolve({ ok: true, series: {}, movies: {} }),
      listLibraryItems: () => Promise.resolve({ items: [], availability: 'complete' }),
    } as unknown as MediaStackApi;

    TestBed.configureTestingModule({
      providers: [
        CalendarFacade,
        { provide: MEDIA_STACK_API, useValue: api },
        { provide: CALENDAR_LINK_BASES, useValue: { sonarrBase: '', radarrBase: '' } },
      ],
    });

    const facade = TestBed.inject(CalendarFacade);
    await facade.refresh({ initial: true });

    expect(facade.status()).toBe('ready');
    expect(facade.degradedSources()).toEqual([]);
  });

  it('uses the Radarr event slug instead of a colliding title-keyed library slug', async () => {
    const feed = eventFeed();
    const movie = feed.find((event) => event.kind === 'movie') as (typeof feed)[number] & {
      titleSlug?: string;
    };
    movie.title = 'The Thing';
    movie.titleSlug = 'the-thing-2011';
    feed.sources = { sonarr: 'ok', radarr: 'ok' };
    const api = {
      listCalendarEvents: () => Promise.resolve(feed),
      getArrLibrary: () =>
        Promise.resolve({ ok: true, series: {}, movies: { 'the thing': 'the-thing-1982' } }),
      listLibraryItems: () => Promise.resolve({ items: [], availability: 'complete' }),
    } as unknown as MediaStackApi;

    TestBed.configureTestingModule({
      providers: [
        CalendarFacade,
        { provide: MEDIA_STACK_API, useValue: api },
        { provide: CALENDAR_LINK_BASES, useValue: { sonarrBase: '', radarrBase: 'http://radarr.local' } },
      ],
    });

    const facade = TestBed.inject(CalendarFacade);
    await facade.refresh({ initial: true });

    expect(facade.events().find((event) => event.kind === 'movie')?.href).toBe(
      'http://radarr.local/movie/the-thing-2011',
    );
  });
});