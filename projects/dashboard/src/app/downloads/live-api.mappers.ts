import {
  LibraryItemKind,
  MediaStackAutomationPreviewItemDto,
  MediaStackAutomationProblemDto,
  MediaStackAutomationServiceDto,
  MediaStackAutomationSummaryDto,
  MediaStackLibraryItemDto,
  MediaStackTorrentDto,
} from './media-stack-api';

/** Raw qBittorrent payload from GET /qbt/torrents. */
export interface LiveQbtTorrent {
  hash?: string;
  name?: string;
  state?: string;
  progress?: number;
  size?: number;
  total_size?: number;
  amount_left?: number;
  dlspeed?: number;
  upspeed?: number;
  eta?: number;
  category?: string;
}

/** Jellyfin list item from GET /jellyfin/movies|series. */
export interface LiveJellyfinItem {
  name?: string;
  year?: number | null;
  id?: string;
  image?: string | null;
  rating?: number | null;
}

export interface LiveJellyfinListResponse {
  ok?: boolean;
  total?: number;
  items?: LiveJellyfinItem[];
  error?: string;
}

export interface LiveAutomationPreviewItem {
  label?: string;
  airDate?: string;
  status?: string;
  timeleft?: string;
  error?: string;
  warning?: boolean;
  href?: string | null;
  titleSlug?: string;
  seriesId?: number;
}

export interface LiveAutomationServiceBlock {
  ok?: boolean;
  series?: number;
  movies?: number;
  monitored?: number;
  queued?: number;
  missing?: number;
  missingItems?: LiveAutomationPreviewItem[];
  queueItems?: LiveAutomationPreviewItem[];
  indexers?: number;
  enabled?: number;
  disabled?: { name: string }[];
  cooldown?: { name: string; until?: string; reason?: string }[];
  wanted?: number;
  wantedEpisodes?: number;
  wantedMovies?: number;
  wantedItems?: LiveAutomationPreviewItem[];
  error?: string;
}

/** Nested automation summary from GET /automation/summary (React contract). */
export interface LiveAutomationSummary {
  ok?: boolean;
  sonarr?: LiveAutomationServiceBlock;
  radarr?: LiveAutomationServiceBlock;
  prowlarr?: LiveAutomationServiceBlock;
  bazarr?: LiveAutomationServiceBlock;
  generatedAt?: string;
  error?: string;
}

export function mapLiveTorrent(raw: LiveQbtTorrent, index = 0): MediaStackTorrentDto {
  const size = Number(raw.size ?? raw.total_size);
  const progress = Number(raw.progress);
  const amountLeft = Number(raw.amount_left);
  const safeSize = Number.isFinite(size) ? size : 0;
  const safeProgress = Number.isFinite(progress) ? progress : 0;
  const downloaded = Number.isFinite(amountLeft)
    ? Math.max(0, safeSize - amountLeft)
    : Math.max(0, safeSize * safeProgress);

  return {
    hash: raw.hash ? String(raw.hash) : `missing-hash-${index}`,
    name: raw.name ? String(raw.name) : 'Unknown torrent',
    state: typeof raw.state === 'string' ? raw.state : 'unknown',
    progress: safeProgress,
    size: safeSize,
    downloaded,
    dlspeed: Number(raw.dlspeed) || 0,
    upspeed: Number(raw.upspeed) || 0,
    eta: Number(raw.eta) || 0,
    category: raw.category ? String(raw.category) : undefined,
  };
}

export function mapLiveJellyfinItem(
  item: LiveJellyfinItem,
  kind: LibraryItemKind,
): MediaStackLibraryItemDto {
  const posterUrl = item.image ? String(item.image) : undefined;
  return {
    id: item.id ? String(item.id) : '',
    title: item.name ? String(item.name) : 'Untitled',
    kind,
    year: item.year == null ? undefined : Number(item.year) || undefined,
    posterUrl,
    artworkState: posterUrl ? 'ok' : 'missing',
    playable: true,
    rating: item.rating,
  };
}

function serviceStatus(
  block: LiveAutomationServiceBlock | undefined,
  degraded: boolean,
): string {
  if (!block) return 'unknown';
  if (block.ok === false || block.error) return 'down';
  if (degraded) return 'degraded';
  return 'healthy';
}

function sonarrDetail(block: LiveAutomationServiceBlock | undefined): string {
  if (!block) return 'No data';
  if (block.error) return block.error;
  return `${block.missing ?? 0} missing · ${block.monitored ?? 0} shows · ${block.queued ?? 0} queued`;
}

function radarrDetail(block: LiveAutomationServiceBlock | undefined): string {
  if (!block) return 'No data';
  if (block.error) return block.error;
  return `${block.missing ?? 0} missing · ${block.movies ?? 0} movies · ${block.queued ?? 0} queued`;
}

function prowlarrDetail(block: LiveAutomationServiceBlock | undefined): string {
  if (!block) return 'No data';
  if (block.error) return block.error;
  const disabled = block.disabled?.length ?? 0;
  const cooldown = block.cooldown?.length ?? 0;
  return `${block.enabled ?? 0}/${block.indexers ?? 0} enabled · ${disabled} off · ${cooldown} cooldown`;
}

function bazarrDetail(block: LiveAutomationServiceBlock | undefined): string {
  if (!block) return 'No data';
  if (block.error) return block.error;
  return `${block.wantedEpisodes ?? 0} ep · ${block.wantedMovies ?? 0} movies wanted`;
}

function mapPreviewItems(
  items: LiveAutomationPreviewItem[] | undefined,
  kind: string,
  serviceId: string,
): MediaStackAutomationPreviewItemDto[] {
  return (items ?? [])
    .filter((item) => item.label)
    .map((item, index) => ({
      id: `${serviceId}-${kind}-${index}`,
      title: String(item.label),
      when: item.airDate || item.timeleft || item.status || undefined,
      kind,
    }));
}

/**
 * Translate nested homepage-actions automation summary into the flat Angular DTO
 * consumed by normalizeAutomationSummary.
 */
export function mapLiveAutomationSummary(live: LiveAutomationSummary): MediaStackAutomationSummaryDto {
  if (live && live.ok === false && !live.sonarr && !live.radarr && !live.prowlarr && !live.bazarr) {
    throw new Error(live.error || 'Automation summary unavailable');
  }

  const sonarr = live.sonarr;
  const radarr = live.radarr;
  const prowlarr = live.prowlarr;
  const bazarr = live.bazarr;

  const sonarrDegraded = (sonarr?.missing ?? 0) > 0 || (sonarr?.queueItems ?? []).some((q) => q.warning);
  const radarrDegraded = (radarr?.missing ?? 0) > 0 || (radarr?.queueItems ?? []).some((q) => q.warning);
  const prowlarrDegraded = (prowlarr?.disabled?.length ?? 0) > 0 || (prowlarr?.cooldown?.length ?? 0) > 0;
  const bazarrDegraded = (bazarr?.wantedEpisodes ?? 0) > 0 || (bazarr?.wantedMovies ?? 0) > 0;

  const services: MediaStackAutomationServiceDto[] = [
    {
      id: 'sonarr',
      name: 'Sonarr',
      status: serviceStatus(sonarr, sonarrDegraded),
      detail: sonarrDetail(sonarr),
    },
    {
      id: 'radarr',
      name: 'Radarr',
      status: serviceStatus(radarr, radarrDegraded),
      detail: radarrDetail(radarr),
    },
    {
      id: 'prowlarr',
      name: 'Prowlarr',
      status: serviceStatus(prowlarr, prowlarrDegraded),
      detail: prowlarrDetail(prowlarr),
    },
    {
      id: 'bazarr',
      name: 'Bazarr',
      status: serviceStatus(bazarr, bazarrDegraded),
      detail: bazarrDetail(bazarr),
    },
  ];

  // Prefer actionable queue warnings, then missing, then wanted.
  const preview: MediaStackAutomationPreviewItemDto[] = [
    ...mapPreviewItems(
      (sonarr?.queueItems ?? []).filter((q) => q.warning),
      'queue',
      'sonarr',
    ),
    ...mapPreviewItems(
      (radarr?.queueItems ?? []).filter((q) => q.warning),
      'queue',
      'radarr',
    ),
    ...mapPreviewItems(sonarr?.missingItems, 'missing', 'sonarr'),
    ...mapPreviewItems(radarr?.missingItems, 'missing', 'radarr'),
    ...mapPreviewItems(bazarr?.wantedItems, 'wanted', 'bazarr'),
  ].slice(0, 12);

  const problems: MediaStackAutomationProblemDto[] = [];

  for (const [id, block] of [
    ['sonarr', sonarr],
    ['radarr', radarr],
    ['prowlarr', prowlarr],
    ['bazarr', bazarr],
  ] as const) {
    if (block?.error || block?.ok === false) {
      problems.push({
        id: `${id}-error`,
        summary: block.error || `${id} unreachable`,
        serviceId: id,
        severity: 'actionable',
      });
    }
  }

  for (const item of prowlarr?.disabled ?? []) {
    problems.push({
      id: `prowlarr-disabled-${item.name}`,
      summary: `${item.name} · disabled`,
      serviceId: 'prowlarr',
      severity: 'warning',
    });
  }

  for (const item of prowlarr?.cooldown ?? []) {
    const until = item.until ? ` · until ${item.until}` : '';
    problems.push({
      id: `prowlarr-cooldown-${item.name}`,
      summary: `${item.name} · cooldown${until}`,
      serviceId: 'prowlarr',
      severity: 'warning',
    });
  }

  if ((sonarr?.missing ?? 0) > 0) {
    problems.push({
      id: 'sonarr-missing',
      summary: `${sonarr?.missing} Sonarr episode(s) missing`,
      serviceId: 'sonarr',
      severity: 'warning',
    });
  }

  if ((radarr?.missing ?? 0) > 0) {
    problems.push({
      id: 'radarr-missing',
      summary: `${radarr?.missing} Radarr movie(s) missing`,
      serviceId: 'radarr',
      severity: 'warning',
    });
  }

  if (live.error) {
    problems.push({
      id: 'automation-global',
      summary: live.error,
      severity: 'actionable',
    });
  }

  return {
    generatedAt: live.generatedAt ?? new Date().toISOString(),
    services,
    preview,
    problems,
  };
}
