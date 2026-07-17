import { DestroyRef, inject, Injectable, signal } from '@angular/core';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import { LibraryStats } from './library.models';

export type LibraryStatsStatus = 'loading' | 'ready' | 'error';

@Injectable()
export class LibraryStatsFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly destroyRef = inject(DestroyRef);
  private readonly _status = signal<LibraryStatsStatus>('loading');
  private readonly _stats = signal<LibraryStats | null>(null);
  private readonly _error = signal('');
  readonly status = this._status.asReadonly();
  readonly stats = this._stats.asReadonly();
  readonly error = this._error.asReadonly();

  constructor() {
    void this.refresh();
  }

  async refresh(): Promise<void> {
    this._status.set('loading');
    try {
      const stats = await this.api.getLibraryStats();
      this._stats.set(stats);
      this._error.set('');
      this._status.set('ready');
    } catch {
      this._stats.set(null);
      this._status.set('error');
      this._error.set('Library stats are temporarily unavailable. Try again.');
    }
  }
}
