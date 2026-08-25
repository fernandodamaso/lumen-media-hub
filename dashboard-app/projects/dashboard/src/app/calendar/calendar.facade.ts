import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { groupCalendarEvents } from './calendar-format';
import {
  CALENDAR_LINK_BASES,
  CalendarEvent,
  CalendarSource,
  CalendarSources,
  compareCalendarEvents,
  resolveArrPosterArt,
  resolveCalendarLink,
} from './calendar.models';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import { isAbortError } from '../media-stack/http-response';
import {
  applyPolledRefreshFailure,
  isInitialRefresh,
  runPolledRefresh,
} from '../media-stack/polled-refresh';
import { ScheduledPollController } from '../media-stack/scheduled-poll';

export type CalendarStatus = 'loading' | 'ready' | 'empty' | 'error';

export interface CalendarRailEvent extends CalendarEvent {
  href: string | null;
}

const REFRESH_ERROR = 'Could not refresh calendar. Showing last loaded schedule.';
const LOAD_ERROR = 'Calendar is temporarily unavailable. Try again.';
const HEALTHY_SOURCES: CalendarSources = { sonarr: 'ok', radarr: 'ok' };
const CALENDAR_SOURCES: CalendarSource[] = ['sonarr', 'radarr'];
/** Re-export for existing specs; canonical home is `media-stack/scheduled-poll`. */
export { SCHEDULED_REFRESH_TIMEOUT_MS } from '../media-stack/scheduled-poll';

@Injectable()
export class CalendarFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly linkBases = inject(CALENDAR_LINK_BASES);
  private readonly destroyRef = inject(DestroyRef);
  private readonly poll = new ScheduledPollController();
  private readonly _status = signal<CalendarStatus>('loading');
  private readonly _events = signal<CalendarRailEvent[]>([]);
  private readonly _sources = signal<CalendarSources>({ ...HEALTHY_SOURCES });
  private readonly _error = signal('');
  private readonly _refreshing = signal(false);
  private readonly _lastFetchedAt = signal('');

  readonly status = this._status.asReadonly();
  readonly events = this._events.asReadonly();
  readonly groups = computed(() => groupCalendarEvents(this._events()));
  readonly sources = this._sources.asReadonly();
  readonly degradedSources = computed(() =>
    CALENDAR_SOURCES.filter((source) => this._sources()[source] === 'error'),
  );
  readonly error = this._error.asReadonly();
  readonly refreshing = this._refreshing.asReadonly();
  readonly lastFetchedAt = this._lastFetchedAt.asReadonly();

  constructor() {
    this.destroyRef.onDestroy(() => {
      this.poll.stop();
      this._refreshing.set(false);
    });
  }

  startPolling(intervalMs = 60_000): void {
    this.poll.startRefreshing(
      intervalMs,
      (options) => this.refresh(options),
      (initial) => {
        this.applyRefreshFailure(initial);
        this._refreshing.set(false);
      },
    );
  }

  stopPolling(): void {
    this.poll.stop();
    this._refreshing.set(false);
  }

  async refresh(options: { initial?: boolean; signal?: AbortSignal } = {}): Promise<void> {
    const initial = isInitialRefresh(this._status(), options.initial);
    await runPolledRefresh({
      poll: this.poll,
      refreshing: this._refreshing,
      signal: options.signal,
      load: async (requestId) => {
        const rawEvents = await this.api.listCalendarEvents(options.signal);
        if (!this.poll.isCurrent(requestId)) return;
        const sources = rawEvents.sources ?? HEALTHY_SOURCES;
        const [library, posters] = await Promise.all([
          this.loadLibrary(options.signal),
          this.loadPosterArtByTitle(options.signal),
        ]);
        if (!this.poll.isCurrent(requestId)) return;
        const events = [...rawEvents]
          .sort(compareCalendarEvents)
          .map((event) => ({
            ...event,
            art:
              posters.get(event.title.trim().toLowerCase()) ??
              resolveArrPosterArt(event, this.linkBases) ??
              event.art,
            href: resolveCalendarLink(
              event.title,
              library,
              this.linkBases,
              event.kind,
              event.titleSlug,
            ),
          }));
        // Abort after enrichment must not commit, or the scheduled timeout path would wipe a false success.
        if (!this.poll.isCurrent(requestId) || options.signal?.aborted) return;
        this._events.set(events);
        this._sources.set({ ...sources });
        this._lastFetchedAt.set(rawEvents.generatedAt ?? new Date().toISOString());
        this._status.set(events.length ? 'ready' : 'empty');
        this._error.set('');
      },
      onFailure: () => {
        this.applyRefreshFailure(initial);
      },
    });
  }

  private async loadLibrary(signal?: AbortSignal) {
    try {
      return await this.api.getArrLibrary(signal);
    } catch (error: unknown) {
      // Aborts must propagate so refresh does not commit a de-linked schedule, then look like a failed retention.
      if (signal?.aborted || isAbortError(error)) {
        throw error;
      }
      return { ok: false, series: {}, movies: {} };
    }
  }

  private async loadPosterArtByTitle(signal?: AbortSignal): Promise<Map<string, string>> {
    try {
      const result = await this.api.listLibraryItems(undefined, signal);
      const posters = new Map<string, string>();
      for (const item of result.items) {
        const key = item.title.trim().toLowerCase();
        if (!key || item.artworkState !== 'ok' || !item.art.trim()) continue;
        if (!posters.has(key)) posters.set(key, item.art);
      }
      return posters;
    } catch (error: unknown) {
      if (signal?.aborted || isAbortError(error)) {
        throw error;
      }
      return new Map();
    }
  }

  private applyRefreshFailure(initial: boolean): void {
    applyPolledRefreshFailure({
      initial,
      status: this._status,
      error: this._error,
      refreshError: REFRESH_ERROR,
      loadError: LOAD_ERROR,
      clearPayload: () => {
        this._events.set([]);
        this._sources.set({ sonarr: 'error', radarr: 'error' });
      },
    });
  }
}