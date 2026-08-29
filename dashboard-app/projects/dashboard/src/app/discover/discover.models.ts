import { MediaLifecycleService, MediaLifecycleStatus } from '../media-request/media-request.models';

export type DiscoverFeedback = 'liked' | 'disliked' | 'watched' | 'skipped';
export type TraktHistorySyncStatus = 'pending' | 'synced' | 'reconnect_required' | 'failed';
type DiscoverMediaType = 'movie' | 'tv';
export type DiscoverSourceTab = 'hermes' | 'jellyseerr' | 'trakt';
export type JellyseerrDiscoverKind = 'trending' | 'movies' | 'tv';
export type TraktDiscoverType = 'movies' | 'shows';
type LibraryExclusionStatus = 'fresh' | 'stale' | 'unavailable';

export interface LibraryExclusionState {
  status: LibraryExclusionStatus;
  last_successful_refresh_at: string | null;
}

export interface TraktHistorySyncState {
  status: TraktHistorySyncStatus;
}

interface DiscoverLifecycleState {
  media_status?: MediaLifecycleStatus;
  service?: MediaLifecycleService;
  service_href?: string | null;
  request_id?: number | null;
  monitored?: boolean | null;
}

export interface DiscoverItem extends DiscoverLifecycleState {
  id: string;
  source: string;
  type: DiscoverMediaType;
  title: string;
  year?: number | null;
  tmdb_id: number;
  reason?: string;
  active: boolean;
  feedback: DiscoverFeedback | null;
  feedback_at: string | null;
  request_state: 'requested' | null;
  requested_at: string | null;
  jellyseerr_request_id: number | null;
  in_library?: boolean;
  excluded_reason?: 'in_library' | 'watched_on_trakt' | null;
  watched_on_trakt?: boolean;
  jellyfin_id?: string | null;
  poster_path?: string | null;
  poster_url?: string | null;
  added_at: string;
  notes?: string;
  rating?: number | null;
  trakt_history_sync?: TraktHistorySyncState | null;
}

export interface ExternalDiscoverItem extends DiscoverLifecycleState {
  id?: string;
  source?: string;
  type: DiscoverMediaType;
  title: string;
  year?: number | null;
  tmdb_id: number;
  trakt_slug?: string | null;
  overview?: string;
  poster_url?: string | null;
  rating?: number | null;
}

export type ExternalDiscoverAvailability = 'available' | 'disabled';
type WatchedExclusionStatus = 'fresh' | 'stale' | 'unavailable';

export interface WatchedExclusionState {
  status: WatchedExclusionStatus;
  last_successful_refresh_at: string | null;
}

export interface HermesDiscover {
  ok: boolean;
  items: DiscoverItem[];
  pending_request_sync?: { id: string; jellyseerr_request_id: number }[];
  generation_request?: { requested_at: string; status: 'pending' } | null;
  error?: string;
  library_exclusion?: LibraryExclusionState;
  watched_exclusion?: WatchedExclusionState;
}

export interface ExternalDiscover {
  ok: boolean;
  items: ExternalDiscoverItem[];
  availability?: ExternalDiscoverAvailability;
  code?: 'reconnect_required';
  error?: string;
  library_exclusion?: LibraryExclusionState;
  watched_exclusion?: WatchedExclusionState;
}

export interface DiscoverAction {
  ok: boolean;
  code?: 'reconnect_required' | 'confirmation_required';
  error?: string;
  message?: string;
  partial_success?: boolean;
  jellyseerr_request_id?: number | null;
  dashboard_state_persisted?: boolean;
  reconciliation_queued?: boolean;
  request_status?: 'requested' | 'processing';
  already_requested?: boolean;
  queued?: boolean;
  already_pending?: boolean;
  requested_at?: string;
  trakt_history_sync?: TraktHistorySyncState | null;
}

export interface SubmitHermesFeedbackOptions {
  notes?: string;
  confirmAllAired?: boolean;
}

export interface DiscoverRequestPayload {
  mediaType: DiscoverMediaType;
  mediaId: number;
  hermesId?: string;
  is4k?: boolean;
  seasons?: number[] | 'all';
}
