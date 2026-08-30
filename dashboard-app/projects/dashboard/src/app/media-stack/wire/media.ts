type MediaStackMediaTypeDto = 'movie' | 'tv';
type MediaStackMediaStatusDto =
  | 'available'
  | 'requested'
  | 'processing'
  | 'tracked'
  | 'missing'
  | 'unknown';
type MediaStackMediaServiceDto = 'jellyfin' | 'radarr' | 'sonarr' | null;
type MediaStackSourceHealthDto = 'fresh' | 'stale' | 'unavailable' | 'disabled';

export interface MediaStackMediaSearchItemDto {
  identity: string;
  type: MediaStackMediaTypeDto;
  tmdbId: number;
  title: string;
  year: number | null;
  overview: string;
  posterUrl: string | null;
  status: MediaStackMediaStatusDto;
  service: MediaStackMediaServiceDto;
  serviceHref: string | null;
  requestId: number | null;
  monitored: boolean | null;
  jellyfinId?: string;
}

export interface MediaStackMediaSearchDto {
  ok: boolean;
  availability: 'available' | 'disabled' | 'unavailable';
  sources: Partial<
    Record<'jellyseerr' | 'jellyfin' | 'radarr' | 'sonarr', MediaStackSourceHealthDto>
  >;
  items: MediaStackMediaSearchItemDto[];
  error?: string;
}

export interface MediaStackTvSeasonDto {
  seasonNumber: number;
  name: string;
  episodeCount: number;
  airDate: string | null;
}

export interface MediaStackTvSeasonCollectionDto {
  ok: true;
  tmdbId: number;
  title: string;
  seasons: MediaStackTvSeasonDto[];
}

export interface MediaStackMediaRequestActionDto {
  ok: boolean;
  error?: string;
  partial_success?: boolean;
  jellyseerr_request_id?: number;
  request_status?: 'requested' | 'processing';
  already_requested?: boolean;
  dashboard_state_persisted?: boolean;
  reconciliation_queued?: boolean;
  message?: string;
}
