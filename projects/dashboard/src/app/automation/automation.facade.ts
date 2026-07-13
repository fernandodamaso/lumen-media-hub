import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import {
  AutomationSummary,
  MEDIA_STACK_API,
  normalizeAutomationSummary,
  summarizeAutomationHealth,
} from '../downloads/media-stack-api';

export type AutomationStatus = 'loading' | 'ready' | 'empty' | 'partial' | 'error';

@Injectable()
export class AutomationFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly destroyRef = inject(DestroyRef);
  private readonly _status = signal<AutomationStatus>('loading');
  private readonly _summary = signal<AutomationSummary | null>(null);
  private readonly _error = signal('');
  readonly status = this._status.asReadonly();
  readonly summary = this._summary.asReadonly();
  readonly error = this._error.asReadonly();
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
    try {
      const dto = await this.api.getAutomationSummary();
      const summary = normalizeAutomationSummary(dto);
      this._summary.set(summary);
      this._status.set(this.deriveStatus(summary));
      this._error.set('');
    } catch {
      this._status.set('error');
      this._error.set('Automation is temporarily unavailable. Try again.');
    }
  }

  private deriveStatus(summary: AutomationSummary): AutomationStatus {
    const availability = summary.availability;
    const hasAnySignal =
      summary.services.length > 0 ||
      summary.preview.length > 0 ||
      summary.problems.length > 0;

    const anyUnavailable =
      availability.services === 'unavailable' ||
      availability.preview === 'unavailable' ||
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
