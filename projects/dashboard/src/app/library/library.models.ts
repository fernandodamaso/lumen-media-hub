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
}

export interface JellyfinLinkBases {
  jellyfinBase?: string;
}

/** Disabled by default; local Demo/live inject bases from environment. */
export const DEFAULT_JELLYFIN_LINK_BASES: Required<JellyfinLinkBases> = {
  jellyfinBase: '',
};

/** Explicit no-op bases for static/Pages builds and tests. */
export const DISABLED_JELLYFIN_LINK_BASES: Required<JellyfinLinkBases> = {
  jellyfinBase: '',
};

export const JELLYFIN_LINK_BASES = new InjectionToken<JellyfinLinkBases>('JELLYFIN_LINK_BASES', {
  providedIn: 'root',
  factory: () => ({ ...DEFAULT_JELLYFIN_LINK_BASES }),
});

export const DEFAULT_LIBRARY_ART =
  'linear-gradient(145deg, color-mix(in srgb, var(--mm-component-accent) 28%, var(--mm-component-card-bg)), var(--mm-component-card-bg) 72%)';

export const resolveJellyfinLibraryLink = (
  kind: LibraryItemKind,
  bases: JellyfinLinkBases = {},
): string | null => {
  const base = (bases.jellyfinBase ?? DEFAULT_JELLYFIN_LINK_BASES.jellyfinBase).replace(/\/$/, '');
  if (!base) return null;
  return `${base}/web/index.html#!/${kind === 'movie' ? 'movies' : 'tv'}.html`;
};

export const resolveJellyfinItemLink = (
  item: Pick<LibraryItem, 'id' | 'playable'>,
  bases: JellyfinLinkBases = {},
): string | null => {
  if (!item.playable || !item.id || item.id === 'unknown') return null;
  const jellyfinBase = (bases.jellyfinBase ?? DEFAULT_JELLYFIN_LINK_BASES.jellyfinBase).replace(/\/$/, '');
  if (!jellyfinBase) return null;
  return `${jellyfinBase}/web/index.html#!/details?id=${encodeURIComponent(item.id)}`;
};

export const formatLibraryMeta = (year: number | undefined, kind: LibraryItemKind): string => {
  const kindLabel = kind === 'movie' ? 'Movie' : 'Series';
  return Number.isFinite(year) && year ? `${year} · ${kindLabel}` : kindLabel;
};
