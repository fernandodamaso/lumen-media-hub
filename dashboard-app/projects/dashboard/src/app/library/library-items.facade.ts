import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import { LibraryItem, LibraryDeletePreview, LibraryDeleteResult } from './library.models';
import { applyLibraryLoadFailure } from './library-refresh';

export type LibraryItemsStatus = 'loading' | 'ready' | 'empty' | 'error';

const REFRESH_ERROR = 'Could not refresh library items. Showing last loaded titles.';
const LOAD_ERROR = 'Library items are temporarily unavailable. Try again.';
const PARTIAL_LOAD_ERROR =
  'One library source failed to load. Counts and titles may be incomplete.';

@Injectable({ providedIn: 'root' })
export class LibraryItemsFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly destroyRef = inject(DestroyRef);
  private readonly _status = signal<LibraryItemsStatus>('loading');
  private readonly _items = signal<LibraryItem[]>([]);
  private readonly _availability = signal<'complete' | 'partial'>('complete');
  private readonly _error = signal('');
  private readonly _refreshing = signal(false);
  private readonly _lastFetchedAt = signal('');
  private readonly _movieCount = signal(0);
  private readonly _seriesCount = signal(0);
  private requestId = 0;

  readonly status = this._status.asReadonly();
  readonly items = this._items.asReadonly();
  readonly availability = this._availability.asReadonly();
  readonly error = this._error.asReadonly();
  readonly refreshing = this._refreshing.asReadonly();
  readonly lastFetchedAt = this._lastFetchedAt.asReadonly();
  readonly movieCount = this._movieCount.asReadonly();
  readonly seriesCount = this._seriesCount.asReadonly();
  readonly totalCount = computed(() => this._movieCount() + this._seriesCount());

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
      const result = await this.api.listLibraryItems(undefined, options.signal);
      if (requestId !== this.requestId) return;
      this._items.set(result.items);
      this._availability.set(result.availability);
      this._lastFetchedAt.set(new Date().toISOString());
      this.applyCounts(result);
      if (result.availability === 'partial') {
        this._error.set(PARTIAL_LOAD_ERROR);
        this._status.set(result.items.length ? 'ready' : 'error');
        return;
      }
      this._error.set('');
      this._status.set(result.items.length ? 'ready' : 'empty');
    } catch {
      if (requestId !== this.requestId) return;
      if (options.signal?.aborted) return;
      applyLibraryLoadFailure({
        initial,
        status: this._status,
        error: this._error,
        hasPriorData: this._status() === 'ready' || this._status() === 'empty',
        refreshError: REFRESH_ERROR,
        loadError: LOAD_ERROR,
        clearOnInitial: () => {
          this._items.set([]);
          this._movieCount.set(0);
          this._seriesCount.set(0);
        },
      });
    } finally {
      if (requestId === this.requestId) this._refreshing.set(false);
    }
  }

  private applyCounts(result: {
    items: LibraryItem[];
    movieCount?: number;
    seriesCount?: number;
  }): void {
    const moviesFromItems = result.items.filter((item) => item.kind === 'movie').length;
    const seriesFromItems = result.items.filter((item) => item.kind === 'series').length;
    this._movieCount.set(
      typeof result.movieCount === 'number' && Number.isFinite(result.movieCount)
        ? Math.max(moviesFromItems, Math.floor(result.movieCount))
        : moviesFromItems,
    );
    this._seriesCount.set(
      typeof result.seriesCount === 'number' && Number.isFinite(result.seriesCount)
        ? Math.max(seriesFromItems, Math.floor(result.seriesCount))
        : seriesFromItems,
    );
  }

  async setPlayed(id: string, played: boolean): Promise<void> {
    const result = await this.api.setLibraryItemPlayed(id, played);
    this._items.update((items) =>
      items.map((item) => (item.id === id ? { ...item, played: result.played } : item)),
    );
  }

  previewDeletion(id: string): Promise<LibraryDeletePreview> {
    return this.api.previewLibraryItemDeletion(id);
  }

  async deleteItem(id: string, previewId: string): Promise<LibraryDeleteResult> {
    const result = await this.api.deleteLibraryItem(id, previewId);
    if (result.removed) {
      const removed = this._items().find((item) => item.id === id);
      this._items.update((items) => items.filter((item) => item.id !== id));
      if (removed?.kind === 'movie') {
        this._movieCount.update((count) => Math.max(0, count - 1));
      } else if (removed?.kind === 'series') {
        this._seriesCount.update((count) => Math.max(0, count - 1));
      }
      if (this._items().length === 0) {
        this._status.set('empty');
      }
    }
    return result;
  }

  async deleteItemDirectly(id: string): Promise<{ removed: boolean; kind: LibraryItem['kind'] | null }> {
    const removedItem = this._items().find((item) => item.id === id);
    await this.api.deleteLibraryItemDirectly(id);
    this._items.update((items) => items.filter((item) => item.id !== id));
    if (removedItem?.kind === 'movie') {
      this._movieCount.update((count) => Math.max(0, count - 1));
    } else if (removedItem?.kind === 'series') {
      this._seriesCount.update((count) => Math.max(0, count - 1));
    }
    if (this._items().length === 0) {
      this._status.set('empty');
    }
    return { removed: true, kind: removedItem?.kind ?? null };
  }
}
