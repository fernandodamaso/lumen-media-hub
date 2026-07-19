import { LibraryItemKind } from '../library/library.models';
import { isRecord, requireArrayField, requireNonEmptyString } from './http-response';
import {
  MediaStackAutomationPreviewItemDto,
  MediaStackAutomationProblemDto,
  MediaStackAutomationServiceDto,
  MediaStackAutomationSummaryDto,
} from './wire/automation';
import { MediaStackCalendarEventDto } from './wire/calendar';
import {
  MediaStackDiscoverFeedbackDto,
  MediaStackDiscoverItemDto,
  MediaStackDiscoverMediaTypeDto,
  MediaStackExternalDiscoverItemDto,
} from './wire/discover';
import { MediaStackLibraryItemDto, MediaStackLibraryStatsDto } from './wire/library';
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

/** Validated Jellyfin list member — required identity fields are present. */
export interface ValidatedLiveJellyfinItem {
  id: string;
  name: string;
  year?: number | null;
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

  const progress = requireFiniteNumberField(raw, 'progress', index, 'torrents');
  const size = requireSizeField(raw, index);
  const dlspeed = requireFiniteNumberField(raw, 'dlspeed', index, 'torrents');
  const upspeed = requireFiniteNumberField(raw, 'upspeed', index, 'torrents');
  const eta = requireFiniteNumberField(raw, 'eta', index, 'torrents');

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

/**
 * Reject calendar members lacking required air identity (title/additional/date).
 * Optional presentation fields stay optional; wrong types are rejected.
 */
export function requireLiveCalendarEvent(raw: unknown, index = 0): MediaStackCalendarEventDto {
  if (!isRecord(raw)) {
    throw new Error(`Malformed calendar response: member ${index} is not an object`);
  }

  const title = raw['title'];
  const additional = raw['additional'];
  const date = raw['date'];
  if (typeof title !== 'string' || !title.trim()) {
    throw new Error(`Malformed calendar response: member ${index} is missing title`);
  }
  if (typeof additional !== 'string') {
    throw new Error(`Malformed calendar response: member ${index} is missing additional`);
  }
  if (typeof date !== 'string' || !date.trim()) {
    throw new Error(`Malformed calendar response: member ${index} is missing date`);
  }

  const airDateRaw = raw['airDate'];
  let airDate: string | undefined;
  if (airDateRaw !== undefined && airDateRaw !== null) {
    if (typeof airDateRaw !== 'string') {
      throw new Error(`Malformed calendar response: member ${index} has invalid airDate`);
    }
    airDate = airDateRaw;
  }

  const kindRaw = raw['kind'];
  let kind: 'episode' | 'movie' | undefined;
  if (kindRaw !== undefined && kindRaw !== null) {
    if (kindRaw !== 'episode' && kindRaw !== 'movie') {
      throw new Error(`Malformed calendar response: member ${index} has invalid kind`);
    }
    kind = kindRaw;
  }

  const statusRaw = raw['status'];
  let status: string | undefined;
  if (statusRaw !== undefined && statusRaw !== null) {
    if (typeof statusRaw !== 'string') {
      throw new Error(`Malformed calendar response: member ${index} has invalid status`);
    }
    status = statusRaw;
  }

  const artRaw = raw['art'];
  let art: string | undefined;
  if (artRaw !== undefined && artRaw !== null) {
    if (typeof artRaw !== 'string') {
      throw new Error(`Malformed calendar response: member ${index} has invalid art`);
    }
    art = artRaw;
  }

  const hasFile = optionalBoolean(raw, 'hasFile', index, 'calendar');
  const monitored = optionalBoolean(raw, 'monitored', index, 'calendar');
  const premiere = optionalBoolean(raw, 'premiere', index, 'calendar');
  const seriesId = optionalFiniteNumber(raw, 'seriesId', index, 'calendar');

  return {
    title,
    additional,
    date,
    airDate,
    kind,
    status,
    art,
    hasFile,
    monitored,
    premiere,
    seriesId,
  };
}

/**
 * Reject Jellyfin list members lacking required identity (id/name).
 * Do not synthesize ids or titles for missing values.
 */
export function requireLiveJellyfinItem(raw: unknown, index = 0): ValidatedLiveJellyfinItem {
  if (!isRecord(raw)) {
    throw new Error(`Malformed jellyfin items response: member ${index} is not an object`);
  }

  const id = raw['id'];
  const name = raw['name'];
  if (typeof id !== 'string' || !id.trim()) {
    throw new Error(`Malformed jellyfin items response: member ${index} is missing id`);
  }
  if (typeof name !== 'string' || !name.trim()) {
    throw new Error(`Malformed jellyfin items response: member ${index} is missing name`);
  }

  const yearRaw = raw['year'];
  let year: number | null | undefined;
  if (yearRaw !== undefined) {
    if (yearRaw !== null && (typeof yearRaw !== 'number' || !Number.isFinite(yearRaw))) {
      throw new Error(`Malformed jellyfin items response: member ${index} has invalid year`);
    }
    year = yearRaw;
  }

  const imageRaw = raw['image'];
  let image: string | null | undefined;
  if (imageRaw !== undefined) {
    if (imageRaw !== null && typeof imageRaw !== 'string') {
      throw new Error(`Malformed jellyfin items response: member ${index} has invalid image`);
    }
    image = imageRaw;
  }

  const ratingRaw = raw['rating'];
  let rating: number | null | undefined;
  if (ratingRaw !== undefined) {
    if (ratingRaw !== null && (typeof ratingRaw !== 'number' || !Number.isFinite(ratingRaw))) {
      throw new Error(`Malformed jellyfin items response: member ${index} has invalid rating`);
    }
    rating = ratingRaw;
  }

  return { id, name, year, image, rating };
}

/**
 * Reject library stats envelopes that coerce missing counts into zeros.
 * Finite zero counts are valid empty totals.
 */
export function requireLiveLibraryStats(raw: unknown): MediaStackLibraryStatsDto {
  if (!isRecord(raw)) {
    throw new Error('Malformed library stats response');
  }
  const movies = raw['movies'];
  const series = raw['series'];
  if (typeof movies !== 'number' || !Number.isFinite(movies)) {
    throw new Error('Malformed library stats response: missing movies');
  }
  if (typeof series !== 'number' || !Number.isFinite(series)) {
    throw new Error('Malformed library stats response: missing series');
  }
  // Negative counts are malformed — do not clamp into trustworthy zeros at the format layer.
  if (movies < 0) {
    throw new Error('Malformed library stats response: invalid movies');
  }
  if (series < 0) {
    throw new Error('Malformed library stats response: invalid series');
  }
  return {
    ok: typeof raw['ok'] === 'boolean' ? raw['ok'] : undefined,
    movies,
    series,
    error: typeof raw['error'] === 'string' ? raw['error'] : undefined,
  };
}

function requireFiniteNumberField(
  raw: Record<string, unknown>,
  field: string,
  index: number,
  resource: string,
): number {
  const value = raw[field];
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`Malformed ${resource} response: member ${index} is missing ${field}`);
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

function optionalBoolean(
  raw: Record<string, unknown>,
  field: string,
  index: number,
  resource: string,
): boolean | undefined {
  const value = raw[field];
  if (value === undefined || value === null) return undefined;
  if (typeof value !== 'boolean') {
    throw new Error(`Malformed ${resource} response: member ${index} has invalid ${field}`);
  }
  return value;
}

function optionalFiniteNumber(
  raw: Record<string, unknown>,
  field: string,
  index: number,
  resource: string,
): number | undefined {
  const value = raw[field];
  if (value === undefined || value === null) return undefined;
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`Malformed ${resource} response: member ${index} has invalid ${field}`);
  }
  return value;
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
  item: unknown,
  kind: LibraryItemKind,
  index = 0,
): MediaStackLibraryItemDto {
  const validated = requireLiveJellyfinItem(item, index);
  const posterUrl = validated.image ? String(validated.image) : undefined;
  return {
    id: validated.id,
    title: validated.name,
    kind,
    year: validated.year == null ? undefined : Number(validated.year) || undefined,
    posterUrl,
    artworkState: posterUrl ? 'ok' : 'missing',
    playable: true,
    rating: validated.rating,
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

/** Validated storage volume — identity and byte capacities are present (zeros allowed). */
export interface ValidatedLiveStorageVolume {
  id: string;
  label: string;
  kind?: string;
  usedBytes: number;
  totalBytes: number;
}

/**
 * Reject storage volumes that lack required identity or byte capacities.
 * Do not synthesize volume ids, names, or zero capacities for missing fields.
 */
export function requireLiveStorageVolume(raw: unknown, index = 0): ValidatedLiveStorageVolume {
  if (!isRecord(raw)) {
    throw new Error(`Malformed storage overview response: member ${index} is not an object`);
  }

  const id = raw['id'];
  if (typeof id !== 'string' || !id.trim()) {
    throw new Error(`Malformed storage overview response: member ${index} is missing id`);
  }

  const labelRaw = raw['label'];
  const nameRaw = raw['name'];
  let label: string | undefined;
  if (typeof labelRaw === 'string' && labelRaw.trim()) {
    label = labelRaw;
  } else if (typeof nameRaw === 'string' && nameRaw.trim()) {
    label = nameRaw;
  } else if (labelRaw !== undefined && labelRaw !== null && typeof labelRaw !== 'string') {
    throw new Error(`Malformed storage overview response: member ${index} has invalid label`);
  } else if (nameRaw !== undefined && nameRaw !== null && typeof nameRaw !== 'string') {
    throw new Error(`Malformed storage overview response: member ${index} has invalid name`);
  } else {
    throw new Error(`Malformed storage overview response: member ${index} is missing label`);
  }

  const used =
    typeof raw['usedBytes'] === 'number' && Number.isFinite(raw['usedBytes'])
      ? raw['usedBytes']
      : typeof raw['used'] === 'number' && Number.isFinite(raw['used'])
        ? raw['used']
        : null;
  const total =
    typeof raw['totalBytes'] === 'number' && Number.isFinite(raw['totalBytes'])
      ? raw['totalBytes']
      : typeof raw['total'] === 'number' && Number.isFinite(raw['total'])
        ? raw['total']
        : null;
  if (used === null) {
    throw new Error(`Malformed storage overview response: member ${index} is missing usedBytes`);
  }
  if (total === null) {
    throw new Error(`Malformed storage overview response: member ${index} is missing totalBytes`);
  }
  // Negative capacities are malformed — zeros remain valid empty capacity.
  if (used < 0) {
    throw new Error(`Malformed storage overview response: member ${index} has invalid usedBytes`);
  }
  if (total < 0) {
    throw new Error(`Malformed storage overview response: member ${index} has invalid totalBytes`);
  }

  const kindRaw = raw['kind'];
  let kind: string | undefined;
  if (kindRaw !== undefined && kindRaw !== null) {
    if (typeof kindRaw !== 'string') {
      throw new Error(`Malformed storage overview response: member ${index} has invalid kind`);
    }
    kind = kindRaw;
  }

  return { id, label, kind, usedBytes: used, totalBytes: total };
}

export function mapLiveStorageVolume(raw: unknown, index = 0): MediaStackStorageVolumeDto {
  const volume = requireLiveStorageVolume(raw, index);
  return {
    id: volume.id,
    label: volume.label,
    kind: volume.kind,
    usedBytes: volume.usedBytes,
    totalBytes: volume.totalBytes,
  };
}

const DISCOVER_MEDIA_TYPES: ReadonlySet<string> = new Set(['movie', 'tv']);
const DISCOVER_FEEDBACK: ReadonlySet<string> = new Set(['liked', 'disliked', 'watched', 'skipped']);

/**
 * Validate GET /discover/hermes success envelopes before domain mapping.
 * Soft `{ ok: false }` envelopes skip this (handled by requireSoftEnvelope).
 */
export function requireHermesDiscoverPayload(data: Record<string, unknown>): void {
  const items = requireArrayField(data, 'items', 'Malformed Hermes response');
  items.forEach((item, index) => {
    requireLiveHermesDiscoverItem(item, index);
  });

  const pending = data['pending_request_sync'];
  if (pending !== undefined && pending !== null) {
    if (!Array.isArray(pending)) {
      throw new Error('Malformed Hermes response: pending_request_sync is not an array');
    }
    pending.forEach((entry, index) => {
      if (!isRecord(entry)) {
        throw new Error(`Malformed Hermes response: pending_request_sync member ${index} is not an object`);
      }
      requireNonEmptyString(
        entry['id'],
        `Malformed Hermes response: pending_request_sync member ${index} is missing id`,
      );
      const requestId = entry['jellyseerr_request_id'];
      if (typeof requestId !== 'number' || !Number.isFinite(requestId)) {
        throw new Error(
          `Malformed Hermes response: pending_request_sync member ${index} is missing jellyseerr_request_id`,
        );
      }
    });
  }

  const generation = data['generation_request'];
  if (generation !== undefined && generation !== null) {
    if (!isRecord(generation)) {
      throw new Error('Malformed Hermes response: generation_request is not an object');
    }
    requireNonEmptyString(
      generation['requested_at'],
      'Malformed Hermes response: generation_request is missing requested_at',
    );
    if (generation['status'] !== 'pending') {
      throw new Error('Malformed Hermes response: generation_request has invalid status');
    }
  }
}

/**
 * Validate GET /discover/jellyseerr|trakt success envelopes before domain mapping.
 */
export function requireExternalDiscoverPayload(
  data: Record<string, unknown>,
  resource: 'Jellyseerr' | 'Trakt',
): void {
  const items = requireArrayField(data, 'items', `Malformed ${resource} response`);
  items.forEach((item, index) => {
    requireLiveExternalDiscoverItem(item, index, resource);
  });
}

/**
 * Reject Hermes members lacking required identity/browse fields.
 * Call before mapHermesDiscover so missing values are never synthesized into plausible cards.
 */
export function requireLiveHermesDiscoverItem(raw: unknown, index = 0): MediaStackDiscoverItemDto {
  if (!isRecord(raw)) {
    throw new Error(`Malformed Hermes response: member ${index} is not an object`);
  }

  const id = requireNonEmptyString(raw['id'], `Malformed Hermes response: member ${index} is missing id`);
  const source = requireNonEmptyString(
    raw['source'],
    `Malformed Hermes response: member ${index} is missing source`,
  );
  const type = requireDiscoverMediaType(raw['type'], index, 'Hermes');
  const title = requireNonEmptyString(
    raw['title'],
    `Malformed Hermes response: member ${index} is missing title`,
  );
  const tmdbId = requireRequiredFiniteNumber(raw, 'tmdb_id', index, 'Hermes');
  const active = raw['active'];
  if (typeof active !== 'boolean') {
    throw new Error(`Malformed Hermes response: member ${index} is missing active`);
  }
  const addedAt = requireNonEmptyString(
    raw['added_at'],
    `Malformed Hermes response: member ${index} is missing added_at`,
  );

  const year = optionalNullableFiniteNumber(raw, 'year', index, 'Hermes');
  const reason = optionalNullableString(raw, 'reason', index, 'Hermes');
  const feedback = requireDiscoverFeedback(raw['feedback'], index, 'Hermes');
  const feedbackAt = optionalNullableString(raw, 'feedback_at', index, 'Hermes') ?? null;
  const requestState = requireDiscoverRequestState(raw['request_state'], index, 'Hermes');
  const requestedAt = optionalNullableString(raw, 'requested_at', index, 'Hermes') ?? null;
  const jellyseerrRequestId = optionalNullableFiniteNumber(raw, 'jellyseerr_request_id', index, 'Hermes');
  const inLibrary = optionalBoolean(raw, 'in_library', index, 'Hermes');
  const jellyfinId = optionalNullableString(raw, 'jellyfin_id', index, 'Hermes');
  const posterPath = optionalNullableString(raw, 'poster_path', index, 'Hermes');
  const posterUrl = optionalNullableString(raw, 'poster_url', index, 'Hermes');
  const notes = optionalNullableString(raw, 'notes', index, 'Hermes');
  const rating = optionalNullableFiniteNumber(raw, 'rating', index, 'Hermes');

  return {
    id,
    source,
    type,
    title,
    year,
    tmdb_id: tmdbId,
    reason: reason ?? undefined,
    active,
    feedback,
    feedback_at: feedbackAt,
    request_state: requestState,
    requested_at: requestedAt,
    jellyseerr_request_id: jellyseerrRequestId ?? null,
    in_library: inLibrary,
    jellyfin_id: jellyfinId,
    poster_path: posterPath,
    poster_url: posterUrl,
    added_at: addedAt,
    notes: notes ?? undefined,
    rating,
  };
}

/**
 * Reject external discover members lacking required type/title/tmdb identity.
 */
export function requireLiveExternalDiscoverItem(
  raw: unknown,
  index = 0,
  resource: 'Jellyseerr' | 'Trakt' = 'Jellyseerr',
): MediaStackExternalDiscoverItemDto {
  if (!isRecord(raw)) {
    throw new Error(`Malformed ${resource} response: member ${index} is not an object`);
  }

  const type = requireDiscoverMediaType(raw['type'], index, resource);
  const title = requireNonEmptyString(
    raw['title'],
    `Malformed ${resource} response: member ${index} is missing title`,
  );
  const tmdbId = requireRequiredFiniteNumber(raw, 'tmdb_id', index, resource);

  const id = optionalNullableString(raw, 'id', index, resource) ?? undefined;
  const source = optionalNullableString(raw, 'source', index, resource) ?? undefined;
  const year = optionalNullableFiniteNumber(raw, 'year', index, resource);
  const overview = optionalNullableString(raw, 'overview', index, resource) ?? undefined;
  const posterUrl = optionalNullableString(raw, 'poster_url', index, resource);
  const rating = optionalNullableFiniteNumber(raw, 'rating', index, resource);

  return {
    id: id ?? undefined,
    source: source ?? undefined,
    type,
    title,
    year,
    tmdb_id: tmdbId,
    overview,
    poster_url: posterUrl,
    rating,
  };
}

function requireDiscoverMediaType(
  value: unknown,
  index: number,
  resource: string,
): MediaStackDiscoverMediaTypeDto {
  if (typeof value !== 'string' || !DISCOVER_MEDIA_TYPES.has(value)) {
    throw new Error(`Malformed ${resource} response: member ${index} is missing type`);
  }
  return value as MediaStackDiscoverMediaTypeDto;
}

function requireDiscoverFeedback(
  value: unknown,
  index: number,
  resource: string,
): MediaStackDiscoverFeedbackDto | null {
  if (value === undefined) return null;
  if (value === null) return null;
  if (typeof value !== 'string' || !DISCOVER_FEEDBACK.has(value)) {
    throw new Error(`Malformed ${resource} response: member ${index} has invalid feedback`);
  }
  return value as MediaStackDiscoverFeedbackDto;
}

function requireDiscoverRequestState(
  value: unknown,
  index: number,
  resource: string,
): 'requested' | null {
  if (value === undefined || value === null) return null;
  if (value !== 'requested') {
    throw new Error(`Malformed ${resource} response: member ${index} has invalid request_state`);
  }
  return 'requested';
}

function requireRequiredFiniteNumber(
  raw: Record<string, unknown>,
  field: string,
  index: number,
  resource: string,
): number {
  const value = raw[field];
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`Malformed ${resource} response: member ${index} is missing ${field}`);
  }
  return value;
}

function optionalNullableString(
  raw: Record<string, unknown>,
  field: string,
  index: number,
  resource: string,
): string | null | undefined {
  const value = raw[field];
  if (value === undefined) return undefined;
  if (value === null) return null;
  if (typeof value !== 'string') {
    throw new Error(`Malformed ${resource} response: member ${index} has invalid ${field}`);
  }
  return value;
}

function optionalNullableFiniteNumber(
  raw: Record<string, unknown>,
  field: string,
  index: number,
  resource: string,
): number | null | undefined {
  const value = raw[field];
  if (value === undefined) return undefined;
  if (value === null) return null;
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`Malformed ${resource} response: member ${index} has invalid ${field}`);
  }
  return value;
}
