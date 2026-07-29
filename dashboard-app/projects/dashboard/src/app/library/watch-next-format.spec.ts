import { DEFAULT_LIBRARY_ART } from './library.models';
import { mapWatchNextItem } from './watch-next-format';

describe('watch-next format', () => {
  it('maps episode and movie items with clamped progress', () => {    const episode = mapWatchNextItem({
      id: 'ep-1',
      parentId: 'series-1',
      title: 'The Expanse',
      subtitle: 'S04E02 · Jetsam',
      kind: 'episode',
      posterUrl: 'https://jellyfin.example/ep.jpg',
      playable: true,
      progressPercent: 42.8,
    });
    expect(episode).toMatchObject({
      id: 'ep-1',
      parentId: 'series-1',
      title: 'The Expanse',
      subtitle: 'S04E02 · Jetsam',
      kind: 'episode',
      progressPercent: 42.8,
      playable: true,
      href: null,
    });
    expect(episode.art).toContain('jellyfin.example');

    const movie = mapWatchNextItem({
      id: 'mv-1',
      parentId: null,
      title: 'Dune',
      subtitle: '',
      kind: 'movie',
      progressPercent: 150,
    });
    expect(movie.parentId).toBeNull();
    expect(movie.progressPercent).toBe(100);
  });

  it('rejects malformed identities and progress', () => {
    expect(() =>
      mapWatchNextItem({
        id: '',
        parentId: 'series-1',
        title: 'Show',
        subtitle: '',
        kind: 'episode',
        progressPercent: 0,
      }),
    ).toThrow(/missing id or title/);

    expect(() =>
      mapWatchNextItem({
        id: 'ep-1',
        parentId: '',
        title: 'Show',
        subtitle: '',
        kind: 'episode',
        progressPercent: 0,
      }),
    ).toThrow(/missing parentId/);

    expect(() =>
      mapWatchNextItem({
        id: 'mv-1',
        parentId: 'series-1',
        title: 'Dune',
        subtitle: '',
        kind: 'movie',
        progressPercent: 10,
      }),
    ).toThrow(/movie parentId must be null/);

    expect(() =>
      mapWatchNextItem({
        id: 'mv-1',
        parentId: null,
        title: 'Dune',
        subtitle: '',
        kind: 'movie',
        progressPercent: Number.NaN,
      }),
    ).toThrow(/invalid progressPercent/);
  });

  it('uses stable artwork fallback for missing art', () => {
    const item = mapWatchNextItem({
      id: 'mv-2',
      parentId: null,
      title: 'Night Transit',
      subtitle: '',
      kind: 'movie',
      artworkState: 'missing',
      progressPercent: 0,
    });
    expect(item.art).toBe(DEFAULT_LIBRARY_ART);
    expect(item.artworkState).toBe('missing');
  });
});
