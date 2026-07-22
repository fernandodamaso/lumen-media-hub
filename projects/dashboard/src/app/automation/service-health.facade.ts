import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import { ScheduledPollController } from '../media-stack/scheduled-poll';
import { AutomationSummary, summarizeAutomationHealth } from './automation.models';

export type ServiceHealthStatus = 'loading' | 'ready' | 'empty' | 'error';

const REFRESH_ERROR = 'Could not refresh service health. Showing last loaded status.';
const LOAD_ERROR = 'Service health is temporarily unavailable. Try again.';
/** Re-export for existing specs; canonical home is `media-stack/scheduled-poll`. */
export { SCHEDULED_REFRESH_TIMEOUT_MS } from '../media-stack/scheduled-poll';

@Injectable({ providedIn: 'root' })
export class ServiceHealthFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly destroyRef = inject(DestroyRef);
  private readonly poll = new ScheduledPollController();
  private readonly _status = signal<ServiceHealthStatus>('loading');
  private readonly _summary = signal<AutomationSummary | null>(null);
  private readonly _error = signal('');
  private readonly _refreshing = signal(false);
  private readonly _lastFetchedAt = signal('');

  readonly status = this._status.asReadonly();
  readonly summary = this._summary.asReadonly();
  readonly error = this._error.asReadonly();
  readonly refreshing = this._refreshing.asReadonly();
  readonly lastFetchedAt = this._lastFetchedAt.asReadonly();
  readonly services = computed(() => this._summary()?.services ?? []);
  readonly problems = computed(() => this._summary()?.problems ?? []);
  readonly generatedAt = computed(() => this._summary()?.generatedAt ?? '');
  readonly health = computed(() => {
    const summary = this._summary();
    return summary ? summarizeAutomationHealth(summary) : { overall: 'unknown' as const, actionableCount: 0 };
  });

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

  async refresh(options: { initial?: boolean; signal?: AbortSignal } = {}): Promise<void> {
    const initial =
      options.initial === true || this._status() === 'loading' || this._status() === 'error';
    this._refreshing.set(true);
    const requestId = this.poll.beginRequest();
    try {
      const summary = await this.api.getAutomationSummary(options.signal);
      if (!this.poll.isCurrent(requestId)) return;
      this._summary.set(summary);
      this._lastFetchedAt.set(new Date().toISOString());
      this._error.set('');
      this._status.set(summary.services.length ? 'ready' : 'empty');
    } catch {
      if (!this.poll.isCurrent(requestId)) return;
      // Cancelled refreshes must not mutate facade state; callers apply timeout/teardown policy.
      if (options.signal?.aborted) return;
      this.applyRefreshFailure(initial);
    } finally {
      if (this.poll.isCurrent(requestId)) this._refreshing.set(false);
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
}
