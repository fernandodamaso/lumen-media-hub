import {
  DiscoverAction,
  DiscoverFeedback,
  DiscoverItem,
  DiscoverRequestPayload,
  ExternalDiscover,
  ExternalDiscoverItem,
  HermesDiscover,
} from './discover.models';
import {
  MediaStackDiscoverActionDto,
  MediaStackDiscoverItemDto,
  MediaStackDiscoverRequestPayloadDto,
  MediaStackExternalDiscoverDto,
  MediaStackExternalDiscoverItemDto,
  MediaStackHermesDiscoverDto,
} from '../media-stack/wire/discover';

export type DiscoverHistoryFilter = 'all' | DiscoverFeedback | 'requested';

export type DiscoverRequestAction = {
  label: string;
  title: string;
  disabled: boolean;
  syncFailed?: boolean;
};

export type DiscoverCardItem = {
  id: string;
  title: string;
  year?: number | null;
  type: 'movie' | 'tv';
  tmdbId: number;
  hermesId?: string;
  reason?: string;
  overview?: string;
  feedback: DiscoverFeedback | null;
  requestState: 'requested' | null;
  inLibrary: boolean;
  excludedReason?: 'in_library' | null;
  posterUrl?: string | null;
  rating?: number | null;
};

export function toHermesCardItem(item: DiscoverItem): DiscoverCardItem {
  return {
    id: item.id,
    title: item.title,
    year: item.year,
    type: item.type,
    tmdbId: item.tmdb_id,
    hermesId: item.id,
    reason: item.reason,
    feedback: item.feedback,
    requestState: item.request_state,
    inLibrary: Boolean(item.in_library),
    excludedReason: item.excluded_reason,
    posterUrl: item.poster_url,
    rating: item.rating,
  };
}

export function mediaIdentityKey(type: DiscoverCardItem['type'], tmdbId: number): string {
  return `${type}:${tmdbId}`;
}

export function toExternalCardItem(
  item: ExternalDiscoverItem,
  source: string,
  requestedKeys: ReadonlySet<string> = new Set(),
): DiscoverCardItem {
  const requestState = requestedKeys.has(mediaIdentityKey(item.type, item.tmdb_id)) ? 'requested' : null;
  return {
    id: item.id ?? `${source}-${item.type}-${item.tmdb_id}`,
    title: item.title,
    year: item.year,
    type: item.type,
    tmdbId: item.tmdb_id,
    overview: item.overview,
    feedback: null,
    requestState,
    inLibrary: false,
    posterUrl: item.poster_url,
    rating: item.rating,
  };
}

export function resolveRequestAction(
  item: Pick<DiscoverCardItem, 'tmdbId' | 'requestState' | 'inLibrary'>,
  options: { syncFailed?: boolean } = {},
): DiscoverRequestAction {
  if (!item.tmdbId) {
    return {
      label: 'No TMDB ID',
      title: 'Cannot request — missing TMDB id',
      disabled: true,
    };
  }
  if (options.syncFailed) {
    return {
      label: 'Added (sync failed)',
      title: 'Added to Sonarr/Radarr; dashboard synchronization failed.',
      disabled: true,
      syncFailed: true,
    };
  }
  if (item.requestState === 'requested') {
    return {
      label: 'Requested',
      title: 'Already added to Sonarr/Radarr',
      disabled: true,
    };
  }
  if (item.inLibrary) {
    return {
      label: 'In library',
      title: 'Already in your Jellyfin library',
      disabled: true,
    };
  }
  return {
    label: 'Request',
    title: 'Add to Sonarr/Radarr without monitoring or downloading',
    disabled: false,
  };
}

export function matchesHistoryFilter(item: DiscoverItem, filter: DiscoverHistoryFilter): boolean {
  if (filter === 'all') return true;
  if (filter === 'requested') return item.request_state === 'requested';
  if (filter === 'watched') return item.feedback === 'watched' || item.feedback === 'liked';
  return item.feedback === filter;
}

/** Active Hermes browse excludes any title that already has feedback (liked leaves the queue). */
export function isHermesActiveItem(
  item: Pick<DiscoverItem, 'active' | 'feedback' | 'excluded_reason'>,
): boolean {
  return item.active && item.feedback == null && item.excluded_reason !== 'in_library';
}

/** Liked also counts as watched for pressed UI and history filtering. */
export function isDiscoverFeedbackPressed(
  current: DiscoverFeedback | null,
  option: DiscoverFeedback,
): boolean {
  if (current === option) return true;
  return option === 'watched' && current === 'liked';
}

export function discoverPosterFallback(title: string): string {
  const hue = hashHue(title);
  return `linear-gradient(145deg, hsl(${hue} 42% 42%), var(--mm-component-card-bg) 70%)`;
}

export function matchesDiscoverSearch(
  item: Pick<DiscoverCardItem, 'title' | 'year' | 'reason' | 'overview'>,
  query: string,
): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  const haystacks = [
    item.title,
    item.year != null ? String(item.year) : '',
    item.reason ?? '',
    item.overview ?? '',
  ];
  return haystacks.some((part) => part.toLowerCase().includes(needle));
}

const mapDiscoverItem = (dto: MediaStackDiscoverItemDto): DiscoverItem => ({ ...dto });

const mapExternalDiscoverItem = (dto: MediaStackExternalDiscoverItemDto): ExternalDiscoverItem => ({
  ...dto,
});

export const mapHermesDiscover = (dto: MediaStackHermesDiscoverDto): HermesDiscover => ({
  ok: dto.ok,
  items: (dto.items ?? []).map(mapDiscoverItem),
  pending_request_sync: dto.pending_request_sync,
  generation_request: dto.generation_request,
  library_exclusion: dto.library_exclusion,
  error: dto.error,
});

export const mapExternalDiscover = (dto: MediaStackExternalDiscoverDto): ExternalDiscover => ({
  ok: dto.ok,
  items: (dto.items ?? []).map(mapExternalDiscoverItem),
  availability: dto.enabled === false ? 'disabled' : 'available',
  library_exclusion: dto.library_exclusion,
  error: dto.error,
});

export const mapDiscoverAction = (dto: MediaStackDiscoverActionDto): DiscoverAction => ({ ...dto });

export const toDiscoverRequestPayloadDto = (
  payload: DiscoverRequestPayload,
): MediaStackDiscoverRequestPayloadDto => ({ ...payload });

export function formatDiscoverMeta(item: Pick<DiscoverCardItem, 'year' | 'type' | 'rating'>): string {
  const parts = [item.year ? String(item.year) : null, item.type === 'tv' ? 'TV' : 'Movie', item.rating != null ? `${item.rating.toFixed(1)}★` : null].filter(
    Boolean,
  );
  return parts.join(' · ');
}

function hashHue(value: string): number {
  let hash = 0;
  for (let index = 0; index < value.length; index++) {
    hash = (hash * 31 + value.charCodeAt(index)) % 360;
  }
  return hash;
}
