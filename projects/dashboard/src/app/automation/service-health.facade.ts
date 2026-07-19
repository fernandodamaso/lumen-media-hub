import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import { AutomationSummary, summarizeAutomationHealth } from './automation.models';

export type ServiceHealthStatus = 'loading' | 'ready' | 'empty' | 'error';

const REFRESH_ERROR = 'Could not refresh service health. Showing last loaded status.';
const LOAD_ERROR = 'Service health is temporarily unavailable. Try again.';
/** Bound scheduled polls so a hung `/automation/summary` request cannot lock out later ticks. */
export const SCHEDULED_REFRESH_TIMEOUT_MS = 15_000;

@Injectable({ providedIn: 'root' })
export class ServiceHealthFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly destroyRef = inject(DestroyRef);
  private readonly _status = signal<ServiceHealthStatus>('loading');
  private readonly _summary = signal<AutomationSummary | null>(null);
  private readonly _error = signal('');
  private readonly _refreshing = signal(false);
  private requestId = 0;
  private scheduledInFlight = false;
  private pollHandle?: ReturnType<typeof setInterval>;
  private refreshAbort?: AbortController;
  private refreshTimeoutId?: ReturnType<typeof setTimeout>;

  readonly status = this._status.asReadonly();
  readonly summary = this._summary.asReadonly();
  readonly error = this._error.asReadonly();
  readonly refreshing = this._refreshing.asReadonly();
  readonly services = computed(() => this._summary()?.services ?? []);
  readonly problems = computed(() => this._summary()?.problems ?? []);
  readonly generatedAt = computed(() => this._summary()?.generatedAt ?? '');
  readonly health = computed(() => {
    const summary = this._summary();
    return summary ? summarizeAutomationHealth(summary) : { overall: 'unknown' as const, actionableCount: 0 };
  });

  constructor() {
    this.destroyRef.onDestroy(() => this.stopPolling());
  }

  startPolling(intervalMs = 60_000): void {
    if (this.pollHandle) return;
    void this.runScheduledRefresh(true);
    this.pollHandle = setInterval(() => void this.runScheduledRefresh(false), intervalMs);
  }

  async refresh(options: { initial?: boolean; signal?: AbortSignal } = {}): Promise<boolean> {
    const initial =
      options.initial === true || this._status() === 'loading' || this._status() === 'error';
    this._refreshing.set(true);
    const requestId = ++this.requestId;
    try {
      const summary = await this.api.getAutomationSummary(options.signal);
      if (requestId !== this.requestId) return false;
      this._summary.set(summary);
      this._error.set('');
      this._status.set(summary.services.length ? 'ready' : 'empty');
      return true;
    } catch {
      if (requestId !== this.requestId) return false;
      // Cancelled refreshes must not mutate facade state; callers apply timeout/teardown policy.
      if (options.signal?.aborted) return true;
      this.applyRefreshFailure(initial);
      return true;
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
      const wasCurrent = await this.refresh({ initial, signal: abort.signal });
      // Only stamp timeout failure when this aborted request is still the latest generation.
      if (abort.signal.aborted && wasCurrent && this.pollHandle !== undefined) {
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
      this._summary.set(null);
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
