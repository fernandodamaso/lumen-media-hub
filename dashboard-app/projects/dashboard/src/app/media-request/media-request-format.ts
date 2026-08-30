import { DiscoverAction } from '../discover/discover.models';
import {
  MediaLifecycleService,
  MediaLifecycleStatus,
  MediaSearchItem,
  MediaSearchResult,
  MediaSourceHealth,
  TvSeason,
  TvSeasonCollection,
} from './media-request.models';
import { isRecord } from '../media-stack/http-response';
import {
  MediaStackMediaRequestActionDto,
  MediaStackMediaSearchDto,
  MediaStackMediaSearchItemDto,
  MediaStackTvSeasonCollectionDto,
  MediaStackTvSeasonDto,
} from '../media-stack/wire/media';

const SEARCH_ERROR = 'Malformed media search response';
const SEASONS_ERROR = 'Malformed TV seasons response';
const REQUEST_ERROR = 'Malformed media request response';
const MEDIA_STATUSES = new Set<MediaLifecycleStatus>([
  'available',
  'requested',
  'processing',
  'tracked',
  'missing',
  'unknown',
]);
const SOURCE_HEALTH = new Set<MediaSourceHealth>([
  'fresh',
  'stale',
  'unavailable',
  'disabled',
]);
const SOURCE_NAMES = new Set(['jellyseerr', 'jellyfin', 'radarr', 'sonarr']);

export function mapMediaSearchResult(value: unknown): MediaSearchResult {
  const raw = requireRecord(value, SEARCH_ERROR);
  if (typeof raw['ok'] !== 'boolean') fail(SEARCH_ERROR);
  const availability = raw['availability'];
  if (
    availability !== 'available' &&
    availability !== 'disabled' &&
    availability !== 'unavailable'
  ) {
    fail(SEARCH_ERROR);
  }

  const sources = mapSearchSources(raw['sources']);

  const itemsRaw = raw['items'];
  if (!Array.isArray(itemsRaw)) fail(SEARCH_ERROR);
  const items = itemsRaw.map((item) => mapSearchItem(item));
  const error = optionalNonEmptyString(raw['error'], SEARCH_ERROR);

  requireSearchEnvelopeConsistency(raw['ok'], availability, sources, items, error);

  const mapped: MediaStackMediaSearchDto = {
    ok: raw['ok'],
    availability,
    sources,
    items,
    error,
  };
  return mapped;
}

function mapSearchSources(value: unknown): MediaSearchResult['sources'] {
  const sourcesRaw = requireRecord(value, SEARCH_ERROR);
  const sources: MediaSearchResult['sources'] = {};
  for (const [source, health] of Object.entries(sourcesRaw)) {
    if (!SOURCE_NAMES.has(source) || !SOURCE_HEALTH.has(health as MediaSourceHealth)) {
      fail(SEARCH_ERROR);
    }
    sources[source as keyof MediaSearchResult['sources']] = health as MediaSourceHealth;
  }
  if (!sources.jellyseerr) fail(SEARCH_ERROR);
  return sources;
}

function requireSearchEnvelopeConsistency(
  ok: boolean,
  availability: MediaSearchResult['availability'],
  sources: MediaSearchResult['sources'],
  items: MediaSearchItem[],
  error: string | undefined,
): void {
  if (!ok) {
    if (
      availability !== 'unavailable' ||
      sources.jellyseerr !== 'unavailable' ||
      items.length > 0 ||
      !error
    ) {
      fail(SEARCH_ERROR);
    }
    return;
  }
  if (availability === 'unavailable' || error !== undefined) fail(SEARCH_ERROR);
  if (availability === 'available' && sources.jellyseerr !== 'fresh') fail(SEARCH_ERROR);
  if (
    availability === 'disabled' &&
    (sources.jellyseerr !== 'disabled' || items.length > 0)
  ) {
    fail(SEARCH_ERROR);
  }
}

export function mapTvSeasonCollection(
  value: unknown,
  expectedTmdbId: number,
): TvSeasonCollection {
  const raw = requireRecord(value, SEASONS_ERROR);
  if (raw['ok'] !== true) fail(SEASONS_ERROR);
  const tmdbId = requirePositiveInteger(raw['tmdbId'], SEASONS_ERROR);
  if (tmdbId !== expectedTmdbId) fail(SEASONS_ERROR);
  const title = requireNonEmptyString(raw['title'], SEASONS_ERROR);
  if (!Array.isArray(raw['seasons'])) fail(SEASONS_ERROR);

  const seen = new Set<number>();
  const seasons = raw['seasons'].map((season) => mapSeason(season, seen));
  seasons.sort((left, right) => left.seasonNumber - right.seasonNumber);
  const mapped: MediaStackTvSeasonCollectionDto = {
    ok: true,
    tmdbId,
    title,
    seasons,
  };
  return { tmdbId: mapped.tmdbId, title: mapped.title, seasons: mapped.seasons };
}

export function mapMediaRequestAction(value: unknown): DiscoverAction {
  const raw = requireRecord(value, REQUEST_ERROR);
  if (typeof raw['ok'] !== 'boolean') fail(REQUEST_ERROR);
  if (!raw['ok']) {
    return {
      ok: false,
      error: requireNonEmptyString(raw['error'], REQUEST_ERROR),
    };
  }

  const requestStatus = raw['request_status'];
  if (requestStatus !== 'requested' && requestStatus !== 'processing') {
    fail(REQUEST_ERROR);
  }
  const partialSuccess = requireBoolean(raw['partial_success'], REQUEST_ERROR);
  const requestId = requirePositiveInteger(raw['jellyseerr_request_id'], REQUEST_ERROR);
  const alreadyRequested = requireBoolean(raw['already_requested'], REQUEST_ERROR);
  const dashboardStatePersisted = requireBoolean(
    raw['dashboard_state_persisted'],
    REQUEST_ERROR,
  );
  const reconciliationQueued = requireBoolean(raw['reconciliation_queued'], REQUEST_ERROR);
  const message = requireNonEmptyString(raw['message'], REQUEST_ERROR);

  const mapped: MediaStackMediaRequestActionDto = {
    ok: true,
    partial_success: partialSuccess,
    jellyseerr_request_id: requestId,
    request_status: requestStatus,
    already_requested: alreadyRequested,
    dashboard_state_persisted: dashboardStatePersisted,
    reconciliation_queued: reconciliationQueued,
    message,
  };
  return mapped;
}

function mapSearchItem(value: unknown): MediaSearchItem {
  const raw = requireRecord(value, SEARCH_ERROR);
  const type = raw['type'];
  if (type !== 'movie' && type !== 'tv') fail(SEARCH_ERROR);
  const tmdbId = requirePositiveInteger(raw['tmdbId'], SEARCH_ERROR);
  const identity = requireNonEmptyString(raw['identity'], SEARCH_ERROR);
  if (identity !== `${type}:${tmdbId}`) fail(SEARCH_ERROR);
  const title = requireNonEmptyString(raw['title'], SEARCH_ERROR);
  const year = requireYear(raw['year']);
  const overview = typeof raw['overview'] === 'string' ? raw['overview'] : fail(SEARCH_ERROR);
  const posterUrl = requireSafeNullableLink(raw['posterUrl'], SEARCH_ERROR);
  const status = raw['status'];
  if (!MEDIA_STATUSES.has(status as MediaLifecycleStatus)) fail(SEARCH_ERROR);
  const service = requireService(raw['service']);
  const serviceHref = requireSafeNullableLink(raw['serviceHref'], SEARCH_ERROR);
  const requestId = requireNullablePositiveInteger(raw['requestId'], SEARCH_ERROR);
  const monitored = requireNullableBoolean(raw['monitored'], SEARCH_ERROR);
  const jellyfinId = optionalNonEmptyString(raw['jellyfinId'], SEARCH_ERROR);

  requireLifecycleConsistency({
    type,
    status: status as MediaLifecycleStatus,
    service,
    serviceHref,
    requestId,
    monitored,
    jellyfinId,
  });

  const mapped: MediaStackMediaSearchItemDto = {
    identity,
    type,
    tmdbId,
    title,
    year,
    overview,
    posterUrl,
    status: status as MediaLifecycleStatus,
    service,
    serviceHref,
    requestId,
    monitored,
    ...(jellyfinId ? { jellyfinId } : {}),
  };
  return mapped;
}

function requireLifecycleConsistency(value: {
  type: 'movie' | 'tv';
  status: MediaLifecycleStatus;
  service: MediaLifecycleService;
  serviceHref: string | null;
  requestId: number | null;
  monitored: boolean | null;
  jellyfinId?: string;
}): void {
  if (value.status === 'available') {
    if (
      value.service !== 'jellyfin' ||
      !value.jellyfinId ||
      value.requestId !== null ||
      value.monitored !== null
    ) {
      fail(SEARCH_ERROR);
    }
    return;
  }
  if (value.status === 'tracked') {
    const expected = value.type === 'movie' ? 'radarr' : 'sonarr';
    if (
      value.service !== expected ||
      typeof value.monitored !== 'boolean' ||
      value.requestId !== null ||
      value.jellyfinId
    ) {
      fail(SEARCH_ERROR);
    }
    return;
  }
  if (
    value.service !== null ||
    value.serviceHref !== null ||
    value.monitored !== null ||
    value.jellyfinId
  ) {
    fail(SEARCH_ERROR);
  }
  if (
    value.status !== 'requested' &&
    value.status !== 'processing' &&
    value.requestId !== null
  ) {
    fail(SEARCH_ERROR);
  }
}

function mapSeason(value: unknown, seen: Set<number>): TvSeason {
  const raw = requireRecord(value, SEASONS_ERROR);
  const seasonNumber = raw['seasonNumber'];
  if (
    typeof seasonNumber !== 'number' ||
    !Number.isInteger(seasonNumber) ||
    seasonNumber < 0 ||
    seen.has(seasonNumber)
  ) {
    fail(SEASONS_ERROR);
  }
  seen.add(seasonNumber);
  const name = requireNonEmptyString(raw['name'], SEASONS_ERROR);
  const episodeCount = raw['episodeCount'];
  if (
    typeof episodeCount !== 'number' ||
    !Number.isInteger(episodeCount) ||
    episodeCount < 0
  ) {
    fail(SEASONS_ERROR);
  }
  const airDate = raw['airDate'];
  if (airDate !== null && !isIsoDate(airDate)) fail(SEASONS_ERROR);
  const mapped: MediaStackTvSeasonDto = { seasonNumber, name, episodeCount, airDate };
  return mapped;
}

function requireRecord(value: unknown, message: string): Record<string, unknown> {
  if (!isRecord(value)) fail(message);
  return value;
}

function requirePositiveInteger(value: unknown, message: string): number {
  if (typeof value !== 'number' || !Number.isInteger(value) || value <= 0) fail(message);
  return value;
}

function requireNullablePositiveInteger(value: unknown, message: string): number | null {
  if (value === undefined || value === null) return null;
  return requirePositiveInteger(value, message);
}

function requireNullableBoolean(value: unknown, message: string): boolean | null {
  if (value === undefined || value === null) return null;
  return requireBoolean(value, message);
}

function requireBoolean(value: unknown, message: string): boolean {
  if (typeof value !== 'boolean') fail(message);
  return value;
}

function requireNonEmptyString(value: unknown, message: string): string {
  if (typeof value !== 'string' || !value.trim()) fail(message);
  return value.trim();
}

function optionalNonEmptyString(value: unknown, message: string): string | undefined {
  if (value === undefined) return undefined;
  return requireNonEmptyString(value, message);
}

function requireYear(value: unknown): number | null {
  if (value === null) return null;
  if (
    typeof value !== 'number' ||
    !Number.isInteger(value) ||
    value <= 0 ||
    value > 9999
  ) {
    fail(SEARCH_ERROR);
  }
  return value;
}

function requireService(value: unknown): MediaLifecycleService {
  if (value === null || value === 'jellyfin' || value === 'radarr' || value === 'sonarr') {
    return value;
  }
  return fail(SEARCH_ERROR);
}

function requireSafeNullableLink(value: unknown, message: string): string | null {
  if (value === null) return null;
  if (typeof value !== 'string' || !value.trim() || /[\u0000-\u001f\u007f]/.test(value)) {
    fail(message);
  }
  try {
    const url = new URL(value);
    if ((url.protocol !== 'http:' && url.protocol !== 'https:') || url.username || url.password) {
      fail(message);
    }
  } catch {
    fail(message);
  }
  return value;
}

function isIsoDate(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split('-').map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return (
    parsed.getUTCFullYear() === year &&
    parsed.getUTCMonth() === month - 1 &&
    parsed.getUTCDate() === day
  );
}

function fail(message: string): never {
  throw new Error(message);
}
