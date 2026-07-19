import {
  DEFAULT_LIBRARY_ART,
  LibraryArtworkState,
  LibraryItem,
  LibraryItemKind,
  LibraryStats,
  formatLibraryMeta,
} from './library.models';
import { MediaStackLibraryItemDto, MediaStackLibraryStatsDto } from '../media-stack/wire/library';

export { formatLibraryMeta };

export const LIBRARY_KIND_LABEL: Record<LibraryItemKind, string> = {
  movie: 'Movies',
  series: 'Series',
};

export const mapLibraryItem = (dto: MediaStackLibraryItemDto): LibraryItem | null => {
  const kind = normalizeLibraryKind(dto.kind);
  if (!kind) return null;
  const id = dto.id?.trim();
  const title = dto.title?.trim();
  if (!id || !title) return null;
  const artworkState = normalizeArtworkState(dto.artworkState, dto.posterUrl);
  return {
    id,
    title,
    kind,
    meta: formatLibraryMeta(dto.year, kind),
    art: resolveLibraryArt(dto.posterUrl, artworkState),
    overview: dto.overview?.trim() || '',
    href: null,
    artworkState,
    playable: dto.playable !== false,
    rating: normalizeRating(dto.rating),
  };
};

function normalizeRating(value: number | null | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 10
    ? Math.round(value * 10) / 10
    : null;
}

function normalizeLibraryKind(kind: string | undefined): LibraryItemKind | null {
  const normalized = kind?.trim().toLowerCase();
  if (normalized === 'movie') return 'movie';
  if (normalized === 'series') return 'series';
  return null;
}

function normalizeArtworkState(
  state: LibraryArtworkState | undefined,
  posterUrl: string | undefined,
): LibraryArtworkState {
  if (state === 'failed' || state === 'missing' || state === 'ok') return state;
  return posterUrl?.trim() ? 'ok' : 'missing';
}

function resolveLibraryArt(posterUrl: string | undefined, artworkState: LibraryArtworkState): string {
  if (artworkState === 'missing' || artworkState === 'failed') return DEFAULT_LIBRARY_ART;
  const value = posterUrl?.trim();
  if (!value) return DEFAULT_LIBRARY_ART;
  if (value.startsWith('url(') || value.includes('gradient(')) return value;
  return `url("${value}") center / cover no-repeat`;
}

export const libraryEmptyMessage = (kind: LibraryItemKind): string =>
  kind === 'movie' ? 'No movies in the demo library.' : 'No series in the demo library.';

export const mapLibraryStats = (dto: MediaStackLibraryStatsDto): LibraryStats => {
  if (typeof dto.movies !== 'number' || !Number.isFinite(dto.movies)) {
    throw new Error('Malformed library stats: missing movies');
  }
  if (typeof dto.series !== 'number' || !Number.isFinite(dto.series)) {
    throw new Error('Malformed library stats: missing series');
  }
  return {
    movies: Math.max(0, Math.round(dto.movies)),
    series: Math.max(0, Math.round(dto.series)),
    availability: 'complete',
  };
};
