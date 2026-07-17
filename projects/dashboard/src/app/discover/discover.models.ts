export type DiscoverFeedback = 'liked' | 'disliked' | 'watched' | 'skipped';
export type DiscoverMediaType = 'movie' | 'tv';
export type DiscoverSourceTab = 'hermes' | 'jellyseerr' | 'trakt';
export type JellyseerrDiscoverKind = 'trending' | 'movies' | 'tv';
export type TraktDiscoverType = 'movies' | 'shows';

export interface DiscoverItem {
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
  jellyfin_id?: string | null;
  poster_path?: string | null;
  poster_url?: string | null;
  added_at: string;
  notes?: string;
  rating?: number | null;
}

export interface ExternalDiscoverItem {
  id?: string;
  source?: string;
  type: DiscoverMediaType;
  title: string;
  year?: number | null;
  tmdb_id: number;
  overview?: string;
  poster_url?: string | null;
  rating?: number | null;
}

export interface HermesDiscover {
  ok: boolean;
  items: DiscoverItem[];
  pending_request_sync?: { id: string; jellyseerr_request_id: number }[];
  generation_request?: { requested_at: string; status: 'pending' } | null;
  error?: string;
}

export interface ExternalDiscover {
  ok: boolean;
  items: ExternalDiscoverItem[];
  error?: string;
}

export interface DiscoverAction {
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

export interface DiscoverRequestPayload {
  mediaType: DiscoverMediaType;
  mediaId: number;
  hermesId?: string;
  is4k?: boolean;
}
