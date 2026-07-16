import { DEFAULT_LIBRARY_ART } from './library.models';
import { formatLibraryMeta, LIBRARY_KIND_LABEL, libraryEmptyMessage, mapLibraryItem } from './library-format';

describe('library format / library mapping', () => {
  it('maps library DTO meta and artwork state', () => {
    const present = mapLibraryItem({
      id: 'jf-dune',
      title: 'Dune',
      kind: 'movie',
      year: 2021,
      overview: 'Desert power.',
      posterUrl: 'linear-gradient(145deg, #8b5a2b, #1a1a1a 70%)',
    });
    expect(present).toMatchObject({
      id: 'jf-dune',
      title: 'Dune',
      kind: 'movie',
      meta: '2021 · Movie',
      artworkState: 'ok',
      playable: true,
      href: null,
    });
    expect(present?.art).toContain('gradient');

    const missing = mapLibraryItem({
      id: 'jf-missing',
      title: 'Night Transit',
      kind: 'movie',
      year: 2026,
    });
    expect(missing?.artworkState).toBe('missing');
    expect(missing?.art).toBe(DEFAULT_LIBRARY_ART);
    expect(missing?.meta).toBe('2026 · Movie');

    const failed = mapLibraryItem({
      id: 'jf-failed',
      title: 'Broken Art',
      kind: 'series',
      posterUrl: 'http://example.invalid/poster.jpg',
      artworkState: 'failed',
    });
    expect(failed?.artworkState).toBe('failed');
    expect(failed?.art).toBe(DEFAULT_LIBRARY_ART);
    expect(failed?.meta).toBe('Series');
  });

  it('drops unknown library kinds instead of coercing them to movie', () => {
    expect(
      mapLibraryItem({
        id: 'jf-season',
        title: 'Season 1',
        kind: 'Season',
      }),
    ).toBeNull();
    expect(
      mapLibraryItem({
        id: 'jf-folder',
        title: 'Collections',
        kind: 'Folder',
      }),
    ).toBeNull();
  });

  it('sizes remote poster URLs to cover the 2:3 art host', () => {
    const item = mapLibraryItem({
      id: 'jf-poster',
      title: 'Afterlight',
      kind: 'movie',
      posterUrl: 'https://jellyfin.example/Items/jf-poster/Images/Primary',
    });
    expect(item?.art).toBe(
      'url("https://jellyfin.example/Items/jf-poster/Images/Primary") center / cover no-repeat',
    );
  });

  it('formats meta and collection labels', () => {
    expect(formatLibraryMeta(2021, 'movie')).toBe('2021 · Movie');
    expect(formatLibraryMeta(undefined as unknown as number, 'series')).toBe('Series');
    expect(LIBRARY_KIND_LABEL.movie).toBe('Movies');
    expect(LIBRARY_KIND_LABEL.series).toBe('Series');
  });

  it('builds empty-state copy per collection', () => {
    expect(libraryEmptyMessage('movie')).toContain('movies');
    expect(libraryEmptyMessage('series')).toContain('series');
  });
});
