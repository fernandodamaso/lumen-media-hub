import { ServiceLinkBases } from '../media-stack/media-stack-api.providers';

export interface ServiceCatalogEntry {
  id: keyof ServiceLinkBases | 'sabnzbd';
  name: string;
  initial: string;
  /** Present only in Demo fixtures; omitted from Live shell. */
  demoOnly?: boolean;
}

/** Canonical service list for sidebar navigation (and shared link helpers). */
export const SERVICE_CATALOG: readonly ServiceCatalogEntry[] = [
  { id: 'jellyfin', name: 'Jellyfin', initial: 'J' },
  { id: 'sonarr', name: 'Sonarr', initial: 'S' },
  { id: 'radarr', name: 'Radarr', initial: 'R' },
  { id: 'prowlarr', name: 'Prowlarr', initial: 'P' },
  { id: 'sabnzbd', name: 'SABnzbd', initial: 'S', demoOnly: true },
  { id: 'qbittorrent', name: 'qBittorrent', initial: 'q' },
  { id: 'bazarr', name: 'Bazarr', initial: 'B' },
];

/** Services shown in the app shell for the active API mode. */
export function visibleServiceCatalog(useLiveApi: boolean): ServiceCatalogEntry[] {
  return SERVICE_CATALOG.filter((entry) => !(useLiveApi && entry.demoOnly));
}

/** Build an external service URL from link bases; null when the base is missing. */
export function resolveServiceHref(
  id: string,
  linkBases: ServiceLinkBases,
): string | null {
  const base = linkBases[id as keyof ServiceLinkBases]?.replace(/\/$/, '');
  return base ? `${base}/` : null;
}
