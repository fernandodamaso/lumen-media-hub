import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { groupCalendarEvents } from './calendar-format';
import {
  CALENDAR_LINK_BASES,
  CalendarEvent,
  MEDIA_STACK_API,
  compareCalendarEvents,
  normalizeCalendarEvent,
  resolveCalendarLink,
} from '../media-stack/media-stack-api';

export type CalendarStatus = 'loading' | 'ready' | 'empty' | 'error';

export interface CalendarRailEvent extends CalendarEvent {
  href: string | null;
}

@Injectable()
export class CalendarFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly linkBases = inject(CALENDAR_LINK_BASES);
  private readonly destroyRef = inject(DestroyRef);
  private readonly _status = signal<CalendarStatus>('loading');
  private readonly _events = signal<CalendarRailEvent[]>([]);
  private readonly _error = signal('');
  readonly status = this._status.asReadonly();
  readonly events = this._events.asReadonly();
  readonly groups = computed(() => groupCalendarEvents(this._events()));
  readonly error = this._error.asReadonly();
  private pollHandle?: ReturnType<typeof setInterval>;

  constructor() {
    this.destroyRef.onDestroy(() => this.stopPolling());
  }

  startPolling(intervalMs = 60_000): void {
    if (this.pollHandle) return;
    void this.refresh();
    this.pollHandle = setInterval(() => void this.refresh(), intervalMs);
  }

  async refresh(): Promise<void> {
    try {
      const rawEvents = await this.api.listCalendarEvents();
      const library = await this.loadLibrary();
      const events = rawEvents
        .map(normalizeCalendarEvent)
        .sort(compareCalendarEvents)
        .map((event) => ({
          ...event,
          href: resolveCalendarLink(event.title, library, this.linkBases, event.kind),
        }));
      this._events.set(events);
      this._status.set(events.length ? 'ready' : 'empty');
      this._error.set('');
    } catch {
      this._status.set('error');
      this._error.set('Calendar is temporarily unavailable. Try again.');
    }
  }

  private async loadLibrary() {
    try {
      return await this.api.getArrLibrary();
    } catch {
      return { ok: false, series: {}, movies: {} };
    }
  }

  private stopPolling(): void {
    if (this.pollHandle) clearInterval(this.pollHandle);
    this.pollHandle = undefined;
  }
}
