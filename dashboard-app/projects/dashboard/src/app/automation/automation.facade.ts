import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import {
  applyPolledRefreshFailure,
  isInitialRefresh,
  runPolledRefresh,
} from '../media-stack/polled-refresh';
import { ScheduledPollController } from '../media-stack/scheduled-poll';
import { CronRun } from '../reports/reports.models';
import { ServiceHealthFacade } from './service-health.facade';

export type AutomationStatus = 'loading' | 'ready' | 'empty' | 'error';

const REFRESH_ERROR = 'Could not refresh automation runs. Showing last loaded history.';
const LOAD_ERROR = 'Automation runs are temporarily unavailable. Try again.';
/** Re-export for existing specs; canonical home is `media-stack/scheduled-poll`. */
export { SCHEDULED_REFRESH_TIMEOUT_MS } from '../media-stack/scheduled-poll';

@Injectable()
export class AutomationFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly destroyRef = inject(DestroyRef);
  private readonly serviceHealth = inject(ServiceHealthFacade);
  private readonly poll = new ScheduledPollController();
  private readonly _status = signal<AutomationStatus>('loading');
  private readonly _error = signal('');
  private readonly _tasks = signal<CronRun[]>([]);
  private readonly _refreshing = signal(false);
  private readonly _lastFetchedAt = signal('');

  readonly summary = this.serviceHealth.summary;
  readonly health = this.serviceHealth.health;
  readonly status = this._status.asReadonly();
  readonly error = this._error.asReadonly();
  readonly refreshing = this._refreshing.asReadonly();
  readonly lastFetchedAt = this._lastFetchedAt.asReadonly();
  readonly tasks = this._tasks.asReadonly();
  readonly latestRuns = computed(() =>
    [...this._tasks()]
      .sort((left, right) => right.timestamp.localeCompare(left.timestamp))
      .slice(0, 3),
  );

  constructor() {
    this.destroyRef.onDestroy(() => {
      this.poll.stop();
      this._refreshing.set(false);
    });
  }

  startPolling(intervalMs = 60_000): void {
    if (this.poll.armed) return;
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
        const logs = await this.api.listCronLogs(options.signal);
        if (!this.poll.isCurrent(requestId)) return;
        if (!logs.ok) {
          this.applyRefreshFailure(initial, logs.error?.trim());
          return;
        }
        // Backend exposes one current run per job; no per-job dedup needed here.
        const tasks = [...logs.currentRuns].sort((left, right) =>
          left.jobTitle.localeCompare(right.jobTitle),
        );
        this._tasks.set(tasks);
        this._lastFetchedAt.set(new Date().toISOString());
        this._error.set('');
        this._status.set(this._tasks().length ? 'ready' : 'empty');
      },
      onFailure: () => {
        this.applyRefreshFailure(initial);
      },
    });
  }

  private applyRefreshFailure(initial: boolean, backendMessage?: string): void {
    applyPolledRefreshFailure({
      initial,
      status: this._status,
      error: this._error,
      refreshError: REFRESH_ERROR,
      loadError: LOAD_ERROR,
      backendMessage,
      clearPayload: () => {
        this._tasks.set([]);
      },
    });
  }
}
