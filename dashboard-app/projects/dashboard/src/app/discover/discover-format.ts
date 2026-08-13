import {
  DiscoverAction,
  DiscoverFeedback,
  DiscoverItem,
  DiscoverRequestPayload,
  ExternalDiscover,
  ExternalDiscoverItem,
  HermesDiscover,
  TraktHistorySyncState,
  TraktHistorySyncStatus,
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
  excludedReason?: 'in_library' | 'watched_on_trakt' | null;
  watchedOnTrakt?: boolean;
  traktHistorySync?: TraktHistorySyncState | null;
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
    inLibrary: item.in_library || item.excluded_reason === 'in_library',
    excludedReason: item.excluded_reason,
    watchedOnTrakt: item.watched_on_trakt === true,
    traktHistorySync: item.trakt_history_sync ?? null,
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
    watchedOnTrakt: false,
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
  if (filter === 'watched') return item.feedback === 'watched' || item.feedback === 'liked' || item.watched_on_trakt === true;
  return item.feedback === filter;
}

/** Active Hermes browse excludes any title that already has feedback (liked leaves the queue). */
export function isHermesActiveItem(
  item: Pick<DiscoverItem, 'active' | 'feedback' | 'excluded_reason' | 'watched_on_trakt'>,
): boolean {
  return item.active && item.feedback == null && item.excluded_reason !== 'in_library' && item.excluded_reason !== 'watched_on_trakt' && item.watched_on_trakt !== true;
}

/** Liked also counts as watched for pressed UI and history filtering. */
export function isDiscoverFeedbackPressed(
  current: DiscoverFeedback | null,
  option: DiscoverFeedback,
  traktHistorySync?: TraktHistorySyncState | null,
): boolean {
  if (isWatchedFeedbackDisabled({ feedback: current, traktHistorySync }) && option === 'watched') {
    return true;
  }
  if (current === option) return true;
  return option === 'watched' && current === 'liked';
}

export function isWatchedFeedbackDisabled(
  item: Pick<DiscoverCardItem, 'feedback' | 'traktHistorySync'>,
): boolean {
  if (item.feedback === 'watched') return true;
  const status = item.traktHistorySync?.status;
  return status === 'pending' || status === 'synced';
}

export function traktHistorySyncLabel(status: TraktHistorySyncStatus | undefined): string | null {
  switch (status) {
    case 'pending':
      return 'Pending Trakt sync';
    case 'synced':
      return 'Watched on Trakt';
    case 'reconnect_required':
      return 'Trakt reconnect required';
    case 'failed':
      return 'Trakt sync failed';
    default:
      return null;
  }
}

export function traktHistorySyncTone(
  status: TraktHistorySyncStatus | undefined,
): 'info' | 'warning' | 'danger' {
  switch (status) {
    case 'reconnect_required':
    case 'failed':
      return 'danger';
    case 'pending':
      return 'warning';
    default:
      return 'info';
  }
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

const mapDiscoverItem = (dto: MediaStackDiscoverItemDto): DiscoverItem => ({
  id: dto.id,
  source: dto.source,
  type: dto.type,
  title: dto.title,
  year: dto.year,
  tmdb_id: dto.tmdb_id,
  reason: dto.reason,
  active: dto.active,
  feedback: dto.feedback,
  feedback_at: dto.feedback_at,
  request_state: dto.request_state,
  requested_at: dto.requested_at,
  jellyseerr_request_id: dto.jellyseerr_request_id,
  in_library: dto.in_library,
  excluded_reason: dto.excluded_reason,
  watched_on_trakt: dto.watched_on_trakt,
  jellyfin_id: dto.jellyfin_id,
  poster_path: dto.poster_path,
  poster_url: dto.poster_url,
  added_at: dto.added_at,
  notes: dto.notes,
  rating: dto.rating,
  trakt_history_sync: dto.trakt_history_sync ?? null,
});

const mapExternalDiscoverItem = (dto: MediaStackExternalDiscoverItemDto): ExternalDiscoverItem => ({
  ...dto,
});

export const mapHermesDiscover = (dto: MediaStackHermesDiscoverDto): HermesDiscover => ({
  ok: dto.ok,
  items: (dto.items ?? []).map(mapDiscoverItem),
  pending_request_sync: dto.pending_request_sync,
  generation_request: dto.generation_request,
  library_exclusion: dto.library_exclusion,
  watched_exclusion: dto.watched_exclusion,
  error: dto.error,
});

export const mapExternalDiscover = (dto: MediaStackExternalDiscoverDto): ExternalDiscover => ({
  ok: dto.ok,
  items: (dto.items ?? []).map(mapExternalDiscoverItem),
  availability: dto.enabled === false ? 'disabled' : 'available',
  ...(dto.code === 'reconnect_required' ? { code: dto.code } : {}),
  library_exclusion: dto.library_exclusion,
  watched_exclusion: dto.watched_exclusion,
  error: dto.error,
});

export const mapDiscoverAction = (dto: MediaStackDiscoverActionDto): DiscoverAction => {
  const { code, trakt_history_sync, ...rest } = dto;
  return {
    ...rest,
    ...(code === 'reconnect_required' || code === 'confirmation_required' ? { code } : {}),
    ...(trakt_history_sync ? { trakt_history_sync } : {}),
  };
};

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
