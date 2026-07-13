import { inject, Injectable, signal } from '@angular/core';
import {
  JELLYFIN_LINK_BASES,
  LibraryItem,
  LibraryItemKind,
  MEDIA_STACK_API,
  normalizeLibraryItem,
  resolveJellyfinItemLink,
} from '../downloads/media-stack-api';

export type LibraryStatus = 'loading' | 'ready' | 'empty' | 'error';

@Injectable()
export class LibraryFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly linkBases = inject(JELLYFIN_LINK_BASES);
  private catalog: LibraryItem[] = [];
  private readonly _status = signal<LibraryStatus>('loading');
  private readonly _kind = signal<LibraryItemKind>('movie');
  private readonly _items = signal<LibraryItem[]>([]);
  private readonly _movieCount = signal(0);
  private readonly _seriesCount = signal(0);
  private readonly _error = signal('');

  readonly status = this._status.asReadonly();
  readonly kind = this._kind.asReadonly();
  readonly items = this._items.asReadonly();
  readonly movieCount = this._movieCount.asReadonly();
  readonly seriesCount = this._seriesCount.asReadonly();
  readonly error = this._error.asReadonly();

  constructor() {
    void this.refresh();
  }

  setKind(kind: LibraryItemKind): void {
    if (this._kind() === kind) return;
    this._kind.set(kind);
    this.syncItems();
    if (this._status() === 'loading' || this._status() === 'error') return;
    this.settleStatus();
  }

  async refresh(): Promise<void> {
    this._status.set('loading');
    try {
      const raw = await this.api.listLibraryItems();
      this.catalog = raw.map(normalizeLibraryItem).map((item) => ({
        ...item,
        href: resolveJellyfinItemLink(item, this.linkBases),
      }));
      this._movieCount.set(this.catalog.filter((item) => item.kind === 'movie').length);
      this._seriesCount.set(this.catalog.filter((item) => item.kind === 'series').length);
      this._error.set('');
      this.syncItems();
      this.settleStatus();
    } catch {
      this.catalog = [];
      this._items.set([]);
      this._movieCount.set(0);
      this._seriesCount.set(0);
      this._status.set('error');
      this._error.set('Library is temporarily unavailable. Try again.');
    }
  }

  private syncItems(): void {
    const kind = this._kind();
    this._items.set(this.catalog.filter((item) => item.kind === kind));
  }

  private settleStatus(): void {
    this._status.set(this._items().length ? 'ready' : 'empty');
  }
}
