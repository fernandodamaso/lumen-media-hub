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
}
