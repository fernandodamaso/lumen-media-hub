import { InjectionToken } from '@angular/core';

export type CalendarMediaKind = 'episode' | 'movie';
export type CalendarEventStatus = 'available' | 'pending';

export interface CalendarEvent {
  id: string;
  time: string;
  kind: CalendarMediaKind;
  title: string;
  subtitle: string;
  status: CalendarEventStatus;
  airDate: string;
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
export const DEFAULT_CALENDAR_LINK_BASES: Required<CalendarLinkBases> = {
  sonarrBase: '',
  radarrBase: '',
};

/** Explicit no-op bases for tests and link-disabled states. */
export const DISABLED_CALENDAR_LINK_BASES: Required<CalendarLinkBases> = {
  sonarrBase: '',
  radarrBase: '',
};

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
  return left.title.localeCompare(right.title);
};

export const resolveCalendarLink = (
  title: string | null | undefined,
  library: Pick<ArrLibrary, 'series' | 'movies'>,
  bases: CalendarLinkBases = {},
  kind?: CalendarMediaKind,
): string | null => {
  if (!title) return null;
  const key = title.trim().toLowerCase();
  const sonarrBase = (bases.sonarrBase ?? DEFAULT_CALENDAR_LINK_BASES.sonarrBase).replace(/\/$/, '');
  const radarrBase = (bases.radarrBase ?? DEFAULT_CALENDAR_LINK_BASES.radarrBase).replace(/\/$/, '');
  // Empty bases must not emit relative /series/... or /movie/... URLs.
  const seriesHref =
    sonarrBase && library.series?.[key] ? `${sonarrBase}/series/${library.series[key]}` : null;
  const movieHref =
    radarrBase && library.movies?.[key] ? `${radarrBase}/movie/${library.movies[key]}` : null;
  if (kind === 'movie') return movieHref ?? seriesHref;
  if (kind === 'episode') return seriesHref ?? movieHref;
  return seriesHref ?? movieHref;
};
