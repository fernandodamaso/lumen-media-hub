import { InjectionToken } from '@angular/core';

export type CalendarMediaKind = 'episode' | 'movie';
export type CalendarEventStatus = 'available' | 'monitored' | 'premiere' | 'pending';
export type CalendarSource = 'sonarr' | 'radarr';
export type CalendarSourceStatus = 'ok' | 'error' | 'unconfigured';
export type CalendarSources = Record<CalendarSource, CalendarSourceStatus>;

export interface CalendarEvent {
  id: string;
  time: string;
  kind: CalendarMediaKind;
  title: string;
  subtitle: string;
  status: CalendarEventStatus;
  airDate: string;
  /** Optional gradient thumbnail, same style as library item art. */
  art?: string;
  /** Sonarr episode id when known. */
  episodeId?: number;
  /** Radarr movie id when known. */
  movieId?: number;
  /** Radarr title slug when known — used for identity-specific deep links. */
  titleSlug?: string;
  /** Sonarr series id when known — used for MediaCover poster fallback. */
  seriesId?: number;
}

/** Array-shaped calendar result keeps existing Demo/API callers compatible while carrying Live source health. */
export interface CalendarEventCollection extends Array<CalendarEvent> {
  sources?: CalendarSources;
  generatedAt?: string;
}

export interface ArrLibrary {
  ok: boolean;
  series: Record<string, string>;
  movies: Record<string, string>;
  error?: string;
}

export interface CalendarLinkBases {
  sonarrBase?: string;
  radarrBase?: string;
}

/** Disabled by default; local Demo/live inject bases from environment. */
const DEFAULT_CALENDAR_LINK_BASES: Required<CalendarLinkBases> = {
  sonarrBase: '',
  radarrBase: '',
};

/** Explicit no-op bases for tests and link-disabled states. */
export const CALENDAR_LINK_BASES = new InjectionToken<CalendarLinkBases>('CALENDAR_LINK_BASES', {
  providedIn: 'root',
  factory: () => ({ ...DEFAULT_CALENDAR_LINK_BASES }),
});

export const compareCalendarEvents = (left: CalendarEvent, right: CalendarEvent): number => {
  const leftKey = left.airDate || '\uffff';
  const rightKey = right.airDate || '\uffff';
  const byAirDate = leftKey.localeCompare(rightKey);
  if (byAirDate !== 0) return byAirDate;
  const byTime = left.time.localeCompare(right.time);
  if (byTime !== 0) return byTime;
  const byKind = left.kind.localeCompare(right.kind);
  if (byKind !== 0) return byKind;
  const byTitle = left.title.localeCompare(right.title);
  if (byTitle !== 0) return byTitle;
  return left.id.localeCompare(right.id);
};

export const resolveCalendarLink = (
  title: string | null | undefined,
  library: Pick<ArrLibrary, 'series' | 'movies'>,
  bases: CalendarLinkBases = {},
  kind?: CalendarMediaKind,
  titleSlug?: string,
): string | null => {
  const key = title?.trim().toLowerCase() ?? '';
  const directMovieSlug = titleSlug?.trim() || undefined;
  if (!key && !directMovieSlug) return null;
  const sonarrBase = (bases.sonarrBase ?? DEFAULT_CALENDAR_LINK_BASES.sonarrBase).replace(/\/$/, '');
  const radarrBase = (bases.radarrBase ?? DEFAULT_CALENDAR_LINK_BASES.radarrBase).replace(/\/$/, '');
  const movieSlug = directMovieSlug ?? (key ? library.movies[key] : undefined);
  // Empty bases must not emit relative /series/... or /movie/... URLs.
  const seriesHref =
    sonarrBase && key && library.series[key] ? `${sonarrBase}/series/${library.series[key]}` : null;
  const movieHref = radarrBase && movieSlug ? `${radarrBase}/movie/${movieSlug}` : null;
  if (kind === 'movie') return movieHref;
  if (kind === 'episode') return seriesHref;
  return seriesHref ?? movieHref;
};

/** Sonarr serves posters at /MediaCover/{id}/poster-250.jpg without an API key. */
export const resolveArrPosterArt = (
  event: Pick<CalendarEvent, 'seriesId' | 'kind'>,
  bases: CalendarLinkBases = {},
): string | null => {
  const seriesId = event.seriesId;
  if (event.kind === 'movie' || seriesId == null || !Number.isFinite(seriesId) || seriesId <= 0) {
    return null;
  }
  const sonarrBase = (bases.sonarrBase ?? DEFAULT_CALENDAR_LINK_BASES.sonarrBase).replace(/\/$/, '');
  if (!sonarrBase) return null;
  return `url("${sonarrBase}/MediaCover/${seriesId}/poster-250.jpg") center / cover no-repeat`;
};