import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
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
    this.serviceHealth.startPolling(intervalMs);
    this.poll.startRefreshing(
      intervalMs,
      (options) => this.refresh(options),
      (initial) => {
        this.applyRefreshFailure(initial);
        this._refreshing.set(false);
      },
    );
  }

  async refresh(options: { initial?: boolean; signal?: AbortSignal } = {}): Promise<void> {
    const initial =
      options.initial === true || this._status() === 'loading' || this._status() === 'error';
    this._refreshing.set(true);
    const requestId = this.poll.beginRequest();
    try {
      const logs = await this.api.listCronLogs(options.signal);
      if (!this.poll.isCurrent(requestId)) return;
      if (!logs.ok) {
        this.applyRefreshFailure(initial, logs.error?.trim());
        return;
      }
      const latest = new Map<string, CronRun>();
      for (const run of logs.runs) {
        const current = latest.get(run.jobId);
        if (!current || (run.timestamp || '') > (current.timestamp || '')) latest.set(run.jobId, run);
      }
      this._tasks.set([...latest.values()].sort((left, right) => left.jobTitle.localeCompare(right.jobTitle)));
      this._lastFetchedAt.set(new Date().toISOString());
      this._error.set('');
      this._status.set(this._tasks().length ? 'ready' : 'empty');
    } catch {
      if (!this.poll.isCurrent(requestId)) return;
      // Cancelled refreshes must not mutate facade state; callers apply timeout/teardown policy.
      if (options.signal?.aborted) return;
      this.applyRefreshFailure(initial);
    } finally {
      if (this.poll.isCurrent(requestId)) this._refreshing.set(false);
    }
  }

  private applyRefreshFailure(initial: boolean, backendMessage?: string): void {
    const hasPrior = this._status() === 'ready' || this._status() === 'empty';
    if (!initial && hasPrior) {
      this._error.set(REFRESH_ERROR);
      return;
    }
    this._status.set('error');
    this._error.set(backendMessage || LOAD_ERROR);
    if (initial) {
      this._tasks.set([]);
    }
  }
}
