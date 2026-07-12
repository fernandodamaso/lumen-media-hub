import { CalendarEventStatus, CalendarMediaKind } from '../downloads/media-stack-api';

export type StatusTone = 'success' | 'warning' | 'danger' | 'info';

export const CALENDAR_KIND_VIEW: Record<CalendarMediaKind, { label: string; tone: StatusTone }> = {
  episode: { label: 'Episode', tone: 'info' },
  movie: { label: 'Movie', tone: 'info' },
};

export const CALENDAR_STATUS_VIEW: Record<CalendarEventStatus, { label: string; tone: StatusTone }> = {
  available: { label: 'Available', tone: 'success' },
  pending: { label: 'Upcoming', tone: 'warning' },
};
