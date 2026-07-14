import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import { DownloadTorrent, summarizeDownloads } from './downloads.models';

export type DownloadsStatus = 'loading' | 'ready' | 'empty' | 'error';
export type DownloadsAction = 'pause' | 'resume';

@Injectable()
export class DownloadsFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly destroyRef = inject(DestroyRef);
  private readonly _status = signal<DownloadsStatus>('loading');
  private readonly _torrents = signal<DownloadTorrent[]>([]);
  private readonly _error = signal('');
  private readonly _notice = signal('');
  private readonly _pendingAction = signal<DownloadsAction | null>(null);
  readonly status = this._status.asReadonly();
  readonly torrents = this._torrents.asReadonly();
  readonly error = this._error.asReadonly();
  readonly notice = this._notice.asReadonly();
  readonly pendingAction = this._pendingAction.asReadonly();
  readonly summary = computed(() => summarizeDownloads(this._torrents()));
  private pollHandle?: ReturnType<typeof setInterval>;

  constructor() {
    this.destroyRef.onDestroy(() => this.stopPolling());
  }

  startPolling(intervalMs = 10_000): void {
    if (this.pollHandle) return;
    void this.refresh();
    this.pollHandle = setInterval(() => void this.refresh(), intervalMs);
  }

  async refresh(): Promise<void> {
    try {
      const torrents = await this.api.listTorrents();
      this._torrents.set(torrents);
      this._status.set(torrents.length ? 'ready' : 'empty');
      this._error.set('');
    } catch {
      this._status.set('error');
      this._error.set('Downloads are temporarily unavailable. Try again.');
      this._notice.set('');
    }
  }

  async runAction(action: DownloadsAction): Promise<void> {
    if (this._pendingAction()) return;
    this._pendingAction.set(action);
    this._notice.set('');
    try {
      await (action === 'pause' ? this.api.pauseAll() : this.api.resumeAll());
      await this.refresh();
      this._notice.set(action === 'pause' ? 'All downloads paused.' : 'All downloads resumed.');
    } catch {
      this._status.set('error');
      this._error.set(`Could not ${action} downloads. Try again.`);
      this._notice.set('');
    } finally {
      this._pendingAction.set(null);
    }
  }

  private stopPolling(): void {
    if (this.pollHandle) clearInterval(this.pollHandle);
    this.pollHandle = undefined;
  }
}
