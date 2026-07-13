import { formatLibraryMeta, LIBRARY_KIND_LABEL, libraryEmptyMessage } from './library-format';

describe('library-format', () => {
  it('formats meta and collection labels', () => {
    expect(formatLibraryMeta(2021, 'movie')).toBe('2021 · Movie');
    expect(formatLibraryMeta(undefined, 'series')).toBe('Series');
    expect(LIBRARY_KIND_LABEL.movie).toBe('Movies');
    expect(LIBRARY_KIND_LABEL.series).toBe('Series');
  });

  it('builds empty-state copy per collection', () => {
    expect(libraryEmptyMessage('movie')).toContain('movies');
    expect(libraryEmptyMessage('series')).toContain('series');
  });
});
