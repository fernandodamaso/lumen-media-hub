import { InjectionToken } from '@angular/core';

export type LibraryItemKind = 'movie' | 'series';
export type LibraryArtworkState = 'ok' | 'missing' | 'failed';

export interface LibraryItem {
  id: string;
  title: string;
  kind: LibraryItemKind;
  meta: string;
  art: string;
  overview: string;
  href: string | null;
  artworkState: LibraryArtworkState;
  playable: boolean;
  rating?: number | null;
  episodeCount: number | null;
  played: boolean;
}

export interface LibraryDeletePreview {
  previewId: string;
  title: string;
  kind: LibraryItemKind;
  manager: 'Radarr' | 'Sonarr';
  episodeCount: number | null;
  torrentCount: number;
  expiresAt: string;
}

export interface DirectDeleteResult {
  ok: boolean;
  removed: boolean;
  mode: 'jellyfin-direct';
  title?: string | null;
}

export type LibraryDeleteStepStatus = 'ok' | 'skipped' | 'failed' | 'pending';

export interface LibraryDeleteSteps {
  torrents: LibraryDeleteStepStatus;
  library: LibraryDeleteStepStatus;
  jellyfin: LibraryDeleteStepStatus;
}

export interface LibraryDeleteResult {
  ok: boolean;
  removed: boolean;
  torrentCount: number;
  jellyfinRefresh?: 'ok' | 'pending';
  warning?: string | null;
  partial?: boolean;
  error?: string;
  steps?: LibraryDeleteSteps;
}

export interface LibraryDeleteToast {
  title: string;
  body?: string;
  tone: 'success' | 'gold' | 'error';
}

/** Unfiltered movies+series aggregation can be complete or one-source partial. */
type LibraryAvailability = 'complete' | 'partial';

export interface LibraryStats {
  movies: number;
  series: number;
  /** Always `complete` for the dedicated stats endpoint; partial applies to list aggregation. */
  availability: LibraryAvailability;
}

/** Result of listing library items — exposes partial when one Jellyfin kind fails. */
export interface LibraryListResult {
  items: LibraryItem[];
  availability: LibraryAvailability;
  /** Authoritative movie total when the API reports more than the returned page. */
  movieCount?: number;
  /** Authoritative series total when the API reports more than the returned page. */
  seriesCount?: number;
}

export interface JellyfinLinkBases {
  jellyfinBase?: string;
}

/** Disabled by default; local Demo/live inject bases from environment. */
const DEFAULT_JELLYFIN_LINK_BASES: Required<JellyfinLinkBases> = {
  jellyfinBase: '',
};

/** Explicit no-op bases for tests and link-disabled states. */
export const JELLYFIN_LINK_BASES = new InjectionToken<JellyfinLinkBases>('JELLYFIN_LINK_BASES', {
  providedIn: 'root',
  factory: () => ({ ...DEFAULT_JELLYFIN_LINK_BASES }),
});

export const DEFAULT_LIBRARY_ART =
  'linear-gradient(145deg, color-mix(in srgb, var(--mm-component-accent) 28%, var(--mm-component-card-bg)), var(--mm-component-card-bg) 72%)';

export const resolveJellyfinItemLink = (
  item: Pick<LibraryItem, 'id' | 'playable'>,
  bases: JellyfinLinkBases = {},
): string | null => {
  if (!item.playable || !item.id || item.id === 'unknown') return null;
  const jellyfinBase = (bases.jellyfinBase ?? DEFAULT_JELLYFIN_LINK_BASES.jellyfinBase).replace(/\/$/, '');
  if (!jellyfinBase) return null;
  return `${jellyfinBase}/web/index.html#!/details?id=${encodeURIComponent(item.id)}`;
};

export const formatLibraryMeta = (
  year: number | undefined,
  kind: LibraryItemKind,
  episodeCount?: number | null,
): string => {
  const kindLabel = kind === 'movie' ? 'Movie' : 'Series';
  const base =
    Number.isFinite(year) && year ? `${year} · ${kindLabel}` : kindLabel;
  if (kind !== 'series' || episodeCount == null || !Number.isFinite(episodeCount)) {
    return base;
  }
  const count = Math.floor(episodeCount);
  const episodeLabel = count === 1 ? '1 episode' : `${count} episodes`;
  return `${base} · ${episodeLabel}`;
};

export interface LibraryDeleteDialogCopy {
  title: string;
  rest: string;
}

export const formatLibraryDeleteDialogCopy = (
  preview: LibraryDeletePreview,
): LibraryDeleteDialogCopy => {
  const torrentWord = preview.torrentCount === 1 ? 'torrent' : 'torrents';
  if (preview.kind === 'series') {
    const episodeWord = preview.episodeCount === 1 ? 'episode' : 'episodes';
    const episodePart =
      preview.episodeCount != null && Number.isFinite(preview.episodeCount)
        ? ` (${preview.episodeCount} ${episodeWord})`
        : '';
    const title = `${preview.title}${episodePart}`;
    if (preview.torrentCount > 0) {
      return {
        title,
        rest: ` from Sonarr and delete ${preview.torrentCount} matching ${torrentWord} from qBittorrent.`,
      };
    }
    return {
      title,
      rest: ' from Sonarr. No matching torrents are currently in qBittorrent.',
    };
  }
  if (preview.torrentCount > 0) {
    return {
      title: preview.title,
      rest: ` from Radarr and delete ${preview.torrentCount} matching ${torrentWord} from qBittorrent.`,
    };
  }
  return {
    title: preview.title,
    rest: ' from Radarr. No matching torrents are currently in qBittorrent.',
  };
};

export const formatLibraryDeleteDialogBody = (preview: LibraryDeletePreview): string => {
  const copy = formatLibraryDeleteDialogCopy(preview);
  return `This will remove ${copy.title}${copy.rest}`;
};

export const formatLibraryDeleteToasts = (
  result: LibraryDeleteResult,
  preview: Pick<LibraryDeletePreview, 'title' | 'manager'>,
): LibraryDeleteToast[] => {
  const steps = result.steps;
  if (result.partial || steps?.library === 'failed') {
    const torrentsRemoved =
      steps?.torrents === 'ok' || (steps == null && result.torrentCount > 0);
    return [
      {
        title: torrentsRemoved
          ? 'Removed torrents; library item remains'
          : 'Could not remove library item',
        body: `${preview.manager} did not remove this title.`,
        tone: 'error',
      },
    ];
  }
  if (result.removed) {
    const toasts: LibraryDeleteToast[] = [
      {
        title: `Removed ${preview.title}`,
        body:
          steps?.torrents === 'ok'
            ? `Deleted from ${preview.manager} and qBittorrent.`
            : `Deleted from ${preview.manager}.`,
        tone: 'success',
      },
    ];
    if (result.warning || steps?.jellyfin === 'pending') {
      toasts.push({
        title: result.warning?.trim() || 'Removed; Jellyfin refresh pending',
        tone: 'gold',
      });
    }
    return toasts;
  }
  if (steps?.torrents === 'failed') {
    return [
      {
        title: 'Could not delete this title',
        body: 'Matching torrents were not removed.',
        tone: 'error',
      },
    ];
  }
  const error = result.error?.trim();
  return [{ title: error || 'Could not delete this title', tone: 'error' }];
};
