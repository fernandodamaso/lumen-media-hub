import { LibraryArtworkState } from './library.models';

export type RecentlyAvailableKind = 'movie' | 'episode';

export interface RecentlyAvailableItem {
  id: string;
  parentId: string | null;
  title: string;
  subtitle: string;
  kind: RecentlyAvailableKind;
  availableAt: string;
  art: string;
  artworkState: LibraryArtworkState;
  thumbUrl: string | null;
  href: string | null;
  playable: true;
  year: number | null;
}

export interface RecentlyAvailableResult {
  items: RecentlyAvailableItem[];
}
