import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import { StorageOverview, StorageVolume } from './storage.models';

export type StorageStatus = 'loading' | 'ready' | 'empty' | 'error';

const REFRESH_ERROR = 'Could not refresh storage. Showing last loaded capacity.';
const LOAD_ERROR = 'Storage overview is temporarily unavailable. Try again.';
/** Bound scheduled polls so a hung storage request cannot lock out later ticks. */
export const SCHEDULED_REFRESH_TIMEOUT_MS = 15_000;

@Injectable()
export class StorageFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly destroyRef = inject(DestroyRef);
  private readonly _status = signal<StorageStatus>('loading');
  private readonly _overview = signal<StorageOverview | null>(null);
  private readonly _error = signal('');
  private readonly _refreshing = signal(false);
  private requestId = 0;
  private scheduledInFlight = false;
  private pollHandle?: ReturnType<typeof setInterval>;
  private refreshAbort?: AbortController;
  private refreshTimeoutId?: ReturnType<typeof setTimeout>;

  readonly status = this._status.asReadonly();
  readonly overview = this._overview.asReadonly();
  readonly error = this._error.asReadonly();
  readonly refreshing = this._refreshing.asReadonly();
  readonly volumes = computed(() => this._overview()?.volumes ?? []);

  constructor() {
    this.destroyRef.onDestroy(() => this.stopPolling());
  }

  startPolling(intervalMs = 60_000): void {
    if (this.pollHandle) return;
    void this.runScheduledRefresh(true);
    this.pollHandle = setInterval(() => void this.runScheduledRefresh(false), intervalMs);
  }

  async refresh(options: { initial?: boolean; signal?: AbortSignal } = {}): Promise<void> {
    const initial =
      options.initial === true || this._status() === 'loading' || this._status() === 'error';
    this._refreshing.set(true);
    const requestId = ++this.requestId;
    try {
      const overview = await this.api.getStorageOverview(options.signal);
      if (requestId !== this.requestId) return;
      this._overview.set(overview);
      this._error.set('');
      this._status.set(overview.volumes.length ? 'ready' : 'empty');
    } catch {
      if (requestId !== this.requestId) return;
      if (options.signal?.aborted) return;
      this.applyRefreshFailure(initial);
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
      await this.refresh({ initial, signal: abort.signal });
      if (abort.signal.aborted && this.pollHandle !== undefined) {
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
      this._overview.set(null);
    }
  }

  private stopPolling(): void {
    if (this.pollHandle) clearInterval(this.pollHandle);
    this.pollHandle = undefined;
    if (this.refreshTimeoutId !== undefined) {
      clearTimeout(this.refreshTimeoutId);
      this.refreshTimeoutId = undefined;
    }
    this.requestId++;
    this.refreshAbort?.abort();
    this.refreshAbort = undefined;
    this.scheduledInFlight = false;
    this._refreshing.set(false);
  }
}

export const percentageUsed = (volume: StorageVolume): number => {
  if (!volume.totalBytes) return 0;
  return Math.min(100, Math.round((volume.usedBytes / volume.totalBytes) * 100));
};
