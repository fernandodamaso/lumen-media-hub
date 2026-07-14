import { ArrLibrary, CalendarEvent } from '../../calendar/calendar.models';
import { MediaStackArrLibraryDto, MediaStackCalendarEventDto } from '../wire/calendar';

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
