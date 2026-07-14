import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { AutomationSummary, summarizeAutomationHealth } from './automation.models';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import { CronRun } from '../reports/reports.models';

export type AutomationStatus = 'loading' | 'ready' | 'empty' | 'partial' | 'error';

@Injectable()
export class AutomationFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly destroyRef = inject(DestroyRef);
  private readonly _status = signal<AutomationStatus>('loading');
  private readonly _summary = signal<AutomationSummary | null>(null);
  private readonly _error = signal('');
  private readonly _tasks = signal<CronRun[]>([]);
  private readonly _summaryUnavailable = signal(false);
  private readonly _tasksUnavailable = signal(false);
  readonly status = this._status.asReadonly();
  readonly summary = this._summary.asReadonly();
  readonly error = this._error.asReadonly();
  readonly tasks = this._tasks.asReadonly();
  readonly summaryUnavailable = this._summaryUnavailable.asReadonly();
  readonly tasksUnavailable = this._tasksUnavailable.asReadonly();
  readonly health = computed(() => {
    const summary = this._summary();
    return summary ? summarizeAutomationHealth(summary) : { overall: 'unknown' as const, actionableCount: 0 };
  });
  private pollHandle?: number;

  constructor() {
    this.destroyRef.onDestroy(() => this.stopPolling());
  }

  startPolling(intervalMs = 60_000): void {
    if (this.pollHandle) return;
    void this.refresh();
    this.pollHandle = window.setInterval(() => void this.refresh(), intervalMs);
  }

  async refresh(): Promise<void> {
    const [summaryResult, cronResult] = await Promise.allSettled([
      this.api.getAutomationSummary(),
      this.api.listCronLogs(),
    ]);
    if (summaryResult.status === 'fulfilled') {
      this._summary.set(summaryResult.value);
      this._summaryUnavailable.set(false);
    } else {
      this._summaryUnavailable.set(true);
    }
    if (cronResult.status === 'fulfilled' && cronResult.value.ok !== false) {
      const latest = new Map<string, CronRun>();
      for (const run of cronResult.value.runs) {
        const current = latest.get(run.jobId);
        if (!current || (run.timestamp || '') > (current.timestamp || '')) latest.set(run.jobId, run);
      }
      this._tasks.set([...latest.values()].sort((a, b) => a.jobTitle.localeCompare(b.jobTitle)));
      this._tasksUnavailable.set(false);
    } else {
      this._tasksUnavailable.set(true);
    }
    if (this._summaryUnavailable() && this._tasksUnavailable()) {
      this._status.set('error');
      this._error.set('Automation is temporarily unavailable. Try again.');
      return;
    }
    this._error.set('');
    if (this._summaryUnavailable() || this._tasksUnavailable()) this._status.set('partial');
    else if (!this._summary() && this._tasks().length === 0) this._status.set('empty');
    else {
      const summaryStatus = this._summary() ? this.deriveStatus(this._summary()!) : 'empty';
      this._status.set(summaryStatus === 'partial' ? 'partial' : this._tasks().length > 0 ? 'ready' : summaryStatus);
    }
  }

  private deriveStatus(summary: AutomationSummary): AutomationStatus {
    const availability = summary.availability;
    const hasAnySignal =
      summary.services.length > 0 ||
      summary.problems.length > 0;

    const anyUnavailable =
      availability.services === 'unavailable' ||
      availability.problems === 'unavailable';

    if (anyUnavailable) return 'partial';
    if (!hasAnySignal) return 'empty';
    return 'ready';
  }

  private stopPolling(): void {
    if (this.pollHandle) window.clearInterval(this.pollHandle);
    this.pollHandle = undefined;
  }
}
