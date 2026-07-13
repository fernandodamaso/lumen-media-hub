import { LibraryItemKind, formatLibraryMeta } from '../downloads/media-stack-api';

export { formatLibraryMeta };

export const LIBRARY_KIND_LABEL: Record<LibraryItemKind, string> = {
  movie: 'Movies',
  series: 'Series',
};

export const libraryEmptyMessage = (kind: LibraryItemKind): string =>
  kind === 'movie' ? 'No movies in the demo library.' : 'No series in the demo library.';
