import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom, fromEvent, takeUntil } from 'rxjs';

import { environment } from '../../environments/environment';
import { ArrLibrary, CalendarEvent } from '../calendar/calendar.models';
import {
  DiscoverAction,
  DiscoverFeedback,
  DiscoverRequestPayload,
  ExternalDiscover,
  HermesDiscover,
  JellyseerrDiscoverKind,
  TraktDiscoverType,
} from '../discover/discover.models';
import { DownloadTorrent } from '../downloads/downloads.models';
import {
  LibraryItem,
  LibraryItemKind,
  LibraryListResult,
  LibraryStats,
} from '../library/library.models';
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
import { mapTorrent } from '../downloads/downloads-format';
import { mapStorageOverview } from '../storage/storage-format';
import { MediaStackArrLibraryDto } from './wire/calendar';
import { MediaStackCronLogsDto } from './wire/cron';
import { MediaStackDiscoverActionDto, MediaStackExternalDiscoverDto, MediaStackHermesDiscoverDto } from './wire/discover';
import {
  LiveAutomationSummary,
  LiveJellyfinListResponse,
  mapLiveAutomationSummary,
  mapLiveJellyfinItem,
  mapLiveSystemResourcesDisk,
  mapLiveTorrent,
  requireExternalDiscoverPayload,
  requireHermesDiscoverPayload,
  requireLiveCalendarEvent,
} from './live-api.mappers';
import {
  OkEnvelope,
  isAbortError,
  isRecord,
  requireArrayField,
  requireCronLogsPayload,
  requireHardEnvelope,
  requireOkEnvelope,
  requireSoftEnvelope,
} from './http-response';

@Injectable()
export class HttpMediaStackApi implements MediaStackApi {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl.replace(/\/$/, '');

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
        requireArrayField(data as unknown as Record<string, unknown>, 'events', 'Malformed calendar response');
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

    // Filtered loads: surface the requested kind's failure instead of masking as empty.
    if (kind === 'movie') {
      const items = await this.fetchJellyfinKind('movies', signal);
      return { items, availability: 'complete' };
    }
    if (kind === 'series') {
      const items = await this.fetchJellyfinKind('series', signal);
      return { items, availability: 'complete' };
    }

    const [moviesResult, seriesResult] = await Promise.allSettled([
      this.fetchJellyfinKind('movies', signal),
      this.fetchJellyfinKind('series', signal),
    ]);

    // Cancellation must not look like one-source partial availability.
    if (signal?.aborted) {
      throw new DOMException('The operation was aborted.', 'AbortError');
    }
    const abortedResult = [moviesResult, seriesResult].find(
      (result): result is PromiseRejectedResult =>
        result.status === 'rejected' && isAbortError(result.reason),
    );
    if (abortedResult) {
      throw abortedResult.reason instanceof Error
        ? abortedResult.reason
        : new DOMException('The operation was aborted.', 'AbortError');
    }

    const movies = moviesResult.status === 'fulfilled' ? moviesResult.value : [];
    const series = seriesResult.status === 'fulfilled' ? seriesResult.value : [];

    if (moviesResult.status === 'rejected' && seriesResult.status === 'rejected') {
      throw moviesResult.reason instanceof Error
        ? moviesResult.reason
        : new Error('Failed to list library items');
    }

    const availability =
      moviesResult.status === 'fulfilled' && seriesResult.status === 'fulfilled'
        ? 'complete'
        : 'partial';
    return { items: [...movies, ...series], availability };
  }

  async getAutomationSummary(signal?: AbortSignal): Promise<AutomationSummary> {
    const probesPromise = this.probeSidebarServices(signal);
    try {
      const data = await this.getRaw<unknown>('/automation/summary', signal);
      const envelope = requireSoftEnvelope<OkEnvelope & Partial<LiveAutomationSummary>>(
        data,
        'Malformed automation summary response',
        (value) => {
          if (
            !['sonarr', 'radarr', 'prowlarr', 'bazarr'].some(
              (key) => isRecord((value as unknown as Record<string, unknown>)[key]),
            )
          ) {
            throw new Error('Malformed automation summary response');
          }
        },
      );
      const summary = mapAutomationSummary(mapLiveAutomationSummary(envelope as LiveAutomationSummary));
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
      this.fetchJellyfinKind('movies', signal),
      this.fetchJellyfinKind('series', signal),
    ]);

    return mapLibraryStats({
      movies: movies.length,
      series: series.length,
    });
  }

  listCronLogs(signal?: AbortSignal): Promise<CronLogs> {
    return this.getSoftEnvelope<MediaStackCronLogsDto>(
      '/cron/logs',
      (data) => {
        requireCronLogsPayload(data as unknown as Record<string, unknown>);
      },
      signal,
    ).then(mapCronLogs);
  }

  listHermesRecommendations(): Promise<HermesDiscover> {
    return this.getSoftEnvelope<MediaStackHermesDiscoverDto>('/discover/hermes', (data) => {
      requireHermesDiscoverPayload(data as unknown as Record<string, unknown>);
    }).then(mapHermesDiscover);
  }

  submitHermesFeedback(
    id: string,
    feedback: DiscoverFeedback,
    notes?: string,
  ): Promise<DiscoverAction> {
    return this.mutateSoft(`/discover/hermes/${encodeURIComponent(id)}`, 'PATCH', {
      status: feedback,
      notes,
    });
  }

  requestHermesMore(): Promise<DiscoverAction> {
    return this.mutateSoft('/discover/hermes/request-more', 'POST');
  }

  listJellyseerrDiscover(kind: JellyseerrDiscoverKind): Promise<ExternalDiscover> {
    return this.getSoftEnvelope<MediaStackExternalDiscoverDto>(
      `/discover/jellyseerr?kind=${kind}`,
      (data) => {
        requireExternalDiscoverPayload(data as unknown as Record<string, unknown>, 'Jellyseerr');
      },
    ).then(mapExternalDiscover);
  }

  listTraktDiscover(type: TraktDiscoverType): Promise<ExternalDiscover> {
    return this.getSoftEnvelope<MediaStackExternalDiscoverDto>(`/discover/trakt?type=${type}`, (data) => {
      requireExternalDiscoverPayload(data as unknown as Record<string, unknown>, 'Trakt');
    }).then(mapExternalDiscover);
  }

  requestMedia(payload: DiscoverRequestPayload): Promise<DiscoverAction> {
    return this.mutateSoft('/discover/request', 'POST', toDiscoverRequestPayloadDto(payload));
  }

  private async fetchJellyfinKind(
    kind: 'movies' | 'series',
    signal?: AbortSignal,
  ): Promise<LibraryItem[]> {
    const data = await this.getRaw<LiveJellyfinListResponse>(`/jellyfin/${kind}`, signal);
    const envelope = requireSoftEnvelope<OkEnvelope & { items?: unknown }>(
      data,
      `Failed to list jellyfin ${kind}`,
      (value) => {
        requireArrayField(
          value as unknown as Record<string, unknown>,
          'items',
          `Malformed jellyfin ${kind} response`,
        );
      },
    );
    if (envelope.ok === false) {
      throw new Error(envelope.error || `Failed to list jellyfin ${kind}`);
    }
    const itemKind: LibraryItemKind = kind === 'movies' ? 'movie' : 'series';
    return ((data as LiveJellyfinListResponse).items ?? [])
      .map((item, index) => mapLibraryItem(mapLiveJellyfinItem(item, itemKind, index)))
      .filter((item): item is LibraryItem => item !== null);
  }

  private async getRaw<T>(path: string, signal?: AbortSignal): Promise<T> {
    try {
      if (signal?.aborted) {
        throw new DOMException('The operation was aborted.', 'AbortError');
      }
      const request$ = this.http.get<T>(`${this.base}${path}`);
      // Unsubscribe on abort so Angular tears down the in-flight XHR/fetch request.
      return await firstValueFrom(
        signal ? request$.pipe(takeUntil(fromEvent(signal, 'abort'))) : request$,
      );
    } catch (error) {
      if (signal?.aborted) {
        throw new DOMException('The operation was aborted.', 'AbortError');
      }
      throw this.toError(error, `GET ${path} failed`);
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
    if (envelope.ok === false) {
      throw new Error(envelope.error || 'Failed to list torrents');
    }
    return requireArrayField(
      data as Record<string, unknown>,
      'torrents',
      'Malformed torrents response',
    );
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
    const envelope = requireHardEnvelope<T>(data, `GET ${path} failed`);
    validate?.(envelope);
    return envelope;
  }

  /** Void mutations: malformed, ok:false, and transport errors reject. */
  private async postVoid(path: string, body?: unknown): Promise<void> {
    try {
      const data = await firstValueFrom(this.http.post<unknown>(`${this.base}${path}`, body ?? null));
      const envelope = requireOkEnvelope(data, `Malformed response for POST ${path}`);
      if (envelope.ok === false) {
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
      const data =
        method === 'PATCH'
          ? await firstValueFrom(this.http.patch<unknown>(`${this.base}${path}`, body ?? null))
          : await firstValueFrom(
              body === undefined
                ? this.http.post<unknown>(`${this.base}${path}`, null)
                : this.http.post<unknown>(`${this.base}${path}`, body),
            );
      const envelope = requireOkEnvelope(
        data,
        `Malformed response for ${method} ${path}`,
      ) as MediaStackDiscoverActionDto;
      return mapDiscoverAction(envelope);
    } catch (error) {
      throw this.toError(error, `${method} ${path} failed`);
    }
  }

  private toError(error: unknown, fallback: string): Error {
    if (error instanceof HttpErrorResponse) {
      const body = error.error as OkEnvelope | string | null;
      if (body && typeof body === 'object' && body.error) {
        return new Error(String(body.error));
      }
      if (typeof body === 'string' && body.trim()) {
        return new Error(body);
      }
      return new Error(error.message || `HTTP ${error.status}` || fallback);
    }
    if (error instanceof Error) {
      return error;
    }
    return new Error(fallback);
  }
}
