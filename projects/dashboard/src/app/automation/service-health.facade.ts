import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import { AutomationSummary, summarizeAutomationHealth } from './automation.models';

export type ServiceHealthStatus = 'loading' | 'ready' | 'empty' | 'error';

@Injectable({ providedIn: 'root' })
export class ServiceHealthFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly destroyRef = inject(DestroyRef);
  private readonly _status = signal<ServiceHealthStatus>('loading');
  private readonly _summary = signal<AutomationSummary | null>(null);
  private readonly _error = signal('');
  readonly status = this._status.asReadonly();
  readonly summary = this._summary.asReadonly();
  readonly error = this._error.asReadonly();
  readonly services = computed(() => this._summary()?.services ?? []);
  readonly problems = computed(() => this._summary()?.problems ?? []);
  readonly generatedAt = computed(() => this._summary()?.generatedAt ?? '');
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
    this._status.set('loading');
    try {
      const summary = await this.api.getAutomationSummary();
      this._summary.set(summary);
      this._error.set('');
      this._status.set(summary.services.length ? 'ready' : 'empty');
    } catch {
      this._summary.set(null);
      this._status.set('error');
      this._error.set('Service health is temporarily unavailable. Try again.');
    }
  }

  private stopPolling(): void {
    if (this.pollHandle) window.clearInterval(this.pollHandle);
    this.pollHandle = undefined;
  }
}
