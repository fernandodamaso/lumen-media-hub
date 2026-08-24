import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import {
  applyPolledRefreshFailure,
  isInitialRefresh,
  runPolledRefresh,
} from '../media-stack/polled-refresh';
import { ScheduledPollController } from '../media-stack/scheduled-poll';
import { DownloadTorrent, summarizeDownloads } from './downloads.models';
import { DownloadsVisibilityStore, isTorrentVisible } from './downloads-visibility';

export type DownloadsStatus = 'loading' | 'ready' | 'empty' | 'error';
export type DownloadsAction = 'pause' | 'resume';

const REFRESH_ERROR = 'Could not refresh downloads. Showing last loaded queue.';
const LOAD_ERROR = 'Downloads are temporarily unavailable. Try again.';
/** Re-export for existing specs; canonical home is `media-stack/scheduled-poll`. */
export { SCHEDULED_REFRESH_TIMEOUT_MS } from '../media-stack/scheduled-poll';

@Injectable()
export class DownloadsFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly destroyRef = inject(DestroyRef);
  private readonly poll = new ScheduledPollController();
  private readonly _status = signal<DownloadsStatus>('loading');
  private readonly _torrents = signal<DownloadTorrent[]>([]);
  private readonly _error = signal('');
  private readonly _notice = signal('');
  private readonly _pendingAction = signal<DownloadsAction | null>(null);
  private readonly _pendingTorrentId = signal<string | null>(null);
  private readonly _refreshing = signal(false);
  private readonly _lastFetchedAt = signal('');
  private readonly visibilityStore = new DownloadsVisibilityStore();
  private readonly _dismissedCompletedIds = signal<Set<string>>(this.visibilityStore.load());
  private readonly _nowMs = signal(Date.now());

  readonly status = this._status.asReadonly();
  readonly torrents = this._torrents.asReadonly();
  readonly error = this._error.asReadonly();
  readonly notice = this._notice.asReadonly();
  readonly pendingAction = this._pendingAction.asReadonly();
  readonly pendingTorrentId = this._pendingTorrentId.asReadonly();
  readonly refreshing = this._refreshing.asReadonly();
  readonly lastFetchedAt = this._lastFetchedAt.asReadonly();
  readonly summary = computed(() => summarizeDownloads(this._torrents()));
  readonly visibleTorrents = computed(() =>
    this._torrents().filter((torrent) => isTorrentVisible(torrent, this._nowMs(), this._dismissedCompletedIds())),
  );
  readonly hasVisibleTorrents = computed(() => this.visibleTorrents().length > 0);
  readonly visibleCompletedCount = computed(() => this.visibleTorrents().filter((torrent) => torrent.completed).length);
  readonly canPauseAll = computed(() => this._torrents().some((torrent) => torrent.state === 'downloading'));
  readonly canResumeAll = computed(() => this._torrents().some((torrent) => torrent.state === 'paused'));
  readonly nextAction = computed<DownloadsAction | null>(() => {
    if (this.canPauseAll()) return 'pause';
    if (this.canResumeAll()) return 'resume';
    return null;
  });

  constructor() {
    this.destroyRef.onDestroy(() => {
      this.poll.stop();
      this._refreshing.set(false);
    });
  }

  startPolling(intervalMs = 10_000): void {
    this.poll.startRefreshing(
      intervalMs,
      (options) => this.refresh(options),
      (initial) => {
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
        const torrents = await this.api.listTorrents(options.signal);
        if (!this.poll.isCurrent(requestId)) return;
        this._torrents.set(torrents);
        this._nowMs.set(Date.now());
        this.pruneDismissedIds(torrents);
        this._lastFetchedAt.set(new Date().toISOString());
        this._status.set(torrents.length ? 'ready' : 'empty');
        this._error.set('');
      },
      onFailure: () => {
        this.applyRefreshFailure(initial);
      },
    });
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

  clearCompletedFromView(): void {
    const next = new Set(this._dismissedCompletedIds());
    for (const torrent of this.visibleTorrents()) {
      if (torrent.completed) next.add(torrent.id);
    }
    this._dismissedCompletedIds.set(next);
    this.visibilityStore.save(next);
    this._notice.set('Completed items hidden from this dashboard. Torrents and files were not removed.');
  }

  private pruneDismissedIds(torrents: DownloadTorrent[]): void {
    const currentIds = new Set(torrents.map((torrent) => torrent.id));
    const current = this._dismissedCompletedIds();
    const next = new Set([...current].filter((id) => currentIds.has(id)));
    if (next.size === current.size) return;
    this._dismissedCompletedIds.set(next);
    this.visibilityStore.save(next);
  }

  private applyRefreshFailure(initial: boolean): void {
    applyPolledRefreshFailure({
      initial,
      status: this._status,
      error: this._error,
      refreshError: REFRESH_ERROR,
      loadError: LOAD_ERROR,
      clearPayload: () => {
        this._torrents.set([]);
      },
    });
  }
}
