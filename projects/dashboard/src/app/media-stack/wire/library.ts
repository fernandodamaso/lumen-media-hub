/** Raw Jellyfin-shaped browse payload stays behind this boundary. */
export interface MediaStackLibraryItemDto {
  id: string;
  title: string;
  kind: 'movie' | 'series' | string;
  year?: number;
  overview?: string;
  posterUrl?: string;
  artworkState?: 'ok' | 'missing' | 'failed';
  playable?: boolean;
  rating?: number | null;
}

/** Raw library stats payload from GET /jellyfin/stats. */
export interface MediaStackLibraryStatsDto {
  ok?: boolean;
  /** Required finite counts when ok:true — missing must not coerce to 0 as success. */
  movies: number;
  series: number;
  error?: string;
}
