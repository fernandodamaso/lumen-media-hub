import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import { ScheduledPollController } from '../media-stack/scheduled-poll';
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
  ExternalDiscoverAvailability,
  ExternalDiscoverItem,
  HermesDiscover,
  JellyseerrDiscoverKind,
  LibraryExclusionState,
  TraktDiscoverType,
  WatchedExclusionState,
} from './discover.models';

export type DiscoverStatus = 'loading' | 'ready' | 'empty' | 'disabled' | 'error';
export type HermesView = 'active' | 'history';

const HERMES_POLL_MS = 30_000;
const EXTERNAL_POLL_MS = 60_000;
const LOAD_ERROR = 'Discover is temporarily unavailable. Try again.';
const REFRESH_NOTICE = 'Could not refresh. Showing last loaded results.';
const STALE_HINT = ' Results may be stale.';

interface ExternalBrowseCacheEntry {
  items: ExternalDiscoverItem[];
  availability: ExternalDiscoverAvailability;
  libraryExclusion?: LibraryExclusionState;
  watchedExclusion?: WatchedExclusionState;
}

interface NoticeState {
  text: string;
  tone: 'success' | 'warning' | 'danger' | 'info';
}

/** Re-export for specs; canonical home is `media-stack/scheduled-poll`. */
export { SCHEDULED_REFRESH_TIMEOUT_MS } from '../media-stack/scheduled-poll';

@Injectable()
export class DiscoverFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly destroyRef = inject(DestroyRef);
  private readonly poll = new ScheduledPollController();

  private readonly _tab = signal<DiscoverSourceTab>('hermes');
  private readonly _hermesView = signal<HermesView>('active');
  private readonly _historyFilter = signal<DiscoverHistoryFilter>('all');
  private readonly _jellyseerrKind = signal<JellyseerrDiscoverKind>('trending');
  private readonly _traktType = signal<TraktDiscoverType>('movies');

  private readonly _status = signal<DiscoverStatus>('loading');
  private readonly _error = signal('');
  private readonly _mutationNotice = signal<NoticeState | null>(null);
  private readonly _browseNotice = signal<NoticeState | null>(null);
  private readonly _exclusionNotice = signal('');

  private readonly _hermesItems = signal<DiscoverItem[]>([]);
  private readonly _generationPending = signal(false);
  private readonly _jellyseerrCache = signal<Partial<Record<JellyseerrDiscoverKind, ExternalBrowseCacheEntry>>>({});
  private readonly _traktCache = signal<Partial<Record<TraktDiscoverType, ExternalBrowseCacheEntry>>>({});

  private readonly _busyItemId = signal<string | null>(null);
  private readonly _requestingMore = signal(false);
  private readonly _requestSyncFailedIds = signal<ReadonlySet<string>>(new Set());
  private readonly _requestSyncFailedKeys = signal<ReadonlySet<string>>(new Set());
  private readonly _requestedKeys = signal<ReadonlySet<string>>(new Set());

  /** True after a local request-more until the API has reported generation_request at least once. */
  private generationObserved = false;

  private hermesRequestId = 0;
  /** Highest generation whose success payload was committed (Hermes). */
  private hermesAppliedId = 0;
  private readonly jellyseerrGeneration: Record<JellyseerrDiscoverKind, number> = {
    trending: 0,
    movies: 0,
    tv: 0,
  };
  private readonly jellyseerrAppliedGeneration: Record<JellyseerrDiscoverKind, number> = {
    trending: 0,
    movies: 0,
    tv: 0,
  };
  private readonly traktGeneration: Record<TraktDiscoverType, number> = {
    movies: 0,
    shows: 0,
  };
  private readonly traktAppliedGeneration: Record<TraktDiscoverType, number> = {
    movies: 0,
    shows: 0,
  };
  /** True after at least one successful Hermes payload (including empty). */
  private hermesLoaded = false;

  readonly tab = this._tab.asReadonly();
  readonly hermesView = this._hermesView.asReadonly();
  readonly historyFilter = this._historyFilter.asReadonly();
  readonly jellyseerrKind = this._jellyseerrKind.asReadonly();
  readonly traktType = this._traktType.asReadonly();
  readonly status = this._status.asReadonly();
  readonly error = this._error.asReadonly();
  readonly notice = computed(() => {
    const mutation = this._mutationNotice()?.text;
    const browse = this._browseNotice()?.text;
    const exclusion = this._exclusionNotice();
    return [mutation, browse, exclusion].filter(Boolean).join('');
  });
  readonly noticeTone = computed(() =>
    this._mutationNotice()?.tone ?? this._browseNotice()?.tone ?? (this._exclusionNotice() ? 'warning' : 'info'),
  );
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
      return (this._jellyseerrCache()[kind]?.items ?? []).map((item) => toExternalCardItem(item, 'jellyseerr', requestedKeys));
    }
    const type = this._traktType();
    return (this._traktCache()[type]?.items ?? []).map((item) => toExternalCardItem(item, 'trakt', requestedKeys));
  });

  constructor() {
    this.destroyRef.onDestroy(() => {
      this.stopPolling();
    });
  }

  async setTab(tab: DiscoverSourceTab): Promise<void> {
    const changed = this._tab() !== tab;
    if (changed) {
      this._tab.set(tab);
      this.clearMutationNotice();
      this.clearBrowseNotice();
      this._exclusionNotice.set('');
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
    this.clearMutationNotice();
    try {
      const result = await this.api.submitHermesFeedback(id, feedback);
      if (!result.ok) {
        this.setMutationNotice(result.error ?? 'Could not save feedback.', 'danger');
        return;
      }
      this.setMutationNotice(result.message ?? 'Feedback saved.', 'success');
      // Drop in-flight Hermes loads started before this feedback so stale polls cannot undo the archive.
      this.hermesRequestId++;
      this.hermesAppliedId = this.hermesRequestId;
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
      this.setMutationNotice('Could not save feedback. Try again.', 'danger');
    } finally {
      this._busyItemId.set(null);
    }
  }

  async requestItem(item: DiscoverCardItem): Promise<void> {
    if (this._busyItemId()) return;
    const action = resolveRequestAction(item, { syncFailed: this.isSyncFailed(item) });
    if (action.disabled) return;
    this._busyItemId.set(item.id);
    this.clearMutationNotice();
    try {
      const result = await this.api.requestMedia({
        mediaType: item.type,
        mediaId: item.tmdbId,
        hermesId: item.hermesId,
      });
      if (!result.ok) {
        this.setMutationNotice(result.error ?? 'Could not request media.', 'danger');
        return;
      }
      if (result.dashboard_state_persisted === false) {
        this.addSyncFailed(item);
        this.setMutationNotice(result.message ?? 'Added to Sonarr/Radarr; dashboard synchronization failed.', 'warning');
      } else {
        this.markRequested(item.type, item.tmdbId);
        this.setMutationNotice(result.message ?? 'Requested.', 'success');
      }
      if (this._tab() === 'hermes') {
        await this.loadHermes();
      }
    } catch {
      this.setMutationNotice('Could not request media. Try again.', 'danger');
    } finally {
      this._busyItemId.set(null);
    }
  }

  async requestMore(): Promise<void> {
    if (this._requestingMore() || this._generationPending()) return;
    this._requestingMore.set(true);
    this.clearMutationNotice();
    try {
      const result = await this.api.requestHermesMore();
      if (!result.ok) {
        this.setMutationNotice(result.error ?? 'Could not queue more recommendations.', 'danger');
        return;
      }
      this._generationPending.set(true);
      this.generationObserved = false;
      if (result.already_pending) {
        this.setMutationNotice(result.message ?? 'A recommendation refresh is already pending.', 'info');
      } else {
        this.setMutationNotice(result.message ?? 'More recommendations queued.', 'success');
      }
      await this.loadHermes();
    } catch {
      this.setMutationNotice('Could not queue more recommendations. Try again.', 'danger');
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

  private async refreshCurrentTab(signal?: AbortSignal): Promise<void> {
    const tab = this._tab();
    if (tab === 'hermes') {
      await this.loadHermes(signal);
      return;
    }
    if (tab === 'jellyseerr') {
      await this.loadJellyseerr(this._jellyseerrKind(), signal);
      return;
    }
    await this.loadTrakt(this._traktType(), signal);
  }

  private restartPolling(): void {
    this.poll.stop();
    const interval = this._tab() === 'hermes' ? HERMES_POLL_MS : EXTERNAL_POLL_MS;
    this.poll.start(interval, (initial) => {
      if (initial) return;
      void this.poll.run(
        async (scheduledSignal) => {
          this.poll.beginRequest();
          await this.refreshCurrentTab(scheduledSignal);
        },
        () => {
          this.applyBrowseFailure(this.isBrowseInitialForCurrentTab(), LOAD_ERROR);
        },
      );
    });
  }

  private stopPolling(invalidateInFlight = true): void {
    this.poll.stop();
    if (invalidateInFlight) {
      this.hermesRequestId++;
    }
  }

  private isBrowseInitialForCurrentTab(): boolean {
    const tab = this._tab();
    if (tab === 'hermes') return !this.hermesLoaded;
    if (tab === 'jellyseerr') return !this._jellyseerrCache()[this._jellyseerrKind()];
    return !this._traktCache()[this._traktType()];
  }

  private async loadHermes(signal?: AbortSignal): Promise<void> {
    const requestId = ++this.hermesRequestId;
    const isInitial = !this.hermesLoaded;
    if (isInitial && this._tab() === 'hermes') {
      this._status.set('loading');
    }
    try {
      const response = await this.api.listHermesRecommendations(signal);
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
      if (signal?.aborted) return;
      if (!this.isCurrentHermesRequest(requestId)) return;
      this.applyBrowseFailure(isInitial, LOAD_ERROR);
    }
  }

  private isCurrentHermesRequest(requestId: number): boolean {
    return requestId === this.hermesRequestId && this._tab() === 'hermes';
  }

  private async loadJellyseerr(kind: JellyseerrDiscoverKind, signal?: AbortSignal): Promise<void> {
    await this.loadExternalBrowse({
      nextGeneration: () => ++this.jellyseerrGeneration[kind],
      currentGeneration: () => this.jellyseerrGeneration[kind],
      appliedGeneration: () => this.jellyseerrAppliedGeneration[kind],
      setAppliedGeneration: (generation) => {
        this.jellyseerrAppliedGeneration[kind] = generation;
      },
      isActive: () => this._tab() === 'jellyseerr' && this._jellyseerrKind() === kind,
      cached: () => this._jellyseerrCache()[kind],
      writeCache: (items, availability, libraryExclusion, watchedExclusion) => {
        this._jellyseerrCache.update((cache) => ({ ...cache, [kind]: { items, availability, libraryExclusion, watchedExclusion } }));
      },
      fetch: () => this.api.listJellyseerrDiscover(kind, signal),
      signal,
    });
  }

  private async loadTrakt(type: TraktDiscoverType, signal?: AbortSignal): Promise<void> {
    await this.loadExternalBrowse({
      nextGeneration: () => ++this.traktGeneration[type],
      currentGeneration: () => this.traktGeneration[type],
      appliedGeneration: () => this.traktAppliedGeneration[type],
      setAppliedGeneration: (generation) => {
        this.traktAppliedGeneration[type] = generation;
      },
      isActive: () => this._tab() === 'trakt' && this._traktType() === type,
      cached: () => this._traktCache()[type],
      writeCache: (items, availability, libraryExclusion, watchedExclusion) => {
        this._traktCache.update((cache) => ({ ...cache, [type]: { items, availability, libraryExclusion, watchedExclusion } }));
      },
      fetch: () => this.api.listTraktDiscover(type, signal),
      signal,
    });
  }

  /** Shared Jellyseerr/Trakt browse load: cache prime, generation guard, soft failure. */
  private async loadExternalBrowse(opts: {
    nextGeneration: () => number;
    currentGeneration: () => number;
    appliedGeneration: () => number;
    setAppliedGeneration: (generation: number) => void;
    isActive: () => boolean;
    cached: () => ExternalBrowseCacheEntry | undefined;
    writeCache: (
      items: ExternalDiscoverItem[],
      availability: ExternalDiscoverAvailability,
      libraryExclusion?: LibraryExclusionState,
      watchedExclusion?: WatchedExclusionState,
    ) => void;
    fetch: () => Promise<{
      ok: boolean;
      items: ExternalDiscoverItem[];
      availability?: ExternalDiscoverAvailability;
      library_exclusion?: LibraryExclusionState;
      watched_exclusion?: WatchedExclusionState;
      error?: string;
      code?: 'reconnect_required';
    }>;
    signal?: AbortSignal;
  }): Promise<void> {
    const generation = opts.nextGeneration();
    const isActive = opts.isActive();
    const isInitial = this.primeBrowseCache(isActive, opts.cached());
    try {
      const response = await opts.fetch();
      if (!response.ok) {
        if (generation !== opts.currentGeneration()) return;
        if (opts.isActive()) this.applyBrowseFailure(isInitial, LOAD_ERROR, response.code, true);
        return;
      }
      const availability = response.availability ?? 'available';
      if (generation !== opts.currentGeneration()) return;
      if (availability === 'disabled' && !opts.isActive()) return;
      if (generation < opts.appliedGeneration()) return;
      opts.writeCache(
        availability === 'disabled' ? [] : response.items,
        availability,
        response.library_exclusion,
        response.watched_exclusion,
      );
      opts.setAppliedGeneration(generation);
      if (!opts.isActive()) return;
      if (availability === 'disabled') {
        this._status.set('disabled');
        this._error.set('');
        this.clearBrowseNotice();
        this._exclusionNotice.set('');
        return;
      }
      this.applyExclusionNotice(response.library_exclusion, response.watched_exclusion);
      this.commitBrowseSuccess(response.items, generation, opts.currentGeneration());
    } catch (error) {
      if (opts.signal?.aborted) return;
      if (generation !== opts.currentGeneration() || !opts.isActive()) return;
      const code = (error as { code?: unknown }).code;
      this.applyBrowseFailure(isInitial, LOAD_ERROR, code, true);
    }
  }

  /** Surface cached items immediately, or mark loading when the active browse has no cache. */
  private primeBrowseCache(isActive: boolean, cached: ExternalBrowseCacheEntry | undefined): boolean {
    if (!isActive) return !cached;
    if (cached) {
      if (cached.availability === 'disabled') {
        this._status.set('disabled');
      } else {
        this._status.set(cached.items.length ? 'ready' : 'empty');
      }
      this._error.set('');
      this.applyExclusionNotice(cached.libraryExclusion, cached.watchedExclusion);
    } else {
      this._status.set('loading');
    }
    return !cached;
  }

  private applyExclusionNotice(library?: LibraryExclusionState, watched?: WatchedExclusionState): void {
    const tab = this._tab();
    let source = 'Trakt';
    if (tab === 'hermes') source = 'Hermes';
    else if (tab === 'jellyseerr') source = 'Jellyseerr';
    const notices: string[] = [];
    if (library?.status === 'stale') {
      notices.push(`Library filtering is using a cached snapshot. Showing ${source} recommendations.`);
    } else if (library?.status === 'unavailable') {
      notices.push(`Library filtering is unavailable. Showing ${source} recommendations.`);
    }
    if (watched?.status === 'stale') {
      notices.push(
        tab === 'jellyseerr'
          ? 'Watched filtering is using a cached snapshot. Showing Jellyseerr recommendations.'
          : 'Watched filtering is using a cached snapshot.',
      );
    } else if (watched?.status === 'unavailable') {
      notices.push(`Watched filtering is unavailable. Showing ${source} recommendations.`);
    }
    if (notices.length) {
      this._exclusionNotice.set(notices.join(' '));
    } else {
      this._exclusionNotice.set('');
    }
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
    this.clearBrowseNotice();
  }

  /**
   * Background failures keep last-good browse state and surface a non-destructive notice.
   * Initial failures (no last-good) flip to exclusive error.
   * Mutation notices stay visible; a refresh failure appends a stale hint rather than replacing them.
   */
  private applyBrowseFailure(
    isInitial: boolean,
    message: string,
    code?: unknown,
    safeExternalError = false,
  ): void {
    const reconnectRequired = code === 'reconnect_required';
    if (reconnectRequired) {
      this.setBrowseNotice('Trakt reconnect required. Run .\\install.ps1 -Mode connect-trakt.', 'warning');
      if (isInitial) {
        this._status.set('error');
        this._error.set(LOAD_ERROR);
      }
      return;
    }
    if (!isInitial) {
      if (safeExternalError) {
        this.setBrowseNotice(LOAD_ERROR, 'warning');
      } else if (this._mutationNotice()) {
        this.setBrowseNotice(STALE_HINT.trim(), 'warning');
      } else {
        this.setBrowseNotice(REFRESH_NOTICE, 'warning');
      }
      return;
    }
    this._status.set('error');
    this._error.set(message);
    if (safeExternalError) this.setBrowseNotice(LOAD_ERROR, 'warning');
    else this.clearBrowseNotice();
    this._exclusionNotice.set('');
  }

  private applyHermesPayload(response: HermesDiscover): void {
    this._hermesItems.set(response.items);
    if (this._tab() === 'hermes') {
      this.applyExclusionNotice(response.library_exclusion, response.watched_exclusion);
    }
    this.seedRequestedFromHermes(response.items);
    this.applyPendingRequestSync(response.items, response.pending_request_sync);
    this.reconcileSyncFailed(response.items);
    this.applyGenerationPending(Boolean(response.generation_request));
  }

  private setMutationNotice(text: string, tone: NoticeState['tone']): void {
    this._mutationNotice.set({ text, tone });
  }

  private clearMutationNotice(): void {
    this._mutationNotice.set(null);
  }

  private setBrowseNotice(text: string, tone: NoticeState['tone']): void {
    this._browseNotice.set({ text, tone });
  }

  private clearBrowseNotice(): void {
    this._browseNotice.set(null);
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
