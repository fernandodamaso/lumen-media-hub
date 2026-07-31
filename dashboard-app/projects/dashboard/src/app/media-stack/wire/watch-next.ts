/** Raw Jellyfin watch-next payload stays behind this boundary. */
export interface MediaStackWatchNextItemDto {
  id: string;
  parentId: string | null;
  title: string;
  subtitle: string;
  kind: 'movie' | 'episode';
  posterUrl?: string;
  artworkState?: 'ok' | 'missing' | 'failed';
  playable?: boolean;
  progressPercent: number;
  year?: number | null;
  rating?: number | null;
  genres?: string[];
  overview?: string | null;
  runtimeTicks?: number | null;
  positionTicks?: number | null;
  backdropUrl?: string | null;
  thumbUrl?: string | null;
}
