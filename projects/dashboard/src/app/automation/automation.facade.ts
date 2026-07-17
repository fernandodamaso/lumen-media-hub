import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import { CronRun } from '../reports/reports.models';
import { ServiceHealthFacade } from './service-health.facade';

export type AutomationStatus = 'loading' | 'ready' | 'empty' | 'error';

@Injectable()
export class AutomationFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly destroyRef = inject(DestroyRef);
  private readonly serviceHealth = inject(ServiceHealthFacade);
  private readonly _status = signal<AutomationStatus>('loading');
  private readonly _error = signal('');
  private readonly _tasks = signal<CronRun[]>([]);
  readonly summary = this.serviceHealth.summary;
  readonly health = this.serviceHealth.health;
  readonly status = this._status.asReadonly();
  readonly error = this._error.asReadonly();
  readonly tasks = this._tasks.asReadonly();
  readonly latestRuns = computed(() =>
    [...this._tasks()]
      .sort((left, right) => (right.timestamp ?? '').localeCompare(left.timestamp ?? ''))
      .slice(0, 3),
  );
  private pollHandle?: number;

  constructor() {
    this.destroyRef.onDestroy(() => this.stopPolling());
  }

  startPolling(intervalMs = 60_000): void {
    if (this.pollHandle) return;
    this.serviceHealth.startPolling(intervalMs);
    void this.refresh();
    this.pollHandle = window.setInterval(() => void this.refresh(), intervalMs);
  }

  async refresh(): Promise<void> {
    this._status.set('loading');
    try {
      const logs = await this.api.listCronLogs();
      if (!logs.ok) {
        this._tasks.set([]);
        this._status.set('error');
        this._error.set(logs.error || 'Automation runs are temporarily unavailable. Try again.');
        return;
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
      this._tasks.set([]);
      this._status.set('error');
      this._error.set('Automation runs are temporarily unavailable. Try again.');
    }
  }

  private stopPolling(): void {
    if (this.pollHandle) window.clearInterval(this.pollHandle);
    this.pollHandle = undefined;
  }
}
