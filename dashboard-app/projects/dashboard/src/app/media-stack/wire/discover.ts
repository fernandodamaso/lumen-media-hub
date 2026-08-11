export type MediaStackDiscoverFeedbackDto = 'liked' | 'disliked' | 'watched' | 'skipped';
export type MediaStackDiscoverMediaTypeDto = 'movie' | 'tv';
type MediaStackLibraryExclusionStatusDto = 'fresh' | 'stale' | 'unavailable';

interface MediaStackLibraryExclusionDto {
  status: MediaStackLibraryExclusionStatusDto;
  last_successful_refresh_at: string | null;
}

export interface MediaStackDiscoverItemDto {
  id: string;
  source: string;
  type: MediaStackDiscoverMediaTypeDto;
  title: string;
  year?: number | null;
  tmdb_id: number;
  reason?: string;
  active: boolean;
  feedback: MediaStackDiscoverFeedbackDto | null;
  feedback_at: string | null;
  request_state: 'requested' | null;
  requested_at: string | null;
  jellyseerr_request_id: number | null;
  in_library?: boolean;
  excluded_reason?: 'in_library' | null;
  jellyfin_id?: string | null;
  poster_path?: string | null;
  poster_url?: string | null;
  added_at: string;
  notes?: string;
  rating?: number | null;
}

export interface MediaStackExternalDiscoverItemDto {
  id?: string;
  source?: string;
  type: MediaStackDiscoverMediaTypeDto;
  title: string;
  year?: number | null;
  tmdb_id: number;
  trakt_slug?: string | null;
  overview?: string;
  poster_url?: string | null;
  rating?: number | null;
}

export interface MediaStackHermesDiscoverDto {
  ok: boolean;
  items?: MediaStackDiscoverItemDto[];
  pending_request_sync?: { id: string; jellyseerr_request_id: number }[];
  generation_request?: { requested_at: string; status: 'pending' } | null;
  library_exclusion?: MediaStackLibraryExclusionDto;
  error?: string;
}

export interface MediaStackExternalDiscoverDto {
  ok: boolean;
  /** False is an explicit capability-disabled response, not an empty result. */
  enabled?: boolean;
  items?: MediaStackExternalDiscoverItemDto[];
  library_exclusion?: MediaStackLibraryExclusionDto;
  error?: string;
}

export interface MediaStackDiscoverActionDto {
  ok: boolean;
  error?: string;
  message?: string;
  partial_success?: boolean;
  jellyseerr_request_id?: number | null;
  dashboard_state_persisted?: boolean;
  reconciliation_queued?: boolean;
  queued?: boolean;
  already_pending?: boolean;
  requested_at?: string;
}

export interface MediaStackDiscoverRequestPayloadDto {
  mediaType: MediaStackDiscoverMediaTypeDto;
  mediaId: number;
  hermesId?: string;
  is4k?: boolean;
}
