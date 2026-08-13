import { DEFAULT_LIBRARY_ART, LibraryArtworkState } from './library.models';
import {
  RecentlyAvailableItem,
  RecentlyAvailableKind,
  RecentlyAvailableResult,
} from './recently-available.models';
import {
  MediaStackRecentlyAvailableItemDto,
} from '../media-stack/wire/recently-available';

const MINUTE_MS = 60_000;
const HOUR_MS = 60 * MINUTE_MS;
const DAY_MS = 24 * HOUR_MS;
const FUTURE_SKEW_MS = 5 * MINUTE_MS;

const UTC_SHORT_DATE = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  timeZone: 'UTC',
});

export const mapRecentlyAvailableItem = (
  dto: MediaStackRecentlyAvailableItemDto,
): RecentlyAvailableItem => {
  const kind = normalizeKind(dto.kind);
  if (!kind) {
    throw new Error('Malformed recently-available item: unsupported kind');
  }

  const id = dto.id.trim();
  const title = dto.title.trim();
  if (!id || !title) {
    throw new Error('Malformed recently-available item: missing id or title');
  }

  const parentId = normalizeParentId(kind, dto.parentId);
  if (kind === 'episode' && !parentId) {
    throw new Error('Malformed recently-available item: episode is missing parentId');
  }

  const availableAt = dto.availableAt.trim();
  if (!availableAt) {
    throw new Error('Malformed recently-available item: missing availableAt');
  }

  const artworkState = normalizeArtworkState(dto.artworkState, dto.posterUrl);

  return {
    id,
    parentId,
    title,
    subtitle: dto.subtitle.trim(),
    kind,
    availableAt,
    art: resolveArt(dto.posterUrl, artworkState),
    artworkState,
    thumbUrl: dto.thumbUrl ?? null,
    href: null,
    playable: true,
    year: dto.year ?? null,
  };
};

export const mapRecentlyAvailableResult = (
  items: MediaStackRecentlyAvailableItemDto[],
): RecentlyAvailableResult => ({
  items: [...items]
    .map((item) => mapRecentlyAvailableItem(item))
    .sort((a, b) => Date.parse(b.availableAt) - Date.parse(a.availableAt)),
});

export function formatAvailableAge(availableAt: string, now: Date): string {
  const parsed = Date.parse(availableAt);
  if (!Number.isFinite(parsed)) {
    return 'Ready time unavailable';
  }
  const ageMs = now.getTime() - parsed;
  if (ageMs < -FUTURE_SKEW_MS) {
    return 'Ready time unavailable';
  }
  if (ageMs < MINUTE_MS) {
    return 'Ready now';
  }
  if (ageMs < HOUR_MS) {
    return `Ready ${Math.floor(ageMs / MINUTE_MS)}m ago`;
  }
  if (ageMs < DAY_MS) {
    return `Ready ${Math.floor(ageMs / HOUR_MS)}h ago`;
  }
  if (ageMs < 2 * DAY_MS) {
    return 'Ready yesterday';
  }
  if (ageMs < 7 * DAY_MS) {
    return `Ready ${Math.floor(ageMs / DAY_MS)}d ago`;
  }
  return `Ready ${UTC_SHORT_DATE.format(new Date(parsed))}`;
}

export function isNewlyAvailable(availableAt: string, now: Date): boolean {
  const parsed = Date.parse(availableAt);
  if (!Number.isFinite(parsed)) {
    return false;
  }
  const ageMs = now.getTime() - parsed;
  return ageMs >= -FUTURE_SKEW_MS && ageMs < DAY_MS;
}

export function formatRecentlyAvailableCardSubtitle(
  item: RecentlyAvailableItem,
  now: Date,
): string {
  const readiness = formatAvailableAge(item.availableAt, now);
  if (item.kind === 'episode') {
    return `${item.subtitle} · ${readiness}`;
  }
  const yearPrefix = item.year ? `${item.year} · ` : '';
  return `${yearPrefix}Movie · ${readiness}`;
}

export function recentlyAvailableLinkLabel(item: RecentlyAvailableItem): string {
  if (item.kind === 'episode') {
    const spokenSubtitle = item.subtitle.split('·').map((part) => part.trim()).join(', ');
    return `Open ${item.title}, ${spokenSubtitle} in Jellyfin`;
  }
  if (item.year) {
    return `Open ${item.title}, ${item.year} in Jellyfin`;
  }
  return `Open ${item.title} in Jellyfin`;
}

function normalizeKind(kind: string | undefined): RecentlyAvailableKind | null {
  const normalized = kind?.trim().toLowerCase();
  if (normalized === 'movie') return 'movie';
  if (normalized === 'episode') return 'episode';
  return null;
}

function normalizeParentId(
  kind: RecentlyAvailableKind,
  parentId: string | null | undefined,
): string | null {
  if (kind === 'movie') {
    if (parentId === null || parentId === undefined || parentId === '') return null;
    throw new Error('Malformed recently-available item: movie parentId must be null');
  }
  const value = parentId?.trim();
  return value || null;
}

function normalizeArtworkState(
  state: LibraryArtworkState | undefined,
  posterUrl: string | undefined,
): LibraryArtworkState {
  if (state === 'failed' || state === 'missing' || state === 'ok') return state;
  return posterUrl?.trim() ? 'ok' : 'missing';
}

function resolveArt(posterUrl: string | undefined, artworkState: LibraryArtworkState): string {
  if (artworkState === 'missing' || artworkState === 'failed') return DEFAULT_LIBRARY_ART;
  const value = posterUrl?.trim();
  if (!value) return DEFAULT_LIBRARY_ART;
  if (value.startsWith('url(') || value.includes('gradient(')) return value;
  return `url("${value}") center / cover no-repeat`;
}
