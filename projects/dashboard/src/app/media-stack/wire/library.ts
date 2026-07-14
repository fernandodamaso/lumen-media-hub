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
