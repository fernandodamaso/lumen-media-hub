import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { groupCalendarEvents } from './calendar-format';
import {
  CALENDAR_LINK_BASES,
  CalendarEvent,
  compareCalendarEvents,
  resolveCalendarLink,
} from './calendar.models';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';

export type CalendarStatus = 'loading' | 'ready' | 'empty' | 'error';

export interface CalendarRailEvent extends CalendarEvent {
  href: string | null;
}

const REFRESH_ERROR = 'Could not refresh calendar. Showing last loaded schedule.';
const LOAD_ERROR = 'Calendar is temporarily unavailable. Try again.';
/** Bound scheduled polls so a hung calendar request cannot lock out later ticks. */
export const SCHEDULED_REFRESH_TIMEOUT_MS = 15_000;

@Injectable()
export class CalendarFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly linkBases = inject(CALENDAR_LINK_BASES);
  private readonly destroyRef = inject(DestroyRef);
  private readonly _status = signal<CalendarStatus>('loading');
  private readonly _events = signal<CalendarRailEvent[]>([]);
  private readonly _error = signal('');
  private readonly _refreshing = signal(false);
  private requestId = 0;
  private scheduledInFlight = false;
  private pollHandle?: ReturnType<typeof setInterval>;
  private refreshAbort?: AbortController;
  private refreshTimeoutId?: ReturnType<typeof setTimeout>;

  readonly status = this._status.asReadonly();
  readonly events = this._events.asReadonly();
  readonly groups = computed(() => groupCalendarEvents(this._events()));
  readonly error = this._error.asReadonly();
  readonly refreshing = this._refreshing.asReadonly();

  constructor() {
    this.destroyRef.onDestroy(() => this.stopPolling());
  }

  startPolling(intervalMs = 60_000): void {
    if (this.pollHandle) return;
    void this.runScheduledRefresh(true);
    this.pollHandle = setInterval(() => void this.runScheduledRefresh(false), intervalMs);
  }

  async refresh(options: { initial?: boolean; signal?: AbortSignal } = {}): Promise<void> {
    const initial =
      options.initial === true || this._status() === 'loading' || this._status() === 'error';
    this._refreshing.set(true);
    const requestId = ++this.requestId;
    try {
      const rawEvents = await this.api.listCalendarEvents(options.signal);
      if (requestId !== this.requestId) return;
      const library = await this.loadLibrary(options.signal);
      if (requestId !== this.requestId) return;
      const events = [...rawEvents]
        .sort(compareCalendarEvents)
        .map((event) => ({
          ...event,
          href: resolveCalendarLink(event.title, library, this.linkBases, event.kind),
        }));
      this._events.set(events);
      this._status.set(events.length ? 'ready' : 'empty');
      this._error.set('');
    } catch {
      if (requestId !== this.requestId) return;
      if (options.signal?.aborted) return;
      this.applyRefreshFailure(initial);
    } finally {
      if (requestId === this.requestId) this._refreshing.set(false);
    }
  }

  private async loadLibrary(signal?: AbortSignal) {
    try {
      return await this.api.getArrLibrary(signal);
    } catch {
      return { ok: false, series: {}, movies: {} };
    }
  }

  private async runScheduledRefresh(initial: boolean): Promise<void> {
    if (this.scheduledInFlight) return;
    this.scheduledInFlight = true;
    const abort = new AbortController();
    this.refreshAbort = abort;
    this.refreshTimeoutId = setTimeout(() => abort.abort(), SCHEDULED_REFRESH_TIMEOUT_MS);
    try {
      await this.refresh({ initial, signal: abort.signal });
      if (abort.signal.aborted && this.pollHandle !== undefined) {
        this.applyRefreshFailure(initial);
        this._refreshing.set(false);
      }
    } finally {
      if (this.refreshTimeoutId !== undefined) {
        clearTimeout(this.refreshTimeoutId);
        this.refreshTimeoutId = undefined;
      }
      if (this.refreshAbort === abort) {
        this.refreshAbort = undefined;
      }
      this.scheduledInFlight = false;
    }
  }

  private applyRefreshFailure(initial: boolean): void {
    const hasPrior = this._status() === 'ready' || this._status() === 'empty';
    if (!initial && hasPrior) {
      this._error.set(REFRESH_ERROR);
      return;
    }
    this._status.set('error');
    this._error.set(LOAD_ERROR);
    if (initial) {
      this._events.set([]);
    }
  }

  private stopPolling(): void {
    if (this.pollHandle) clearInterval(this.pollHandle);
    this.pollHandle = undefined;
    if (this.refreshTimeoutId !== undefined) {
      clearTimeout(this.refreshTimeoutId);
      this.refreshTimeoutId = undefined;
    }
    this.requestId++;
    this.refreshAbort?.abort();
    this.refreshAbort = undefined;
    this.scheduledInFlight = false;
    this._refreshing.set(false);
  }
}
