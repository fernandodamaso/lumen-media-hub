import { LibraryItemKind } from '../library/library.models';
import { isRecord } from './http-response';
import {
  MediaStackAutomationPreviewItemDto,
  MediaStackAutomationProblemDto,
  MediaStackAutomationServiceDto,
  MediaStackAutomationSummaryDto,
} from './wire/automation';
import { MediaStackLibraryItemDto } from './wire/library';
import { MediaStackStorageVolumeDto } from './wire/storage';
import { MediaStackTorrentDto } from './wire/torrents';

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

/** Validated live torrent member — required identity/state/progress fields are present. */
export interface ValidatedLiveQbtTorrent {
  hash: string;
  name: string;
  state: string;
  progress: number;
  size: number;
  amount_left?: number;
  dlspeed: number;
  upspeed: number;
  eta: number;
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
  latencyMs?: number | null;
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

/**
 * Reject torrent array members that lack required identity/state/progress fields.
 * Call before mapLiveTorrent so missing values are never synthesized into plausible rows.
 */
export function requireLiveTorrent(raw: unknown, index = 0): ValidatedLiveQbtTorrent {
  if (!isRecord(raw)) {
    throw new Error(`Malformed torrents response: member ${index} is not an object`);
  }

  const hash = raw['hash'];
  const name = raw['name'];
  const state = raw['state'];
  if (typeof hash !== 'string' || !hash.trim()) {
    throw new Error(`Malformed torrents response: member ${index} is missing hash`);
  }
  if (typeof name !== 'string' || !name.trim()) {
    throw new Error(`Malformed torrents response: member ${index} is missing name`);
  }
  if (typeof state !== 'string' || !state.trim()) {
    throw new Error(`Malformed torrents response: member ${index} is missing state`);
  }

  const progress = requireFiniteNumberField(raw, 'progress', index);
  const size = requireSizeField(raw, index);
  const dlspeed = requireFiniteNumberField(raw, 'dlspeed', index);
  const upspeed = requireFiniteNumberField(raw, 'upspeed', index);
  const eta = requireFiniteNumberField(raw, 'eta', index);

  const amountLeftRaw = raw['amount_left'];
  let amount_left: number | undefined;
  if (amountLeftRaw !== undefined && amountLeftRaw !== null) {
    if (typeof amountLeftRaw !== 'number' || !Number.isFinite(amountLeftRaw)) {
      throw new Error(`Malformed torrents response: member ${index} has invalid amount_left`);
    }
    amount_left = amountLeftRaw;
  }

  // Optional: absent/null is fine; a present non-string value is rejected (no silent drop).
  const categoryRaw = raw['category'];
  let category: string | undefined;
  if (categoryRaw !== undefined && categoryRaw !== null) {
    if (typeof categoryRaw !== 'string') {
      throw new Error(`Malformed torrents response: member ${index} has invalid category`);
    }
    category = categoryRaw;
  }

  return {
    hash,
    name,
    state,
    progress,
    size,
    amount_left,
    dlspeed,
    upspeed,
    eta,
    category,
  };
}

function requireFiniteNumberField(
  raw: Record<string, unknown>,
  field: string,
  index: number,
): number {
  const value = raw[field];
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`Malformed torrents response: member ${index} is missing ${field}`);
  }
  return value;
}

function requireSizeField(raw: Record<string, unknown>, index: number): number {
  const size = raw['size'];
  if (typeof size === 'number' && Number.isFinite(size)) {
    return size;
  }
  const totalSize = raw['total_size'];
  if (typeof totalSize === 'number' && Number.isFinite(totalSize)) {
    return totalSize;
  }
  throw new Error(`Malformed torrents response: member ${index} is missing size`);
}

export function mapLiveTorrent(raw: unknown, index = 0): MediaStackTorrentDto {
  const torrent = requireLiveTorrent(raw, index);
  const downloaded =
    torrent.amount_left !== undefined
      ? Math.max(0, torrent.size - torrent.amount_left)
      : Math.max(0, torrent.size * torrent.progress);

  return {
    hash: torrent.hash,
    name: torrent.name,
    state: torrent.state,
    progress: torrent.progress,
    size: torrent.size,
    downloaded,
    dlspeed: torrent.dlspeed,
    upspeed: torrent.upspeed,
    eta: torrent.eta,
    category: torrent.category,
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

function liveLatency(block: LiveAutomationServiceBlock | undefined): number | null {
  const value = block?.latencyMs;
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null;
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

function mapGeneratedAt(value: unknown, context: string): string {
  if (value === undefined || value === null || value === '') {
    // Live backends may omit freshness; never substitute the client clock.
    return '';
  }
  if (typeof value !== 'string' || Number.isNaN(Date.parse(value))) {
    throw new Error(`${context}: invalid generatedAt`);
  }
  return value;
}

function mapPreviewItems(
  items: LiveAutomationPreviewItem[] | undefined,
  kind: string,
  serviceId: string,
): MediaStackAutomationPreviewItemDto[] {
  return (items ?? [])
    .filter((item) => typeof item.label === 'string' && item.label.trim())
    .map((item) => {
      const title = String(item.label).trim();
      return {
        // Identity comes from backend-visible fields — never invent clock/index-only ids.
        id: `${serviceId}-${kind}-${title}`,
        title,
        when: item.airDate || item.timeleft || item.status || undefined,
        kind,
      };
    });
}

/**
 * Translate nested homepage-actions automation summary into the flat Angular DTO
 * consumed by mapAutomationSummary.
 */
export function mapLiveAutomationSummary(live: LiveAutomationSummary): MediaStackAutomationSummaryDto {
  if (live && live.ok === false && !live.sonarr && !live.radarr && !live.prowlarr && !live.bazarr) {
    throw new Error(live.error || 'Automation summary unavailable');
  }

  const generatedAt = mapGeneratedAt(live.generatedAt, 'Malformed automation summary response');

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
      latencyMs: liveLatency(sonarr),
    },
    {
      id: 'radarr',
      name: 'Radarr',
      status: serviceStatus(radarr, radarrDegraded),
      detail: radarrDetail(radarr),
      latencyMs: liveLatency(radarr),
    },
    {
      id: 'prowlarr',
      name: 'Prowlarr',
      status: serviceStatus(prowlarr, prowlarrDegraded),
      detail: prowlarrDetail(prowlarr),
      latencyMs: liveLatency(prowlarr),
    },
    {
      id: 'bazarr',
      name: 'Bazarr',
      status: serviceStatus(bazarr, bazarrDegraded),
      detail: bazarrDetail(bazarr),
      latencyMs: liveLatency(bazarr),
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
    generatedAt,
    services,
    preview,
    problems,
  };
}

/** Raw storage volume from GET /storage/overview. */
export interface LiveStorageVolume {
  id?: string;
  label?: string;
  name?: string;
  kind?: string;
  usedBytes?: number;
  used?: number;
  totalBytes?: number;
  total?: number;
}

export function mapLiveStorageVolume(raw: LiveStorageVolume, index = 0): MediaStackStorageVolumeDto {
  const used = Number(raw.usedBytes ?? raw.used);
  const total = Number(raw.totalBytes ?? raw.total);
  return {
    id: raw.id ? String(raw.id) : `volume-${index}`,
    label: raw.label ? String(raw.label) : raw.name ? String(raw.name) : 'Unnamed volume',
    kind: typeof raw.kind === 'string' ? raw.kind : undefined,
    usedBytes: Number.isFinite(used) ? used : 0,
    totalBytes: Number.isFinite(total) ? total : 0,
  };
}
