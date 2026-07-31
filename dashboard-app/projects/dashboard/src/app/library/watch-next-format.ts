import { DEFAULT_LIBRARY_ART, LibraryArtworkState } from './library.models';
import { WatchNextItem, WatchNextKind, WatchNextResult } from './watch-next.models';
import { MediaStackWatchNextItemDto } from '../media-stack/wire/watch-next';

export const mapWatchNextItem = (dto: MediaStackWatchNextItemDto): WatchNextItem => {
  const kind = normalizeWatchNextKind(dto.kind);
  if (!kind) {
    throw new Error('Malformed watch-next item: unsupported kind');
  }

  const id = dto.id.trim();
  const title = dto.title.trim();
  if (!id || !title) {
    throw new Error('Malformed watch-next item: missing id or title');
  }

  const parentId = normalizeParentId(kind, dto.parentId);
  if (kind === 'episode' && !parentId) {
    throw new Error('Malformed watch-next item: episode is missing parentId');
  }

  const progressPercent = normalizeProgressPercent(dto.progressPercent);
  const artworkState = normalizeArtworkState(dto.artworkState, dto.posterUrl);

  return {
    id,
    parentId,
    title,
    subtitle: dto.subtitle.trim(),
    kind,
    art: resolveWatchNextArt(dto.posterUrl, artworkState),
    artworkState,
    href: null,
    playable: dto.playable !== false,
    progressPercent,
    year: dto.year ?? null,
    rating: dto.rating ?? null,
    genres: dto.genres ? [...dto.genres] : [],
    overview: dto.overview ?? null,
    runtimeTicks: dto.runtimeTicks ?? null,
    positionTicks: dto.positionTicks ?? null,
    backdropUrl: dto.backdropUrl ?? null,
    thumbUrl: dto.thumbUrl ?? null,
  };
};

export const mapWatchNextResult = (items: MediaStackWatchNextItemDto[]): WatchNextResult => ({
  items: items.map((item) => mapWatchNextItem(item)),
});

function normalizeWatchNextKind(kind: string | undefined): WatchNextKind | null {
  const normalized = kind?.trim().toLowerCase();
  if (normalized === 'movie') return 'movie';
  if (normalized === 'episode') return 'episode';
  return null;
}

function normalizeParentId(kind: WatchNextKind, parentId: string | null | undefined): string | null {
  if (kind === 'movie') {
    if (parentId === null || parentId === undefined || parentId === '') return null;
    throw new Error('Malformed watch-next item: movie parentId must be null');
  }
  const value = parentId?.trim();
  return value || null;
}

function normalizeProgressPercent(value: number): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error('Malformed watch-next item: invalid progressPercent');
  }
  return Math.min(100, Math.max(0, value));
}

function normalizeArtworkState(
  state: LibraryArtworkState | undefined,
  posterUrl: string | undefined,
): LibraryArtworkState {
  if (state === 'failed' || state === 'missing' || state === 'ok') return state;
  return posterUrl?.trim() ? 'ok' : 'missing';
}

function resolveWatchNextArt(posterUrl: string | undefined, artworkState: LibraryArtworkState): string {
  if (artworkState === 'missing' || artworkState === 'failed') return DEFAULT_LIBRARY_ART;
  const value = posterUrl?.trim();
  if (!value) return DEFAULT_LIBRARY_ART;
  if (value.startsWith('url(') || value.includes('gradient(')) return value;
  return `url("${value}") center / cover no-repeat`;
}
