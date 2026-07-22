/** Raw Jellyfin-shaped browse payload stays behind this boundary. */
export interface MediaStackLibraryItemDto {
  id: string;
  title: string;
  kind: string;
  year?: number;
  overview?: string;
  posterUrl?: string;
  artworkState?: 'ok' | 'missing' | 'failed';
  playable?: boolean;
  rating?: number | null;
}

/** Aggregate library counts derived from Jellyfin movie/series list responses. */
export interface MediaStackLibraryStatsDto {
  ok?: boolean;
  /** Required finite counts when ok:true — missing must not coerce to 0 as success. */
  movies: number;
  series: number;
  error?: string;
}
