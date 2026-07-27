import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import {
  DiscoverCardItem,
  DiscoverHistoryFilter,
  isHermesActiveItem,
  matchesHistoryFilter,
  mediaIdentityKey,
  resolveRequestAction,
  toExternalCardItem,
  toHermesCardItem,
} from './discover-format';
import {
  DiscoverFeedback,
  DiscoverItem,
  DiscoverSourceTab,
  ExternalDiscoverItem,
  HermesDiscover,
  JellyseerrDiscoverKind,
  TraktDiscoverType,
} from './discover.models';

export type DiscoverStatus = 'loading' | 'ready' | 'empty' | 'error';
export type HermesView = 'active' | 'history';

const HERMES_POLL_MS = 30_000;
const EXTERNAL_POLL_MS = 60_000;
const LOAD_ERROR = 'Discover is temporarily unavailable. Try again.';
const REFRESH_NOTICE = 'Could not refresh. Showing last loaded results.';
const STALE_HINT = ' Results may be stale.';

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

  private readonly _hermesItems = signal<DiscoverItem[]>([]);
  private readonly _generationPending = signal(false);
  private readonly _jellyseerrCache = signal<Partial<Record<JellyseerrDiscoverKind, ExternalDiscoverItem[]>>>({});
  private readonly _traktCache = signal<Partial<Record<TraktDiscoverType, ExternalDiscoverItem[]>>>({});

  private readonly _busyItemId = signal<string | null>(null);
  private readonly _requestingMore = signal(false);
  private readonly _requestSyncFailedIds = signal<ReadonlySet<string>>(new Set());
  private readonly _requestSyncFailedKeys = signal<ReadonlySet<string>>(new Set());
  private readonly _requestedKeys = signal<ReadonlySet<string>>(new Set());

  /** True after a local request-more until the API has reported generation_request at least once. */
  private generationObserved = false;

  private hermesRequestId = 0;
  private jellyseerrRequestId = 0;
  private traktRequestId = 0;
  /** Highest generation whose success payload was committed (Hermes). */
  private hermesAppliedId = 0;
  private jellyseerrAppliedId = 0;
  private traktAppliedId = 0;
  /** True after at least one successful Hermes payload (including empty). */
  private hermesLoaded = false;
  private scheduledInFlight = false;
  private scheduledRefreshGen = 0;
  private pollHandle?: ReturnType<typeof setInterval>;

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
        .filter((item) => (view === 'active' ? isHermesActiveItem(item) : !isHermesActiveItem(item)))
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

  constructor() {
    this.destroyRef.onDestroy(() => { this.stopPolling(); });
  }

  async setTab(tab: DiscoverSourceTab): Promise<void> {
    const changed = this._tab() !== tab;
    if (changed) {
      this._tab.set(tab);
      this._notice.set('');
    }
    await this.refreshCurrentTab();
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
    void this.refreshCurrentTab();
  }

  setTraktType(type: TraktDiscoverType): void {
    if (this._traktType() === type) return;
    this._traktType.set(type);
    void this.refreshCurrentTab();
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
      // Archive immediately so liked/watched leave Active even before reload settles.
      this._hermesItems.update((items) =>
        items.map((item) =>
          item.id === id
            ? {
                ...item,
                active: false,
                feedback,
                feedback_at: new Date().toISOString(),
              }
            : item,
        ),
      );
      this.syncVisibleStatus();
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
    const action = resolveRequestAction(item, { syncFailed: this.isSyncFailed(item) });
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
        this.addSyncFailed(item);
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
      this._generationPending.set(true);
      this.generationObserved = false;
      if (result.already_pending) {
        this._noticeTone.set('info');
        this._notice.set(result.message ?? 'A recommendation refresh is already pending.');
      } else {
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

  isSyncFailed(itemOrId: DiscoverCardItem | string): boolean {
    if (typeof itemOrId === 'string') {
      return this._requestSyncFailedIds().has(itemOrId);
    }
    return (
      this._requestSyncFailedIds().has(itemOrId.id) ||
      this._requestSyncFailedKeys().has(mediaIdentityKey(itemOrId.type, itemOrId.tmdbId))
    );
  }

  private async refreshCurrentTab(): Promise<void> {
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

  private restartPolling(): void {
    // Clear the interval timer only — leave scheduledInFlight alone so an
    // outstanding scheduled refresh keeps owning the overlap guard.
    this.stopPolling(false);
    const interval = this._tab() === 'hermes' ? HERMES_POLL_MS : EXTERNAL_POLL_MS;
    this.pollHandle = setInterval(() => void this.runScheduledRefresh(), interval);
  }

  private async runScheduledRefresh(): Promise<void> {
    if (this.scheduledInFlight) return;
    this.scheduledInFlight = true;
    const ownedGen = ++this.scheduledRefreshGen;
    try {
      await this.refreshCurrentTab();
    } finally {
      if (ownedGen === this.scheduledRefreshGen) {
        this.scheduledInFlight = false;
      }
    }
  }

  private stopPolling(invalidateInFlight = true): void {
    if (this.pollHandle) clearInterval(this.pollHandle);
    this.pollHandle = undefined;
    if (invalidateInFlight) {
      // Destroy / hard stop: drop the interval and orphan any in-flight finally
      // so it cannot clear a later scheduled refresh's guard.
      this.scheduledRefreshGen++;
      this.scheduledInFlight = false;
      this.hermesRequestId++;
      this.jellyseerrRequestId++;
      this.traktRequestId++;
    }
  }

  private async loadHermes(): Promise<void> {
    const requestId = ++this.hermesRequestId;
    const isInitial = !this.hermesLoaded;
    if (isInitial && this._tab() === 'hermes') {
      this._status.set('loading');
    }
    try {
      const response = await this.api.listHermesRecommendations();
      if (!response.ok) {
        // Failures only apply when still current — a stale failure must not clobber newer work.
        if (!this.isCurrentHermesRequest(requestId)) return;
        this.applyBrowseFailure(isInitial, response.error ?? LOAD_ERROR);
        return;
      }
      // Valid success may still commit when superseded, as long as it is not older than an
      // already-applied generation (so a late good payload can recover an exclusive error).
      if (requestId < this.hermesAppliedId) return;
      this.applyHermesPayload(response);
      this.hermesAppliedId = requestId;
      this.hermesLoaded = true;
      if (this._tab() !== 'hermes') return;
      this.commitBrowseSuccessCount(this.visibleItems().length, requestId, this.hermesRequestId);
    } catch {
      if (!this.isCurrentHermesRequest(requestId)) return;
      this.applyBrowseFailure(isInitial, LOAD_ERROR);
    }
  }

  private isCurrentHermesRequest(requestId: number): boolean {
    return requestId === this.hermesRequestId && this._tab() === 'hermes';
  }

  private async loadJellyseerr(kind: JellyseerrDiscoverKind): Promise<void> {
    await this.loadExternalBrowse({
      nextRequestId: () => ++this.jellyseerrRequestId,
      currentRequestId: () => this.jellyseerrRequestId,
      appliedId: () => this.jellyseerrAppliedId,
      setAppliedId: (id) => {
        this.jellyseerrAppliedId = id;
      },
      isActive: () => this._tab() === 'jellyseerr' && this._jellyseerrKind() === kind,
      cached: () => this._jellyseerrCache()[kind],
      writeCache: (items) => {
        this._jellyseerrCache.update((cache) => ({ ...cache, [kind]: items }));
      },
      fetch: () => this.api.listJellyseerrDiscover(kind),
    });
  }

  private async loadTrakt(type: TraktDiscoverType): Promise<void> {
    await this.loadExternalBrowse({
      nextRequestId: () => ++this.traktRequestId,
      currentRequestId: () => this.traktRequestId,
      appliedId: () => this.traktAppliedId,
      setAppliedId: (id) => {
        this.traktAppliedId = id;
      },
      isActive: () => this._tab() === 'trakt' && this._traktType() === type,
      cached: () => this._traktCache()[type],
      writeCache: (items) => {
        this._traktCache.update((cache) => ({ ...cache, [type]: items }));
      },
      fetch: () => this.api.listTraktDiscover(type),
    });
  }

  /** Shared Jellyseerr/Trakt browse load: cache prime, generation guard, soft failure. */
  private async loadExternalBrowse(opts: {
    nextRequestId: () => number;
    currentRequestId: () => number;
    appliedId: () => number;
    setAppliedId: (id: number) => void;
    isActive: () => boolean;
    cached: () => ExternalDiscoverItem[] | undefined;
    writeCache: (items: ExternalDiscoverItem[]) => void;
    fetch: () => Promise<{ ok: boolean; items: ExternalDiscoverItem[]; error?: string }>;
  }): Promise<void> {
    const requestId = opts.nextRequestId();
    const isActive = opts.isActive();
    const isInitial = this.primeBrowseCache(isActive, opts.cached());
    try {
      const response = await opts.fetch();
      if (!response.ok) {
        if (requestId !== opts.currentRequestId()) return;
        if (opts.isActive()) this.applyBrowseFailure(isInitial, response.error ?? LOAD_ERROR);
        return;
      }
      if (requestId < opts.appliedId()) return;
      opts.writeCache(response.items);
      opts.setAppliedId(requestId);
      if (!opts.isActive()) return;
      this.commitBrowseSuccess(response.items, requestId, opts.currentRequestId());
    } catch {
      if (requestId !== opts.currentRequestId() || !opts.isActive()) return;
      this.applyBrowseFailure(isInitial, LOAD_ERROR);
    }
  }

  /** Surface cached items immediately, or mark loading when the active browse has no cache. */
  private primeBrowseCache(isActive: boolean, cached: ExternalDiscoverItem[] | undefined): boolean {
    if (!isActive) return !cached;
    if (cached) {
      this._status.set(cached.length ? 'ready' : 'empty');
      this._error.set('');
    } else {
      this._status.set('loading');
    }
    return !cached;
  }

  private commitBrowseSuccess(
    items: ExternalDiscoverItem[],
    requestId: number,
    currentRequestId: number,
  ): void {
    this.commitBrowseSuccessCount(items.length, requestId, currentRequestId);
  }

  private commitBrowseSuccessCount(
    itemCount: number,
    requestId: number,
    currentRequestId: number,
  ): void {
    const isCurrent = requestId === currentRequestId;
    if (!isCurrent && this._status() !== 'error') return;
    this._status.set(itemCount ? 'ready' : 'empty');
    this._error.set('');
    if (this._notice() === REFRESH_NOTICE) this._notice.set('');
  }

  /**
   * Background failures keep last-good browse state and surface a non-destructive notice.
   * Initial failures (no last-good) flip to exclusive error.
   * Mutation notices stay visible; a refresh failure appends a stale hint rather than replacing them.
   */
  private applyBrowseFailure(isInitial: boolean, message: string): void {
    if (!isInitial) {
      const notice = this._notice();
      if (!notice || notice === REFRESH_NOTICE) {
        this._noticeTone.set('warning');
        this._notice.set(REFRESH_NOTICE);
      } else if (!notice.includes(STALE_HINT)) {
        this._notice.set(`${notice}${STALE_HINT}`);
      }
      return;
    }
    this._status.set('error');
    this._error.set(message);
    this._notice.set('');
  }

  private applyHermesPayload(response: HermesDiscover): void {
    this._hermesItems.set(response.items);
    this.seedRequestedFromHermes(response.items);
    this.applyPendingRequestSync(response.items, response.pending_request_sync);
    this.reconcileSyncFailed(response.items);
    this.applyGenerationPending(Boolean(response.generation_request));
  }

  private applyGenerationPending(apiPending: boolean): void {
    if (apiPending) {
      this._generationPending.set(true);
      this.generationObserved = true;
      return;
    }
    if (!this._generationPending() || this.generationObserved) {
      this._generationPending.set(false);
      this.generationObserved = false;
    }
  }

  private syncVisibleStatus(): void {
    if (this._status() === 'loading' || this._status() === 'error') return;
    this._status.set(this.visibleItems().length ? 'ready' : 'empty');
  }

  private seedRequestedFromHermes(items: DiscoverItem[]): void {
    const keys = items
      .filter((item) => item.request_state === 'requested' && item.tmdb_id)
      .map((item) => mediaIdentityKey(item.type, item.tmdb_id));
    if (!keys.length) return;
    this._requestedKeys.update((existing) => {
      const next = new Set(existing);
      for (const key of keys) next.add(key);
      return next;
    });
  }

  private applyPendingRequestSync(
    items: DiscoverItem[],
    pending?: { id: string; jellyseerr_request_id: number }[],
  ): void {
    if (!pending?.length) return;
    this._requestSyncFailedIds.update((ids) => {
      const next = new Set(ids);
      for (const entry of pending) next.add(entry.id);
      return next;
    });
    this._requestSyncFailedKeys.update((keys) => {
      const next = new Set(keys);
      for (const entry of pending) {
        const item = items.find((candidate) => candidate.id === entry.id);
        if (item?.tmdb_id) next.add(mediaIdentityKey(item.type, item.tmdb_id));
      }
      return next;
    });
  }

  private markRequested(type: DiscoverCardItem['type'], tmdbId: number): void {
    this._requestedKeys.update((keys) => {
      const next = new Set(keys);
      next.add(mediaIdentityKey(type, tmdbId));
      return next;
    });
  }

  private addSyncFailed(item: DiscoverCardItem): void {
    this._requestSyncFailedIds.update((ids) => {
      const next = new Set(ids);
      next.add(item.id);
      return next;
    });
    if (item.tmdbId) {
      this._requestSyncFailedKeys.update((keys) => {
        const next = new Set(keys);
        next.add(mediaIdentityKey(item.type, item.tmdbId));
        return next;
      });
    }
  }

  private reconcileSyncFailed(items: DiscoverItem[]): void {
    if (!this._requestSyncFailedIds().size && !this._requestSyncFailedKeys().size) return;
    this._requestSyncFailedIds.update((ids) => {
      const next = new Set(ids);
      for (const id of ids) {
        const item = items.find((candidate) => candidate.id === id);
        if (item?.request_state === 'requested') next.delete(id);
      }
      return next;
    });
    this._requestSyncFailedKeys.update((keys) => {
      const next = new Set(keys);
      for (const key of keys) {
        const item = items.find((candidate) => mediaIdentityKey(candidate.type, candidate.tmdb_id) === key);
        if (item?.request_state === 'requested') next.delete(key);
      }
      return next;
    });
  }
}
