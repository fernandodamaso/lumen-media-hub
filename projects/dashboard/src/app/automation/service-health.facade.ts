import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import { AutomationSummary, summarizeAutomationHealth } from './automation.models';

export type ServiceHealthStatus = 'loading' | 'ready' | 'empty' | 'error';

const REFRESH_ERROR = 'Could not refresh service health. Showing last loaded status.';
const LOAD_ERROR = 'Service health is temporarily unavailable. Try again.';

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

  async refresh(options: { initial?: boolean } = {}): Promise<void> {
    const initial =
      options.initial === true || this._status() === 'loading' || this._status() === 'error';
    this._refreshing.set(true);
    const requestId = ++this.requestId;
    try {
      const summary = await this.api.getAutomationSummary();
      if (requestId !== this.requestId) return;
      this._summary.set(summary);
      this._error.set('');
      this._status.set(summary.services.length ? 'ready' : 'empty');
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
      this._summary.set(null);
    }
  }

  private stopPolling(): void {
    if (this.pollHandle) clearInterval(this.pollHandle);
    this.pollHandle = undefined;
    // Bump requestId so any in-flight scheduled refresh is ignored after destroy.
    this.requestId += 1;
    this.scheduledInFlight = false;
    this._refreshing.set(false);
  }
}
