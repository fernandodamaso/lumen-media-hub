import { LibraryArtworkState } from './library.models';

export type WatchNextKind = 'movie' | 'episode';

export interface WatchNextItem {
  /** Playable Jellyfin movie or episode ID. */
  id: string;
  /** Parent series ID for episodes; null for movies. */
  parentId: string | null;
  /** Movie title or series title. */
  title: string;
  /** Episode metadata, e.g. "S02E05 · The Long Night". */
  subtitle: string;
  kind: WatchNextKind;
  art: string;
  artworkState: LibraryArtworkState;
  href: string | null;
  playable: boolean;
  /** Normalized inclusive percentage from 0 to 100. */
  progressPercent: number;
}

export interface WatchNextResult {
  items: WatchNextItem[];
}
