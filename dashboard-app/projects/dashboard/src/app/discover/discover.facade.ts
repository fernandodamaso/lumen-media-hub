import { computed, DestroyRef, inject, Injectable, signal } from '@angular/core';
import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import { ScheduledPollController } from '../media-stack/scheduled-poll';
import {
  DiscoverCardItem,
  DiscoverHistoryFilter,
  isAiPickActiveItem,
  matchesHistoryFilter,
  mediaIdentityKey,
  toExternalCardItem,
  toAiPickCardItem,
} from './discover-format';
import {
  DiscoverFeedback,
  DiscoverItem,
  DiscoverSourceTab,
  ExternalDiscoverAvailability,
  ExternalDiscoverItem,
  AiPicksDiscover,
  JellyseerrDiscoverKind,
  LibraryExclusionState,
  SubmitAiPickFeedbackOptions,
  TraktDiscoverType,
  WatchedExclusionState,
} from './discover.models';

export type DiscoverStatus = 'loading' | 'ready' | 'empty' | 'disabled' | 'error';
export type AiPicksView = 'active' | 'history';

const AI_PICKS_POLL_MS = 30_000;
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

  private readonly _tab = signal<DiscoverSourceTab>('ai-picks');
  private readonly _aiPicksView = signal<AiPicksView>('active');
  private readonly _historyFilter = signal<DiscoverHistoryFilter>('all');
  private readonly _jellyseerrKind = signal<JellyseerrDiscoverKind>('trending');
  private readonly _traktType = signal<TraktDiscoverType>('movies');

  private readonly _status = signal<DiscoverStatus>('loading');
  private readonly _error = signal('');
  private readonly _mutationNotice = signal<NoticeState | null>(null);
  private readonly _generationNotice = signal<NoticeState | null>(null);
  private readonly _browseNotice = signal<NoticeState | null>(null);
  private readonly _exclusionNotice = signal('');

  private readonly _aiPickItems = signal<DiscoverItem[]>([]);
  private readonly _generationPending = signal(false);
  private readonly _generationEnabled = signal(false);
  private readonly _jellyseerrCache = signal<Partial<Record<JellyseerrDiscoverKind, ExternalBrowseCacheEntry>>>({});
  private readonly _traktCache = signal<Partial<Record<TraktDiscoverType, ExternalBrowseCacheEntry>>>({});

  private readonly _busyItemId = signal<string | null>(null);
  private readonly _requestingMore = signal(false);
  private readonly _requestSyncFailedIds = signal<ReadonlySet<string>>(new Set());
  private readonly _requestSyncFailedKeys = signal<ReadonlySet<string>>(new Set());

  private aiPicksRequestId = 0;
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
  /** True after at least one successful AI Picks payload (including empty). */
  private aiPicksLoaded = false;

  readonly tab = this._tab.asReadonly();
  readonly aiPicksView = this._aiPicksView.asReadonly();
  readonly historyFilter = this._historyFilter.asReadonly();
  readonly jellyseerrKind = this._jellyseerrKind.asReadonly();
  readonly traktType = this._traktType.asReadonly();
  readonly status = this._status.asReadonly();
  readonly error = this._error.asReadonly();
  readonly notice = computed(() => {
    return [
      this._mutationNotice()?.text,
      this._tab() === 'ai-picks' ? this._generationNotice()?.text : undefined,
      this._browseNotice()?.text,
      this._exclusionNotice(),
    ].filter((notice): notice is string => Boolean(notice)).join(' ');
  });
  readonly noticeTone = computed(() => {
    const tones = [
      this._mutationNotice()?.tone,
      this._tab() === 'ai-picks' ? this._generationNotice()?.tone : undefined,
      this._browseNotice()?.tone,
      this._exclusionNotice() ? 'warning' as const : undefined,
    ].filter((tone): tone is NoticeState['tone'] => Boolean(tone));
    return tones.reduce<NoticeState['tone']>((highest, tone) =>
      this.noticeSeverity(tone) > this.noticeSeverity(highest) ? tone : highest,
      'info',
    );
  });
  readonly busyItemId = this._busyItemId.asReadonly();
  readonly requestingMore = this._requestingMore.asReadonly();
  readonly generationPending = this._generationPending.asReadonly();
  readonly generationEnabled = this._generationEnabled.asReadonly();
  readonly requestSyncFailedIds = this._requestSyncFailedIds.asReadonly();

  readonly visibleItems = computed<DiscoverCardItem[]>(() => {
    const tab = this._tab();
    if (tab === 'ai-picks') {
      const view = this._aiPicksView();
      const filter = this._historyFilter();
      return this._aiPickItems()
        .filter((item) => (view === 'active' ? isAiPickActiveItem(item) : !isAiPickActiveItem(item)))
        .filter((item) => (view === 'history' ? matchesHistoryFilter(item, filter) : true))
        .map((item) => toAiPickCardItem(item));
    }
    if (tab === 'jellyseerr') {
      const kind = this._jellyseerrKind();
      return (this._jellyseerrCache()[kind]?.items ?? []).map((item) => toExternalCardItem(item, 'jellyseerr'));
    }
    const type = this._traktType();
    return (this._traktCache()[type]?.items ?? []).map((item) => toExternalCardItem(item, 'trakt'));
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

  setAiPicksView(view: AiPicksView): void {
    this._aiPicksView.set(view);
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

  async refreshActiveFeed(): Promise<void> {
    await this.refreshCurrentTab();
  }

  async submitFeedback(
    id: string,
    feedback: DiscoverFeedback,
    options?: SubmitAiPickFeedbackOptions,
  ): Promise<void> {
    if (this._busyItemId()) return;
    this._busyItemId.set(id);
    this.clearMutationNotice();
    try {
      const result = await this.api.submitAiPickFeedback(id, feedback, options);
      if (!result.ok) {
        if (result.code === 'confirmation_required') {
          this.setMutationNotice('Confirm marking all aired episodes watched on Trakt.', 'warning');
        } else {
          this.setMutationNotice(result.error ?? 'Could not save feedback.', 'danger');
        }
        return;
      }
      this.setMutationNotice(result.message ?? 'Feedback saved.', 'success');
      this.aiPicksRequestId++;
      this._aiPickItems.update((items) =>
        items.map((item) =>
          item.id === id
            ? {
                ...item,
                active: false,
                feedback,
                feedback_at: new Date().toISOString(),
                trakt_history_sync:
                  result.trakt_history_sync ?? (feedback === 'watched' ? { status: 'pending' } : item.trakt_history_sync),
              }
            : item,
        ),
      );
      this.syncVisibleStatus();
      await this.loadAiPicks();
    } catch {
      this.setMutationNotice('Could not save feedback. Try again.', 'danger');
    } finally {
      this._busyItemId.set(null);
    }
  }

  async requestMore(): Promise<void> {
    if (!this._generationEnabled() || this._requestingMore() || this._generationPending()) return;
    this._requestingMore.set(true);
    this.clearMutationNotice();
    try {
      const result = await this.api.requestMoreAiPicks();
      if (!result.ok) {
        this.setMutationNotice(result.error ?? 'Could not queue more recommendations.', 'danger');
        return;
      }
      this._generationPending.set(true);
      if (result.already_pending) {
        this.setMutationNotice(result.message ?? 'A recommendation refresh is already pending.', 'info');
      } else {
        this.setMutationNotice(result.message ?? 'More recommendations queued.', 'success');
      }
      await this.loadAiPicks();
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
    if (tab === 'ai-picks') {
      await this.loadAiPicks(signal);
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
    const interval = this._tab() === 'ai-picks' ? AI_PICKS_POLL_MS : EXTERNAL_POLL_MS;
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
      this.aiPicksRequestId++;
    }
  }

  private isBrowseInitialForCurrentTab(): boolean {
    const tab = this._tab();
    if (tab === 'ai-picks') return !this.aiPicksLoaded;
    if (tab === 'jellyseerr') return !this._jellyseerrCache()[this._jellyseerrKind()];
    return !this._traktCache()[this._traktType()];
  }

  private async loadAiPicks(signal?: AbortSignal): Promise<void> {
    const requestId = ++this.aiPicksRequestId;
    const isInitial = !this.aiPicksLoaded;
    if (isInitial && this._tab() === 'ai-picks') {
      this._status.set('loading');
    }
    try {
      const response = await this.api.listAiPicks(signal);
      if (!response.ok) {
        // Failures only apply when still current — a stale failure must not clobber newer work.
        if (!this.isCurrentAiPicksRequest(requestId)) return;
        this.applyBrowseFailure(isInitial, LOAD_ERROR, undefined, true);
        return;
      }
      if (!this.isCurrentAiPicksRequest(requestId)) return;
      this.applyAiPicksPayload(response);
      this.aiPicksLoaded = true;
      if (this._tab() !== 'ai-picks') return;
      this.commitBrowseSuccessCount(this.visibleItems().length, requestId, this.aiPicksRequestId);
    } catch {
      if (signal?.aborted) return;
      if (!this.isCurrentAiPicksRequest(requestId)) return;
      this.applyBrowseFailure(isInitial, LOAD_ERROR, undefined, true);
    }
  }

  private isCurrentAiPicksRequest(requestId: number): boolean {
    return requestId === this.aiPicksRequestId && this._tab() === 'ai-picks';
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
      allowReconnect: false,
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
      allowReconnect: true,
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
    allowReconnect: boolean;
  }): Promise<void> {
    const generation = opts.nextGeneration();
    const isActive = opts.isActive();
    const isInitial = this.primeBrowseCache(isActive, opts.cached());
    try {
      const response = await opts.fetch();
      if (!response.ok) {
        if (generation !== opts.currentGeneration()) return;
        if (opts.isActive()) {
          this.applyBrowseFailure(
            isInitial,
            LOAD_ERROR,
            opts.allowReconnect ? response.code : undefined,
            true,
          );
        }
        return;
      }
      const availability = response.availability ?? 'available';
      if (generation !== opts.currentGeneration() || !opts.isActive()) return;
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
      const code = opts.allowReconnect ? (error as { code?: unknown }).code : undefined;
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
    if (tab === 'ai-picks') source = 'AI Picks';
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
        this.setBrowseNotice(REFRESH_NOTICE, 'warning');
      } else if (this._mutationNotice()) {
        this.setBrowseNotice(STALE_HINT.trim(), 'warning');
      } else {
        this.setBrowseNotice(REFRESH_NOTICE, 'warning');
      }
      return;
    }
    this._status.set('error');
    this._error.set(message);
    this.clearBrowseNotice();
    this._exclusionNotice.set('');
  }

  private applyAiPicksPayload(response: AiPicksDiscover): void {
    this._aiPickItems.set(response.items);
    this._generationEnabled.set(response.generation_enabled === true);
    if (this._tab() === 'ai-picks') {
      this.applyExclusionNotice(response.library_exclusion, response.watched_exclusion);
    }
    this.applyPendingRequestSync(response.items, response.pending_request_sync);
    this.reconcileSyncFailed(response.items);
    const generation = response.generation;
    this._generationPending.set(generation?.status === 'queued' || generation?.status === 'running');
    if (generation?.status === 'failed') {
      this._generationNotice.set({
        text: `AI generation failed (${generation.error_code ?? 'provider_failure'}). Existing picks are unchanged.`,
        tone: 'warning',
      });
    } else {
      this._generationNotice.set(null);
    }
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

  private noticeSeverity(tone: NoticeState['tone']): number {
    switch (tone) {
      case 'danger': return 3;
      case 'warning': return 2;
      case 'success': return 1;
      default: return 0;
    }
  }

  private syncVisibleStatus(): void {
    if (this._status() === 'loading' || this._status() === 'error') return;
    this._status.set(this.visibleItems().length ? 'ready' : 'empty');
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
