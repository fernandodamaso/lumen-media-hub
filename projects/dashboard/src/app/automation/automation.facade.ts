import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import { CronRun } from '../reports/reports.models';
import { ServiceHealthFacade } from './service-health.facade';

export type AutomationStatus = 'loading' | 'ready' | 'empty' | 'error';

const REFRESH_ERROR = 'Could not refresh automation runs. Showing last loaded history.';
const LOAD_ERROR = 'Automation runs are temporarily unavailable. Try again.';

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

  async refresh(options: { initial?: boolean } = {}): Promise<void> {
    const initial =
      options.initial === true || this._status() === 'loading' || this._status() === 'error';
    this._refreshing.set(true);
    const requestId = ++this.requestId;
    try {
      const logs = await this.api.listCronLogs();
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
      this.applyRefreshFailure(initial);
    } finally {
      if (requestId === this.requestId) this._refreshing.set(false);
    }
  }

  private async runScheduledRefresh(initial: boolean): Promise<void> {
    if (this.scheduledInFlight) return;
    this.scheduledInFlight = true;
    try {
      await this.refresh({ initial });
    } finally {
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
    this.requestId += 1;
    this.scheduledInFlight = false;
    this._refreshing.set(false);
  }
}
