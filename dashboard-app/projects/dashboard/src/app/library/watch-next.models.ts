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
  /** Series year for episodes (series identity), else item year. */
  year: number | null;
  rating: number | null;
  genres: string[];
  overview: string | null;
  runtimeTicks: number | null;
  positionTicks: number | null;
  /** Backdrop art URL; null when the item/series has no backdrop. */
  backdropUrl: string | null;
  thumbUrl: string | null;
}

export interface WatchNextResult {
  items: WatchNextItem[];
}
