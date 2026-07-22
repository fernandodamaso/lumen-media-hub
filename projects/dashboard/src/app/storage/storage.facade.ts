import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import { ScheduledPollController } from '../media-stack/scheduled-poll';
import { StorageOverview, StorageVolume } from './storage.models';

export type StorageStatus = 'loading' | 'ready' | 'empty' | 'error';

const REFRESH_ERROR = 'Could not refresh storage. Showing last loaded capacity.';
const LOAD_ERROR = 'Storage overview is temporarily unavailable. Try again.';
/** Re-export for existing specs; canonical home is `media-stack/scheduled-poll`. */
export { SCHEDULED_REFRESH_TIMEOUT_MS } from '../media-stack/scheduled-poll';

@Injectable()
export class StorageFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly destroyRef = inject(DestroyRef);
  private readonly poll = new ScheduledPollController();
  private readonly _status = signal<StorageStatus>('loading');
  private readonly _overview = signal<StorageOverview | null>(null);
  private readonly _error = signal('');
  private readonly _refreshing = signal(false);
  private readonly _lastFetchedAt = signal('');

  readonly status = this._status.asReadonly();
  readonly overview = this._overview.asReadonly();
  readonly error = this._error.asReadonly();
  readonly refreshing = this._refreshing.asReadonly();
  readonly lastFetchedAt = this._lastFetchedAt.asReadonly();
  readonly volumes = computed(() => this._overview()?.volumes ?? []);
  readonly generatedAt = computed(() => this._overview()?.generatedAt ?? '');

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
      const overview = await this.api.getStorageOverview(options.signal);
      if (!this.poll.isCurrent(requestId)) return;
      this._overview.set(overview);
      this._lastFetchedAt.set(new Date().toISOString());
      this._error.set('');
      this._status.set(overview.volumes.length ? 'ready' : 'empty');
    } catch {
      if (!this.poll.isCurrent(requestId)) return;
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
      this._overview.set(null);
    }
  }
}

export const percentageUsed = (volume: StorageVolume): number => {
  if (!volume.totalBytes) return 0;
  return Math.min(100, Math.round((volume.usedBytes / volume.totalBytes) * 100));
};
