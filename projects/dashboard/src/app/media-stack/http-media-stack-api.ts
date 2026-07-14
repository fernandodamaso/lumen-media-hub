import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';

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
import { LibraryItem, LibraryItemKind } from '../library/library.models';
import { AutomationSummary } from '../automation/automation.models';
import { CronLogs } from '../reports/reports.models';
import { MediaStackApi } from './media-stack-api';
import { mapArrLibrary, mapCalendarEvent } from './mappers/calendar';
import { mapAutomationSummary } from './mappers/automation';
import { mapCronLogs } from './mappers/cron';
import {
  mapDiscoverAction,
  mapExternalDiscover,
  mapHermesDiscover,
  toDiscoverRequestPayloadDto,
} from './mappers/discover';
import { mapLibraryItem } from './mappers/library';
import { mapTorrent } from './mappers/torrents';
import { MediaStackArrLibraryDto, MediaStackCalendarEventDto } from './wire/calendar';
import { MediaStackCronLogsDto } from './wire/cron';
import { MediaStackDiscoverActionDto, MediaStackExternalDiscoverDto, MediaStackHermesDiscoverDto } from './wire/discover';
import {
  LiveAutomationSummary,
  LiveJellyfinListResponse,
  LiveQbtTorrent,
  mapLiveAutomationSummary,
  mapLiveJellyfinItem,
  mapLiveTorrent,
} from './live-api.mappers';

interface OkEnvelope {
  ok?: boolean;
  error?: string;
}

@Injectable()
export class HttpMediaStackApi implements MediaStackApi {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiBaseUrl.replace(/\/$/, '');

  listTorrents(): Promise<DownloadTorrent[]> {
    return this.getRaw<LiveQbtTorrent[] | OkEnvelope>('/qbt/torrents').then((data) => {
      if (Array.isArray(data)) {
        return data.map((item, index) => mapTorrent(mapLiveTorrent(item, index)));
      }
      this.rejectIfFailed(data, 'Failed to list torrents');
      throw new Error('Malformed torrents response');
    });
  }

  pauseAll(): Promise<void> {
    return this.postVoid('/stop-all');
  }

  resumeAll(): Promise<void> {
    return this.postVoid('/start-all');
  }

  listCalendarEvents(): Promise<CalendarEvent[]> {
    return this.getHardEnvelope<{ ok?: boolean; error?: string; events?: MediaStackCalendarEventDto[] }>(
      '/sonarr/calendar',
    ).then((data) => (data.events ?? []).map(mapCalendarEvent));
  }

  getArrLibrary(): Promise<ArrLibrary> {
    return this.getSoftEnvelope<MediaStackArrLibraryDto>('/arr/library').then(mapArrLibrary);
  }

  async listLibraryItems(filter?: { kind?: LibraryItemKind }): Promise<LibraryItem[]> {
    const kind = filter?.kind;

    // Filtered loads: surface the requested kind's failure instead of masking as empty.
    if (kind === 'movie') {
      return this.fetchJellyfinKind('movies');
    }
    if (kind === 'series') {
      return this.fetchJellyfinKind('series');
    }

    const [moviesResult, seriesResult] = await Promise.allSettled([
      this.fetchJellyfinKind('movies'),
      this.fetchJellyfinKind('series'),
    ]);
    const movies = moviesResult.status === 'fulfilled' ? moviesResult.value : [];
    const series = seriesResult.status === 'fulfilled' ? seriesResult.value : [];

    if (moviesResult.status === 'rejected' && seriesResult.status === 'rejected') {
      throw moviesResult.reason instanceof Error
        ? moviesResult.reason
        : new Error('Failed to list library items');
    }

    return [...movies, ...series];
  }

  getAutomationSummary(): Promise<AutomationSummary> {
    return this.getRaw<LiveAutomationSummary>('/automation/summary').then((data) =>
      mapAutomationSummary(mapLiveAutomationSummary(data)),
    );
  }

  listCronLogs(): Promise<CronLogs> {
    return this.getSoftEnvelope<MediaStackCronLogsDto>('/cron/logs').then(mapCronLogs);
  }

  listHermesRecommendations(): Promise<HermesDiscover> {
    return this.getSoftEnvelope<MediaStackHermesDiscoverDto>('/discover/hermes').then(mapHermesDiscover);
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
    return this.getSoftEnvelope<MediaStackExternalDiscoverDto>(`/discover/jellyseerr?kind=${kind}`).then(
      mapExternalDiscover,
    );
  }

  listTraktDiscover(type: TraktDiscoverType): Promise<ExternalDiscover> {
    return this.getSoftEnvelope<MediaStackExternalDiscoverDto>(`/discover/trakt?type=${type}`).then(
      mapExternalDiscover,
    );
  }

  requestMedia(payload: DiscoverRequestPayload): Promise<DiscoverAction> {
    return this.mutateSoft('/discover/request', 'POST', toDiscoverRequestPayloadDto(payload));
  }

  private async fetchJellyfinKind(kind: 'movies' | 'series'): Promise<LibraryItem[]> {
    const data = await this.getRaw<LiveJellyfinListResponse>(`/jellyfin/${kind}`);
    if (data?.ok === false) {
      throw new Error(data.error || `Failed to list jellyfin ${kind}`);
    }
    const itemKind: LibraryItemKind = kind === 'movies' ? 'movie' : 'series';
    return (data.items ?? [])
      .map((item) => mapLibraryItem(mapLiveJellyfinItem(item, itemKind)))
      .filter((item): item is LibraryItem => item !== null);
  }

  private async getRaw<T>(path: string): Promise<T> {
    try {
      return await firstValueFrom(this.http.get<T>(`${this.base}${path}`));
    } catch (error) {
      throw this.toError(error, `GET ${path} failed`);
    }
  }

  /** Return envelope DTOs as-is so facades can read ok/error (mock parity). */
  private async getSoftEnvelope<T extends OkEnvelope>(path: string): Promise<T> {
    return this.getRaw<T>(path);
  }

  /** Reject when ok === false (used when unwrapping to non-envelope values). */
  private async getHardEnvelope<T>(path: string): Promise<T> {
    const data = await this.getRaw<T & OkEnvelope>(path);
    this.rejectIfFailed(data, `GET ${path} failed`);
    return data;
  }

  /** Void mutations: ok:false and transport errors reject. */
  private async postVoid(path: string): Promise<void> {
    try {
      const data = await firstValueFrom(this.http.post<OkEnvelope>(`${this.base}${path}`, null));
      this.rejectIfFailed(data, `POST ${path} failed`);
    } catch (error) {
      throw this.toError(error, `POST ${path} failed`);
    }
  }

  /**
   * Discover/action mutations: HTTP 200 with ok:false returns the DTO so facades
   * can surface result.error. Transport failures still reject.
   */
  private async mutateSoft(
    path: string,
    method: 'POST' | 'PATCH',
    body?: unknown,
  ): Promise<DiscoverAction> {
    try {
      const data =
        method === 'PATCH'
          ? await firstValueFrom(
              this.http.patch<MediaStackDiscoverActionDto>(`${this.base}${path}`, body ?? null),
            )
          : await firstValueFrom(
              body === undefined
                ? this.http.post<MediaStackDiscoverActionDto>(`${this.base}${path}`, null)
                : this.http.post<MediaStackDiscoverActionDto>(`${this.base}${path}`, body),
            );
      return mapDiscoverAction(data ?? { ok: true });
    } catch (error) {
      throw this.toError(error, `${method} ${path} failed`);
    }
  }

  private rejectIfFailed(data: OkEnvelope | null | undefined, fallback: string): void {
    if (data && data.ok === false) {
      throw new Error(data.error || fallback);
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
