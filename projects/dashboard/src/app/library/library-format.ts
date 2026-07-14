import { LibraryItemKind, formatLibraryMeta } from './library.models';

export { formatLibraryMeta };

export const LIBRARY_KIND_LABEL: Record<LibraryItemKind, string> = {
  movie: 'Movies',
  series: 'Series',
};

export const libraryEmptyMessage = (kind: LibraryItemKind): string =>
  kind === 'movie' ? 'No movies in the demo library.' : 'No series in the demo library.';
