import { Injectable, inject, signal } from '@angular/core';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import {
  CronHealthSummary,
  CronHistoricalRun,
  CronRun,
  prioritizeCronRuns,
  summarizeCronHealth,
} from './reports.models';

export type ReportsStatus = 'loading' | 'empty' | 'allClear' | 'mixed' | 'error';

const REFRESH_ERROR = 'Could not refresh reports. Showing last loaded history.';
const LOAD_ERROR = 'Reports are temporarily unavailable. Try again.';

@Injectable()
export class ReportsFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly _status = signal<ReportsStatus>('loading');
  private readonly _currentRuns = signal<CronRun[]>([]);
  private readonly _historyRuns = signal<CronHistoricalRun[]>([]);
  private readonly _summary = signal<CronHealthSummary>({
    kind: 'empty',
    totalJobs: 0,
    affectedJobs: 0,
    healthyJobs: 0,
  });
  private readonly _generatedAt = signal('');
  private readonly _error = signal('');
  private readonly _refreshing = signal(false);
  private requestId = 0;

  readonly status = this._status.asReadonly();
  /** Current run per job, actionable-first for display. Drives the health banner. */
  readonly currentRuns = this._currentRuns.asReadonly();
  /** Older runs, newest-first for display, each labeled resolved/historical. */
  readonly historyRuns = this._historyRuns.asReadonly();
  readonly summary = this._summary.asReadonly();
  readonly generatedAt = this._generatedAt.asReadonly();
  readonly error = this._error.asReadonly();
  readonly refreshing = this._refreshing.asReadonly();

  load(): Promise<void> {
    return this.refresh({ initial: true });
  }

  refresh(options: { initial?: boolean } = {}): Promise<void> {
    const initial = options.initial === true;
    // Mark in-flight for both initial load and manual refresh so Refresh stays disabled
    // and concurrent clicks cannot race older responses over newer ones.
    this._refreshing.set(true);
    const requestId = ++this.requestId;
    return this.fetch(initial, requestId).finally(() => {
      if (requestId === this.requestId) this._refreshing.set(false);
    });
  }

  private async fetch(initial: boolean, requestId: number): Promise<void> {
    try {
      const logs = await this.api.listCronLogs();
      if (requestId !== this.requestId) return;
      if (!logs.ok) {
        throw new Error(logs.error?.trim() || 'Cron logs unavailable');
      }
      const current = prioritizeCronRuns(logs.currentRuns);
      const history = [...logs.historyRuns].sort((left, right) =>
        right.timestamp.localeCompare(left.timestamp),
      );
      const summary = summarizeCronHealth(current);
      this._currentRuns.set(current);
      this._historyRuns.set(history);
      this._summary.set(summary);
      this._generatedAt.set(logs.generatedAt ?? '');
      this._error.set('');
      this._status.set(this.statusFromSummary(summary));
    } catch {
      if (requestId !== this.requestId) return;
      const hasPrior = this._currentRuns().length > 0 || this._generatedAt() !== '';
      if (!initial && hasPrior) {
        // Retain prior runs/summary/generatedAt; keep health status. Do not exclusive-error.
        this._error.set(REFRESH_ERROR);
        return;
      }
      this._status.set('error');
      this._error.set(LOAD_ERROR);
      if (initial) {
        this._currentRuns.set([]);
        this._historyRuns.set([]);
        this._summary.set({ kind: 'empty', totalJobs: 0, affectedJobs: 0, healthyJobs: 0 });
        this._generatedAt.set('');
      }
    }
  }

  private statusFromSummary(summary: CronHealthSummary): ReportsStatus {
    if (summary.kind === 'empty') return 'empty';
    if (summary.kind === 'allClear') return 'allClear';
    return 'mixed';
  }
}
