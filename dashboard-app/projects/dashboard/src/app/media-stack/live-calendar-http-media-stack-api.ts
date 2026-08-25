import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { firstValueFrom, fromEvent, takeUntil } from 'rxjs';

import { mapCalendarEvent } from '../calendar/calendar-format';
import {
  CalendarEventCollection,
  CalendarSources,
  CalendarSourceStatus,
} from '../calendar/calendar.models';
import { environment } from '../../environments/environment';
import { HttpMediaStackApi } from './http-media-stack-api';
import {
  isRecord,
  requireArrayField,
  requireHardEnvelope,
  requireNonEmptyString,
} from './http-response';
import { MediaStackCalendarEventDto } from './wire/calendar';

const CALENDAR_RESPONSE_ERROR = 'Malformed calendar response';
const CALENDAR_REQUEST_ERROR = 'GET /calendar failed';

@Injectable()
export class LiveCalendarHttpMediaStackApi extends HttpMediaStackApi {
  private readonly calendarHttp = inject(HttpClient);
  private readonly calendarBase = environment.apiBaseUrl.replace(/\/$/, '');

  override async listCalendarEvents(signal?: AbortSignal): Promise<CalendarEventCollection> {
    if (signal?.aborted) throw abortError();

    try {
      const request = this.calendarHttp.get<unknown>(`${this.calendarBase}/calendar`);
      const data = await firstValueFrom(
        signal ? request.pipe(takeUntil(fromEvent(signal, 'abort'))) : request,
      );
      const envelope = requireHardEnvelope(data, CALENDAR_REQUEST_ERROR);
      const sources = requireCalendarSources(envelope['sources']);
      const rawEvents = requireArrayField(envelope, 'events', CALENDAR_RESPONSE_ERROR);
      const events = rawEvents.map((event, index) =>
        mapCalendarEvent(requireCombinedCalendarEvent(event, index)),
      ) as CalendarEventCollection;
      events.sources = sources;

      const generatedAt = envelope['generatedAt'];
      if (typeof generatedAt === 'string' && generatedAt.trim()) {
        events.generatedAt = generatedAt.trim();
      }
      return events;
    } catch (error: unknown) {
      if (signal?.aborted) throw abortError();
      throw calendarRequestError(error);
    }
  }
}

function requireCombinedCalendarEvent(value: unknown, index: number): MediaStackCalendarEventDto {
  if (!isRecord(value)) {
    throw new Error(`${CALENDAR_RESPONSE_ERROR}: event ${index} is not an object`);
  }

  const kind = value['kind'];
  if (kind !== 'episode' && kind !== 'movie') {
    throw new Error(`${CALENDAR_RESPONSE_ERROR}: event ${index} has invalid kind`);
  }

  const id = requireNonEmptyString(value['id'], `${CALENDAR_RESPONSE_ERROR}: event ${index} is missing id`);
  const title = requireNonEmptyString(
    value['title'],
    `${CALENDAR_RESPONSE_ERROR}: event ${index} is missing title`,
  );
  const additional = requireString(
    value['additional'],
    `${CALENDAR_RESPONSE_ERROR}: event ${index} has invalid additional`,
  );
  const date = requireNonEmptyString(
    value['date'],
    `${CALENDAR_RESPONSE_ERROR}: event ${index} is missing date`,
  );
  const airDate = requireTimestamp(
    value['airDate'],
    `${CALENDAR_RESPONSE_ERROR}: event ${index} has invalid airDate`,
  );

  const episodeId = optionalPositiveId(value['episodeId'], 'episodeId', index);
  const movieId = optionalPositiveId(value['movieId'], 'movieId', index);
  const seriesId = optionalPositiveId(value['seriesId'], 'seriesId', index);
  requireKindIdentity(kind, id, episodeId, movieId, index);

  return {
    id,
    kind,
    title,
    additional,
    date,
    airDate,
    episodeId,
    movieId,
    seriesId,
    hasFile: optionalBoolean(value['hasFile'], 'hasFile', index),
    monitored: optionalBoolean(value['monitored'], 'monitored', index),
    premiere: optionalBoolean(value['premiere'], 'premiere', index),
    status: optionalString(value['status'], 'status', index),
    art: optionalString(value['art'], 'art', index),
  };
}

function requireKindIdentity(
  kind: 'episode' | 'movie',
  id: string,
  episodeId: number | undefined,
  movieId: number | undefined,
  index: number,
): void {
  if (kind === 'episode') {
    if (episodeId === undefined || movieId !== undefined || id !== `sonarr:episode:${episodeId}`) {
      throw new Error(`${CALENDAR_RESPONSE_ERROR}: event ${index} has invalid episodeId identity`);
    }
    return;
  }
  if (movieId === undefined || episodeId !== undefined || id !== `radarr:movie:${movieId}`) {
    throw new Error(`${CALENDAR_RESPONSE_ERROR}: event ${index} has invalid movieId identity`);
  }
}

function requireCalendarSources(value: unknown): CalendarSources {
  if (!isRecord(value)) {
    throw new Error(`${CALENDAR_RESPONSE_ERROR}: missing sources`);
  }
  return {
    sonarr: requireSourceStatus(value['sonarr'], 'sonarr'),
    radarr: requireSourceStatus(value['radarr'], 'radarr'),
  };
}

function requireSourceStatus(value: unknown, source: string): CalendarSourceStatus {
  if (value === 'ok' || value === 'error' || value === 'unconfigured') return value;
  throw new Error(`${CALENDAR_RESPONSE_ERROR}: invalid ${source} source status`);
}

function optionalPositiveId(value: unknown, field: string, index: number): number | undefined {
  if (value === undefined || value === null) return undefined;
  if (typeof value !== 'number' || !Number.isInteger(value) || value <= 0) {
    throw new Error(`${CALENDAR_RESPONSE_ERROR}: event ${index} has invalid ${field}`);
  }
  return value;
}

function optionalBoolean(value: unknown, field: string, index: number): boolean | undefined {
  if (value === undefined || value === null) return undefined;
  if (typeof value !== 'boolean') {
    throw new Error(`${CALENDAR_RESPONSE_ERROR}: event ${index} has invalid ${field}`);
  }
  return value;
}

function optionalString(value: unknown, field: string, index: number): string | undefined {
  if (value === undefined || value === null) return undefined;
  if (typeof value !== 'string') {
    throw new Error(`${CALENDAR_RESPONSE_ERROR}: event ${index} has invalid ${field}`);
  }
  return value;
}

function requireString(value: unknown, context: string): string {
  if (typeof value !== 'string') throw new Error(context);
  return value;
}

function requireTimestamp(value: unknown, context: string): string {
  const timestamp = requireNonEmptyString(value, context);
  if (Number.isNaN(Date.parse(timestamp))) throw new Error(context);
  return timestamp;
}

function calendarRequestError(error: unknown): Error {
  if (error instanceof HttpErrorResponse && isRecord(error.error)) {
    const message = error.error['error'];
    if (typeof message === 'string' && message.trim()) return new Error(message.trim());
  }
  return error instanceof Error ? error : new Error(CALENDAR_REQUEST_ERROR);
}

function abortError(): DOMException {
  return new DOMException('The operation was aborted.', 'AbortError');
}
