import { DEFAULT_LIBRARY_ART, formatLibraryDeleteDialogBody, formatLibraryDeleteDialogCopy, formatLibraryDeleteToasts } from './library.models';
import {
  formatLibraryMeta,
  LIBRARY_KIND_LABEL,
  libraryEmptyMessage,
  mapLibraryItem,
  mapLibraryStats,
} from './library-format';

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
    expect(formatLibraryMeta(2023, 'series', 1)).toBe('2023 · Series · 1 episode');
    expect(formatLibraryMeta(2023, 'series', 2)).toBe('2023 · Series · 2 episodes');
    expect(formatLibraryMeta(undefined as unknown as number, 'series')).toBe('Series');
    expect(LIBRARY_KIND_LABEL.movie).toBe('Movies');
    expect(LIBRARY_KIND_LABEL.series).toBe('Series');
  });

  it('accentuates delete-dialog titles separately from the surrounding copy', () => {
    const movie = formatLibraryDeleteDialogCopy({
      previewId: 'p1',
      title: 'Moonrise',
      kind: 'movie',
      manager: 'Radarr',
      episodeCount: null,
      torrentCount: 0,
      expiresAt: '2026-01-01T00:00:00.000Z',
    });
    expect(movie).toEqual({
      title: 'Moonrise',
      rest: ' from Radarr. No matching torrents are currently in qBittorrent.',
    });
    expect(
      formatLibraryDeleteDialogBody({
        previewId: 'p1',
        title: 'Moonrise',
        kind: 'movie',
        manager: 'Radarr',
        episodeCount: null,
        torrentCount: 0,
        expiresAt: '2026-01-01T00:00:00.000Z',
      }),
    ).toBe('This will remove Moonrise from Radarr. No matching torrents are currently in qBittorrent.');

    const series = formatLibraryDeleteDialogCopy({
      previewId: 'p2',
      title: 'Silo',
      kind: 'series',
      manager: 'Sonarr',
      episodeCount: 10,
      torrentCount: 2,
      expiresAt: '2026-01-01T00:00:00.000Z',
    });
    expect(series.title).toBe('Silo (10 episodes)');
    expect(series.rest).toContain('from Sonarr and delete 2 matching torrents');
  });

  it('maps delete step outcomes to toasts', () => {
    const preview = { title: 'Silo', manager: 'Sonarr' as const };
    expect(
      formatLibraryDeleteToasts(
        {
          ok: true,
          removed: true,
          torrentCount: 2,
          steps: { torrents: 'ok', library: 'ok', jellyfin: 'ok' },
        },
        preview,
      ),
    ).toEqual([
      {
        title: 'Removed Silo',
        body: 'Deleted from Sonarr and qBittorrent.',
        tone: 'success',
      },
    ]);
    expect(
      formatLibraryDeleteToasts(
        {
          ok: false,
          removed: false,
          partial: true,
          torrentCount: 1,
          steps: { torrents: 'ok', library: 'failed', jellyfin: 'skipped' },
        },
        preview,
      ),
    ).toEqual([
      {
        title: 'Removed torrents; library item remains',
        body: 'Sonarr did not remove this title.',
        tone: 'error',
      },
    ]);
    expect(
      formatLibraryDeleteToasts(
        {
          ok: false,
          removed: false,
          torrentCount: 1,
          error: 'Unable to delete this title',
          steps: { torrents: 'failed', library: 'skipped', jellyfin: 'skipped' },
        },
        preview,
      ),
    ).toEqual([
      {
        title: 'Could not delete this title',
        body: 'Matching torrents were not removed.',
        tone: 'error',
      },
    ]);
    expect(
      formatLibraryDeleteToasts(
        {
          ok: true,
          removed: true,
          torrentCount: 0,
          jellyfinRefresh: 'pending',
          warning: 'Removed; Jellyfin refresh pending',
          steps: { torrents: 'skipped', library: 'ok', jellyfin: 'pending' },
        },
        preview,
      ),
    ).toEqual([
      {
        title: 'Removed Silo',
        body: 'Deleted from Sonarr.',
        tone: 'success',
      },
      {
        title: 'Removed; Jellyfin refresh pending',
        tone: 'gold',
      },
    ]);
  });

  it('builds empty-state copy per collection', () => {
    expect(libraryEmptyMessage('movie')).toContain('movies');
    expect(libraryEmptyMessage('series')).toContain('series');
  });

  it('maps library stats and rejects missing counts', () => {
    expect(mapLibraryStats({ movies: 428, series: 76 })).toEqual({
      movies: 428,
      series: 76,
      availability: 'complete',
    });
    expect(mapLibraryStats({ movies: 0, series: 0 })).toEqual({
      movies: 0,
      series: 0,
      availability: 'complete',
    });
    expect(() => mapLibraryStats({ movies: 12 } as never)).toThrow(/missing series/);
    expect(() => mapLibraryStats({} as never)).toThrow(/missing movies/);
  });
});
