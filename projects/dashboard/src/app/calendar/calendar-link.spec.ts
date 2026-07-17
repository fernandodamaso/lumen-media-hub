import { mapCalendarEvent } from './calendar-format';
import { resolveCalendarLink, compareCalendarEvents } from './calendar.models';

describe('calendar API boundary', () => {
  it('normalizes episode and movie events with status and stable ids', () => {
    const episode = mapCalendarEvent({
      title: 'Cowboy Bebop',
      additional: 'S1 E5',
      date: 'Jul 12',
      airDate: '2026-07-12T18:00:00Z',
      hasFile: false,
      kind: 'episode',
    });
    expect(episode).toMatchObject({
      id: 'Cowboy Bebop-S1 E5-2026-07-12T18:00:00Z',
      time: 'Jul 12',
      kind: 'episode',
      title: 'Cowboy Bebop',
      subtitle: 'S1 E5',
      status: 'pending',
      airDate: '2026-07-12T18:00:00Z',
    });
    expect(episode.art).toContain('linear-gradient');

    const movie = mapCalendarEvent({
      title: 'Dune',
      additional: 'Theatrical',
      date: 'Jul 13',
      airDate: '2026-07-13T00:00:00Z',
      hasFile: true,
      kind: 'movie',
    });
    expect(movie.kind).toBe('movie');
    expect(movie.status).toBe('available');
  });

  it('infers episode kind from SxxExx subtitle when kind is omitted', () => {
    const event = mapCalendarEvent({
      title: 'The Expanse',
      additional: 'S4 E2',
      date: 'Jul 14',
      airDate: '2026-07-14T21:00:00Z',
    });
    expect(event.kind).toBe('episode');
  });

  it('sorts dated events first and keeps undated events after them', () => {
    const undated = mapCalendarEvent({
      title: 'Night Transit',
      additional: 'Premiere',
      date: 'Jul 15',
      kind: 'movie',
    });
    const earlier = mapCalendarEvent({
      title: 'Cowboy Bebop',
      additional: 'S1 E5',
      date: 'Jul 12',
      airDate: '2026-07-12T18:00:00Z',
      kind: 'episode',
    });
    const later = mapCalendarEvent({
      title: 'Dune',
      additional: 'Theatrical',
      date: 'Jul 13',
      airDate: '2026-07-13T00:00:00Z',
      kind: 'movie',
    });
    expect([undated, later, earlier].sort(compareCalendarEvents).map((event) => event.title)).toEqual([
      'Cowboy Bebop',
      'Dune',
      'Night Transit',
    ]);
  });

  it('resolves sonarr and radarr destinations and leaves unmatched titles inert', () => {
    const library = {
      series: { 'cowboy bebop': 'cowboy-bebop' },
      movies: { dune: 'dune-2021' },
    };
    const localBases = {
      sonarrBase: 'http://localhost:8989',
      radarrBase: 'http://localhost:7878',
    };
    expect(resolveCalendarLink('Cowboy Bebop', library, localBases, 'episode')).toBe(
      'http://localhost:8989/series/cowboy-bebop',
    );
    expect(resolveCalendarLink('Dune', library, localBases, 'movie')).toBe(
      'http://localhost:7878/movie/dune-2021',
    );
    expect(resolveCalendarLink('Missing', library, localBases)).toBeNull();
    expect(resolveCalendarLink('', library, localBases)).toBeNull();
  });

  it('prefers the destination matching event kind when titles collide', () => {
    const library = {
      series: { fargo: 'fargo' },
      movies: { fargo: 'fargo-1996' },
    };
    const localBases = {
      sonarrBase: 'http://localhost:8989',
      radarrBase: 'http://localhost:7878',
    };
    expect(resolveCalendarLink('Fargo', library, localBases, 'movie')).toBe(
      'http://localhost:7878/movie/fargo-1996',
    );
    expect(resolveCalendarLink('Fargo', library, localBases, 'episode')).toBe(
      'http://localhost:8989/series/fargo',
    );
  });

  it('keeps external base urls configurable at the boundary', () => {
    const library = {
      series: { 'cowboy bebop': 'cowboy-bebop' },
      movies: { dune: 'dune-2021' },
    };
    expect(
      resolveCalendarLink(
        'Cowboy Bebop',
        library,
        {
          sonarrBase: 'https://sonarr.example/',
          radarrBase: 'https://radarr.example/',
        },
        'episode',
      ),
    ).toBe('https://sonarr.example/series/cowboy-bebop');
    expect(
      resolveCalendarLink(
        'Dune',
        library,
        {
          sonarrBase: 'https://sonarr.example/',
          radarrBase: 'https://radarr.example/',
        },
        'movie',
      ),
    ).toBe('https://radarr.example/movie/dune-2021');
  });

  it('disables operational links without emitting relative service paths', () => {
    const library = {
      series: { 'cowboy bebop': 'cowboy-bebop' },
      movies: { dune: 'dune-2021' },
    };
    expect(
      resolveCalendarLink('Cowboy Bebop', library, { sonarrBase: '', radarrBase: '' }, 'episode'),
    ).toBeNull();
    expect(resolveCalendarLink('Dune', library, { sonarrBase: '', radarrBase: '' }, 'movie')).toBeNull();
    expect(resolveCalendarLink('Cowboy Bebop', library, {}, 'episode')).toBeNull();
  });
});
