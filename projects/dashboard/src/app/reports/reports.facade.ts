import { Injectable, inject, signal } from '@angular/core';
import {
  CronHealthSummary,
  CronRun,
  MEDIA_STACK_API,
  flattenCronRuns,
  prioritizeCronRuns,
  summarizeCronHealth,
} from '../media-stack/media-stack-api';

export type ReportsStatus = 'loading' | 'empty' | 'allClear' | 'mixed' | 'error';

const REFRESH_ERROR = 'Could not refresh reports. Showing last loaded history.';
const LOAD_ERROR = 'Reports are temporarily unavailable. Try again.';

@Injectable()
export class ReportsFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly _status = signal<ReportsStatus>('loading');
  private readonly _runs = signal<CronRun[]>([]);
  private readonly _summary = signal<CronHealthSummary>({ kind: 'empty', total: 0, actionable: 0, quiet: 0 });
  private readonly _generatedAt = signal('');
  private readonly _error = signal('');
  private readonly _refreshing = signal(false);
  private requestId = 0;

  readonly status = this._status.asReadonly();
  readonly runs = this._runs.asReadonly();
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
      const dto = await this.api.listCronLogs();
      if (requestId !== this.requestId) return;
      if (!dto.ok) {
        throw new Error(dto.error?.trim() || 'Cron logs unavailable');
      }
      const runs = prioritizeCronRuns(flattenCronRuns(dto));
      const summary = summarizeCronHealth(runs);
      this._runs.set(runs);
      this._summary.set(summary);
      this._generatedAt.set(dto.generatedAt ?? new Date().toISOString());
      this._error.set('');
      this._status.set(this.statusFromSummary(summary));
    } catch {
      if (requestId !== this.requestId) return;
      const hasPrior = this._runs().length > 0 || this._generatedAt() !== '';
      if (!initial && hasPrior) {
        // Retain prior runs/summary/generatedAt; keep health status. Do not exclusive-error.
        this._error.set(REFRESH_ERROR);
        return;
      }
      this._status.set('error');
      this._error.set(LOAD_ERROR);
      if (initial) {
        this._runs.set([]);
        this._summary.set({ kind: 'empty', total: 0, actionable: 0, quiet: 0 });
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
