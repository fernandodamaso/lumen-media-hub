import { mediaStackLibraryMutationStub } from '../../testing/media-stack-library-stub';
import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { DiscoverAction, DiscoverFeedback, DiscoverItem, DiscoverRequestPayload, ExternalDiscoverAvailability, ExternalDiscoverItem, AiPicksDiscover, JellyseerrDiscoverKind, SubmitAiPickFeedbackOptions, TraktDiscoverType } from './discover.models';
import { MEDIA_STACK_API, MediaStackApi } from '../media-stack/media-stack-api';
import { DiscoverFacade, SCHEDULED_REFRESH_TIMEOUT_MS } from './discover.facade';

type ExclusionFixture = { status: 'fresh' | 'stale' | 'unavailable'; last_successful_refresh_at: string | null };

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

  it('loads AI Picks by default and isolates visible content across tabs', async () => {
    await facade.setTab('ai-picks');
    expect(facade.tab()).toBe('ai-picks');
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Signal Drift']);
    expect(api.aiPicksCalls).toBe(1);

    void facade.setTab('jellyseerr');
    await Promise.resolve();
    await flush();
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Trending Ember']);
    expect(api.jellyseerrCalls).toEqual(['trending']);

    facade.setJellyseerrKind('movies');
    await flush();
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Neon Archive']);
    expect(api.jellyseerrCalls).toEqual(['trending', 'movies']);

    void facade.setTab('trakt');
    await flush();
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Trakt Horizon']);
    expect(api.traktCalls).toEqual(['movies']);

    await facade.setTab('ai-picks');
    await flush();
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Signal Drift']);
  });

  it('renders an explicit disabled Jellyseerr capability as unavailable without an error', async () => {
    api.jellyseerrAvailability = 'disabled';

    await facade.setTab('jellyseerr');

    expect(facade.status()).toBe('disabled');
    expect(facade.error()).toBe('');
    expect(facade.notice()).toBe('');
    expect(facade.visibleItems()).toEqual([]);
  });

  it('warns when Jellyseerr watched filtering is stale or unavailable and clears on fresh recovery', async () => {
    api.jellyseerrWatchedExclusion = { status: 'stale', last_successful_refresh_at: '2026-08-11T12:00:00Z' };
    await facade.setTab('jellyseerr');
    expect(facade.notice()).toContain('Jellyseerr');
    expect(facade.notice()).toContain('cached snapshot');

    api.jellyseerrWatchedExclusion = { status: 'unavailable', last_successful_refresh_at: null };
    await facade.setTab('jellyseerr');
    expect(facade.notice()).toContain('Watched filtering is unavailable');
    expect(facade.notice()).toContain('Jellyseerr');

    api.jellyseerrWatchedExclusion = { status: 'fresh', last_successful_refresh_at: '2026-08-11T12:15:00Z' };
    await facade.setTab('jellyseerr');
    expect(facade.notice()).toBe('');
  });

  it('warns and recovers library filtering independently for AI Picks, Jellyseerr, and Trakt', async () => {
    api.aiPicks.library_exclusion = { status: 'stale', last_successful_refresh_at: '2026-08-11T12:00:00Z' };
    await facade.setTab('ai-picks');
    expect(facade.notice()).toContain('Library filtering');
    api.aiPicks.library_exclusion = { status: 'fresh', last_successful_refresh_at: '2026-08-11T12:01:00Z' };
    await facade.setTab('ai-picks');
    expect(facade.notice()).toBe('');

    api.jellyseerrLibraryExclusion = { status: 'unavailable', last_successful_refresh_at: null };
    await facade.setTab('jellyseerr');
    expect(facade.notice()).toContain('Library filtering is unavailable');
    api.jellyseerrLibraryExclusion = { status: 'fresh', last_successful_refresh_at: '2026-08-11T12:02:00Z' };
    await facade.setTab('jellyseerr');
    expect(facade.notice()).toBe('');

    api.traktLibraryExclusion = { status: 'stale', last_successful_refresh_at: '2026-08-11T12:03:00Z' };
    await facade.setTab('trakt');
    expect(facade.notice()).toContain('Library filtering is using a cached snapshot');
    api.traktLibraryExclusion = { status: 'fresh', last_successful_refresh_at: '2026-08-11T12:04:00Z' };
    await facade.setTab('trakt');
    expect(facade.notice()).toBe('');
  });

  it('keeps watched and library warnings visible together and recovers each independently', async () => {
    api.traktWatchedExclusion = { status: 'stale', last_successful_refresh_at: '2026-08-11T12:00:00Z' };
    api.traktLibraryExclusion = { status: 'unavailable', last_successful_refresh_at: null };
    await facade.setTab('trakt');
    expect(facade.notice()).toContain('Watched filtering');
    expect(facade.notice()).toContain('Library filtering');

    api.traktWatchedExclusion = { status: 'fresh', last_successful_refresh_at: '2026-08-11T12:01:00Z' };
    await facade.setTab('trakt');
    expect(facade.notice()).not.toContain('Watched filtering');
    expect(facade.notice()).toContain('Library filtering');
    api.traktLibraryExclusion = { status: 'fresh', last_successful_refresh_at: '2026-08-11T12:02:00Z' };
    await facade.setTab('trakt');
    expect(facade.notice()).toBe('');
  });

  it('does not let a late Jellyseerr library state overwrite the active Trakt warning', async () => {
    const deferred = Promise.withResolvers<{
      ok: boolean;
      items: ExternalDiscoverItem[];
      availability: ExternalDiscoverAvailability;
      library_exclusion: { status: 'stale' | 'unavailable'; last_successful_refresh_at: string | null };
      watched_exclusion: { status: 'fresh'; last_successful_refresh_at: string | null };
    }>();
    api.jellyseerrGate = deferred.promise;
    const jellyseerrLoad = facade.setTab('jellyseerr');
    await facade.setTab('trakt');
    api.traktLibraryExclusion = { status: 'unavailable', last_successful_refresh_at: null };
    await facade.setTab('trakt');
    expect(facade.notice()).toContain('Trakt');

    deferred.resolve({
      ok: true,
      items: api.jellyseerr.trending,
      availability: 'available',
      library_exclusion: { status: 'stale', last_successful_refresh_at: '2026-08-11T12:00:00Z' },
      watched_exclusion: { status: 'fresh', last_successful_refresh_at: null },
    });
    await jellyseerrLoad;
    expect(facade.tab()).toBe('trakt');
    expect(facade.notice()).toContain('Trakt');
    expect(facade.notice()).not.toContain('Jellyseerr');
  });

  it('keeps Trakt cards and warns when watched filtering is unavailable', async () => {
    api.traktWatchedExclusion = { status: 'unavailable', last_successful_refresh_at: null };

    await facade.setTab('trakt');

    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Trakt Horizon']);
    expect(facade.notice()).toContain('Watched filtering is unavailable');
  });

  it('shows a stale watched warning and clears it after a fresh refresh', async () => {
    api.traktWatchedExclusion = {
      status: 'stale',
      last_successful_refresh_at: '2026-08-11T12:00:00+00:00',
    };
    await facade.setTab('trakt');
    expect(facade.notice()).toContain('cached snapshot');

    api.traktWatchedExclusion = { status: 'fresh', last_successful_refresh_at: '2026-08-11T12:15:00+00:00' };
    await facade.setTab('trakt');
    expect(facade.notice()).toBe('');
  });

  it('shows a stale watched warning for AI Picks and clears it after fresh recovery', async () => {
    api.aiPicks.watched_exclusion = {
      status: 'stale',
      last_successful_refresh_at: '2026-08-11T12:00:00+00:00',
    };
    await facade.setTab('ai-picks');

    expect(facade.visibleItems()).toHaveLength(1);
    expect(facade.notice()).toContain('cached snapshot');

    api.aiPicks.watched_exclusion = { status: 'fresh', last_successful_refresh_at: '2026-08-11T12:15:00+00:00' };
    await facade.setTab('ai-picks');
    expect(facade.visibleItems()).toHaveLength(1);
    expect(facade.notice()).toBe('');
  });

  it('shows an unavailable watched warning for AI Picks while preserving cards', async () => {
    api.aiPicks.watched_exclusion = { status: 'unavailable', last_successful_refresh_at: null };
    await facade.setTab('ai-picks');

    expect(facade.visibleItems()).toHaveLength(1);
    expect(facade.notice()).toBe('Watched filtering is unavailable. Showing AI Picks recommendations.');
  });

  it('renders the local Trakt reconnect instruction only for the safe backend code', async () => {
    api.traktError = { message: 'Trakt reconnect required', code: 'reconnect_required' };
    await facade.setTab('trakt');
    expect(facade.notice()).toBe('Trakt reconnect required. Run .\\install.ps1 -Mode connect-trakt.');

    api.traktError = { message: 'Trakt request failed' };
    await facade.setTab('trakt');
    expect(facade.notice()).not.toContain('connect-trakt');
  });

  it('uses safe copy for AI Picks browse failures and does not expose backend text', async () => {
    api.aiPicks = { ok: false, items: [], error: '<script>backend-secret</script>' };

    await facade.setTab('ai-picks');

    expect(facade.status()).toBe('error');
    expect(facade.error()).toBe('Discover is temporarily unavailable. Try again.');
    expect(facade.notice()).toBe('');
    expect(facade.notice()).not.toContain('backend-secret');
  });

  it('does not show a Trakt reconnect command for Jellyseerr errors', async () => {
    api.jellyseerrError = { message: 'internal reconnect', code: 'reconnect_required' };

    await facade.setTab('jellyseerr');

    expect(facade.error()).toBe('Discover is temporarily unavailable. Try again.');
    expect(facade.notice()).toBe('');
    expect(facade.notice()).not.toContain('connect-trakt');
  });

  it('uses safe load-error copy for arbitrary Trakt backend error text', async () => {
    await facade.setTab('trakt');
    api.traktError = { message: '<img src=x onerror=alert(1)>' };

    await facade.setTab('trakt');

    expect(facade.notice()).toBe('Could not refresh. Showing last loaded results.');
    expect(facade.notice()).not.toContain('onerror');
  });

  it('preserves disabled Jellyseerr availability while a tab refresh is pending', async () => {
    api.jellyseerrAvailability = 'disabled';
    await facade.setTab('jellyseerr');
    await facade.setTab('trakt');

    const { promise, resolve } = Promise.withResolvers<{
      ok: boolean;
      items: ExternalDiscoverItem[];
      availability: ExternalDiscoverAvailability;
    }>();
    api.jellyseerrGate = promise;
    const pending = facade.setTab('jellyseerr');
    await Promise.resolve();

    expect(facade.status()).toBe('disabled');
    resolve({ ok: true, items: [], availability: 'disabled' });
    await pending;
    expect(facade.status()).toBe('disabled');
  });

  it('does not let a stale disabled Jellyseerr response overwrite the cache', async () => {
    await facade.setTab('jellyseerr');
    const { promise, resolve } = Promise.withResolvers<{
      ok: boolean;
      items: ExternalDiscoverItem[];
      availability: ExternalDiscoverAvailability;
    }>();
    api.jellyseerrGate = promise;
    const stale = facade.setTab('jellyseerr');
    await facade.setTab('trakt');

    resolve({ ok: true, items: [], availability: 'disabled' });
    await stale;

    api.jellyseerrAvailability = 'available';
    const { promise: current, resolve: releaseCurrent } = Promise.withResolvers<{
      ok: boolean;
      items: ExternalDiscoverItem[];
      availability: ExternalDiscoverAvailability;
    }>();
    api.jellyseerrGate = current;
    const active = facade.setTab('jellyseerr');
    await Promise.resolve();
    expect(facade.status()).toBe('ready');

    releaseCurrent({ ok: true, items: api.jellyseerr.trending, availability: 'available' });
    await active;
  });

  it('submitFeedback calls only submitAiPickFeedback and refreshes AI Picks', async () => {
    await facade.setTab('ai-picks');
    await facade.submitFeedback('ai-eligible', 'liked');
    expect(api.feedbackCalls).toEqual([{ id: 'ai-eligible', feedback: 'liked', options: undefined }]);
    expect(api.requestCalls).toEqual([]);
    expect(facade.notice()).toContain('Feedback');
  });

  it('stores pending Trakt sync after watched feedback and updates on refresh', async () => {
    await facade.setTab('ai-picks');
    await facade.submitFeedback('ai-eligible', 'watched', { confirmAllAired: true });
    expect(api.feedbackCalls[0]).toEqual({
      id: 'ai-eligible',
      feedback: 'watched',
      options: { confirmAllAired: true },
    });
    api.aiPicks.items = api.aiPicks.items.map((item) =>
      item.id === 'ai-eligible'
        ? { ...item, active: false, feedback: 'watched', trakt_history_sync: { status: 'synced' } }
        : item,
    );
    facade.setAiPicksView('history');
    await facade.setTab('ai-picks');
    const card = facade.visibleItems().find((item) => item.id === 'ai-eligible');
    expect(card?.traktHistorySync?.status).toBe('synced');
  });

  it('ignores stale AI Picks poll responses that predate feedback', async () => {
    await facade.setTab('ai-picks');
    expect(facade.visibleItems().some((item) => item.id === 'ai-eligible')).toBe(true);

    let resolveStale!: (value: AiPicksDiscover) => void;
    api.aiPicksGate = new Promise((resolve) => {
      resolveStale = resolve;
    });

    const poll = facade.setTab('ai-picks');

    api.aiPicks.items = api.aiPicks.items.map((item) =>
      item.id === 'ai-eligible'
        ? { ...item, active: false, feedback: 'liked' as const, feedback_at: '2026-07-27T00:00:00Z' }
        : item,
    );
    await facade.submitFeedback('ai-eligible', 'liked');
    expect(facade.visibleItems().some((item) => item.id === 'ai-eligible')).toBe(false);

    resolveStale({
      ok: true,
      items: api.aiPicks.items.map((item) =>
        item.id === 'ai-eligible' ? { ...item, active: true, feedback: null } : item,
      ),
    });
    await poll;

    expect(facade.visibleItems().some((item) => item.id === 'ai-eligible')).toBe(false);
  });

  it('removes liked titles from Active even when the API still reports active', async () => {
    await facade.setTab('ai-picks');
    expect(facade.visibleItems().some((item) => item.id === 'ai-eligible')).toBe(true);

    api.aiPicks.items = api.aiPicks.items.map((item) =>
      item.id === 'ai-eligible'
        ? { ...item, active: true, feedback: 'liked' as const, feedback_at: '2026-07-27T00:00:00Z' }
        : item,
    );
    await facade.submitFeedback('ai-eligible', 'liked');

    expect(facade.visibleItems().some((item) => item.id === 'ai-eligible')).toBe(false);
    facade.setAiPicksView('history');
    facade.setHistoryFilter('watched');
    expect(facade.visibleItems().some((item) => item.id === 'ai-eligible')).toBe(true);
  });

  it('moves an excluded AI Picks item from Active to History without removing it', async () => {
    api.aiPicks.items = [
      {
        ...api.aiPicks.items[0],
        title: 'The Bear',
        active: true,
        in_library: true,
        excluded_reason: 'in_library',
      },
    ];

    await facade.setTab('ai-picks');
    expect(facade.visibleItems()).toEqual([]);

    facade.setAiPicksView('history');
    expect(facade.visibleItems()).toMatchObject([
      { title: 'The Bear', inLibrary: true, excludedReason: 'in_library' },
    ]);
  });

  it('moves a projected Trakt-watched AI Picks item from Active to Watched History', async () => {
    api.aiPicks.items = [
      {
        ...api.aiPicks.items[0],
        active: true,
        excluded_reason: 'watched_on_trakt',
        watched_on_trakt: true,
      },
    ];

    await facade.setTab('ai-picks');
    expect(facade.visibleItems()).toEqual([]);

    facade.setAiPicksView('history');
    facade.setHistoryFilter('watched');
    expect(facade.visibleItems()).toMatchObject([
      { title: 'Signal Drift', watchedOnTrakt: true, excludedReason: 'watched_on_trakt' },
    ]);
  });

  it('prevents duplicate busy mutations', async () => {
    await facade.setTab('ai-picks');
    const { promise: feedbackGate, resolve: resolveFeedback } = Promise.withResolvers<DiscoverAction>();
    const release = () => { resolveFeedback({ ok: true, message: 'Feedback saved.' }); };
    api.feedbackGate = feedbackGate;
    const first = facade.submitFeedback('ai-eligible', 'liked');
    await facade.submitFeedback('ai-eligible', 'disliked');
    expect(api.feedbackCalls).toHaveLength(1);
    release();
    await first;
  });

  it('requestMore reports queued then blocks duplicates while pending', async () => {
    await facade.setTab('ai-picks');
    api.moreResult = { ok: true, queued: true, message: 'More recommendations queued.' };
    await facade.requestMore();
    expect(facade.generationPending()).toBe(true);
    expect(facade.notice()).toContain('queued');

    api.moreResult = { ok: true, already_pending: true, message: 'A recommendation refresh is already pending.' };
    await facade.requestMore();
    expect(api.moreCalls).toBe(1);
  });

  it('disables generation without clearing existing picks', async () => {
    api.aiPicks.generation_enabled = false;
    await facade.setTab('ai-picks');

    expect(facade.generationEnabled()).toBe(false);
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Signal Drift']);
    await facade.requestMore();
    expect(api.moreCalls).toBe(0);
  });

  it('shows a safe failed generation state while retaining cards', async () => {
    api.aiPicks.generation = {
      id: 'job-failed',
      status: 'failed',
      trigger: 'on_demand',
      requested_at: '2026-08-29T10:00:00Z',
      started_at: '2026-08-29T10:00:01Z',
      finished_at: '2026-08-29T10:01:01Z',
      desired_count: 10,
      attempt: 1,
      error_code: 'model_timeout',
      counts: null,
    };

    await facade.setTab('ai-picks');

    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Signal Drift']);
    expect(facade.generationPending()).toBe(false);
    expect(facade.notice()).toBe(
      'AI generation failed (model_timeout). Existing picks are unchanged.',
    );
  });

  it('clears a failed generation warning after a later generation succeeds', async () => {
    api.aiPicks.generation = {
      id: 'job-failed',
      status: 'failed',
      trigger: 'on_demand',
      requested_at: '2026-08-29T10:00:00Z',
      started_at: '2026-08-29T10:00:01Z',
      finished_at: '2026-08-29T10:01:01Z',
      desired_count: 10,
      attempt: 1,
      error_code: 'model_timeout',
      counts: null,
    };
    await facade.setTab('ai-picks');
    expect(facade.notice()).toContain('AI generation failed');

    api.aiPicks.generation = {
      ...api.aiPicks.generation,
      id: 'job-succeeded',
      status: 'succeeded',
      finished_at: '2026-08-29T10:02:00Z',
      error_code: null,
      counts: { accepted: 10, retained: 0, rotated: 10, rejected: 0 },
    };
    await facade.setTab('ai-picks');

    expect(facade.notice()).toBe('');
  });

  it('surfaces already_pending when the adapter reports it on first call', async () => {
    await facade.setTab('ai-picks');
    api.moreResult = { ok: true, already_pending: true, message: 'A recommendation refresh is already pending.' };
    await facade.requestMore();
    expect(facade.generationPending()).toBe(true);
    expect(facade.noticeTone()).toBe('info');
    expect(facade.notice()).toContain('already pending');
  });

  it('recomputes ready/empty when switching AI Picks view after active becomes empty', async () => {
    api.aiPicks.items = [
      {
        id: 'ai-eligible',
        source: 'ai',
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
        id: 'ai-history-liked',
        source: 'ai',
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
    await facade.setTab('ai-picks');
    expect(facade.status()).toBe('ready');

    api.aiPicks.items = api.aiPicks.items.map((item) =>
      item.id === 'ai-eligible'
        ? { ...item, active: false, feedback: 'skipped' as const, feedback_at: '2026-07-12T00:00:00Z' }
        : item,
    );
    await facade.setTab('ai-picks');
    expect(facade.status()).toBe('empty');
    expect(facade.visibleItems()).toEqual([]);

    facade.setAiPicksView('history');
    expect(facade.status()).toBe('ready');
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Signal Drift', 'Copper Skies']);
  });

  it('uses the active feed lifecycle instead of projecting AI Picks request state', async () => {
    api.aiPicks.items = [
      {
        ...api.aiPicks.items[0],
        request_state: 'requested',
        media_status: 'requested',
        service: null,
        service_href: null,
        request_id: 9001,
        monitored: null,
        requested_at: '2026-07-09T09:00:00Z',
        jellyseerr_request_id: 9001,
      },
    ];
    api.jellyseerr.trending = [{
      type: 'movie',
      title: 'Same Title',
      tmdb_id: 101001,
      media_status: 'missing',
      service: null,
      service_href: null,
      request_id: null,
      monitored: null,
    }];
    await facade.setTab('ai-picks');
    await facade.setTab('jellyseerr');
    await flush();
    expect(facade.visibleItems()[0]).toMatchObject({
      mediaStatus: 'missing',
      requestState: null,
    });
  });

  it('refreshes the active source and filter after request completion', async () => {
    await facade.setTab('jellyseerr');
    facade.setJellyseerrKind('tv');
    await flush();
    expect(api.jellyseerrCalls).toEqual(['trending', 'tv']);

    await facade.refreshActiveFeed();

    expect(api.jellyseerrCalls).toEqual(['trending', 'tv', 'tv']);
    expect(api.aiPicksCalls).toBe(0);
  });

  it('honors pending_request_sync as sync-failed across identities', async () => {
    api.aiPicks = {
      ok: true,
      items: [
        {
          id: 'ai-sync',
          source: 'ai',
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
      pending_request_sync: [{ id: 'ai-sync', jellyseerr_request_id: 55 }],
    };
    api.jellyseerr.trending = [{ type: 'tv', title: 'Night Courier External', tmdb_id: 101005 }];
    await facade.setTab('ai-picks');
    expect(facade.isSyncFailed('ai-sync')).toBe(true);
    expect(facade.isSyncFailed(facade.visibleItems()[0])).toBe(true);

    await facade.setTab('jellyseerr');
    await flush();
    expect(facade.isSyncFailed(facade.visibleItems()[0])).toBe(true);
  });

  it('ignores stale AI Picks failures after switching tabs', async () => {
    const { promise: aiPicksGate, resolve: releaseAiPicks } = Promise.withResolvers<AiPicksDiscover>();
    api.aiPicksGate = aiPicksGate;
    const pending = facade.setTab('ai-picks');
    await facade.setTab('jellyseerr');
    await flush();
    expect(facade.status()).toBe('ready');
    releaseAiPicks({ ok: false, items: [], error: 'AI Picks offline' });
    await pending;
    expect(facade.tab()).toBe('jellyseerr');
    expect(facade.status()).toBe('ready');
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Trending Ember']);
  });

  it('does not let a late AI Picks success clear the active Trakt watched warning', async () => {
    const { promise: aiPicksGate, resolve: releaseAiPicks } = Promise.withResolvers<AiPicksDiscover>();
    api.aiPicksGate = aiPicksGate;
    const pending = facade.setTab('ai-picks');
    await Promise.resolve();

    api.traktWatchedExclusion = { status: 'unavailable', last_successful_refresh_at: null };
    await facade.setTab('trakt');
    expect(facade.notice()).toBe('Watched filtering is unavailable. Showing Trakt recommendations.');

    releaseAiPicks({
      ...api.aiPicks,
      watched_exclusion: { status: 'fresh', last_successful_refresh_at: null },
    });
    await pending;

    expect(facade.tab()).toBe('trakt');
    expect(facade.notice()).toBe('Watched filtering is unavailable. Showing Trakt recommendations.');
  });

  it('ignores stale Jellyseerr failures after switching to Trakt', async () => {
    const { promise: jellyseerrGate, resolve: releaseJellyseerr } = Promise.withResolvers<{
      ok: boolean;
      items: ExternalDiscoverItem[];
      error?: string;
    }>();
    api.jellyseerrGate = jellyseerrGate;
    const pending = facade.setTab('jellyseerr');
    await facade.setTab('trakt');
    await flush();
    expect(facade.tab()).toBe('trakt');
    expect(facade.status()).toBe('ready');
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Trakt Horizon']);

    releaseJellyseerr({ ok: false, items: [], error: 'Jellyseerr offline' });
    await pending;
    expect(facade.tab()).toBe('trakt');
    expect(facade.status()).toBe('ready');
    expect(facade.error()).toBe('');
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Trakt Horizon']);
  });

  it('ignores a superseded AI Picks response for the same filter', async () => {
    await facade.setTab('ai-picks');
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Signal Drift']);

    const { promise: firstGate, resolve: releaseFirst } = Promise.withResolvers<AiPicksDiscover>();
    api.aiPicksGate = firstGate;
    const first = facade.setTab('ai-picks');
    await Promise.resolve();

    api.aiPicks = {
      ok: true,
      items: [
        {
          ...api.aiPicks.items[0],
          title: 'Newer AI Picks',
        },
      ],
    };
    const second = facade.setTab('ai-picks');
    await second;
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Newer AI Picks']);

    releaseFirst({
      ok: true,
      items: [{ ...api.aiPicks.items[0], title: 'Stale AI Picks' }],
    });
    await first;
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Newer AI Picks']);
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

  it('does not commit an older same-kind Jellyseerr success while a newer request is pending', async () => {
    const first = Promise.withResolvers<{
      ok: boolean;
      items: ExternalDiscoverItem[];
      availability?: ExternalDiscoverAvailability;
      watched_exclusion?: ExclusionFixture;
    }>();
    api.jellyseerrGate = first.promise;
    const firstLoad = facade.setTab('jellyseerr');
    await Promise.resolve();

    const second = Promise.withResolvers<{
      ok: boolean;
      items: ExternalDiscoverItem[];
      availability?: ExternalDiscoverAvailability;
      watched_exclusion?: ExclusionFixture;
    }>();
    api.jellyseerrGate = second.promise;
    const secondLoad = facade.setTab('jellyseerr');
    await Promise.resolve();

    first.resolve({
      ok: true,
      items: [{ type: 'movie', title: 'Older Jellyseerr', tmdb_id: 91 }],
      watched_exclusion: { status: 'stale', last_successful_refresh_at: '2026-08-11T12:00:00Z' },
    });
    await firstLoad;
    expect(facade.visibleItems()).toEqual([]);
    expect(facade.notice()).not.toContain('cached snapshot');

    second.resolve({
      ok: true,
      items: [{ type: 'movie', title: 'Newer Jellyseerr', tmdb_id: 92 }],
      watched_exclusion: { status: 'fresh', last_successful_refresh_at: null },
    });
    await secondLoad;
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Newer Jellyseerr']);
  });

  it('does not commit an older same-type Trakt success while a newer request is pending', async () => {
    const first = Promise.withResolvers<{
      ok: boolean;
      items: ExternalDiscoverItem[];
      library_exclusion?: ExclusionFixture;
      watched_exclusion?: ExclusionFixture;
    }>();
    api.traktGate = first.promise;
    const firstLoad = facade.setTab('trakt');
    await Promise.resolve();

    const second = Promise.withResolvers<{
      ok: boolean;
      items: ExternalDiscoverItem[];
      library_exclusion?: ExclusionFixture;
      watched_exclusion?: ExclusionFixture;
    }>();
    api.traktGate = second.promise;
    const secondLoad = facade.setTab('trakt');
    await Promise.resolve();

    first.resolve({
      ok: true,
      items: [{ type: 'movie', title: 'Older Trakt', tmdb_id: 81 }],
      library_exclusion: { status: 'stale', last_successful_refresh_at: '2026-08-11T12:00:00Z' },
      watched_exclusion: { status: 'fresh', last_successful_refresh_at: null },
    });
    await firstLoad;
    expect(facade.visibleItems()).toEqual([]);
    expect(facade.notice()).not.toContain('cached snapshot');

    second.resolve({
      ok: true,
      items: [{ type: 'movie', title: 'Newer Trakt', tmdb_id: 82 }],
      library_exclusion: { status: 'fresh', last_successful_refresh_at: null },
      watched_exclusion: { status: 'fresh', last_successful_refresh_at: null },
    });
    await secondLoad;
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Newer Trakt']);
  });

  it('retains last-good AI Picks results when a background refresh fails', async () => {
    await facade.setTab('ai-picks');
    expect(facade.status()).toBe('ready');
    expect(facade.visibleItems()).toHaveLength(1);

    api.aiPicks = { ok: false, items: [], error: 'AI Picks offline' };
    await facade.setTab('ai-picks');
    expect(facade.status()).toBe('ready');
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Signal Drift']);
    expect(facade.noticeTone()).toBe('warning');
    expect(facade.notice()).toBe('Could not refresh. Showing last loaded results.');
  });

  it('retains an empty AI Picks last-good state when a later refresh fails', async () => {
    api.aiPicks = { ok: true, items: [] };
    await facade.setTab('ai-picks');
    expect(facade.status()).toBe('empty');
    expect(facade.visibleItems()).toEqual([]);

    api.aiPicks = { ok: false, items: [], error: 'AI Picks offline' };
    await facade.setTab('ai-picks');
    expect(facade.status()).toBe('empty');
    expect(facade.error()).toBe('');
    expect(facade.noticeTone()).toBe('warning');
    expect(facade.notice()).toBe('Could not refresh. Showing last loaded results.');
  });

  it('hard-errors on the initial AI Picks load failure', async () => {
    api.aiPicks = { ok: false, items: [], error: 'AI Picks offline' };
    await facade.setTab('ai-picks');
    expect(facade.status()).toBe('error');
    expect(facade.error()).toBe('Discover is temporarily unavailable. Try again.');
    expect(facade.visibleItems()).toEqual([]);
  });

  it('ignores a superseded AI Picks success after a newer failure', async () => {
    const { promise: firstGate, resolve: releaseFirst } = Promise.withResolvers<AiPicksDiscover>();
    api.aiPicksGate = firstGate;
    const first = facade.setTab('ai-picks');
    await Promise.resolve();

    api.aiPicks = { ok: false, items: [], error: 'AI Picks offline' };
    await facade.setTab('ai-picks');
    expect(facade.status()).toBe('error');

    releaseFirst({
      ok: true,
      items: [
        {
          id: 'ai-eligible',
          source: 'ai',
          type: 'movie',
          title: 'Recovered Title',
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
      ],
    });
    await first;
    expect(facade.status()).toBe('error');
    expect(facade.visibleItems()).toEqual([]);
    expect(facade.error()).toBe('Discover is temporarily unavailable. Try again.');
  });

  it('does not cache an inactive Jellyseerr response after navigating away and back', async () => {
    const { promise, resolve } = Promise.withResolvers<{
      ok: boolean;
      items: ExternalDiscoverItem[];
      availability?: ExternalDiscoverAvailability;
      library_exclusion?: ExclusionFixture;
      watched_exclusion?: ExclusionFixture;
    }>();
    api.jellyseerrGate = promise;
    const pending = facade.setTab('jellyseerr');
    await Promise.resolve();

    await facade.setTab('ai-picks');
    resolve({
      ok: true,
      items: [{ type: 'movie', title: 'Stale Jellyseerr', tmdb_id: 991 }],
      library_exclusion: { status: 'fresh', last_successful_refresh_at: null },
      watched_exclusion: { status: 'fresh', last_successful_refresh_at: null },
    });
    await pending;

    const { promise: current, resolve: releaseCurrent } = Promise.withResolvers<{
      ok: boolean;
      items: ExternalDiscoverItem[];
      availability?: ExternalDiscoverAvailability;
      library_exclusion?: ExclusionFixture;
      watched_exclusion?: ExclusionFixture;
    }>();
    api.jellyseerrGate = current;
    const returned = facade.setTab('jellyseerr');
    await Promise.resolve();
    expect(facade.visibleItems()).toEqual([]);
    releaseCurrent({
      ok: true,
      items: [{ type: 'movie', title: 'Fresh Jellyseerr', tmdb_id: 992 }],
      library_exclusion: { status: 'fresh', last_successful_refresh_at: null },
      watched_exclusion: { status: 'fresh', last_successful_refresh_at: null },
    });
    await returned;
  });

  it('skips overlapping scheduled polls while a refresh is in flight', async () => {
    vi.useFakeTimers();
    await facade.setTab('ai-picks');
    expect(api.aiPicksCalls).toBe(1);

    const { promise: aiPicksGate, resolve: releaseAiPicks } = Promise.withResolvers<AiPicksDiscover>();
    api.aiPicksGate = aiPicksGate;
    await vi.advanceTimersByTimeAsync(30_000);
    expect(api.aiPicksCalls).toBe(2);

    await vi.advanceTimersByTimeAsync(29_000);
    expect(api.aiPicksCalls).toBe(2);

    await vi.advanceTimersByTimeAsync(1_000);
    expect(api.aiPicksCalls).toBe(2);

    releaseAiPicks({
      ok: true,
      items: api.aiPicks.items.map((item) => ({ ...item })),
    });
    await flush();
    await vi.advanceTimersByTimeAsync(30_000);
    expect(api.aiPicksCalls).toBe(3);
    vi.useRealTimers();
  });

  it('uses the authoritative generation state after request-more', async () => {
    await facade.setTab('ai-picks');
    api.moreResult = { ok: true, queued: true, message: 'More recommendations queued.' };
    api.skipGenerationOnMore = true;
    await facade.requestMore();
    expect(facade.generationPending()).toBe(false);
    await facade.requestMore();
    expect(api.moreCalls).toBe(2);
  });

  it('recovers scheduled polling after a hung AI Picks refresh times out', async () => {
    vi.useFakeTimers();
    await facade.setTab('ai-picks');
    expect(facade.status()).toBe('ready');

    const { promise: aiPicksDeferred, resolve: releaseAiPicks } = Promise.withResolvers<AiPicksDiscover>();
    api.aiPicksDeferred = aiPicksDeferred;
    await vi.advanceTimersByTimeAsync(30_000);
    expect(api.aiPicksCalls).toBe(2);

    await vi.advanceTimersByTimeAsync(SCHEDULED_REFRESH_TIMEOUT_MS);
    expect(facade.status()).toBe('ready');
    expect(facade.notice()).toContain('Could not refresh');

    releaseAiPicks({
      ok: true,
      items: api.aiPicks.items.map((item) => ({ ...item })),
    });
    api.aiPicksDeferred = null;
    await flush();

    await vi.advanceTimersByTimeAsync(30_000);
    expect(api.aiPicksCalls).toBe(3);

    TestBed.resetTestingModule();
    vi.useRealTimers();
  });

  it('aborts the active AI Picks signal when a scheduled refresh times out', async () => {
    vi.useFakeTimers();
    await facade.setTab('ai-picks');

    const { promise: aiPicksDeferred } = Promise.withResolvers<AiPicksDiscover>();
    api.aiPicksDeferred = aiPicksDeferred;
    await vi.advanceTimersByTimeAsync(30_000);
    expect(api.aiPicksCalls).toBe(2);
    expect(api.lastAiPicksSignal?.aborted).toBe(false);

    await vi.advanceTimersByTimeAsync(SCHEDULED_REFRESH_TIMEOUT_MS);
    expect(api.lastAiPicksSignal?.aborted).toBe(true);

    TestBed.resetTestingModule();
    vi.useRealTimers();
  });

  it('shows cached external feeds immediately when returning to a filter', async () => {
    await facade.setTab('jellyseerr');
    await flush();
    expect(facade.status()).toBe('ready');

    await facade.setTab('ai-picks');
    await flush();
    api.aiPicks = { ok: true, items: [] };
    await facade.setTab('ai-picks');
    expect(facade.status()).toBe('empty');

    const { promise: jellyseerrGate, resolve: resolveJellyseerr } = Promise.withResolvers<{
      ok: boolean;
      items: ExternalDiscoverItem[];
    }>();
    const release = () => { resolveJellyseerr({ ok: true, items: api.jellyseerr.trending }); };
    api.jellyseerrGate = jellyseerrGate;
    void facade.setTab('jellyseerr');
    await Promise.resolve();
    expect(facade.status()).toBe('ready');
    expect(facade.visibleItems().map((item) => item.title)).toEqual(['Trending Ember']);
    release();
    await flush();
  });

  it('polls only while started and stops on destroy', async () => {
    vi.useFakeTimers();
    await facade.setTab('ai-picks');
    await vi.advanceTimersByTimeAsync(0);
    expect(api.aiPicksCalls).toBe(1);
    await vi.advanceTimersByTimeAsync(30_000);
    expect(api.aiPicksCalls).toBe(2);
    TestBed.resetTestingModule();
    await vi.advanceTimersByTimeAsync(30_000);
    expect(api.aiPicksCalls).toBe(2);
    vi.useRealTimers();
  });
});

async function flush(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

class MockApi implements MediaStackApi {
  searchMedia: MediaStackApi['searchMedia'] = () => Promise.resolve({ ok: true, availability: 'available', sources: { jellyseerr: 'fresh' }, items: [] });
  getTvSeasons: MediaStackApi['getTvSeasons'] = (tmdbId) => Promise.resolve({ tmdbId, title: 'Fixture', seasons: [] });
  setLibraryItemPlayed = mediaStackLibraryMutationStub.setLibraryItemPlayed;
  previewLibraryItemDeletion = mediaStackLibraryMutationStub.previewLibraryItemDeletion;
  deleteLibraryItem = mediaStackLibraryMutationStub.deleteLibraryItem;
  deleteLibraryItemDirectly = mediaStackLibraryMutationStub.deleteLibraryItemDirectly;
  aiPicks: AiPicksDiscover = {
    ok: true,
    generation_enabled: true,
    generation: null,
    library_exclusion: { status: 'fresh', last_successful_refresh_at: null },
    watched_exclusion: { status: 'fresh', last_successful_refresh_at: null },
    items: [
      {
        id: 'ai-eligible',
        source: 'ai',
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
  traktWatchedExclusion: ExclusionFixture = {
    status: 'fresh',
    last_successful_refresh_at: null,
  };
  jellyseerrWatchedExclusion: ExclusionFixture = {
    status: 'fresh', last_successful_refresh_at: null,
  };
  jellyseerrLibraryExclusion: ExclusionFixture = {
    status: 'fresh', last_successful_refresh_at: null,
  };
  traktLibraryExclusion: ExclusionFixture = {
    status: 'fresh', last_successful_refresh_at: null,
  };
  traktError: { message: string; code?: 'reconnect_required' } | null = null;
  jellyseerrError: { message: string; code?: 'reconnect_required' } | null = null;
  aiPicksCalls = 0;
  jellyseerrCalls: JellyseerrDiscoverKind[] = [];
  traktCalls: TraktDiscoverType[] = [];
  feedbackCalls: { id: string; feedback: DiscoverFeedback; options?: SubmitAiPickFeedbackOptions }[] = [];
  requestCalls: DiscoverRequestPayload[] = [];
  moreCalls = 0;
  feedbackGate: Promise<DiscoverAction> | null = null;
  aiPicksGate: Promise<AiPicksDiscover> | null = null;
  aiPicksDeferred: Promise<AiPicksDiscover> | null = null;
  lastAiPicksSignal?: AbortSignal;
  jellyseerrGate: Promise<{
    ok: boolean;
    items: ExternalDiscoverItem[];
    availability?: ExternalDiscoverAvailability;
    library_exclusion?: ExclusionFixture;
    watched_exclusion?: ExclusionFixture;
  }> | null = null;
  traktGate: Promise<{
    ok: boolean;
    items: ExternalDiscoverItem[];
    library_exclusion?: ExclusionFixture;
    watched_exclusion?: ExclusionFixture;
  }> | null = null;
  jellyseerrAvailability: 'available' | 'disabled' = 'available';
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
  listWatchNext() {
    return Promise.resolve({ items: [] });
  }
  listRecentlyAvailable() {
    return Promise.resolve({ items: [] });
  }
  getActivity() {
    return Promise.resolve({
      ok: true,
      generatedAt: '',
      sources: { sonarr: 'ok' as const, radarr: 'ok' as const },
      items: [],
    });
  }
  runQueueHygiene(_mode: 'observe' | 'auto') {
    return Promise.reject(new Error('not implemented'));
  }

  getAutomationSummary() {
    return Promise.resolve({
      generatedAt: '',
      services: [],
      preview: [],
      problems: [],
      queueHygiene: null,
      availability: { services: 'empty' as const, preview: 'empty' as const, problems: 'empty' as const },
    });
  }
  listAiPicks(signal?: AbortSignal) {
    this.aiPicksCalls++;
    this.lastAiPicksSignal = signal;
    if (this.aiPicksDeferred) {
      return this.withAbort(signal, this.aiPicksDeferred);
    }
    if (this.aiPicksGate) {
      const gate = this.aiPicksGate;
      this.aiPicksGate = null;
      return gate;
    }
    return Promise.resolve({
      ...this.aiPicks,
      items: this.aiPicks.items.map((item) => ({ ...item })),
      pending_request_sync: this.aiPicks.pending_request_sync?.map((entry) => ({ ...entry })),
    });
  }
  submitAiPickFeedback(id: string, feedback: DiscoverFeedback, options?: SubmitAiPickFeedbackOptions) {
    this.feedbackCalls.push({ id, feedback, options });
    if (feedback === 'watched') {
      return this.feedbackGate ?? Promise.resolve({
        ok: true,
        message: 'Feedback saved.',
        trakt_history_sync: { status: 'pending' as const },
      });
    }
    return this.feedbackGate ?? Promise.resolve({ ok: true, message: 'Feedback saved.' });
  }
  requestMoreAiPicks() {
    this.moreCalls++;
    if (!this.skipGenerationOnMore && (this.moreResult.queued || this.moreResult.already_pending)) {
      this.aiPicks.generation_enabled = true;
      this.aiPicks.generation = {
        id: 'job-1', status: 'queued', trigger: 'on_demand',
        requested_at: '2026-07-12T00:00:00Z', started_at: null, finished_at: null,
        desired_count: 10, attempt: 0, error_code: null, counts: null,
      };
    }
    return Promise.resolve(this.moreResult);
  }
  listJellyseerrDiscover(kind: JellyseerrDiscoverKind, signal?: AbortSignal) {
    this.jellyseerrCalls.push(kind);
    if (this.jellyseerrError) {
      return Promise.reject(Object.assign(new Error(this.jellyseerrError.message), { code: this.jellyseerrError.code }));
    }
    if (this.jellyseerrGate) {
      const gate = this.jellyseerrGate;
      this.jellyseerrGate = null;
      return this.withAbort(signal, gate);
    }
    return Promise.resolve({
      ok: true,
      items: this.jellyseerr[kind].map((item) => ({ ...item })),
      availability: this.jellyseerrAvailability,
      library_exclusion: this.jellyseerrLibraryExclusion,
      watched_exclusion: this.jellyseerrWatchedExclusion,
    });
  }
  listTraktDiscover(type: TraktDiscoverType, _signal?: AbortSignal) {
    this.traktCalls.push(type);
    if (this.traktGate) {
      const gate = this.traktGate;
      this.traktGate = null;
      return gate;
    }
    if (this.traktError) return Promise.reject(Object.assign(new Error(this.traktError.message), { code: this.traktError.code }));
    return Promise.resolve({
      ok: true,
      items: this.trakt[type].map((item) => ({ ...item })),
      library_exclusion: this.traktLibraryExclusion,
      watched_exclusion: this.traktWatchedExclusion,
    });
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
    return Promise.resolve({ ok: true, currentRuns: [], historyRuns: [] });
  }

  private withAbort<T>(signal: AbortSignal | undefined, pending: Promise<T>): Promise<T> {
    if (!signal) return pending;
    if (signal.aborted) {
      return Promise.reject(new DOMException('The operation was aborted.', 'AbortError'));
    }
    return new Promise<T>((resolve, reject) => {
      let settled = false;
      const onAbort = () => {
        if (settled) return;
        settled = true;
        reject(new DOMException('The operation was aborted.', 'AbortError'));
      };
      signal.addEventListener('abort', onAbort, { once: true });
      void pending.then(
        (value) => {
          if (settled) return;
          settled = true;
          signal.removeEventListener('abort', onAbort);
          resolve(value);
        },
        (error: unknown) => {
          if (settled) return;
          settled = true;
          signal.removeEventListener('abort', onAbort);
          reject(error instanceof Error ? error : new Error(String(error)));
        },
      );
    });
  }
}
