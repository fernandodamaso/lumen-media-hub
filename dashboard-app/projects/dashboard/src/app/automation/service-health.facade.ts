import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import {
  applyPolledRefreshFailure,
  isInitialRefresh,
  runPolledRefresh,
} from '../media-stack/polled-refresh';
import { ScheduledPollController } from '../media-stack/scheduled-poll';
import { AutomationSummary, QueueHygieneRunResult, summarizeAutomationHealth } from './automation.models';

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
  private readonly _queueHygieneRunning = signal(false);
  private readonly _queueHygieneError = signal('');
  private readonly _lastQueueHygieneRun = signal<QueueHygieneRunResult | null>(null);
  private queueHygieneRequest: Promise<QueueHygieneRunResult> | null = null;
  private destroyed = false;

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
  readonly queueHygiene = computed(() => this._summary()?.queueHygiene ?? null);
  readonly queueHygieneRunning = this._queueHygieneRunning.asReadonly();
  readonly queueHygieneError = this._queueHygieneError.asReadonly();
  readonly lastQueueHygieneRun = this._lastQueueHygieneRun.asReadonly();

  constructor() {
    this.destroyRef.onDestroy(() => {
      this.poll.stop();
      this._refreshing.set(false);
      this.destroyed = true;
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
    const initial = isInitialRefresh(this._status(), options.initial);
    await runPolledRefresh({
      poll: this.poll,
      refreshing: this._refreshing,
      signal: options.signal,
      load: async (requestId) => {
        const summary = await this.api.getAutomationSummary(options.signal);
        if (!this.poll.isCurrent(requestId)) return;
        this._summary.set(summary);
        this._lastFetchedAt.set(new Date().toISOString());
        this._error.set('');
        this._status.set(summary.services.length ? 'ready' : 'empty');
      },
      onFailure: () => {
        this.applyRefreshFailure(initial);
      },
    });
  }

  runQueueHygiene(mode: 'observe' | 'auto'): Promise<QueueHygieneRunResult> {
    if (this.queueHygieneRequest) return this.queueHygieneRequest;
    this._queueHygieneRunning.set(true);
    this._queueHygieneError.set('');
    const request = (async () => {
      const result = await this.api.runQueueHygiene(mode);
      if (!this.destroyed) {
        this._lastQueueHygieneRun.set(result);
        if (result.status === 'error' || result.status === 'verification_failed' || result.status === 'circuit_open') {
          this._queueHygieneError.set(result.error || 'Queue hygiene requires attention.');
        }
        await this.refresh();
      }
      return result;
    })()
      .catch((error: unknown) => {
        if (!this.destroyed) this._queueHygieneError.set(error instanceof Error ? error.message : 'Queue hygiene action failed.');
        throw error;
      })
      .finally(() => {
        if (!this.destroyed) this._queueHygieneRunning.set(false);
        this.queueHygieneRequest = null;
      });
    this.queueHygieneRequest = request;
    return request;
  }

  private applyRefreshFailure(initial: boolean): void {
    applyPolledRefreshFailure({
      initial,
      status: this._status,
      error: this._error,
      refreshError: REFRESH_ERROR,
      loadError: LOAD_ERROR,
      clearPayload: () => {
        this._summary.set(null);
      },
    });
  }
}
