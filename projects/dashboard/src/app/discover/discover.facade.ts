import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import {
  DiscoverFeedback,
  DiscoverSourceTab,
  JellyseerrDiscoverKind,
  MEDIA_STACK_API,
  MediaStackDiscoverItemDto,
  MediaStackExternalDiscoverItemDto,
  TraktDiscoverType,
} from '../downloads/media-stack-api';
import {
  DiscoverCardItem,
  DiscoverHistoryFilter,
  matchesHistoryFilter,
  mediaIdentityKey,
  resolveRequestAction,
  toExternalCardItem,
  toHermesCardItem,
} from './discover-format';

export type DiscoverStatus = 'loading' | 'ready' | 'empty' | 'error';
export type HermesView = 'active' | 'history';

const HERMES_POLL_MS = 30_000;
const EXTERNAL_POLL_MS = 60_000;

@Injectable()
export class DiscoverFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly destroyRef = inject(DestroyRef);

  private readonly _tab = signal<DiscoverSourceTab>('hermes');
  private readonly _hermesView = signal<HermesView>('active');
  private readonly _historyFilter = signal<DiscoverHistoryFilter>('all');
  private readonly _jellyseerrKind = signal<JellyseerrDiscoverKind>('trending');
  private readonly _traktType = signal<TraktDiscoverType>('movies');

  private readonly _status = signal<DiscoverStatus>('loading');
  private readonly _error = signal('');
  private readonly _notice = signal('');
  private readonly _noticeTone = signal<'success' | 'warning' | 'danger' | 'info'>('info');

  private readonly _hermesItems = signal<MediaStackDiscoverItemDto[]>([]);
  private readonly _generationPending = signal(false);
  private readonly _jellyseerrCache = signal<Partial<Record<JellyseerrDiscoverKind, MediaStackExternalDiscoverItemDto[]>>>({});
  private readonly _traktCache = signal<Partial<Record<TraktDiscoverType, MediaStackExternalDiscoverItemDto[]>>>({});

  private readonly _busyItemId = signal<string | null>(null);
  private readonly _requestingMore = signal(false);
  private readonly _requestSyncFailedIds = signal<ReadonlySet<string>>(new Set());
  private readonly _requestedKeys = signal<ReadonlySet<string>>(new Set());

  readonly tab = this._tab.asReadonly();
  readonly hermesView = this._hermesView.asReadonly();
  readonly historyFilter = this._historyFilter.asReadonly();
  readonly jellyseerrKind = this._jellyseerrKind.asReadonly();
  readonly traktType = this._traktType.asReadonly();
  readonly status = this._status.asReadonly();
  readonly error = this._error.asReadonly();
  readonly notice = this._notice.asReadonly();
  readonly noticeTone = this._noticeTone.asReadonly();
  readonly busyItemId = this._busyItemId.asReadonly();
  readonly requestingMore = this._requestingMore.asReadonly();
  readonly generationPending = this._generationPending.asReadonly();
  readonly requestSyncFailedIds = this._requestSyncFailedIds.asReadonly();

  readonly visibleItems = computed<DiscoverCardItem[]>(() => {
    const tab = this._tab();
    const requestedKeys = this._requestedKeys();
    if (tab === 'hermes') {
      const view = this._hermesView();
      const filter = this._historyFilter();
      return this._hermesItems()
        .filter((item) => (view === 'active' ? item.active : !item.active))
        .filter((item) => (view === 'history' ? matchesHistoryFilter(item, filter) : true))
        .map((item) => {
          const card = toHermesCardItem(item);
          if (card.requestState === 'requested') return card;
          if (requestedKeys.has(mediaIdentityKey(card.type, card.tmdbId))) {
            return { ...card, requestState: 'requested' as const };
          }
          return card;
        });
    }
    if (tab === 'jellyseerr') {
      const kind = this._jellyseerrKind();
      return (this._jellyseerrCache()[kind] ?? []).map((item) => toExternalCardItem(item, 'jellyseerr', requestedKeys));
    }
    const type = this._traktType();
    return (this._traktCache()[type] ?? []).map((item) => toExternalCardItem(item, 'trakt', requestedKeys));
  });

  private pollHandle?: ReturnType<typeof setInterval>;

  constructor() {
    this.destroyRef.onDestroy(() => this.stopPolling());
  }

  startPolling(): void {
    this.restartPolling();
  }

  setTab(tab: DiscoverSourceTab): void {
    if (this._tab() === tab) return;
    this._tab.set(tab);
    this._notice.set('');
    this.restartPolling();
  }

  setHermesView(view: HermesView): void {
    this._hermesView.set(view);
    this.syncVisibleStatus();
  }

  setHistoryFilter(filter: DiscoverHistoryFilter): void {
    this._historyFilter.set(filter);
    this.syncVisibleStatus();
  }

  setJellyseerrKind(kind: JellyseerrDiscoverKind): void {
    if (this._jellyseerrKind() === kind) return;
    this._jellyseerrKind.set(kind);
    void this.refreshActive();
  }

  setTraktType(type: TraktDiscoverType): void {
    if (this._traktType() === type) return;
    this._traktType.set(type);
    void this.refreshActive();
  }

  async refresh(): Promise<void> {
    await this.refreshActive();
  }

  async submitFeedback(id: string, feedback: DiscoverFeedback): Promise<void> {
    if (this._busyItemId()) return;
    this._busyItemId.set(id);
    this._notice.set('');
    try {
      const result = await this.api.submitHermesFeedback(id, feedback);
      if (!result.ok) {
        this._noticeTone.set('danger');
        this._notice.set(result.error ?? 'Could not save feedback.');
        return;
      }
      this._noticeTone.set('success');
      this._notice.set(result.message ?? 'Feedback saved.');
      await this.loadHermes();
    } catch {
      this._noticeTone.set('danger');
      this._notice.set('Could not save feedback. Try again.');
    } finally {
      this._busyItemId.set(null);
    }
  }

  async requestItem(item: DiscoverCardItem): Promise<void> {
    if (this._busyItemId()) return;
    const action = resolveRequestAction(item, { syncFailed: this.isSyncFailed(item.id) });
    if (action.disabled) return;
    this._busyItemId.set(item.id);
    this._notice.set('');
    try {
      const result = await this.api.requestMedia({
        mediaType: item.type,
        mediaId: item.tmdbId,
        hermesId: item.hermesId,
      });
      if (!result.ok) {
        this._noticeTone.set('danger');
        this._notice.set(result.error ?? 'Could not request media.');
        return;
      }
      if (result.dashboard_state_persisted === false) {
        this.addSyncFailed(item.id);
        this._noticeTone.set('warning');
        this._notice.set(result.message ?? 'Added to Sonarr/Radarr; dashboard synchronization failed.');
      } else {
        this.markRequested(item.type, item.tmdbId);
        this._noticeTone.set('success');
        this._notice.set(result.message ?? 'Requested.');
      }
      if (this._tab() === 'hermes') {
        await this.loadHermes();
      }
    } catch {
      this._noticeTone.set('danger');
      this._notice.set('Could not request media. Try again.');
    } finally {
      this._busyItemId.set(null);
    }
  }

  async requestMore(): Promise<void> {
    if (this._requestingMore() || this._generationPending()) return;
    this._requestingMore.set(true);
    this._notice.set('');
    try {
      const result = await this.api.requestHermesMore();
      if (!result.ok) {
        this._noticeTone.set('danger');
        this._notice.set(result.error ?? 'Could not queue more recommendations.');
        return;
      }
      if (result.already_pending) {
        this._generationPending.set(true);
        this._noticeTone.set('info');
        this._notice.set(result.message ?? 'A recommendation refresh is already pending.');
      } else {
        this._generationPending.set(true);
        this._noticeTone.set('success');
        this._notice.set(result.message ?? 'More recommendations queued.');
      }
      await this.loadHermes();
    } catch {
      this._noticeTone.set('danger');
      this._notice.set('Could not queue more recommendations. Try again.');
    } finally {
      this._requestingMore.set(false);
    }
  }

  isSyncFailed(id: string): boolean {
    return this._requestSyncFailedIds().has(id);
  }

  private restartPolling(): void {
    this.stopPolling();
    void this.refreshActive();
    const interval = this._tab() === 'hermes' ? HERMES_POLL_MS : EXTERNAL_POLL_MS;
    this.pollHandle = setInterval(() => void this.refreshActive(), interval);
  }

  private stopPolling(): void {
    if (this.pollHandle) clearInterval(this.pollHandle);
    this.pollHandle = undefined;
  }

  private async refreshActive(): Promise<void> {
    const tab = this._tab();
    if (tab === 'hermes') {
      await this.loadHermes();
      return;
    }
    if (tab === 'jellyseerr') {
      await this.loadJellyseerr(this._jellyseerrKind());
      return;
    }
    await this.loadTrakt(this._traktType());
  }

  private async loadHermes(): Promise<void> {
    const hadData = this._hermesItems().length > 0;
    if (!hadData) this._status.set('loading');
    try {
      const response = await this.api.listHermesRecommendations();
      if (!response.ok) {
        this._status.set('error');
        this._error.set(response.error ?? 'Discover is temporarily unavailable. Try again.');
        return;
      }
      this._hermesItems.set(response.items);
      this._generationPending.set(Boolean(response.generation_request));
      this.reconcileSyncFailed(response.items);
      if (this._tab() !== 'hermes') return;
      const visible = this.visibleItems();
      this._status.set(visible.length ? 'ready' : 'empty');
      this._error.set('');
    } catch {
      if (this._tab() !== 'hermes') return;
      this._status.set('error');
      this._error.set('Discover is temporarily unavailable. Try again.');
      this._notice.set('');
    }
  }

  private async loadJellyseerr(kind: JellyseerrDiscoverKind): Promise<void> {
    const cached = this._jellyseerrCache()[kind];
    if (!cached) this._status.set('loading');
    try {
      const response = await this.api.listJellyseerrDiscover(kind);
      if (!response.ok) {
        if (this._tab() === 'jellyseerr' && this._jellyseerrKind() === kind) {
          this._status.set('error');
          this._error.set(response.error ?? 'Discover is temporarily unavailable. Try again.');
        }
        return;
      }
      this._jellyseerrCache.update((cache) => ({ ...cache, [kind]: response.items }));
      if (this._tab() !== 'jellyseerr' || this._jellyseerrKind() !== kind) return;
      this._status.set(response.items.length ? 'ready' : 'empty');
      this._error.set('');
    } catch {
      if (this._tab() !== 'jellyseerr' || this._jellyseerrKind() !== kind) return;
      this._status.set('error');
      this._error.set('Discover is temporarily unavailable. Try again.');
      this._notice.set('');
    }
  }

  private async loadTrakt(type: TraktDiscoverType): Promise<void> {
    const cached = this._traktCache()[type];
    if (!cached) this._status.set('loading');
    try {
      const response = await this.api.listTraktDiscover(type);
      if (!response.ok) {
        if (this._tab() === 'trakt' && this._traktType() === type) {
          this._status.set('error');
          this._error.set(response.error ?? 'Discover is temporarily unavailable. Try again.');
        }
        return;
      }
      this._traktCache.update((cache) => ({ ...cache, [type]: response.items }));
      if (this._tab() !== 'trakt' || this._traktType() !== type) return;
      this._status.set(response.items.length ? 'ready' : 'empty');
      this._error.set('');
    } catch {
      if (this._tab() !== 'trakt' || this._traktType() !== type) return;
      this._status.set('error');
      this._error.set('Discover is temporarily unavailable. Try again.');
      this._notice.set('');
    }
  }

  private syncVisibleStatus(): void {
    if (this._status() === 'loading' || this._status() === 'error') return;
    this._status.set(this.visibleItems().length ? 'ready' : 'empty');
  }

  private markRequested(type: DiscoverCardItem['type'], tmdbId: number): void {
    this._requestedKeys.update((keys) => {
      const next = new Set(keys);
      next.add(mediaIdentityKey(type, tmdbId));
      return next;
    });
  }

  private addSyncFailed(id: string): void {
    this._requestSyncFailedIds.update((ids) => {
      const next = new Set(ids);
      next.add(id);
      return next;
    });
  }

  private reconcileSyncFailed(items: MediaStackDiscoverItemDto[]): void {
    if (!this._requestSyncFailedIds().size) return;
    this._requestSyncFailedIds.update((ids) => {
      const next = new Set(ids);
      for (const id of ids) {
        const item = items.find((candidate) => candidate.id === id);
        if (item?.request_state === 'requested') next.delete(id);
      }
      return next;
    });
  }
}
