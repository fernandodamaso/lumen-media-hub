import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { ActivityFeed } from '../activity/activity.models';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import {
  applyPolledRefreshFailure,
  isInitialRefresh,
  runPolledRefresh,
} from '../media-stack/polled-refresh';
import { ScheduledPollController } from '../media-stack/scheduled-poll';

export type ActivityStatus = 'loading' | 'ready' | 'empty' | 'error';

const REFRESH_ERROR = 'Could not refresh activity. Showing last loaded activity.';
const LOAD_ERROR = 'Recent activity is temporarily unavailable. Try again.';
const ACTIVITY_LIMIT = 5;

@Injectable()
export class ActivityFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly destroyRef = inject(DestroyRef);
  private readonly poll = new ScheduledPollController();
  private readonly _status = signal<ActivityStatus>('loading');
  private readonly _feed = signal<ActivityFeed | null>(null);
  private readonly _error = signal('');
  private readonly _refreshing = signal(false);
  private readonly _lastFetchedAt = signal('');

  readonly status = this._status.asReadonly();
  readonly error = this._error.asReadonly();
  readonly refreshing = this._refreshing.asReadonly();
  readonly lastFetchedAt = this._lastFetchedAt.asReadonly();
  readonly items = computed(() => this._feed()?.items ?? []);
  readonly sources = computed(
    () =>
      this._feed()?.sources ?? {
        sonarr: 'unconfigured',
        radarr: 'unconfigured',
      },
  );
  /** Source names currently reporting `error` (per-source degradation contract). */
  readonly degradedSources = computed(() =>
    (Object.entries(this.sources()))
      .filter(([, state]) => state === 'error')
      .map(([name]) => name),
  );

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
        const activity = await this.api.getActivity(ACTIVITY_LIMIT, options.signal);
        if (!this.poll.isCurrent(requestId)) return;
        this._feed.set(activity);
        this._lastFetchedAt.set(new Date().toISOString());
        this._error.set('');
        this._status.set(activity.items.length ? 'ready' : 'empty');
      },
      onFailure: () => {
        this.applyRefreshFailure(initial);
      },
    });
  }

  private applyRefreshFailure(initial: boolean): void {
    applyPolledRefreshFailure({
      initial,
      status: this._status,
      error: this._error,
      refreshError: REFRESH_ERROR,
      loadError: LOAD_ERROR,
      clearPayload: () => {
        this._feed.set(null);
      },
    });
  }
}
