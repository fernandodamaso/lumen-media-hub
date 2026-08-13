import { DestroyRef, inject, Injectable, signal } from '@angular/core';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import {
  applyPolledRefreshFailure,
  isInitialRefresh,
  runPolledRefresh,
} from '../media-stack/polled-refresh';
import { ScheduledPollController } from '../media-stack/scheduled-poll';
import { RecentlyAvailableItem } from './recently-available.models';

export type RecentlyAvailableStatus = 'loading' | 'ready' | 'empty' | 'error';

const LOAD_ERROR = 'Newly available media is temporarily unavailable. Try again.';
const REFRESH_ERROR = 'Could not refresh newly available media. Showing last loaded items.';
const RECENTLY_AVAILABLE_LIMIT = 10;

@Injectable({ providedIn: 'root' })
export class RecentlyAvailableFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly destroyRef = inject(DestroyRef);
  private readonly poll = new ScheduledPollController();
  private readonly _status = signal<RecentlyAvailableStatus>('loading');
  private readonly _items = signal<RecentlyAvailableItem[]>([]);
  private readonly _error = signal('');
  private readonly _refreshing = signal(false);
  private readonly _lastFetchedAt = signal('');

  readonly status = this._status.asReadonly();
  readonly items = this._items.asReadonly();
  readonly error = this._error.asReadonly();
  readonly refreshing = this._refreshing.asReadonly();
  readonly lastFetchedAt = this._lastFetchedAt.asReadonly();

  constructor() {
    this.destroyRef.onDestroy(() => {
      this.stopPolling();
    });
  }

  startPolling(intervalMs = 60_000): void {
    this.poll.startRefreshing(
      intervalMs,
      ({ signal }) => this.refresh({ signal }),
      () => {
        const initial = this._status() !== 'ready' && this._status() !== 'empty';
        this.applyRefreshFailure(initial);
        this._refreshing.set(false);
      },
    );
  }

  stopPolling(): void {
    this.poll.stop();
    this._refreshing.set(false);
  }

  async refresh(options: { initial?: boolean; signal?: AbortSignal } = {}): Promise<void> {
    const initial = isInitialRefresh(this._status(), options.initial);
    await runPolledRefresh({
      poll: this.poll,
      refreshing: this._refreshing,
      signal: options.signal,
      load: async (requestId) => {
        const result = await this.api.listRecentlyAvailable(
          RECENTLY_AVAILABLE_LIMIT,
          options.signal,
        );
        if (!this.poll.isCurrent(requestId)) return;
        this._items.set(result.items);
        this._lastFetchedAt.set(new Date().toISOString());
        this._status.set(result.items.length ? 'ready' : 'empty');
        this._error.set('');
      },
      onFailure: () => {
        this.applyRefreshFailure(initial);
      },
    });
  }

  private applyRefreshFailure(initial: boolean): void {
    applyPolledRefreshFailure({
      initial,
      status: this._status,
      error: this._error,
      refreshError: REFRESH_ERROR,
      loadError: LOAD_ERROR,
      clearPayload: () => {
        this._items.set([]);
      },
    });
  }
}
