import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import { LibraryStats } from './library.models';
import { applyLibraryLoadFailure } from './library-refresh';

export type LibraryStatsStatus = 'loading' | 'ready' | 'error';

const REFRESH_ERROR = 'Could not refresh library totals. Showing last loaded counts.';
const LOAD_ERROR = 'Library stats are temporarily unavailable. Try again.';

@Injectable()
export class LibraryStatsFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly destroyRef = inject(DestroyRef);
  private readonly _status = signal<LibraryStatsStatus>('loading');
  private readonly _stats = signal<LibraryStats | null>(null);
  private readonly _error = signal('');
  private readonly _refreshing = signal(false);
  private readonly _lastFetchedAt = signal('');
  private requestId = 0;

  readonly status = this._status.asReadonly();
  readonly stats = this._stats.asReadonly();
  readonly error = this._error.asReadonly();
  readonly refreshing = this._refreshing.asReadonly();
  readonly lastFetchedAt = this._lastFetchedAt.asReadonly();
  readonly availability = computed(() => this._stats()?.availability ?? 'complete');

  constructor() {
    this.destroyRef.onDestroy(() => {
      this.requestId++;
    });
    void this.refresh({ initial: true });
  }

  async refresh(options: { initial?: boolean; signal?: AbortSignal } = {}): Promise<void> {
    const initial =
      options.initial === true || this._status() === 'loading' || this._status() === 'error';
    this._refreshing.set(true);
    const requestId = ++this.requestId;
    try {
      const stats = await this.api.getLibraryStats(options.signal);
      if (requestId !== this.requestId) return;
      this._stats.set(stats);
      this._lastFetchedAt.set(new Date().toISOString());
      this._error.set('');
      this._status.set('ready');
    } catch {
      if (requestId !== this.requestId) return;
      if (options.signal?.aborted) return;
      applyLibraryLoadFailure({
        initial,
        status: this._status,
        error: this._error,
        hasPriorData: this._status() === 'ready' && this._stats() !== null,
        refreshError: REFRESH_ERROR,
        loadError: LOAD_ERROR,
        clearOnInitial: () => {
          this._stats.set(null);
        },
      });
    } finally {
      if (requestId === this.requestId) this._refreshing.set(false);
    }
  }
}
