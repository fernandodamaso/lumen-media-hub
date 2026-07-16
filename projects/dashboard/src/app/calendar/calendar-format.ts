import {
  ArrLibrary,
  CalendarEvent,
  CalendarEventStatus,
  CalendarMediaKind,
} from './calendar.models';
import {
  MediaStackArrLibraryDto,
  MediaStackCalendarEventDto,
} from '../media-stack/wire/calendar';

export interface CalendarDateGroup<T> { key: string; label: string; events: T[]; }

export function groupCalendarEvents<T extends { airDate: string }>(events: T[], now = new Date()): CalendarDateGroup<T>[] {
  const today = localKey(now);
  const tomorrowDate = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  const tomorrow = localKey(tomorrowDate);
  const groups = new Map<string, CalendarDateGroup<T>>();
  for (const event of events) {
    const match = event.airDate.match(/^(\d{4})-(\d{2})-(\d{2})/);
    const key = match ? match[0] : 'undated';
    let group = groups.get(key);
    if (!group) {
      let label = 'DATE UNAVAILABLE';
      if (match) {
        const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), 12);
        const month = new Intl.DateTimeFormat('en', { month: 'short' }).format(date).toUpperCase();
        const day = String(date.getDate());
        const weekday = new Intl.DateTimeFormat('en', { weekday: 'short' }).format(date).toUpperCase();
        label = key === today ? `TODAY, ${month} ${day}` : key === tomorrow ? `TOMORROW, ${month} ${day}` : `${weekday}, ${month} ${day}`;
      }
      group = { key, label, events: [] };
      groups.set(key, group);
    }
    group.events.push(event);
  }
  return [...groups.values()].sort((a, b) => a.key === 'undated' ? 1 : b.key === 'undated' ? -1 : a.key.localeCompare(b.key));
}

function localKey(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

export type StatusTone = 'success' | 'warning' | 'danger' | 'info';

export const CALENDAR_KIND_VIEW: Record<CalendarMediaKind, { label: string; tone: StatusTone }> = {
  episode: { label: 'Episode', tone: 'info' },
  movie: { label: 'Movie', tone: 'info' },
};

export const CALENDAR_STATUS_VIEW: Record<CalendarEventStatus, { label: string; tone: StatusTone }> = {
  available: { label: 'Available', tone: 'success' },
  pending: { label: 'Upcoming', tone: 'warning' },
};

export const mapCalendarEvent = (event: MediaStackCalendarEventDto): CalendarEvent => {
  const airDate = event.airDate ?? '';
  const kind = event.kind ?? (looksLikeEpisode(event.additional) ? 'episode' : 'movie');
  return {
    id: `${event.title}-${event.additional}-${airDate || event.date}`,
    time: event.date,
    kind,
    title: event.title,
    subtitle: event.additional,
    status: event.hasFile ? 'available' : 'pending',
    airDate,
  };
};

export const mapArrLibrary = (dto: MediaStackArrLibraryDto): ArrLibrary => ({
  ok: dto.ok,
  series: dto.series ?? {},
  movies: dto.movies ?? {},
  error: dto.error,
});

function looksLikeEpisode(additional: string): boolean {
  return /^S\d+\s*E\d+/i.test(additional.trim());
}
