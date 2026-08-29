type MediaType = 'movie' | 'tv';
export type MediaLifecycleStatus =
  | 'available'
  | 'requested'
  | 'processing'
  | 'tracked'
  | 'missing'
  | 'unknown';
export type MediaLifecycleService = 'jellyfin' | 'radarr' | 'sonarr' | null;
export type MediaSourceHealth = 'fresh' | 'stale' | 'unavailable' | 'disabled';
type MediaSearchAvailability = 'available' | 'disabled' | 'unavailable';

export interface MediaSearchItem {
  identity: string;
  type: MediaType;
  tmdbId: number;
  title: string;
  year: number | null;
  overview: string;
  posterUrl: string | null;
  status: MediaLifecycleStatus;
  service: MediaLifecycleService;
  serviceHref: string | null;
  requestId: number | null;
  monitored: boolean | null;
  jellyfinId?: string;
}

export interface MediaSearchResult {
  ok: boolean;
  availability: MediaSearchAvailability;
  sources: Partial<Record<'jellyseerr' | 'jellyfin' | 'radarr' | 'sonarr', MediaSourceHealth>>;
  items: MediaSearchItem[];
  error?: string;
}

export interface TvSeason {
  seasonNumber: number;
  name: string;
  episodeCount: number;
  airDate: string | null;
}

export interface TvSeasonCollection {
  tmdbId: number;
  title: string;
  seasons: TvSeason[];
}

export interface RequestableMediaItem {
  identity: string;
  type: MediaType;
  tmdbId: number;
  title: string;
  year?: number | null;
  posterUrl?: string | null;
  hermesId?: string;
}
