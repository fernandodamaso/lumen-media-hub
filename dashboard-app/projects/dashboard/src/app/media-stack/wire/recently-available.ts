export interface MediaStackRecentlyAvailableItemDto {
  id: string;
  parentId: string | null;
  title: string;
  subtitle: string;
  kind: 'movie' | 'episode';
  availableAt: string;
  posterUrl?: string;
  artworkState?: 'ok' | 'missing' | 'failed';
  thumbUrl: string | null;
  playable: true;
  year: number | null;
}
