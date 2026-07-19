import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import { CronRun } from '../reports/reports.models';
import { ServiceHealthFacade } from './service-health.facade';

export type AutomationStatus = 'loading' | 'ready' | 'empty' | 'error';

const REFRESH_ERROR = 'Could not refresh automation runs. Showing last loaded history.';
const LOAD_ERROR = 'Automation runs are temporarily unavailable. Try again.';
/** Bound scheduled polls so a hung `/cron/logs` request cannot lock out later ticks. */
export const SCHEDULED_REFRESH_TIMEOUT_MS = 15_000;

@Injectable()
export class AutomationFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly destroyRef = inject(DestroyRef);
  private readonly serviceHealth = inject(ServiceHealthFacade);
  private readonly _status = signal<AutomationStatus>('loading');
  private readonly _error = signal('');
  private readonly _tasks = signal<CronRun[]>([]);
  private readonly _refreshing = signal(false);
  private requestId = 0;
  private scheduledInFlight = false;
  private pollHandle?: ReturnType<typeof setInterval>;
  private refreshAbort?: AbortController;
  private refreshTimeoutId?: ReturnType<typeof setTimeout>;

  readonly summary = this.serviceHealth.summary;
  readonly health = this.serviceHealth.health;
  readonly status = this._status.asReadonly();
  readonly error = this._error.asReadonly();
  readonly refreshing = this._refreshing.asReadonly();
  readonly tasks = this._tasks.asReadonly();
  readonly latestRuns = computed(() =>
    [...this._tasks()]
      .sort((left, right) => (right.timestamp ?? '').localeCompare(left.timestamp ?? ''))
      .slice(0, 3),
  );

  constructor() {
    this.destroyRef.onDestroy(() => this.stopPolling());
  }

  startPolling(intervalMs = 60_000): void {
    if (this.pollHandle) return;
    this.serviceHealth.startPolling(intervalMs);
    void this.runScheduledRefresh(true);
    this.pollHandle = setInterval(() => void this.runScheduledRefresh(false), intervalMs);
  }

  async refresh(options: { initial?: boolean; signal?: AbortSignal } = {}): Promise<void> {
    const initial =
      options.initial === true || this._status() === 'loading' || this._status() === 'error';
    this._refreshing.set(true);
    const requestId = ++this.requestId;
    try {
      const logs = await this.api.listCronLogs(options.signal);
      if (requestId !== this.requestId) return;
      if (!logs.ok) {
        throw new Error(logs.error?.trim() || 'Cron logs unavailable');
      }
      const latest = new Map<string, CronRun>();
      for (const run of logs.runs) {
        const current = latest.get(run.jobId);
        if (!current || (run.timestamp || '') > (current.timestamp || '')) latest.set(run.jobId, run);
      }
      this._tasks.set([...latest.values()].sort((left, right) => left.jobTitle.localeCompare(right.jobTitle)));
      this._error.set('');
      this._status.set(this._tasks().length ? 'ready' : 'empty');
    } catch {
      if (requestId !== this.requestId) return;
      // Cancelled refreshes must not mutate facade state; callers apply timeout/teardown policy.
      if (options.signal?.aborted) return;
      this.applyRefreshFailure(initial);
    } finally {
      if (requestId === this.requestId) this._refreshing.set(false);
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
      // Timeout abort while polling is still armed: surface retained/hard failure and free the slot.
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
      this._tasks.set([]);
    }
  }

  private stopPolling(): void {
    if (this.pollHandle) clearInterval(this.pollHandle);
    this.pollHandle = undefined;
    if (this.refreshTimeoutId !== undefined) {
      clearTimeout(this.refreshTimeoutId);
      this.refreshTimeoutId = undefined;
    }
    // Invalidate before abort so a racing settle cannot write after teardown.
    this.requestId += 1;
    this.refreshAbort?.abort();
    this.refreshAbort = undefined;
    this.scheduledInFlight = false;
    this._refreshing.set(false);
  }
}
