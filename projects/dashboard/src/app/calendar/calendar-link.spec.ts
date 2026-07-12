import { normalizeCalendarEvent, resolveCalendarLink } from '../downloads/media-stack-api';

describe('calendar API boundary', () => {
  it('normalizes episode and movie events with status and stable ids', () => {
    const episode = normalizeCalendarEvent({
      title: 'Cowboy Bebop',
      additional: 'S1 E5',
      date: 'Jul 12',
      airDate: '2026-07-12T18:00:00Z',
      hasFile: false,
      kind: 'episode',
    });
    expect(episode).toEqual({
      id: 'Cowboy Bebop-S1 E5-2026-07-12T18:00:00Z',
      time: 'Jul 12',
      kind: 'episode',
      title: 'Cowboy Bebop',
      subtitle: 'S1 E5',
      status: 'pending',
      airDate: '2026-07-12T18:00:00Z',
    });

    const movie = normalizeCalendarEvent({
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
    const event = normalizeCalendarEvent({
      title: 'The Expanse',
      additional: 'S4 E2',
      date: 'Jul 14',
      airDate: '2026-07-14T21:00:00Z',
    });
    expect(event.kind).toBe('episode');
  });

  it('resolves sonarr and radarr destinations and leaves unmatched titles inert', () => {
    const library = {
      series: { 'cowboy bebop': 'cowboy-bebop' },
      movies: { dune: 'dune-2021' },
    };
    expect(resolveCalendarLink('Cowboy Bebop', library)).toBe(
      'http://localhost:8989/series/cowboy-bebop',
    );
    expect(resolveCalendarLink('Dune', library)).toBe('http://localhost:7878/movie/dune-2021');
    expect(resolveCalendarLink('Missing', library)).toBeNull();
    expect(resolveCalendarLink('', library)).toBeNull();
  });

  it('keeps external base urls configurable at the boundary', () => {
    const library = {
      series: { 'cowboy bebop': 'cowboy-bebop' },
      movies: { dune: 'dune-2021' },
    };
    expect(
      resolveCalendarLink('Cowboy Bebop', library, {
        sonarrBase: 'https://sonarr.example/',
        radarrBase: 'https://radarr.example/',
      }),
    ).toBe('https://sonarr.example/series/cowboy-bebop');
    expect(
      resolveCalendarLink('Dune', library, {
        sonarrBase: 'https://sonarr.example/',
        radarrBase: 'https://radarr.example/',
      }),
    ).toBe('https://radarr.example/movie/dune-2021');
  });
});
