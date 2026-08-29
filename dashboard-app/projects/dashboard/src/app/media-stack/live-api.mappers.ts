import { LibraryItemKind } from '../library/library.models';
import { isRecord, requireArrayField, requireNonEmptyString } from './http-response';
import {
  MediaStackAutomationPreviewItemDto,
  MediaStackAutomationProblemDto,
  MediaStackAutomationProblemItemDto,
  MediaStackAutomationServiceDto,
  MediaStackAutomationSummaryDto,
  MediaStackQueueHygieneBlockedItemDto,
  MediaStackQueueHygieneEligibleItemDto,
  MediaStackQueueHygieneRunResultDto,
  MediaStackQueueHygieneSummaryDto,
} from './wire/automation';
import { MediaStackCalendarEventDto } from './wire/calendar';
import {
  MediaStackDiscoverFeedbackDto,
  MediaStackDiscoverItemDto,
  MediaStackDiscoverMediaTypeDto,
  MediaStackExternalDiscoverItemDto,
} from './wire/discover';
import { MediaStackLibraryItemDto } from './wire/library';
import { MediaStackWatchNextItemDto } from './wire/watch-next';
import { MediaStackRecentlyAvailableItemDto } from './wire/recently-available';
import { MediaStackStorageVolumeDto } from './wire/storage';
import { MediaStackTorrentDto } from './wire/torrents';
import { MediaStackActivityFeedDto, MediaStackActivityItemDto, MediaStackActivityKindDto, MediaStackActivitySourceDto, MediaStackActivitySourceStatusDto } from './wire/activity';

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
  completion_on: number | null;
}

/** Jellyfin list item from GET /jellyfin/movies|series. */
interface LiveJellyfinItem {
  name?: string;
  year?: number | null;
  id?: string;
  image?: string | null;
  rating?: number | null;
  episodeCount?: number | null;
  played?: boolean;
}

/** Validated Jellyfin list member — required identity fields are present. */
interface ValidatedLiveJellyfinItem {
  id: string;
  name: string;
  year?: number | null;
  image?: string | null;
  rating?: number | null;
  episodeCount?: number | null;
  played: boolean;
}

export interface LiveJellyfinListResponse {
  ok?: boolean;
  total?: number;
  items?: LiveJellyfinItem[];
  error?: string;
}

/** Jellyfin watch-next item from GET /jellyfin/watch-next. */
interface LiveWatchNextItem {
  id?: string;
  parentId?: string | null;
  title?: string;
  subtitle?: string;
  kind?: string;
  image?: string | null;
  playable?: boolean;
  progressPercent?: number;
  year?: number | null;
  rating?: number | null;
  genres?: string[];
  overview?: string | null;
  runtimeTicks?: number | null;
  positionTicks?: number | null;
  backdropUrl?: string | null;
  thumbUrl?: string | null;
}

interface ValidatedLiveWatchNextItem {
  id: string;
  parentId: string | null;
  title: string;
  subtitle: string;
  kind: 'movie' | 'episode';
  image?: string | null;
  playable?: boolean;
  progressPercent: number;
  year: number | null;
  rating: number | null;
  genres: string[];
  overview: string | null;
  runtimeTicks: number | null;
  positionTicks: number | null;
  backdropUrl: string | null;
  thumbUrl: string | null;
}

export interface LiveWatchNextListResponse {
  ok?: boolean;
  items?: LiveWatchNextItem[];
  error?: string;
}

/** Jellyfin recently-available item from GET /jellyfin/recently-available. */
interface LiveRecentlyAvailableItem {
  id?: string;
  parentId?: string | null;
  title?: string;
  subtitle?: string;
  kind?: string;
  availableAt?: string;
  image?: string | null;
  thumbUrl?: string | null;
  playable?: boolean;
  year?: number | null;
}

interface ValidatedLiveRecentlyAvailableItem {
  id: string;
  parentId: string | null;
  title: string;
  subtitle: string;
  kind: 'movie' | 'episode';
  availableAt: string;
  image: string | null;
  thumbUrl: string | null;
  playable: true;
  year: number | null;
}

export interface LiveRecentlyAvailableListResponse {
  ok?: boolean;
  items?: LiveRecentlyAvailableItem[];
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
  configured?: boolean;
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
  degraded?: boolean;
  queueHygiene?: unknown;
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
    completion_on: optionalCompletionTimestamp(raw, index),
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
    episodeCount: optionalNullableFiniteNumber(raw, 'episodeCount', index, 'jellyfin items'),
    played: optionalBoolean(raw, 'played', index, 'jellyfin items') ?? false,
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

function optionalCompletionTimestamp(raw: Record<string, unknown>, index: number): number | null {
  const value = raw['completion_on'];
  if (value === undefined || value === null) return null;
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`Malformed torrents response: member ${index} has invalid completion_on`);
  }
  if (value <= 0) return null;
  if (!Number.isInteger(value)) {
    throw new Error(`Malformed torrents response: member ${index} has invalid completion_on`);
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
    completionOn: torrent.completion_on,
  };
}

export function mapLiveJellyfinItem(
  item: unknown,
  kind: LibraryItemKind,
  index = 0,
): MediaStackLibraryItemDto {
  const validated = requireLiveJellyfinItem(item, index);
  const posterUrl = validated.image ?? undefined;
  const episodeCount = kind === 'movie' ? null : (validated.episodeCount ?? null);
  return {
    id: validated.id,
    title: validated.name,
    kind,
    year: validated.year == null ? undefined : validated.year || undefined,
    posterUrl,
    artworkState: posterUrl ? 'ok' : 'missing',
    playable: true,
    rating: validated.rating,
    episodeCount,
    played: validated.played,
  };
}

function requireLiveWatchNextItem(raw: unknown, index = 0): ValidatedLiveWatchNextItem {
  if (!isRecord(raw)) {
    throw new Error(`Malformed watch-next response: member ${index} is not an object`);
  }

  const id = raw['id'];
  const title = raw['title'];
  const kindRaw = raw['kind'];
  const progressPercent = raw['progressPercent'];
  if (typeof id !== 'string' || !id.trim()) {
    throw new Error(`Malformed watch-next response: member ${index} is missing id`);
  }
  if (typeof title !== 'string' || !title.trim()) {
    throw new Error(`Malformed watch-next response: member ${index} is missing title`);
  }
  if (kindRaw !== 'movie' && kindRaw !== 'episode') {
    throw new Error(`Malformed watch-next response: member ${index} has invalid kind`);
  }
  if (typeof progressPercent !== 'number' || !Number.isFinite(progressPercent)) {
    throw new Error(`Malformed watch-next response: member ${index} is missing progressPercent`);
  }

  const subtitle = optionalString(raw, 'subtitle', index, 'watch-next') ?? '';
  const parentIdRaw = raw['parentId'];
  let parentId: string | null = null;
  if (parentIdRaw !== undefined && parentIdRaw !== null) {
    if (typeof parentIdRaw !== 'string') {
      throw new Error(`Malformed watch-next response: member ${index} has invalid parentId`);
    }
    parentId = parentIdRaw.trim() || null;
  }
  if (kindRaw === 'episode' && !parentId) {
    throw new Error(`Malformed watch-next response: member ${index} is missing parentId`);
  }
  if (kindRaw === 'movie' && parentId) {
    throw new Error(`Malformed watch-next response: member ${index} movie parentId must be null`);
  }

  const playable = optionalBoolean(raw, 'playable', index, 'watch-next');

  return {
    id,
    parentId,
    title,
    subtitle,
    kind: kindRaw,
    image: optionalNullableString(raw, 'image', index, 'watch-next'),
    playable,
    progressPercent,
    year: optionalNullableFiniteNumber(raw, 'year', index, 'watch-next') ?? null,
    rating: optionalNullableFiniteNumber(raw, 'rating', index, 'watch-next') ?? null,
    genres: optionalStringArray(raw, 'genres', index, 'watch-next') ?? [],
    overview: optionalNullableString(raw, 'overview', index, 'watch-next') ?? null,
    runtimeTicks: optionalNullableFiniteNumber(raw, 'runtimeTicks', index, 'watch-next') ?? null,
    positionTicks: optionalNullableFiniteNumber(raw, 'positionTicks', index, 'watch-next') ?? null,
    backdropUrl: optionalNullableString(raw, 'backdropUrl', index, 'watch-next') ?? null,
    thumbUrl: optionalNullableString(raw, 'thumbUrl', index, 'watch-next') ?? null,
  };
}

export function mapLiveWatchNextItem(raw: unknown, index = 0): MediaStackWatchNextItemDto {
  const validated = requireLiveWatchNextItem(raw, index);
  const posterUrl = validated.image ?? undefined;
  return {
    id: validated.id,
    parentId: validated.parentId,
    title: validated.title,
    subtitle: validated.subtitle,
    kind: validated.kind,
    posterUrl,
    artworkState: posterUrl ? 'ok' : 'missing',
    playable: validated.playable,
    progressPercent: validated.progressPercent,
    year: validated.year,
    rating: validated.rating,
    genres: [...validated.genres],
    overview: validated.overview,
    runtimeTicks: validated.runtimeTicks,
    positionTicks: validated.positionTicks,
    backdropUrl: validated.backdropUrl,
    thumbUrl: validated.thumbUrl,
  };
}

const hasExplicitTimezone = (value: string): boolean => /(?:Z|[+-]\d{2}:\d{2})$/i.test(value);

function requireLiveRecentlyAvailableItem(raw: unknown, index = 0): ValidatedLiveRecentlyAvailableItem {
  if (!isRecord(raw)) {
    throw new Error(`Malformed recently-available response: member ${index} is not an object`);
  }

  const id = raw['id'];
  const title = raw['title'];
  const kindRaw = raw['kind'];
  const availableAt = raw['availableAt'];
  if (typeof id !== 'string' || !id.trim()) {
    throw new Error(`Malformed recently-available response: member ${index} is missing id`);
  }
  if (typeof title !== 'string' || !title.trim()) {
    throw new Error(`Malformed recently-available response: member ${index} is missing title`);
  }
  if (kindRaw !== 'movie' && kindRaw !== 'episode') {
    throw new Error(`Malformed recently-available response: member ${index} has invalid kind`);
  }
  if (typeof availableAt !== 'string' || !availableAt.trim() || !hasExplicitTimezone(availableAt.trim())) {
    throw new Error(`Malformed recently-available response: member ${index} has invalid availableAt`);
  }
  if (!Number.isFinite(Date.parse(availableAt.trim()))) {
    throw new Error(`Malformed recently-available response: member ${index} has invalid availableAt`);
  }
  if (raw['playable'] !== true) {
    throw new Error(`Malformed recently-available response: member ${index} is not playable`);
  }

  const subtitle = optionalString(raw, 'subtitle', index, 'recently-available') ?? '';
  if (kindRaw === 'episode' && !subtitle.trim()) {
    throw new Error(`Malformed recently-available response: member ${index} is missing subtitle`);
  }
  const parentIdRaw = raw['parentId'];
  let parentId: string | null = null;
  if (parentIdRaw !== undefined && parentIdRaw !== null) {
    if (typeof parentIdRaw !== 'string') {
      throw new Error(`Malformed recently-available response: member ${index} has invalid parentId`);
    }
    parentId = parentIdRaw.trim() || null;
  }
  if (kindRaw === 'episode' && !parentId) {
    throw new Error(`Malformed recently-available response: member ${index} is missing parentId`);
  }
  if (kindRaw === 'movie' && parentId) {
    throw new Error(`Malformed recently-available response: member ${index} movie parentId must be null`);
  }

  const year = optionalNullableFiniteNumber(raw, 'year', index, 'recently-available') ?? null;
  if (year !== null && (!Number.isInteger(year) || typeof raw['year'] === 'boolean')) {
    throw new Error(`Malformed recently-available response: member ${index} has invalid year`);
  }

  const image = optionalNullableString(raw, 'image', index, 'recently-available') ?? null;
  const thumbUrl = optionalNullableString(raw, 'thumbUrl', index, 'recently-available') ?? null;

  return {
    id: id.trim(),
    parentId,
    title: title.trim(),
    subtitle,
    kind: kindRaw,
    availableAt: availableAt.trim(),
    image,
    thumbUrl,
    playable: true,
    year,
  };
}

export function mapLiveRecentlyAvailableItem(
  raw: unknown,
  index = 0,
): MediaStackRecentlyAvailableItemDto {
  const validated = requireLiveRecentlyAvailableItem(raw, index);
  const posterUrl = validated.image ?? undefined;
  return {
    id: validated.id,
    parentId: validated.parentId,
    title: validated.title,
    subtitle: validated.subtitle,
    kind: validated.kind,
    availableAt: validated.availableAt,
    posterUrl,
    artworkState: posterUrl ? 'ok' : 'missing',
    thumbUrl: validated.thumbUrl,
    playable: true,
    year: validated.year,
  };
}

const QUEUE_HYGIENE_MODES = ['off', 'observe', 'auto'] as const;
const QUEUE_HYGIENE_HASH = /^(?:[0-9a-f]{40}|[0-9a-f]{64})$/i;

function queueHygieneTimestamp(value: unknown, field: string): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== 'string' || !value.trim() || Number.isNaN(Date.parse(value))) {
    throw new Error(`Malformed automation summary response: invalid queueHygiene.${field}`);
  }
  return value;
}

function queueHygieneIds(value: unknown, field: string): number[] {
  if (!Array.isArray(value) || value.some((id) => typeof id !== 'number' || !Number.isInteger(id) || id <= 0)) {
    throw new Error(`Malformed automation summary response: invalid queueHygiene.${field}`);
  }
  const ids: number[] = [];
  for (const id of value as unknown[]) ids.push(id as number);
  return ids;
}

function queueHygieneHashes(value: unknown, field: string): string[] {
  if (!Array.isArray(value) || value.some((hash) => typeof hash !== 'string' || !QUEUE_HYGIENE_HASH.test(hash))) {
    throw new Error(`Malformed automation summary response: invalid queueHygiene.${field}`);
  }
  const hashes: string[] = [];
  for (const hash of value as unknown[]) hashes.push((hash as string).toLowerCase());
  return hashes;
}

function queueHygieneEligible(value: unknown, index: number): MediaStackQueueHygieneEligibleItemDto {
  if (!isRecord(value)) throw new Error(`Malformed automation summary response: invalid queueHygiene.eligibleItems[${index}]`);
  const downloadId = value['downloadId'];
  const titles = value['titles'];
  const reason = value['reason'];
  const completedAt = queueHygieneTimestamp(value['completedAt'], `eligibleItems[${index}].completedAt`);
  const ageHours = value['ageHours'];
  if (typeof downloadId !== 'string' || !downloadId.trim() || !Array.isArray(titles) || titles.some((title) => typeof title !== 'string')) {
    throw new Error(`Malformed automation summary response: invalid queueHygiene.eligibleItems[${index}]`);
  }
  if (typeof reason !== 'string' || !reason.trim() || completedAt === null || typeof ageHours !== 'number' || !Number.isFinite(ageHours) || ageHours < 0) {
    throw new Error(`Malformed automation summary response: invalid queueHygiene.eligibleItems[${index}]`);
  }
  return {
    downloadId: downloadId.trim(),
    queueIds: queueHygieneIds(value['queueIds'], `eligibleItems[${index}].queueIds`),
    titles: (titles as unknown[]).map((title) => (title as string).trim()),
    reason: reason.trim(),
    completedAt,
    ageHours,
  };
}

function queueHygieneBlocked(value: unknown, index: number): MediaStackQueueHygieneBlockedItemDto {
  if (!isRecord(value)) throw new Error(`Malformed automation summary response: invalid queueHygiene.blockedItems[${index}]`);
  const queueId = value['queueId'];
  const title = value['title'];
  const reason = value['reason'];
  const blocker = value['blocker'];
  if (queueId !== null && (typeof queueId !== 'number' || !Number.isInteger(queueId) || queueId <= 0)) {
    throw new Error(`Malformed automation summary response: invalid queueHygiene.blockedItems[${index}].queueId`);
  }
  if (typeof title !== 'string' || typeof reason !== 'string' || typeof blocker !== 'string') {
    throw new Error(`Malformed automation summary response: invalid queueHygiene.blockedItems[${index}]`);
  }
  return { queueId, title: title.trim(), reason: reason.trim(), blocker: blocker.trim() };
}

function validateQueueHygiene(value: unknown): MediaStackQueueHygieneSummaryDto {
  if (!isRecord(value)) throw new Error('Malformed automation summary response: invalid queueHygiene');
  const mode = value['mode'];
  const circuitOpen = value['circuitOpen'];
  const eligibleCount = value['eligibleCount'];
  const blockedCount = value['blockedCount'];
  if (!QUEUE_HYGIENE_MODES.includes(mode as (typeof QUEUE_HYGIENE_MODES)[number]) || typeof circuitOpen !== 'boolean') {
    throw new Error('Malformed automation summary response: invalid queueHygiene mode/circuit');
  }
  if (![eligibleCount, blockedCount].every((count) => typeof count === 'number' && Number.isInteger(count) && count >= 0)) {
    throw new Error('Malformed automation summary response: invalid queueHygiene counts');
  }
  if (!Array.isArray(value['eligibleItems']) || !Array.isArray(value['blockedItems'])) {
    throw new Error('Malformed automation summary response: invalid queueHygiene items');
  }
  const cleanup = value['lastCleanup'];
  let lastCleanup: MediaStackQueueHygieneSummaryDto['lastCleanup'] = null;
  if (cleanup !== null) {
    if (!isRecord(cleanup)) throw new Error('Malformed automation summary response: invalid queueHygiene.lastCleanup');
    const at = queueHygieneTimestamp(cleanup['at'], 'lastCleanup.at');
    if (!at) throw new Error('Malformed automation summary response: invalid queueHygiene.lastCleanup.at');
    lastCleanup = {
      at,
      queueIds: queueHygieneIds(cleanup['queueIds'], 'lastCleanup.queueIds'),
      hashes: queueHygieneHashes(cleanup['hashes'], 'lastCleanup.hashes'),
    };
  }
  const rawVerification = value['verification'];
  let verification: MediaStackQueueHygieneSummaryDto['verification'] = null;
  if (rawVerification !== null) {
    if (!isRecord(rawVerification) || typeof rawVerification['queueIdsGone'] !== 'boolean' || typeof rawVerification['hashesPreserved'] !== 'boolean') {
      throw new Error('Malformed automation summary response: invalid queueHygiene.verification');
    }
    verification = {
      queueIdsGone: rawVerification['queueIdsGone'],
      hashesPreserved: rawVerification['hashesPreserved'],
      missingHashes: queueHygieneHashes(rawVerification['missingHashes'], 'verification.missingHashes'),
    };
  }
  return {
    mode: mode as MediaStackQueueHygieneSummaryDto['mode'],
    circuitOpen,
    eligibleCount: eligibleCount as number,
    blockedCount: blockedCount as number,
    eligibleItems: (value['eligibleItems'] as unknown[]).map(queueHygieneEligible),
    blockedItems: (value['blockedItems'] as unknown[]).map(queueHygieneBlocked),
    lastCycleAt: queueHygieneTimestamp(value['lastCycleAt'], 'lastCycleAt'),
    lastCleanup,
    verification,
    error: typeof value['error'] === 'string' ? value['error'] : undefined,
  };
}

export function mapLiveQueueHygieneRun(value: unknown): MediaStackQueueHygieneRunResultDto {
  if (!isRecord(value)) throw new Error('Malformed queue-hygiene run response');
  const status = value['status'];
  const allowed = ['observed', 'cleaned', 'circuit_open', 'verification_failed', 'error', 'skipped', 'off'];
  if (typeof status !== 'string' || !allowed.includes(status)) {
    throw new Error('Malformed queue-hygiene run response: invalid status');
  }
  let summary: MediaStackQueueHygieneSummaryDto;
  try {
    summary = validateQueueHygiene(value);
  } catch (error) {
    throw new Error(`Malformed queue-hygiene run response: ${error instanceof Error ? error.message : 'invalid payload'}`);
  }
  const observedAt = value['observedAt'];
  if (observedAt !== undefined && (typeof observedAt !== 'string' || Number.isNaN(Date.parse(observedAt)))) {
    throw new Error('Malformed queue-hygiene run response: invalid observedAt');
  }
  const rawCounts = value['counts'];
  let counts: MediaStackQueueHygieneRunResultDto['counts'];
  if (rawCounts !== undefined) {
    if (!isRecord(rawCounts) || ![rawCounts['eligible'], rawCounts['blocked'], rawCounts['queued']].every((count) => typeof count === 'number' && Number.isInteger(count) && count >= 0)) {
      throw new Error('Malformed queue-hygiene run response: invalid counts');
    }
    counts = {
      eligible: rawCounts['eligible'] as number,
      blocked: rawCounts['blocked'] as number,
      queued: rawCounts['queued'] as number,
    };
  }
  return { ...summary, status: status as MediaStackQueueHygieneRunResultDto['status'], observedAt, counts };
}

function serviceStatus(
  block: LiveAutomationServiceBlock | undefined,
  degraded: boolean,
): string {
  if (!block) return 'unknown';
  if (block.configured === false) return 'unknown';
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
  const queueHygiene = sonarr?.queueHygiene == null ? null : validateQueueHygiene(sonarr.queueHygiene);

  const sonarrDegraded = sonarr?.degraded === true
    || (queueHygiene?.eligibleCount ?? 0) > 0
    || (queueHygiene?.blockedCount ?? 0) > 0
    || queueHygiene?.circuitOpen === true
    || (sonarr?.missing ?? 0) > 0
    || (sonarr?.queueItems ?? []).some((q) => q.warning);
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
  ];
  if (bazarr) {
    services.push({
      id: 'bazarr',
      name: 'Bazarr',
      status: serviceStatus(bazarr, bazarrDegraded),
      detail: bazarrDetail(bazarr),
      latencyMs: liveLatency(bazarr),
    });
  }

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
    queueHygiene,
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
    if (block?.configured === false) continue;
    if (block?.error || block?.ok === false) {
      problems.push({
        id: `${id}-error`,
        summary: block.error || `${id} unreachable`,
        serviceId: id,
        severity: 'actionable',
      });
    }
  }

  const disabledIndexers = prowlarr?.disabled ?? [];
  if (disabledIndexers.length > 0) {
    problems.push({
      id: 'prowlarr-disabled',
      summary: `${disabledIndexers.length} indexer(s) disabled`,
      serviceId: 'prowlarr',
      severity: 'warning',
      items: disabledIndexers.map((item) => ({
        title: item.name,
        when: 'disabled',
        href: null,
        posterUrl: null,
      })),
      itemCount: disabledIndexers.length,
    });
  }

  const cooldownIndexers = prowlarr?.cooldown ?? [];
  if (cooldownIndexers.length > 0) {
    problems.push({
      id: 'prowlarr-cooldown',
      summary: `${cooldownIndexers.length} indexer(s) in cooldown`,
      serviceId: 'prowlarr',
      severity: 'warning',
      items: cooldownIndexers.map((item) => ({
        title: item.name,
        when: item.until ?? 'cooldown',
        href: null,
        posterUrl: null,
      })),
      itemCount: cooldownIndexers.length,
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
  }
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
  if (sonarr?.queueHygiene != null) {
    const hygiene = validateQueueHygiene(sonarr.queueHygiene);
    if (hygiene.circuitOpen || hygiene.blockedCount > 0 || hygiene.eligibleCount > 0) {
      const severity = hygiene.circuitOpen || hygiene.blockedCount > 0 ? 'actionable' : 'warning';
      problems.push({
        id: 'sonarr-queue-hygiene',
        summary: hygiene.circuitOpen
          ? 'Automatic Sonarr queue cleanup paused'
          : `${hygiene.eligibleCount + hygiene.blockedCount} Sonarr queue-hygiene item(s) need attention`,
        serviceId: 'sonarr',
        severity,
        itemCount: hygiene.eligibleCount + hygiene.blockedCount,
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
  const library = data['library_exclusion'];
  if (library === undefined || library === null) {
    throw new Error('Malformed Hermes response: library_exclusion is required');
  }
  requireLibraryExclusion(library, 'Hermes');
  const watched = data['watched_exclusion'];
  if (watched === undefined || watched === null) {
    throw new Error('Malformed Hermes response: watched_exclusion is required');
  }
  requireWatchedExclusion(watched, 'Hermes');
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
  // Disabled Jellyseerr is an explicit capability response and has no source snapshots.
  if (resource === 'Jellyseerr' && data['enabled'] === false) return;
  const library = data['library_exclusion'];
  if (library === undefined || library === null) {
    throw new Error(`Malformed ${resource} response: library_exclusion is required`);
  }
  requireLibraryExclusion(library, resource);
  const watched = data['watched_exclusion'];
  if (watched === undefined || watched === null) {
    throw new Error(`Malformed ${resource} response: watched_exclusion is required`);
  }
  requireWatchedExclusion(watched, resource);
}

function requireWatchedExclusion(value: unknown, resource: 'Hermes' | 'Jellyseerr' | 'Trakt'): void {
  if (value === undefined || value === null) return;
  if (!isRecord(value) || !['fresh', 'stale', 'unavailable'].includes(String(value['status']))) {
    throw new Error(`Malformed ${resource} response: watched_exclusion is invalid`);
  }
  if (value['last_successful_refresh_at'] !== null && typeof value['last_successful_refresh_at'] !== 'string') {
    throw new Error(`Malformed ${resource} response: watched_exclusion timestamp is invalid`);
  }
  if (typeof value['last_successful_refresh_at'] === 'string' && Number.isNaN(Date.parse(value['last_successful_refresh_at']))) {
    throw new Error(`Malformed ${resource} response: watched_exclusion timestamp is invalid`);
  }
}

function requireLibraryExclusion(value: unknown, resource: 'Hermes' | 'Jellyseerr' | 'Trakt'): void {
  if (!isRecord(value) || !['fresh', 'stale', 'unavailable'].includes(String(value['status']))) {
    throw new Error(`Malformed ${resource} response: library_exclusion is invalid`);
  }
  if (value['last_successful_refresh_at'] !== null && typeof value['last_successful_refresh_at'] !== 'string') {
    throw new Error(`Malformed ${resource} response: library_exclusion timestamp is invalid`);
  }
  if (typeof value['last_successful_refresh_at'] === 'string' && Number.isNaN(Date.parse(value['last_successful_refresh_at']))) {
    throw new Error(`Malformed ${resource} response: library_exclusion timestamp is invalid`);
  }
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
  if (!Number.isInteger(tmdbId) || tmdbId <= 0) {
    throw new Error(`Malformed Hermes response: member ${index} has invalid tmdb_id`);
  }
  const lifecycle = requireDiscoverLifecycle(raw, index, 'Hermes', type);
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
  const watchedOnTrakt = optionalBoolean(raw, 'watched_on_trakt', index, 'Hermes');
  const excludedReasonRaw = optionalNullableString(raw, 'excluded_reason', index, 'Hermes');
  if (
    excludedReasonRaw !== undefined &&
    excludedReasonRaw !== null &&
    excludedReasonRaw !== 'in_library' &&
    excludedReasonRaw !== 'watched_on_trakt'
  ) {
    throw new Error(`Malformed Hermes response: member ${index} has invalid excluded_reason`);
  }
  const jellyfinId = optionalNullableString(raw, 'jellyfin_id', index, 'Hermes');
  const posterPath = optionalNullableString(raw, 'poster_path', index, 'Hermes');
  const posterUrl = optionalNullableString(raw, 'poster_url', index, 'Hermes');
  const notes = optionalNullableString(raw, 'notes', index, 'Hermes');
  const rating = optionalNullableFiniteNumber(raw, 'rating', index, 'Hermes');
  const traktHistorySync = requireTraktHistorySync(raw['trakt_history_sync'], index, 'Hermes');

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
    excluded_reason: excludedReasonRaw,
    watched_on_trakt: watchedOnTrakt,
    jellyfin_id: jellyfinId,
    poster_path: posterPath,
    poster_url: posterUrl,
    added_at: addedAt,
    notes: notes ?? undefined,
    rating,
    trakt_history_sync: traktHistorySync,
    ...lifecycle,
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
  if (!Number.isInteger(tmdbId) || tmdbId <= 0) {
    throw new Error(`Malformed ${resource} response: member ${index} has invalid tmdb_id`);
  }
  const lifecycle = requireDiscoverLifecycle(raw, index, resource, type);

  const id = optionalNullableString(raw, 'id', index, resource) ?? undefined;
  const source = optionalNullableString(raw, 'source', index, resource) ?? undefined;
  const year = optionalNullableFiniteNumber(raw, 'year', index, resource);
  const traktSlug = optionalNullableString(raw, 'trakt_slug', index, resource);
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
    trakt_slug: traktSlug,
    overview,
    poster_url: posterUrl,
    rating,
    ...lifecycle,
  };
}

function requireDiscoverLifecycle(
  raw: Record<string, unknown>,
  index: number,
  resource: string,
  type: MediaStackDiscoverMediaTypeDto,
): {
  media_status: 'available' | 'requested' | 'processing' | 'tracked' | 'missing' | 'unknown';
  service: 'jellyfin' | 'radarr' | 'sonarr' | null;
  service_href: string | null;
  request_id: number | null;
  monitored: boolean | null;
} {
  const malformed = () => discoverLifecycleError(resource, index);
  const status = requireDiscoverLifecycleStatus(raw['media_status'], malformed);
  const service = requireDiscoverLifecycleService(raw['service'], malformed);
  const href = requireDiscoverLifecycleHref(raw['service_href'], malformed);
  const requestId = requireDiscoverLifecycleRequestId(raw['request_id'], malformed);
  const monitored = requireDiscoverLifecycleMonitored(raw['monitored'], malformed);
  requireDiscoverLifecycleConsistency(
    { status, service, href, requestId, monitored, type },
    malformed,
  );

  return {
    media_status: status,
    service,
    service_href: href,
    request_id: requestId,
    monitored,
  };
}

type DiscoverLifecycleStatus =
  | 'available'
  | 'requested'
  | 'processing'
  | 'tracked'
  | 'missing'
  | 'unknown';
type DiscoverLifecycleService = 'jellyfin' | 'radarr' | 'sonarr' | null;

function discoverLifecycleError(resource: string, index: number): never {
  throw new Error(`Malformed ${resource} response: member ${index} has invalid lifecycle`);
}

function requireDiscoverLifecycleStatus(
  value: unknown,
  malformed: () => never,
): DiscoverLifecycleStatus {
  if (
    value === 'available' ||
    value === 'requested' ||
    value === 'processing' ||
    value === 'tracked' ||
    value === 'missing' ||
    value === 'unknown'
  ) {
    return value;
  }
  return malformed();
}

function requireDiscoverLifecycleService(
  value: unknown,
  malformed: () => never,
): DiscoverLifecycleService {
  if (value === null || value === 'jellyfin' || value === 'radarr' || value === 'sonarr') {
    return value;
  }
  return malformed();
}

function requireDiscoverLifecycleHref(value: unknown, malformed: () => never): string | null {
  if (value === null) return null;
  return isSafeHttpLink(value) ? value : malformed();
}

function requireDiscoverLifecycleRequestId(
  value: unknown,
  malformed: () => never,
): number | null {
  if (value === null) return null;
  if (typeof value === 'number' && Number.isInteger(value) && value > 0) return value;
  return malformed();
}

function requireDiscoverLifecycleMonitored(
  value: unknown,
  malformed: () => never,
): boolean | null {
  if (value === null || typeof value === 'boolean') return value;
  return malformed();
}

function requireDiscoverLifecycleConsistency(
  value: {
    status: DiscoverLifecycleStatus;
    service: DiscoverLifecycleService;
    href: string | null;
    requestId: number | null;
    monitored: boolean | null;
    type: MediaStackDiscoverMediaTypeDto;
  },
  malformed: () => never,
): void {
  if (value.status === 'available') {
    if (value.service !== 'jellyfin' || value.requestId !== null || value.monitored !== null) {
      malformed();
    }
    return;
  }
  if (value.status === 'tracked') {
    const expectedService = value.type === 'movie' ? 'radarr' : 'sonarr';
    if (
      value.service !== expectedService ||
      typeof value.monitored !== 'boolean' ||
      value.requestId !== null
    ) {
      malformed();
    }
    return;
  }
  if (value.service !== null || value.href !== null || value.monitored !== null) malformed();
  if (
    value.status !== 'requested' &&
    value.status !== 'processing' &&
    value.requestId !== null
  ) {
    malformed();
  }
}

function isSafeHttpLink(value: unknown): value is string {
  if (typeof value !== 'string' || !value.trim() || /[\u0000-\u001f\u007f]/.test(value)) {
    return false;
  }
  try {
    const url = new URL(value);
    return (
      (url.protocol === 'http:' || url.protocol === 'https:') &&
      !url.username &&
      !url.password
    );
  } catch {
    return false;
  }
}

function requireTraktHistorySync(
  value: unknown,
  index: number,
  resource: string,
): { status: 'pending' | 'synced' | 'reconnect_required' | 'failed' } | undefined {
  if (value === undefined || value === null) {
    return undefined;
  }
  if (!isRecord(value)) {
    throw new Error(`Malformed ${resource} response: member ${index} has invalid trakt_history_sync`);
  }
  const status = value['status'];
  if (
    status === 'pending' ||
    status === 'synced' ||
    status === 'reconnect_required' ||
    status === 'failed'
  ) {
    return { status };
  }
  throw new Error(`Malformed ${resource} response: member ${index} has invalid trakt_history_sync`);
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

function optionalStringArray(
  raw: Record<string, unknown>,
  field: string,
  index: number,
  resource: string,
): string[] | undefined {
  const value = raw[field];
  if (value === undefined || value === null) return undefined;
  if (!Array.isArray(value) || value.some((entry) => typeof entry !== 'string')) {
    throw new Error(`Malformed ${resource} response: member ${index} has invalid ${field}`);
  }
  return value as string[];
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

/** Activity feed from GET /activity. */
export interface LiveActivityFeed {
  generatedAt?: string;
  sources?: { sonarr?: string; radarr?: string };
  items?: unknown[];
}

function activitySourceStatus(value: unknown): MediaStackActivitySourceStatusDto {
  if (value === undefined || value === null) return 'unconfigured';
  if (value === 'ok' || value === 'error' || value === 'unconfigured') return value;
  throw new Error('Malformed activity response: invalid sources status');
}

function requireLiveActivityItem(raw: unknown, index = 0): MediaStackActivityItemDto {
  if (!isRecord(raw)) {
    throw new Error(`Malformed activity response: member ${index} is not an object`);
  }
  const id = raw['id'];
  const title = raw['title'];
  const timestamp = raw['timestamp'];
  if (typeof id !== 'string' || !id.trim()) {
    throw new Error(`Malformed activity response: member ${index} is missing id`);
  }
  if (typeof title !== 'string' || !title.trim()) {
    throw new Error(`Malformed activity response: member ${index} is missing title`);
  }
  if (typeof timestamp !== 'string' || !timestamp.trim()) {
    throw new Error(`Malformed activity response: member ${index} is missing timestamp`);
  }
  const source = raw['source'];
  if (source !== 'sonarr' && source !== 'radarr') {
    throw new Error(`Malformed activity response: member ${index} has invalid source`);
  }
  const resolvedSource: MediaStackActivitySourceDto = source;
  const kind = raw['kind'];
  if (kind !== 'grabbed' && kind !== 'imported' && kind !== 'deleted' && kind !== 'failed') {
    throw new Error(`Malformed activity response: member ${index} has invalid kind`);
  }
  const resolvedKind: MediaStackActivityKindDto = kind;
  return {
    id,
    source: resolvedSource,
    kind: resolvedKind,
    title,
    subtitle: optionalString(raw, 'subtitle', index, 'activity') ?? '',
    timestamp,
    href: optionalNullableString(raw, 'href', index, 'activity') ?? null,
  };
}

/** Validate GET /activity envelopes; soft ok:false feeds keep per-source status. */
export function mapLiveActivityFeed(
  live: LiveActivityFeed & { ok?: boolean },
): MediaStackActivityFeedDto {
  return {
    ok: live.ok !== false,
    generatedAt: mapGeneratedAt(live.generatedAt, 'Malformed activity response'),
    sources: {
      sonarr: activitySourceStatus(live.sources?.sonarr),
      radarr: activitySourceStatus(live.sources?.radarr),
    },
    items: (live.items ?? []).map((item, index) => requireLiveActivityItem(item, index)),
  };
}
