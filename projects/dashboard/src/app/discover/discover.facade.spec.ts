import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { DiscoverAction, DiscoverFeedback, DiscoverItem, DiscoverRequestPayload, ExternalDiscoverItem, HermesDiscover, JellyseerrDiscoverKind, TraktDiscoverType } from './discover.models';
import { MEDIA_STACK_API, MediaStackApi } from '../media-stack/media-stack-api';
import { DiscoverFacade } from './discover.facade';

describe('DiscoverFacade', () => {
  let api: MockApi;
  let facade: DiscoverFacade;

  beforeEach(() => {
    api = new MockApi();
    TestBed.configureTestingModule({
      providers: [DiscoverFacade, { provide: MEDIA_STACK_API, useValue: api }],
    });
    facade = TestBed.inject(DiscoverFacade);
  });

  it('loads Hermes by default and isolates visible content across tabs', async () => {
    await facade.setTab('hermes');
    expect(facade.tab()).toBe('hermes');
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Signal Drift']);
    expect(api.hermesCalls).toBe(1);

    facade.setTab('jellyseerr');
    await Promise.resolve();
    await flush();
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Trending Ember']);
    expect(api.jellyseerrCalls).toEqual(['trending']);

    facade.setJellyseerrKind('movies');
    await flush();
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Neon Archive']);
    expect(api.jellyseerrCalls).toEqual(['trending', 'movies']);

    facade.setTab('trakt');
    await flush();
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Trakt Horizon']);
    expect(api.traktCalls).toEqual(['movies']);

    await facade.setTab('hermes');
    await flush();
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Signal Drift']);
  });

  it('submitFeedback calls only submitHermesFeedback and refreshes Hermes', async () => {
    await facade.setTab('hermes');
    await facade.submitFeedback('hermes-eligible', 'liked');
    expect(api.feedbackCalls).toEqual([{ id: 'hermes-eligible', feedback: 'liked' }]);
    expect(api.requestCalls).toEqual([]);
    expect(facade.notice()).toContain('Feedback');
  });

  it('requestItem calls only requestMedia and tracks sync-failed notices', async () => {
    await facade.setTab('hermes');
    api.requestResult = {
      ok: true,
      dashboard_state_persisted: false,
      partial_success: true,
      message: 'Added to Sonarr/Radarr; dashboard synchronization failed.',
    };
    await facade.requestItem(facade.visibleItems()[0]);
    expect(api.requestCalls).toHaveLength(1);
    expect(api.feedbackCalls).toEqual([]);
    expect(facade.isSyncFailed('hermes-eligible')).toBe(true);
    expect(facade.noticeTone()).toBe('warning');
    expect(facade.notice()).toContain('synchronization failed');
  });

  it('prevents duplicate busy mutations', async () => {
    await facade.setTab('hermes');
    const { promise: feedbackGate, resolve: resolveFeedback } = Promise.withResolvers<DiscoverAction>();
    const release = () => resolveFeedback({ ok: true, message: 'Feedback saved.' });
    api.feedbackGate = feedbackGate;
    const first = facade.submitFeedback('hermes-eligible', 'liked');
    await facade.submitFeedback('hermes-eligible', 'disliked');
    expect(api.feedbackCalls).toHaveLength(1);
    release();
    await first;
  });

  it('requestMore reports queued then blocks duplicates while pending', async () => {
    await facade.setTab('hermes');
    api.moreResult = { ok: true, queued: true, message: 'More recommendations queued.' };
    await facade.requestMore();
    expect(facade.generationPending()).toBe(true);
    expect(facade.notice()).toContain('queued');

    api.moreResult = { ok: true, already_pending: true, message: 'A recommendation refresh is already pending.' };
    await facade.requestMore();
    expect(api.moreCalls).toBe(1);
  });

  it('surfaces already_pending when the adapter reports it on first call', async () => {
    await facade.setTab('hermes');
    api.moreResult = { ok: true, already_pending: true, message: 'A recommendation refresh is already pending.' };
    await facade.requestMore();
    expect(facade.generationPending()).toBe(true);
    expect(facade.noticeTone()).toBe('info');
    expect(facade.notice()).toContain('already pending');
  });

  it('clears sync-failed ids once Hermes shows requested state', async () => {
    await facade.setTab('hermes');
    api.requestResult = {
      ok: true,
      dashboard_state_persisted: false,
      message: 'sync failed',
    };
    await facade.requestItem(facade.visibleItems()[0]);
    expect(facade.isSyncFailed('hermes-eligible')).toBe(true);

    api.hermes.items = [
      {
        ...api.hermes.items[0],
        request_state: 'requested',
        requested_at: '2026-07-12T00:00:00Z',
        jellyseerr_request_id: 1,
      },
    ];
    await facade.setTab('hermes');
    expect(facade.isSyncFailed('hermes-eligible')).toBe(false);
  });

  it('recomputes ready/empty when switching Hermes view after active becomes empty', async () => {
    api.hermes.items = [
      {
        id: 'hermes-eligible',
        source: 'hermes',
        type: 'movie',
        title: 'Signal Drift',
        year: 2024,
        tmdb_id: 101001,
        active: true,
        feedback: null,
        feedback_at: null,
        request_state: null,
        requested_at: null,
        jellyseerr_request_id: null,
        in_library: false,
        added_at: '2026-07-10T12:00:00Z',
      },
      {
        id: 'hermes-history-liked',
        source: 'hermes',
        type: 'movie',
        title: 'Copper Skies',
        year: 2021,
        tmdb_id: 201001,
        active: false,
        feedback: 'liked',
        feedback_at: '2026-07-01T10:00:00Z',
        request_state: null,
        requested_at: null,
        jellyseerr_request_id: null,
        in_library: false,
        added_at: '2026-06-20T12:00:00Z',
      },
    ];
    await facade.setTab('hermes');
    expect(facade.status()).toBe('ready');

    api.hermes.items = api.hermes.items.map((item) =>
      item.id === 'hermes-eligible'
        ? { ...item, active: false, feedback: 'skipped' as const, feedback_at: '2026-07-12T00:00:00Z' }
        : item,
    );
    await facade.setTab('hermes');
    expect(facade.status()).toBe('empty');
    expect(facade.visibleItems()).toEqual([]);

    facade.setHermesView('history');
    expect(facade.status()).toBe('ready');
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Signal Drift', 'Copper Skies']);
  });

  it('marks external items requested and refuses duplicate requestMedia calls', async () => {
    await facade.setTab('jellyseerr');
    await flush();
    const item = facade.visibleItems()[0];
    expect(item.requestState).toBeNull();

    await facade.requestItem(item);
    expect(api.requestCalls).toHaveLength(1);
    expect(facade.visibleItems()[0].requestState).toBe('requested');

    await facade.requestItem(facade.visibleItems()[0]);
    expect(api.requestCalls).toHaveLength(1);
  });

  it('seeds requested keys from Hermes so external tabs disable duplicates', async () => {
    api.hermes.items = [
      {
        ...api.hermes.items[0],
        request_state: 'requested',
        requested_at: '2026-07-09T09:00:00Z',
        jellyseerr_request_id: 9001,
      },
    ];
    api.jellyseerr.trending = [{ type: 'movie', title: 'Same Title', tmdb_id: 101001 }];
    await facade.setTab('hermes');
    await facade.setTab('jellyseerr');
    await flush();
    expect(facade.visibleItems()[0].requestState).toBe('requested');
    await facade.requestItem(facade.visibleItems()[0]);
    expect(api.requestCalls).toHaveLength(0);
  });

  it('honors pending_request_sync as sync-failed across identities', async () => {
    api.hermes = {
      ok: true,
      items: [
        {
          id: 'hermes-sync',
          source: 'hermes',
          type: 'tv',
          title: 'Night Courier',
          year: 2022,
          tmdb_id: 101005,
          active: true,
          feedback: null,
          feedback_at: null,
          request_state: null,
          requested_at: null,
          jellyseerr_request_id: 55,
          in_library: false,
          added_at: '2026-07-10T14:00:00Z',
        },
      ],
      pending_request_sync: [{ id: 'hermes-sync', jellyseerr_request_id: 55 }],
    };
    api.jellyseerr.trending = [{ type: 'tv', title: 'Night Courier External', tmdb_id: 101005 }];
    await facade.setTab('hermes');
    expect(facade.isSyncFailed('hermes-sync')).toBe(true);
    expect(facade.isSyncFailed(facade.visibleItems()[0])).toBe(true);

    await facade.setTab('jellyseerr');
    await flush();
    expect(facade.isSyncFailed(facade.visibleItems()[0])).toBe(true);
    await facade.requestItem(facade.visibleItems()[0]);
    expect(api.requestCalls).toHaveLength(0);
  });

  it('ignores stale Hermes failures after switching tabs', async () => {
    const { promise: hermesGate, resolve: releaseHermes } = Promise.withResolvers<HermesDiscover>();
    api.hermesGate = hermesGate;
    const pending = facade.setTab('hermes');
    await facade.setTab('jellyseerr');
    await flush();
    expect(facade.status()).toBe('ready');
    releaseHermes({ ok: false, items: [], error: 'Hermes offline' });
    await pending;
    expect(facade.tab()).toBe('jellyseerr');
    expect(facade.status()).toBe('ready');
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Trending Ember']);
  });

  it('ignores a superseded Hermes response for the same filter', async () => {
    await facade.setTab('hermes');
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Signal Drift']);

    const { promise: firstGate, resolve: releaseFirst } = Promise.withResolvers<HermesDiscover>();
    api.hermesGate = firstGate;
    const first = facade.setTab('hermes');
    await Promise.resolve();

    api.hermes = {
      ok: true,
      items: [
        {
          ...api.hermes.items[0],
          title: 'Newer Hermes',
        },
      ],
    };
    const second = facade.setTab('hermes');
    await second;
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Newer Hermes']);

    releaseFirst({
      ok: true,
      items: [{ ...api.hermes.items[0], title: 'Stale Hermes' }],
    });
    await first;
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Newer Hermes']);
  });

  it('ignores a superseded Jellyseerr filter response after switching kinds', async () => {
    await facade.setTab('jellyseerr');
    await flush();

    const { promise: trendingGate, resolve: releaseTrending } = Promise.withResolvers<{
      ok: boolean;
      items: ExternalDiscoverItem[];
    }>();
    api.jellyseerrGate = trendingGate;
    const stale = facade.setTab('jellyseerr');
    await Promise.resolve();

    facade.setJellyseerrKind('movies');
    await flush();
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Neon Archive']);

    releaseTrending({
      ok: true,
      items: [{ type: 'movie', title: 'Stale Trending', tmdb_id: 99 }],
    });
    await stale;
    expect(facade.jellyseerrKind()).toBe('movies');
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Neon Archive']);
  });

  it('retains last-good Hermes results when a background refresh fails', async () => {
    await facade.setTab('hermes');
    expect(facade.status()).toBe('ready');
    expect(facade.visibleItems()).toHaveLength(1);

    api.hermes = { ok: false, items: [], error: 'Hermes offline' };
    await facade.setTab('hermes');
    expect(facade.status()).toBe('ready');
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Signal Drift']);
    expect(facade.noticeTone()).toBe('warning');
    expect(facade.notice()).toContain('Showing last loaded');
  });

  it('hard-errors on the initial Hermes load failure', async () => {
    api.hermes = { ok: false, items: [], error: 'Hermes offline' };
    await facade.setTab('hermes');
    expect(facade.status()).toBe('error');
    expect(facade.error()).toContain('Hermes offline');
    expect(facade.visibleItems()).toEqual([]);
  });

  it('keeps browse status ready while a request mutation is busy', async () => {
    await facade.setTab('hermes');
    const { promise: requestGate, resolve: releaseRequest } = Promise.withResolvers<DiscoverAction>();
    api.requestGate = requestGate;
    const pending = facade.requestItem(facade.visibleItems()[0]);
    await Promise.resolve();
    expect(facade.busyItemId()).toBe('hermes-eligible');
    expect(facade.status()).toBe('ready');
    expect(facade.visibleItems()).toHaveLength(1);
    releaseRequest({ ok: false, error: 'Cannot request' });
    await pending;
    expect(facade.status()).toBe('ready');
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Signal Drift']);
    expect(facade.noticeTone()).toBe('danger');
  });

  it('skips overlapping scheduled polls while a refresh is in flight', async () => {
    vi.useFakeTimers();
    await facade.setTab('hermes');
    expect(api.hermesCalls).toBe(1);

    const { promise: hermesGate, resolve: releaseHermes } = Promise.withResolvers<HermesDiscover>();
    api.hermesGate = hermesGate;
    await vi.advanceTimersByTimeAsync(30_000);
    expect(api.hermesCalls).toBe(2);

    await vi.advanceTimersByTimeAsync(30_000);
    expect(api.hermesCalls).toBe(2);

    releaseHermes({
      ok: true,
      items: api.hermes.items.map((item) => ({ ...item })),
    });
    await flush();
    await vi.advanceTimersByTimeAsync(30_000);
    expect(api.hermesCalls).toBe(3);
    vi.useRealTimers();
  });

  it('keeps request-more pending when the follow-up list omits generation_request', async () => {
    await facade.setTab('hermes');
    api.moreResult = { ok: true, queued: true, message: 'More recommendations queued.' };
    api.skipGenerationOnMore = true;
    await facade.requestMore();
    expect(facade.generationPending()).toBe(true);
    await facade.requestMore();
    expect(api.moreCalls).toBe(1);
  });

  it('shows cached external feeds immediately when returning to a filter', async () => {
    await facade.setTab('jellyseerr');
    await flush();
    expect(facade.status()).toBe('ready');

    await facade.setTab('hermes');
    await flush();
    api.hermes = { ok: true, items: [] };
    await facade.setTab('hermes');
    expect(facade.status()).toBe('empty');

    const { promise: jellyseerrGate, resolve: resolveJellyseerr } = Promise.withResolvers<{
      ok: boolean;
      items: ExternalDiscoverItem[];
    }>();
    const release = () => resolveJellyseerr({ ok: true, items: api.jellyseerr.trending });
    api.jellyseerrGate = jellyseerrGate;
    facade.setTab('jellyseerr');
    await Promise.resolve();
    expect(facade.status()).toBe('ready');
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Trending Ember']);
    release();
    await flush();
  });

  it('polls only while started and stops on destroy', async () => {
    vi.useFakeTimers();
    await facade.setTab('hermes');
    await vi.advanceTimersByTimeAsync(0);
    expect(api.hermesCalls).toBe(1);
    await vi.advanceTimersByTimeAsync(30_000);
    expect(api.hermesCalls).toBe(2);
    TestBed.resetTestingModule();
    await vi.advanceTimersByTimeAsync(30_000);
    expect(api.hermesCalls).toBe(2);
    vi.useRealTimers();
  });
});

async function flush(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

class MockApi implements MediaStackApi {
  hermes: HermesDiscover = {
    ok: true,
    items: [
      {
        id: 'hermes-eligible',
        source: 'hermes',
        type: 'movie',
        title: 'Signal Drift',
        year: 2024,
        tmdb_id: 101001,
        active: true,
        feedback: null,
        feedback_at: null,
        request_state: null,
        requested_at: null,
        jellyseerr_request_id: null,
        in_library: false,
        added_at: '2026-07-10T12:00:00Z',
      } satisfies DiscoverItem,
    ],
  };
  jellyseerr: Record<JellyseerrDiscoverKind, ExternalDiscoverItem[]> = {
    trending: [{ type: 'movie', title: 'Trending Ember', tmdb_id: 1 }],
    movies: [{ type: 'movie', title: 'Neon Archive', tmdb_id: 2 }],
    tv: [{ type: 'tv', title: 'Late Broadcast', tmdb_id: 3 }],
  };
  trakt: Record<TraktDiscoverType, ExternalDiscoverItem[]> = {
    movies: [{ type: 'movie', title: 'Trakt Horizon', tmdb_id: 4 }],
    shows: [{ type: 'tv', title: 'Trakt Relay', tmdb_id: 5 }],
  };
  hermesCalls = 0;
  jellyseerrCalls: JellyseerrDiscoverKind[] = [];
  traktCalls: TraktDiscoverType[] = [];
  feedbackCalls: { id: string; feedback: DiscoverFeedback }[] = [];
  requestCalls: DiscoverRequestPayload[] = [];
  moreCalls = 0;
  feedbackGate: Promise<DiscoverAction> | null = null;
  hermesGate: Promise<HermesDiscover> | null = null;
  jellyseerrGate: Promise<{ ok: boolean; items: ExternalDiscoverItem[] }> | null = null;
  requestGate: Promise<DiscoverAction> | null = null;
  requestResult: DiscoverAction = { ok: true, dashboard_state_persisted: true, message: 'Requested.' };
  moreResult: DiscoverAction = { ok: true, queued: true };
  skipGenerationOnMore = false;

  listTorrents() {
    return Promise.resolve([]);
  }
  pauseAll() {
    return Promise.resolve();
  }
  resumeAll() {
    return Promise.resolve();
  }
  pauseTorrent() {
    return Promise.resolve();
  }
  resumeTorrent() {
    return Promise.resolve();
  }
  getLibraryStats() {
    return Promise.resolve({ movies: 0, series: 0, availability: 'complete' as const });
  }
  getStorageOverview() {
    return Promise.resolve({ generatedAt: '', volumes: [] });
  }
  listCalendarEvents() {
    return Promise.resolve([]);
  }
  getArrLibrary() {
    return Promise.resolve({ ok: true, series: {}, movies: {} });
  }
  listLibraryItems() {
    return Promise.resolve({ items: [], availability: 'complete' as const });
  }
  getAutomationSummary() {
    return Promise.resolve({ generatedAt: '', services: [], preview: [], problems: [], availability: { services: 'empty' as const, preview: 'empty' as const, problems: 'empty' as const } });
  }
  listHermesRecommendations() {
    this.hermesCalls++;
    if (this.hermesGate) {
      const gate = this.hermesGate;
      this.hermesGate = null;
      return gate;
    }
    return Promise.resolve({
      ...this.hermes,
      items: this.hermes.items.map((item) => ({ ...item })),
      pending_request_sync: this.hermes.pending_request_sync?.map((entry) => ({ ...entry })),
    });
  }
  submitHermesFeedback(id: string, feedback: DiscoverFeedback) {
    this.feedbackCalls.push({ id, feedback });
    return this.feedbackGate ?? Promise.resolve({ ok: true, message: 'Feedback saved.' });
  }
  requestHermesMore() {
    this.moreCalls++;
    if (!this.skipGenerationOnMore && (this.moreResult.queued || this.moreResult.already_pending)) {
      this.hermes.generation_request = { requested_at: '2026-07-12T00:00:00Z', status: 'pending' };
    }
    return Promise.resolve(this.moreResult);
  }
  listJellyseerrDiscover(kind: JellyseerrDiscoverKind) {
    this.jellyseerrCalls.push(kind);
    if (this.jellyseerrGate) {
      const gate = this.jellyseerrGate;
      this.jellyseerrGate = null;
      return gate;
    }
    return Promise.resolve({ ok: true, items: this.jellyseerr[kind].map((item) => ({ ...item })) });
  }
  listTraktDiscover(type: TraktDiscoverType) {
    this.traktCalls.push(type);
    return Promise.resolve({ ok: true, items: this.trakt[type].map((item) => ({ ...item })) });
  }
  requestMedia(payload: DiscoverRequestPayload) {
    this.requestCalls.push(payload);
    if (this.requestGate) {
      const gate = this.requestGate;
      this.requestGate = null;
      return gate;
    }
    return Promise.resolve(this.requestResult);
  }
  listCronLogs() {
    return Promise.resolve({ ok: true, runs: [] });
  }
}
