import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import { DownloadTorrent, summarizeDownloads } from './downloads.models';

export type DownloadsStatus = 'loading' | 'ready' | 'empty' | 'error';
export type DownloadsAction = 'pause' | 'resume';

const REFRESH_ERROR = 'Could not refresh downloads. Showing last loaded queue.';
const LOAD_ERROR = 'Downloads are temporarily unavailable. Try again.';
/** Bound scheduled polls so a hung `/qbt/torrents` request cannot lock out later ticks. */
export const SCHEDULED_REFRESH_TIMEOUT_MS = 15_000;

@Injectable()
export class DownloadsFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly destroyRef = inject(DestroyRef);
  private readonly _status = signal<DownloadsStatus>('loading');
  private readonly _torrents = signal<DownloadTorrent[]>([]);
  private readonly _error = signal('');
  private readonly _notice = signal('');
  private readonly _pendingAction = signal<DownloadsAction | null>(null);
  private readonly _pendingTorrentId = signal<string | null>(null);
  private readonly _refreshing = signal(false);
  private requestId = 0;
  private scheduledInFlight = false;
  private pollHandle?: ReturnType<typeof setInterval>;
  private refreshAbort?: AbortController;
  private refreshTimeoutId?: ReturnType<typeof setTimeout>;

  readonly status = this._status.asReadonly();
  readonly torrents = this._torrents.asReadonly();
  readonly error = this._error.asReadonly();
  readonly notice = this._notice.asReadonly();
  readonly pendingAction = this._pendingAction.asReadonly();
  readonly pendingTorrentId = this._pendingTorrentId.asReadonly();
  readonly refreshing = this._refreshing.asReadonly();
  readonly summary = computed(() => summarizeDownloads(this._torrents()));
  readonly canPauseAll = computed(() => this._torrents().some((torrent) => torrent.state === 'downloading'));
  readonly canResumeAll = computed(() => this._torrents().some((torrent) => torrent.state === 'paused'));
  readonly nextAction = computed<DownloadsAction | null>(() => {
    if (this.canPauseAll()) return 'pause';
    if (this.canResumeAll()) return 'resume';
    return null;
  });

  constructor() {
    this.destroyRef.onDestroy(() => this.stopPolling());
  }

  startPolling(intervalMs = 10_000): void {
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
      const torrents = await this.api.listTorrents(options.signal);
      if (requestId !== this.requestId) return;
      this._torrents.set(torrents);
      this._status.set(torrents.length ? 'ready' : 'empty');
      this._error.set('');
    } catch {
      if (requestId !== this.requestId) return;
      // Cancelled refreshes must not mutate facade state; callers apply timeout/teardown policy.
      if (options.signal?.aborted) return;
      this.applyRefreshFailure(initial);
    } finally {
      if (requestId === this.requestId) this._refreshing.set(false);
    }
  }

  async runAction(action: DownloadsAction): Promise<void> {
    if (this._pendingAction()) return;
    this._pendingAction.set(action);
    this._notice.set('');
    try {
      await (action === 'pause' ? this.api.pauseAll() : this.api.resumeAll());
      await this.refresh();
      if (!this._error()) {
        this._notice.set(action === 'pause' ? 'All downloads paused.' : 'All downloads resumed.');
      }
    } catch {
      this._notice.set(`Could not ${action} downloads. Try again.`);
    } finally {
      this._pendingAction.set(null);
    }
  }

  async runTorrentAction(id: string, action: DownloadsAction): Promise<void> {
    if (this._pendingTorrentId()) return;
    this._pendingTorrentId.set(id);
    this._notice.set('');
    try {
      await (action === 'pause' ? this.api.pauseTorrent(id) : this.api.resumeTorrent(id));
      await this.refresh();
    } catch {
      this._notice.set(`Could not ${action} torrent. Try again.`);
    } finally {
      this._pendingTorrentId.set(null);
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
      // Timeout abort while polling is still armed: surface retained/hard failure and free the slot.
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
      this._torrents.set([]);
    }
  }

  private stopPolling(): void {
    if (this.pollHandle) clearInterval(this.pollHandle);
    this.pollHandle = undefined;
    if (this.refreshTimeoutId !== undefined) {
      clearTimeout(this.refreshTimeoutId);
      this.refreshTimeoutId = undefined;
    }
    // Invalidate before abort so a racing settle cannot write after teardown.
    this.requestId++;
    this.refreshAbort?.abort();
    this.refreshAbort = undefined;
    this.scheduledInFlight = false;
    this._refreshing.set(false);
  }
}
