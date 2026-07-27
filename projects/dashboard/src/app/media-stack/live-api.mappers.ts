import { LibraryItemKind } from '../library/library.models';
import { isRecord, requireArrayField, requireNonEmptyString } from './http-response';
import {
  MediaStackAutomationPreviewItemDto,
  MediaStackAutomationProblemDto,
  MediaStackAutomationProblemItemDto,
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
import { MediaStackLibraryItemDto } from './wire/library';
import { MediaStackStorageVolumeDto } from './wire/storage';
import { MediaStackTorrentDto } from './wire/torrents';

/** Validated live torrent member — required identity/state/progress fields are present. */
interface ValidatedLiveQbtTorrent {
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
interface LiveJellyfinItem {
  name?: string;
  year?: number | null;
  id?: string;
  image?: string | null;
  rating?: number | null;
}

/** Validated Jellyfin list member — required identity fields are present. */
interface ValidatedLiveJellyfinItem {
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

interface LiveAutomationPreviewItem {
  label?: string;
  airDate?: string;
  status?: string;
  timeleft?: string;
  error?: string;
  warning?: boolean;
  href?: string | null;
  titleSlug?: string;
  seriesId?: number;
  posterUrl?: string | null;
}

interface LiveAutomationServiceBlock {
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
function requireLiveTorrent(raw: unknown, index = 0): ValidatedLiveQbtTorrent {
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

  return {
    hash,
    name,
    state,
    progress: requireFiniteNumberField(raw, 'progress', index, 'torrents'),
    size: requireSizeField(raw, index),
    amount_left: optionalFiniteNumber(raw, 'amount_left', index, 'torrents'),
    dlspeed: requireFiniteNumberField(raw, 'dlspeed', index, 'torrents'),
    upspeed: requireFiniteNumberField(raw, 'upspeed', index, 'torrents'),
    eta: requireFiniteNumberField(raw, 'eta', index, 'torrents'),
    category: optionalString(raw, 'category', index, 'torrents'),
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

  return {
    title,
    additional,
    date,
    airDate: optionalString(raw, 'airDate', index, 'calendar'),
    kind: optionalCalendarKind(raw, index),
    status: optionalString(raw, 'status', index, 'calendar'),
    art: optionalString(raw, 'art', index, 'calendar'),
    hasFile: optionalBoolean(raw, 'hasFile', index, 'calendar'),
    monitored: optionalBoolean(raw, 'monitored', index, 'calendar'),
    premiere: optionalBoolean(raw, 'premiere', index, 'calendar'),
    seriesId: optionalFiniteNumber(raw, 'seriesId', index, 'calendar'),
  };
}

/**
 * Reject Jellyfin list members lacking required identity (id/name).
 * Do not synthesize ids or titles for missing values.
 */
function requireLiveJellyfinItem(raw: unknown, index = 0): ValidatedLiveJellyfinItem {
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

  return {
    id,
    name,
    year: optionalNullableFiniteNumber(raw, 'year', index, 'jellyfin items'),
    image: optionalNullableString(raw, 'image', index, 'jellyfin items'),
    rating: optionalNullableFiniteNumber(raw, 'rating', index, 'jellyfin items'),
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

function optionalString(
  raw: Record<string, unknown>,
  field: string,
  index: number,
  resource: string,
): string | undefined {
  const value = raw[field];
  if (value === undefined || value === null) return undefined;
  if (typeof value !== 'string') {
    throw new Error(`Malformed ${resource} response: member ${index} has invalid ${field}`);
  }
  return value;
}

function optionalCalendarKind(
  raw: Record<string, unknown>,
  index: number,
): 'episode' | 'movie' | undefined {
  const kindRaw = raw['kind'];
  if (kindRaw === undefined || kindRaw === null) return undefined;
  if (kindRaw !== 'episode' && kindRaw !== 'movie') {
    throw new Error(`Malformed calendar response: member ${index} has invalid kind`);
  }
  return kindRaw;
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
  const posterUrl = validated.image ?? undefined;
  return {
    id: validated.id,
    title: validated.name,
    kind,
    year: validated.year == null ? undefined : validated.year || undefined,
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

function mapProblemDetailItems(
  items: LiveAutomationPreviewItem[] | undefined,
): MediaStackAutomationProblemItemDto[] {
  return (items ?? [])
    .filter((item) => typeof item.label === 'string' && item.label.trim())
    .map((item) => ({
      title: String(item.label).trim(),
      when: item.airDate || item.timeleft || item.status || undefined,
      href: typeof item.href === 'string' && item.href.trim() ? item.href : null,
      posterUrl: typeof item.posterUrl === 'string' && item.posterUrl.trim() ? item.posterUrl : null,
    }));
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
  if (live.ok === false && !live.sonarr && !live.radarr && !live.prowlarr && !live.bazarr) {
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

  return {
    generatedAt,
    services,
    preview,
    problems: collectAutomationProblems(live),
  };
}

function collectAutomationProblems(live: LiveAutomationSummary): MediaStackAutomationProblemDto[] {
  const problems: MediaStackAutomationProblemDto[] = [];
  const sonarr = live.sonarr;
  const radarr = live.radarr;
  const prowlarr = live.prowlarr;
  const bazarr = live.bazarr;

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
    const items = mapProblemDetailItems(sonarr?.missingItems);
    problems.push({
      id: 'sonarr-missing',
      summary: `${sonarr?.missing} Sonarr episode(s) missing`,
      serviceId: 'sonarr',
      severity: 'warning',
      items,
      itemCount: sonarr?.missing ?? items.length,
    });
  } else {
    const sonarrQueueWarnings = (sonarr?.queueItems ?? []).filter((q) => q.warning);
    if (sonarrQueueWarnings.length > 0) {
      const items = mapProblemDetailItems(sonarrQueueWarnings);
      problems.push({
        id: 'sonarr-queue',
        summary: `${sonarrQueueWarnings.length} Sonarr queue item(s) need attention`,
        serviceId: 'sonarr',
        severity: 'warning',
        items,
        itemCount: sonarrQueueWarnings.length,
      });
    }
  }

  if ((radarr?.missing ?? 0) > 0) {
    const items = mapProblemDetailItems(radarr?.missingItems);
    problems.push({
      id: 'radarr-missing',
      summary: `${radarr?.missing} Radarr movie(s) missing`,
      serviceId: 'radarr',
      severity: 'warning',
      items,
      itemCount: radarr?.missing ?? items.length,
    });
  } else {
    const radarrQueueWarnings = (radarr?.queueItems ?? []).filter((q) => q.warning);
    if (radarrQueueWarnings.length > 0) {
      const items = mapProblemDetailItems(radarrQueueWarnings);
      problems.push({
        id: 'radarr-queue',
        summary: `${radarrQueueWarnings.length} Radarr queue item(s) need attention`,
        serviceId: 'radarr',
        severity: 'warning',
        items,
        itemCount: radarrQueueWarnings.length,
      });
    }
  }

  if (live.error) {
    problems.push({
      id: 'automation-global',
      summary: live.error,
      severity: 'actionable',
    });
  }

  return problems;
}

/**
 * Map the disk block from GET /system/resources into a stable storage volume.
 * Uses the backend mount path as the label and a fixed volume identity.
 * Validates path/used/total and enforces used ≤ total.
 */
export function mapLiveSystemResourcesDisk(disk: unknown): MediaStackStorageVolumeDto {
  if (!isRecord(disk)) {
    throw new Error('Malformed system resources response: disk is not an object');
  }

  const path = disk['path'];
  if (typeof path !== 'string' || !path.trim()) {
    throw new Error('Malformed system resources response: missing disk.path');
  }

  const used = disk['used'];
  const total = disk['total'];

  if (typeof used !== 'number' || !Number.isFinite(used)) {
    throw new Error('Malformed system resources response: missing disk.used');
  }
  if (typeof total !== 'number' || !Number.isFinite(total)) {
    throw new Error('Malformed system resources response: missing disk.total');
  }
  if (used < 0 || total < 0) {
    throw new Error('Malformed system resources response: negative disk capacity');
  }
  if (used > total) {
    throw new Error('Malformed system resources response: disk.used exceeds disk.total');
  }

  return {
    id: 'media-volume',
    label: `Media volume (${path})`,
    kind: 'library',
    usedBytes: used,
    totalBytes: total,
  };
}

/**
 * Validate GET /discover/hermes success envelopes before domain mapping.
 * Soft `{ ok: false }` envelopes skip this (handled by requireSoftEnvelope).
 */
export function requireHermesDiscoverPayload(data: Record<string, unknown>): void {
  const items = requireArrayField(data, 'items', 'Malformed Hermes response');
  items.forEach((item, index) => {
    requireLiveHermesDiscoverItem(item, index);
  });

  requirePendingRequestSync(data['pending_request_sync']);
  requireGenerationRequest(data['generation_request']);
}

function requirePendingRequestSync(pending: unknown): void {
  if (pending === undefined || pending === null) return;
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

function requireGenerationRequest(generation: unknown): void {
  if (generation === undefined || generation === null) return;
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
function requireLiveHermesDiscoverItem(raw: unknown, index = 0): MediaStackDiscoverItemDto {
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
  const tmdbId = requireFiniteNumberField(raw, 'tmdb_id', index, 'Hermes');
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
function requireLiveExternalDiscoverItem(
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
  const tmdbId = requireFiniteNumberField(raw, 'tmdb_id', index, resource);

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
  if (value === 'movie' || value === 'tv') {
    return value;
  }
  throw new Error(`Malformed ${resource} response: member ${index} is missing type`);
}

function requireDiscoverFeedback(
  value: unknown,
  index: number,
  resource: string,
): MediaStackDiscoverFeedbackDto | null {
  if (value === undefined || value === null) return null;
  if (value === 'liked' || value === 'disliked' || value === 'watched' || value === 'skipped') {
    return value;
  }
  throw new Error(`Malformed ${resource} response: member ${index} has invalid feedback`);
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
