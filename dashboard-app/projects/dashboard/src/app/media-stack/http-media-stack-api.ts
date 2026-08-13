import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { finalize, firstValueFrom, fromEvent, Observable, shareReplay, takeUntil } from 'rxjs';

import { environment } from '../../environments/environment';
import { ArrLibrary, CalendarEvent } from '../calendar/calendar.models';
import {
  DiscoverAction,
  DiscoverFeedback,
  DiscoverRequestPayload,
  ExternalDiscover,
  HermesDiscover,
  JellyseerrDiscoverKind,
  SubmitHermesFeedbackOptions,
  TraktDiscoverType,
} from '../discover/discover.models';
import { DownloadTorrent } from '../downloads/downloads.models';
import {
  LibraryItem,
  LibraryItemKind,
  LibraryListResult,
  LibraryStats,
  LibraryDeletePreview,
  LibraryDeleteResult,
  LibraryDeleteStepStatus,
  LibraryDeleteSteps,
} from '../library/library.models';
import { WatchNextResult } from '../library/watch-next.models';
import { RecentlyAvailableResult } from '../library/recently-available.models';
import { ActivityFeed } from '../activity/activity.models';
import { mapActivityFeed } from '../activity/activity-format';
import { AutomationService, AutomationSummary } from '../automation/automation.models';
import { CronLogs } from '../reports/reports.models';
import { StorageOverview } from '../storage/storage.models';
import { MediaStackApi } from './media-stack-api';
import { mapArrLibrary, mapCalendarEvent } from '../calendar/calendar-format';
import { mapAutomationSummary } from '../automation/automation-format';
import { mapCronLogs } from '../reports/reports-format';
import {
  mapDiscoverAction,
  mapExternalDiscover,
  mapHermesDiscover,
  toDiscoverRequestPayloadDto,
} from '../discover/discover-format';
import { mapLibraryItem, mapLibraryStats } from '../library/library-format';
import { mapWatchNextItem } from '../library/watch-next-format';
import { mapRecentlyAvailableResult } from '../library/recently-available-format';
import { mapTorrent } from '../downloads/downloads-format';
import { mapStorageOverview } from '../storage/storage-format';
import { MediaStackArrLibraryDto } from './wire/calendar';
import { MediaStackCronLogsDto } from './wire/cron';
import { MediaStackDiscoverActionDto, MediaStackExternalDiscoverDto, MediaStackHermesDiscoverDto } from './wire/discover';
import {
  LiveAutomationSummary,
  LiveActivityFeed,
  LiveJellyfinListResponse,
  LiveWatchNextListResponse,
  LiveRecentlyAvailableListResponse,
  mapLiveActivityFeed,
  mapLiveAutomationSummary,
  mapLiveJellyfinItem,
  mapLiveWatchNextItem,
  mapLiveRecentlyAvailableItem,
  mapLiveSystemResourcesDisk,
  mapLiveTorrent,
  requireExternalDiscoverPayload,
  requireHermesDiscoverPayload,
  requireLiveCalendarEvent,
} from './live-api.mappers';
import {
  OkEnvelope,
  OkEnvelopeRecord,
  isAbortError,
  isRecord,
  requireArrayField,
  requireCronLogsPayload,
  requireHardEnvelope,
  requireOkEnvelope,
  requireSoftEnvelope,
} from './http-response';

const DISCOVER_LOAD_ERROR = 'Discover is temporarily unavailable. Try again.';
const TRAKT_RECONNECT_ERROR = 'Trakt reconnect required';

/** Narrow validated envelopes to Record so require* payload helpers accept them. */
function requireEnvelopeRecord(data: OkEnvelope, fallback: string): OkEnvelopeRecord {
  if (!isRecord(data)) {
    throw new Error(fallback);
  }
  // OkEnvelope + Record index — same runtime object requireOkEnvelope already accepted.
  return data;
}

@Injectable()
export class HttpMediaStackApi implements MediaStackApi {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl.replace(/\/$/, '');
  /** Share concurrent identical GETs so stats/calendar/probes do not fan out duplicate traffic. */
  private readonly inFlightGets = new Map<string, Observable<unknown>>();

  listTorrents(signal?: AbortSignal): Promise<DownloadTorrent[]> {
    return this.getRaw<unknown>('/qbt/torrents', signal).then((data) => {
      const members = this.requireTorrentMembers(data);
      return members.map((item, index) => mapTorrent(mapLiveTorrent(item, index)));
    });
  }

  pauseAll(): Promise<void> {
    return this.postVoid('/stop-all');
  }

  resumeAll(): Promise<void> {
    return this.postVoid('/start-all');
  }

  pauseTorrent(id: string): Promise<void> {
    return this.postVoid('/qbt/torrents/stop', { id });
  }

  resumeTorrent(id: string): Promise<void> {
    return this.postVoid('/qbt/torrents/start', { id });
  }

  listCalendarEvents(signal?: AbortSignal): Promise<CalendarEvent[]> {
    return this.getHardEnvelope<OkEnvelope & { events?: unknown[] }>(
      '/sonarr/calendar',
      (data) => {
        requireArrayField(
          requireEnvelopeRecord(data, 'Malformed calendar response'),
          'events',
          'Malformed calendar response',
        );
      },
      signal,
    ).then((data) => {
      const events = data.events ?? [];
      return events.map((event, index) => mapCalendarEvent(requireLiveCalendarEvent(event, index)));
    });
  }

  getArrLibrary(signal?: AbortSignal): Promise<ArrLibrary> {
    return this.getSoftEnvelope<MediaStackArrLibraryDto>(
      '/arr/library',
      (data) => {
        if (!isRecord(data['series']) || !isRecord(data['movies'])) {
          throw new Error('Malformed arr library response');
        }
      },
      signal,
    ).then(mapArrLibrary);
  }

  async listLibraryItems(
    filter?: { kind?: LibraryItemKind },
    signal?: AbortSignal,
  ): Promise<LibraryListResult> {
    const kind = filter?.kind;
    if (kind === 'movie' || kind === 'series') {
      return this.listLibraryItemsByKind(kind, signal);
    }
    return this.listLibraryItemsMerged(signal);
  }

  setLibraryItemPlayed(id: string, played: boolean): Promise<{ played: boolean }> {
    return this.mutateHard<OkEnvelope & { played?: boolean }>(
      `/jellyfin/items/${encodeURIComponent(id)}/played`,
      'PATCH',
      { played },
      (envelope) => {
        if (typeof envelope.played !== 'boolean') {
          throw new Error('Malformed played response');
        }
      },
    ).then((envelope) => ({ played: envelope.played as boolean }));
  }

  previewLibraryItemDeletion(id: string): Promise<LibraryDeletePreview> {
    return this.getHardEnvelope<OkEnvelope & Partial<LibraryDeletePreview>>(
      `/library/items/${encodeURIComponent(id)}/delete-preview`,
      (envelope) => {
        this.validateDeletePreview(envelope);
      },
    ).then((envelope) => {
      const episodeCount =
        typeof envelope.episodeCount === 'number' && Number.isFinite(envelope.episodeCount)
          ? Math.floor(envelope.episodeCount)
          : null;
      const torrentCount =
        typeof envelope.torrentCount === 'number' && Number.isFinite(envelope.torrentCount)
          ? Math.floor(envelope.torrentCount)
          : 0;
      return {
        previewId: String(envelope.previewId),
        title: String(envelope.title),
        kind: envelope.kind === 'series' ? 'series' : 'movie',
        manager: envelope.manager === 'Sonarr' ? 'Sonarr' : 'Radarr',
        episodeCount,
        torrentCount,
        expiresAt: String(envelope.expiresAt),
      };
    });
  }

  async deleteLibraryItem(id: string, previewId: string): Promise<LibraryDeleteResult> {
    try {
      const data = await firstValueFrom(
        this.http.delete<unknown>(
          `${this.base}/library/items/${encodeURIComponent(id)}?previewId=${encodeURIComponent(previewId)}`,
        ),
      );
      return this.mapDeleteResult(requireSoftEnvelope(data, 'DELETE library item failed'));
    } catch (error) {
      if (error instanceof HttpErrorResponse && isRecord(error.error)) {
        return this.mapDeleteResult(
          requireSoftEnvelope(error.error, 'DELETE library item failed'),
        );
      }
      throw this.toError(error, 'DELETE library item failed');
    }
  }

  async listWatchNext(signal?: AbortSignal): Promise<WatchNextResult> {
    const data = await this.getRaw<LiveWatchNextListResponse>('/jellyfin/watch-next', signal);
    const envelope = requireSoftEnvelope<OkEnvelope & { items?: unknown }>(
      data,
      'Failed to list watch-next items',
      (value) => {
        requireArrayField(
          requireEnvelopeRecord(value, 'Malformed watch-next response'),
          'items',
          'Malformed watch-next response',
        );
      },
    );
    if (!envelope.ok) {
      throw new Error(envelope.error || 'Failed to list watch-next items');
    }
    const items = (data.items ?? []).map((item, index) =>
      mapWatchNextItem(mapLiveWatchNextItem(item, index)),
    );
    return { items };
  }

  async listRecentlyAvailable(limit?: number, signal?: AbortSignal): Promise<RecentlyAvailableResult> {
    const base = limit ?? 10;
    const safe = Number.isFinite(base) ? base : 10;
    const normalized = Math.max(1, Math.min(50, Math.floor(safe)));
    const data = await this.getRaw<LiveRecentlyAvailableListResponse>(
      `/jellyfin/recently-available?limit=${normalized}`,
      signal,
    );
    const envelope = requireSoftEnvelope<OkEnvelope & { items?: unknown }>(
      data,
      'Failed to list recently available items',
      (value) => {
        requireArrayField(
          requireEnvelopeRecord(value, 'Malformed recently-available response'),
          'items',
          'Malformed recently-available response',
        );
      },
    );
    if (!envelope.ok) {
      throw new Error(envelope.error || 'Failed to list recently available items');
    }
    const items = (data.items ?? []).map((item, index) =>
      mapLiveRecentlyAvailableItem(item, index),
    );
    return mapRecentlyAvailableResult(items);
  }

  async getActivity(limit = 20, signal?: AbortSignal): Promise<ActivityFeed> {
    const clamped = Number.isFinite(limit) ? Math.max(1, Math.min(50, Math.floor(limit))) : 20;
    const data = await this.getRaw<unknown>(`/activity?limit=${clamped}`, signal);
    const envelope = requireSoftEnvelope<OkEnvelope & LiveActivityFeed>(
      data,
      'Malformed activity response',
    );
    return mapActivityFeed(mapLiveActivityFeed(envelope));
  }

  private async listLibraryItemsByKind(
    kind: LibraryItemKind,
    signal?: AbortSignal,
  ): Promise<LibraryListResult> {
    const jellyfinKind = kind === 'movie' ? 'movies' : 'series';
    const data = await this.fetchJellyfinList(jellyfinKind, signal);
    const items = this.mapJellyfinListItems(data, jellyfinKind);
    const total = jellyfinListTotal(data, items.length);
    return {
      items,
      availability: 'complete',
      movieCount: kind === 'movie' ? total : 0,
      seriesCount: kind === 'series' ? total : 0,
    };
  }

  private async listLibraryItemsMerged(signal?: AbortSignal): Promise<LibraryListResult> {
    const [moviesResult, seriesResult] = await Promise.allSettled([
      this.fetchJellyfinList('movies', signal),
      this.fetchJellyfinList('series', signal),
    ]);

    this.throwIfLibraryListAborted(signal, moviesResult, seriesResult);

    const moviesData = moviesResult.status === 'fulfilled' ? moviesResult.value : null;
    const seriesData = seriesResult.status === 'fulfilled' ? seriesResult.value : null;
    const movies = moviesData ? this.mapJellyfinListItems(moviesData, 'movies') : [];
    const series = seriesData ? this.mapJellyfinListItems(seriesData, 'series') : [];

    if (moviesResult.status === 'rejected' && seriesResult.status === 'rejected') {
      throw moviesResult.reason instanceof Error
        ? moviesResult.reason
        : new Error('Failed to list library items');
    }

    return {
      items: [...movies, ...series],
      availability:
        moviesResult.status === 'fulfilled' && seriesResult.status === 'fulfilled'
          ? 'complete'
          : 'partial',
      movieCount: moviesData !== null ? jellyfinListTotal(moviesData, movies.length) : undefined,
      seriesCount: seriesData !== null ? jellyfinListTotal(seriesData, series.length) : undefined,
    };
  }

  private throwIfLibraryListAborted(
    signal: AbortSignal | undefined,
    moviesResult: PromiseSettledResult<LiveJellyfinListResponse>,
    seriesResult: PromiseSettledResult<LiveJellyfinListResponse>,
  ): void {
    if (signal?.aborted) {
      throw new DOMException('The operation was aborted.', 'AbortError');
    }
    const abortedResult = [moviesResult, seriesResult].find(
      (result): result is PromiseRejectedResult =>
        result.status === 'rejected' && isAbortError(result.reason),
    );
    if (!abortedResult) return;
    throw abortedResult.reason instanceof Error
      ? abortedResult.reason
      : new DOMException('The operation was aborted.', 'AbortError');
  }

  async getAutomationSummary(signal?: AbortSignal): Promise<AutomationSummary> {
    const probesPromise = this.probeSidebarServices(signal);
    try {
      const data = await this.getRaw<unknown>('/automation/summary', signal);
      const envelope = requireSoftEnvelope<OkEnvelope & Partial<LiveAutomationSummary>>(
        data,
        'Malformed automation summary response',
        (value) => {
          const record = requireEnvelopeRecord(value, 'Malformed automation summary response');
          if (
            !['sonarr', 'radarr', 'prowlarr', 'bazarr'].some((key) => isRecord(record[key]))
          ) {
            throw new Error('Malformed automation summary response');
          }
        },
      );
      const summary = mapAutomationSummary(mapLiveAutomationSummary(envelope));
      const extras = await probesPromise;
      return {
        ...summary,
        services: [...summary.services, ...extras],
      };
    } catch (error) {
      // Settle probes so a failed summary does not leave in-flight sidebar checks hanging.
      await probesPromise.catch(() => undefined);
      throw error;
    }
  }

  /** Soft-probe Jellyfin / qBittorrent so sidebar dots are API-driven (not stuck unknown). */
  private async probeSidebarServices(signal?: AbortSignal): Promise<AutomationService[]> {
    const [jellyfin, qbittorrent] = await Promise.all([
      this.probeReachableService('jellyfin', 'Jellyfin', '/jellyfin/series', signal),
      this.probeReachableService('qbittorrent', 'qBittorrent', '/qbt/torrents', signal),
    ]);
    return [jellyfin, qbittorrent];
  }

  private async probeReachableService(
    id: string,
    name: string,
    path: string,
    signal?: AbortSignal,
  ): Promise<AutomationService> {
    try {
      await this.getRaw<unknown>(path, signal);
      return { id, name, status: 'healthy', detail: 'Reachable', latencyMs: null };
    } catch (error) {
      if (signal?.aborted || isAbortError(error)) {
        throw error;
      }
      return {
        id,
        name,
        status: 'down',
        detail: error instanceof Error ? error.message : 'Unavailable',
        latencyMs: null,
      };
    }
  }

  getStorageOverview(signal?: AbortSignal): Promise<StorageOverview> {
    return this.getRaw<unknown>('/system/resources', signal).then((data) => {
      const envelope = requireSoftEnvelope<OkEnvelope & { generatedAt?: string; disk?: unknown }>(
        data,
        'Malformed system resources response',
      );
      const disk = envelope.disk;
      if (!disk) {
        throw new Error('Malformed system resources response: missing disk');
      }
      const volume = mapLiveSystemResourcesDisk(disk);
      return mapStorageOverview({
        generatedAt: envelope.generatedAt,
        volumes: [volume],
      });
    });
  }

  async getLibraryStats(signal?: AbortSignal): Promise<LibraryStats> {
    const [movies, series] = await Promise.all([
      this.fetchJellyfinCount('movies', signal),
      this.fetchJellyfinCount('series', signal),
    ]);

    return mapLibraryStats({
      movies,
      series,
    });
  }

  listCronLogs(signal?: AbortSignal): Promise<CronLogs> {
    return this.getSoftEnvelope<MediaStackCronLogsDto>(
      '/cron/logs',
      (data) => {
        requireCronLogsPayload(requireEnvelopeRecord(data, 'Malformed cron logs response'));
      },
      signal,
    ).then(mapCronLogs);
  }

  listHermesRecommendations(signal?: AbortSignal): Promise<HermesDiscover> {
    return this.getSoftEnvelope<MediaStackHermesDiscoverDto>(
      '/discover/hermes',
      (data) => {
        requireHermesDiscoverPayload(requireEnvelopeRecord(data, 'Malformed Hermes response'));
      },
      signal,
    ).then(mapHermesDiscover);
  }

  submitHermesFeedback(
    id: string,
    feedback: DiscoverFeedback,
    options?: SubmitHermesFeedbackOptions,
  ): Promise<DiscoverAction> {
    return this.mutateSoft(`/discover/hermes/${encodeURIComponent(id)}`, 'PATCH', {
      status: feedback,
      notes: options?.notes,
      ...(options?.confirmAllAired ? { confirm_all_aired: true } : {}),
    });
  }

  requestHermesMore(): Promise<DiscoverAction> {
    return this.mutateSoft('/discover/hermes/request-more', 'POST');
  }

  listJellyseerrDiscover(kind: JellyseerrDiscoverKind, signal?: AbortSignal): Promise<ExternalDiscover> {
    return this.getSoftEnvelope<MediaStackExternalDiscoverDto>(
      `/discover/jellyseerr?kind=${kind}`,
      (data) => {
        requireExternalDiscoverPayload(
          requireEnvelopeRecord(data, 'Malformed Jellyseerr response'),
          'Jellyseerr',
        );
      },
      signal,
    ).then(mapExternalDiscover);
  }

  listTraktDiscover(type: TraktDiscoverType, signal?: AbortSignal): Promise<ExternalDiscover> {
    return this.getSoftEnvelope<MediaStackExternalDiscoverDto>(
      `/discover/trakt?type=${type}`,
      (data) => {
        requireExternalDiscoverPayload(
          requireEnvelopeRecord(data, 'Malformed Trakt response'),
          'Trakt',
        );
      },
      signal,
    ).then(mapExternalDiscover);
  }

  requestMedia(payload: DiscoverRequestPayload): Promise<DiscoverAction> {
    return this.mutateSoft('/discover/request', 'POST', toDiscoverRequestPayloadDto(payload));
  }

  private mapJellyfinListItems(
    data: LiveJellyfinListResponse,
    kind: 'movies' | 'series',
  ): LibraryItem[] {
    const itemKind: LibraryItemKind = kind === 'movies' ? 'movie' : 'series';
    return (data.items ?? [])
      .map((item, index) => mapLibraryItem(mapLiveJellyfinItem(item, itemKind, index)))
      .filter((item): item is LibraryItem => item !== null);
  }

  /** Prefer backend `total` when present so stats avoid mapping every library item. */
  private async fetchJellyfinCount(
    kind: 'movies' | 'series',
    signal?: AbortSignal,
  ): Promise<number> {
    const data = await this.fetchJellyfinList(kind, signal);
    return jellyfinListTotal(data, this.mapJellyfinListItems(data, kind).length);
  }

  private async fetchJellyfinList(
    kind: 'movies' | 'series',
    signal?: AbortSignal,
  ): Promise<LiveJellyfinListResponse> {
    const data = await this.getRaw<LiveJellyfinListResponse>(`/jellyfin/${kind}`, signal);
    const envelope = requireSoftEnvelope<OkEnvelope & { items?: unknown }>(
      data,
      `Failed to list jellyfin ${kind}`,
      (value) => {
        requireArrayField(
          requireEnvelopeRecord(value, `Malformed jellyfin ${kind} response`),
          'items',
          `Malformed jellyfin ${kind} response`,
        );
      },
    );
    if (!envelope.ok) {
      throw new Error(envelope.error || `Failed to list jellyfin ${kind}`);
    }
    return data;
  }

  private async getRaw<T>(path: string, signal?: AbortSignal): Promise<T> {
    if (signal?.aborted) {
      throw new DOMException('The operation was aborted.', 'AbortError');
    }

    let shared$ = this.inFlightGets.get(path) as Observable<T> | undefined;
    if (!shared$) {
      // Concurrent callers share one in-flight GET per path (shareReplay + refCount).
      // Aborting one waiter unsubscribes that waiter only; the shared XHR continues while
      // other waiters remain. The last waiter's abort tears down the shared request.
      // finalize before shareReplay so cleanup runs when the last waiter unsubscribes.
      shared$ = this.http.get<T>(`${this.base}${path}`).pipe(
        finalize(() => {
          if (this.inFlightGets.get(path) === shared$) {
            this.inFlightGets.delete(path);
          }
        }),
        shareReplay({ bufferSize: 1, refCount: true }),
      );
      this.inFlightGets.set(path, shared$);
    }

    try {
      const request$ = signal
        ? shared$.pipe(takeUntil(fromEvent(signal, 'abort')))
        : shared$;
      return await firstValueFrom(request$);
    } catch (error) {
      if (signal?.aborted) {
        throw new DOMException('The operation was aborted.', 'AbortError');
      }
      const isDiscoverBrowse = path.startsWith('/discover/jellyseerr') || path.startsWith('/discover/trakt');
      throw this.toError(error, isDiscoverBrowse ? DISCOVER_LOAD_ERROR : `GET ${path} failed`, isDiscoverBrowse);
    }
  }

  /**
   * Accept bare torrent arrays or successful envelopes with a torrents array.
   * Soft `{ ok: false }` throws with the backend message; malformed shapes reject separately.
   */
  private requireTorrentMembers(data: unknown): unknown[] {
    if (Array.isArray(data)) {
      return data;
    }
    const envelope = requireOkEnvelope(data, 'Malformed torrents response');
    if (!envelope.ok) {
      throw new Error(envelope.error || 'Failed to list torrents');
    }
    return requireArrayField(envelope, 'torrents', 'Malformed torrents response');
  }

  /** Return envelope DTOs when valid so facades can read ok/error (mock parity). */
  private async getSoftEnvelope<T extends OkEnvelope>(
    path: string,
    validate?: (envelope: T) => void,
    signal?: AbortSignal,
  ): Promise<T> {
    const data = await this.getRaw<unknown>(path, signal);
    return requireSoftEnvelope<T>(data, `Malformed response for GET ${path}`, validate);
  }

  /** Reject malformed payloads and when ok === false. */
  private async getHardEnvelope<T extends OkEnvelope>(
    path: string,
    validate?: (envelope: T) => void,
    signal?: AbortSignal,
  ): Promise<T> {
    const data = await this.getRaw<unknown>(path, signal);
    const envelope = requireHardEnvelope(data, `GET ${path} failed`) as T;
    validate?.(envelope);
    return envelope;
  }

  /** Void mutations: malformed, ok:false, and transport errors reject. */
  private async postVoid(path: string, body?: unknown): Promise<void> {
    try {
      const data = await firstValueFrom(this.http.post<unknown>(`${this.base}${path}`, body ?? null));
      const envelope = requireOkEnvelope(data, `Malformed response for POST ${path}`);
      if (!envelope.ok) {
        throw new Error(envelope.error || `POST ${path} failed`);
      }
    } catch (error) {
      throw this.toError(error, `POST ${path} failed`);
    }
  }

  /**
   * Discover/action mutations: HTTP 200 with ok:false returns the action so facades
   * can surface result.error. Null/malformed bodies and transport failures reject.
   */
  private async mutateSoft(
    path: string,
    method: 'POST' | 'PATCH',
    body?: unknown,
  ): Promise<DiscoverAction> {
    try {
      const data = await firstValueFrom(
        method === 'PATCH'
          ? this.http.patch<unknown>(`${this.base}${path}`, body ?? null)
          : this.http.post<unknown>(`${this.base}${path}`, body ?? null),
      );
      return mapDiscoverAction(
        requireSoftEnvelope<MediaStackDiscoverActionDto>(
          data,
          `Malformed response for ${method} ${path}`,
        ),
      );
    } catch (error) {
      if (error instanceof HttpErrorResponse) {
        const body: unknown = error.error;
        if (isRecord(body) && typeof body['ok'] === 'boolean') {
          return mapDiscoverAction(
            requireSoftEnvelope<MediaStackDiscoverActionDto>(
              body,
              `Malformed response for ${method} ${path}`,
            ),
          );
        }
      }
      throw this.toError(error, `${method} ${path} failed`);
    }
  }

  private async mutateHard<T extends OkEnvelope>(
    path: string,
    method: 'PATCH' | 'POST',
    body?: unknown,
    validate?: (envelope: T) => void,
  ): Promise<T> {
    try {
      const data = await firstValueFrom(
        method === 'PATCH'
          ? this.http.patch<unknown>(`${this.base}${path}`, body ?? null)
          : this.http.post<unknown>(`${this.base}${path}`, body ?? null),
      );
      const envelope = requireHardEnvelope(data, `${method} ${path} failed`) as T;
      validate?.(envelope);
      return envelope;
    } catch (error) {
      throw this.toError(error, `${method} ${path} failed`);
    }
  }

  private validateDeletePreview(envelope: OkEnvelope & Partial<LibraryDeletePreview>): void {
    if (typeof envelope.previewId !== 'string' || !envelope.previewId.trim()) {
      throw new Error('Malformed delete preview response');
    }
    if (typeof envelope.title !== 'string' || !envelope.title.trim()) {
      throw new Error('Malformed delete preview response');
    }
    if (envelope.kind !== 'movie' && envelope.kind !== 'series') {
      throw new Error('Malformed delete preview response');
    }
    if (envelope.manager !== 'Radarr' && envelope.manager !== 'Sonarr') {
      throw new Error('Malformed delete preview response');
    }
    if (typeof envelope.torrentCount !== 'number' || !Number.isFinite(envelope.torrentCount)) {
      throw new Error('Malformed delete preview response');
    }
    if (typeof envelope.expiresAt !== 'string' || !envelope.expiresAt.trim()) {
      throw new Error('Malformed delete preview response');
    }
    if (
      envelope.episodeCount != null &&
      (typeof envelope.episodeCount !== 'number' || !Number.isFinite(envelope.episodeCount))
    ) {
      throw new Error('Malformed delete preview response');
    }
  }

  private mapDeleteResult(data: OkEnvelope & Partial<LibraryDeleteResult>): LibraryDeleteResult {
    let jellyfinRefresh: 'ok' | 'pending' | undefined;
    if (data.jellyfinRefresh === 'pending') {
      jellyfinRefresh = 'pending';
    } else if (data.jellyfinRefresh === 'ok') {
      jellyfinRefresh = 'ok';
    }

    return {
      ok: data.ok,
      removed: data.removed === true,
      torrentCount:
        typeof data.torrentCount === 'number' && Number.isFinite(data.torrentCount)
          ? Math.floor(data.torrentCount)
          : 0,
      jellyfinRefresh,
      warning: typeof data.warning === 'string' ? data.warning : null,
      partial: data.partial === true,
      error: typeof data.error === 'string' ? data.error : undefined,
      steps: mapLibraryDeleteSteps(data.steps),
    };
  }

  private toError(error: unknown, fallback: string, safeDiscoverError = false): Error {
    if (error instanceof HttpErrorResponse) {
      const body: unknown = error.error;
      if (isRecord(body) && body['code'] === 'reconnect_required') {
        const mapped = new Error(TRAKT_RECONNECT_ERROR);
        Object.assign(mapped, { code: 'reconnect_required' as const });
        return mapped;
      }
      if (isRecord(body) && typeof body['error'] === 'string' && body['error'].trim()) {
        return new Error(safeDiscoverError ? fallback : body['error']);
      }
      if (typeof body === 'string' && body.trim()) {
        return new Error(safeDiscoverError ? fallback : body);
      }
      return new Error(error.message || `HTTP ${error.status}` || fallback);
    }
    if (error instanceof Error) {
      return error;
    }
    return new Error(fallback);
  }
}

function jellyfinListTotal(data: LiveJellyfinListResponse, mappedLength: number): number {
  const total = data.total;
  if (typeof total === 'number' && Number.isFinite(total) && total >= 0) {
    return Math.floor(total);
  }
  return mappedLength;
}

function mapLibraryDeleteSteps(raw: unknown): LibraryDeleteSteps | undefined {
  if (!isRecord(raw)) return undefined;
  const torrents = asLibraryDeleteStep(raw['torrents']);
  const library = asLibraryDeleteStep(raw['library']);
  const jellyfin = asLibraryDeleteStep(raw['jellyfin']);
  if (!torrents || !library || !jellyfin) return undefined;
  return { torrents, library, jellyfin };
}

function asLibraryDeleteStep(value: unknown): LibraryDeleteStepStatus | undefined {
  if (value === 'ok' || value === 'skipped' || value === 'failed' || value === 'pending') {
    return value;
  }
  return undefined;
}
