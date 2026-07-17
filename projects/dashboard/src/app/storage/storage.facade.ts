import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import { StorageOverview, StorageVolume } from './storage.models';

export type StorageStatus = 'loading' | 'ready' | 'empty' | 'error';

@Injectable()
export class StorageFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly destroyRef = inject(DestroyRef);
  private readonly _status = signal<StorageStatus>('loading');
  private readonly _overview = signal<StorageOverview | null>(null);
  private readonly _error = signal('');
  readonly status = this._status.asReadonly();
  readonly overview = this._overview.asReadonly();
  readonly error = this._error.asReadonly();
  readonly volumes = computed(() => this._overview()?.volumes ?? []);
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
      const overview = await this.api.getStorageOverview();
      this._overview.set(overview);
      this._error.set('');
      this._status.set(overview.volumes.length ? 'ready' : 'empty');
    } catch {
      this._overview.set(null);
      this._status.set('error');
      this._error.set('Storage overview is temporarily unavailable. Try again.');
    }
  }

  private stopPolling(): void {
    if (this.pollHandle) window.clearInterval(this.pollHandle);
    this.pollHandle = undefined;
  }
}

export const percentageUsed = (volume: StorageVolume): number => {
  if (!volume.totalBytes) return 0;
  return Math.min(100, Math.round((volume.usedBytes / volume.totalBytes) * 100));
};
