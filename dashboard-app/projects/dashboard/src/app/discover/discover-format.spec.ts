import { DiscoverItem } from './discover.models';
import {
  discoverPosterFallback,
  isDiscoverFeedbackPressed,
  isAiPickActiveItem,
  isWatchedFeedbackDisabled,
  matchesDiscoverSearch,
  matchesHistoryFilter,
  resolveRequestAction,
  toExternalCardItem,
  toAiPickCardItem,
  traktHistorySyncLabel,
} from './discover-format';
import { mapAiPicksDiscover } from './discover-format';

function aiPickItem(overrides: Partial<DiscoverItem> = {}): DiscoverItem {
  return {
    id: 'item-1',
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
    ...overrides,
  };
}

describe('discover-format', () => {
  it('whitelists AI Picks item fields and drops backend-only metadata', () => {
    const mapped = mapAiPicksDiscover({
      ok: true,
      items: [{
        id: 'item-1',
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
        token: 'secret-token',
        watched_at: '2026-07-10T12:00:00Z',
        provider_metadata: { internal_id: 'private' },
      } as never],
    });

    expect(mapped.items[0]).toEqual({
      id: 'item-1',
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
      trakt_history_sync: null,
    });
    expect(mapped.items[0]).not.toHaveProperty('token');
    expect(mapped.items[0]).not.toHaveProperty('watched_at');
    expect(mapped.items[0]).not.toHaveProperty('provider_metadata');
  });

  it('maps request button labels and titles to the contract matrix', () => {
    expect(resolveRequestAction({ tmdbId: 0, requestState: null, inLibrary: false })).toEqual({
      label: 'No TMDB ID',
      title: 'Cannot request — missing TMDB id',
      disabled: true,
    });
    expect(resolveRequestAction({ tmdbId: 1, requestState: null, inLibrary: false }, { syncFailed: true })).toEqual({
      label: 'Added (sync failed)',
      title: 'Added to Sonarr/Radarr; dashboard synchronization failed.',
      disabled: true,
      syncFailed: true,
    });
    expect(resolveRequestAction({ tmdbId: 1, requestState: 'requested', inLibrary: false })).toEqual({
      label: 'Requested',
      title: 'Already added to Sonarr/Radarr',
      disabled: true,
    });
    expect(resolveRequestAction({ tmdbId: 1, requestState: null, inLibrary: true })).toEqual({
      label: 'In library',
      title: 'Already in your Jellyfin library',
      disabled: true,
    });
    expect(resolveRequestAction({ tmdbId: 1, requestState: null, inLibrary: false })).toEqual({
      label: 'Request',
      title: 'Add to Sonarr/Radarr without monitoring or downloading',
      disabled: false,
    });
  });

  it('treats liked as watched for history filtering and requested by request_state', () => {
    const liked = aiPickItem({ feedback: 'liked', active: false });
    const watched = aiPickItem({ id: 'w', feedback: 'watched', active: false });
    const disliked = aiPickItem({ id: 'd', feedback: 'disliked', active: false });
    const requested = aiPickItem({ id: 'r', request_state: 'requested', active: false });

    expect(matchesHistoryFilter(liked, 'watched')).toBe(true);
    expect(matchesHistoryFilter(watched, 'watched')).toBe(true);
    expect(matchesHistoryFilter(disliked, 'watched')).toBe(false);
    expect(matchesHistoryFilter(requested, 'requested')).toBe(true);
    expect(matchesHistoryFilter(liked, 'requested')).toBe(false);
    expect(matchesHistoryFilter(liked, 'liked')).toBe(true);
    expect(matchesHistoryFilter(liked, 'all')).toBe(true);
  });

  it('removes feedbacked titles from the Active AI Picks queue', () => {
    expect(isAiPickActiveItem(aiPickItem({ active: true, feedback: null }))).toBe(true);
    expect(isAiPickActiveItem(aiPickItem({ active: true, feedback: 'liked' }))).toBe(false);
    expect(isAiPickActiveItem(aiPickItem({ active: false, feedback: null }))).toBe(false);
  });

  it('treats liked as pressed for both liked and watched controls', () => {
    expect(isDiscoverFeedbackPressed('liked', 'liked')).toBe(true);
    expect(isDiscoverFeedbackPressed('liked', 'watched')).toBe(true);
    expect(isDiscoverFeedbackPressed('liked', 'disliked')).toBe(false);
    expect(isDiscoverFeedbackPressed('watched', 'watched')).toBe(true);
    expect(isDiscoverFeedbackPressed('watched', 'liked')).toBe(false);
  });

  it('maps Trakt sync status labels for AI Picks history badges', () => {
    expect(traktHistorySyncLabel('pending')).toBe('Pending Trakt sync');
    expect(traktHistorySyncLabel('synced')).toBe('Watched on Trakt');
    expect(traktHistorySyncLabel('reconnect_required')).toBe('Trakt reconnect required');
    expect(traktHistorySyncLabel('failed')).toBe('Trakt sync failed');
  });

  it('disables watched feedback while Trakt sync is pending or complete', () => {
    expect(isWatchedFeedbackDisabled({ feedback: null, traktHistorySync: { status: 'pending' } })).toBe(true);
    expect(isWatchedFeedbackDisabled({ feedback: 'watched', traktHistorySync: { status: 'synced' } })).toBe(true);
    expect(isWatchedFeedbackDisabled({ feedback: null, traktHistorySync: { status: 'failed' } })).toBe(false);
  });

  it('builds a deterministic title-based poster fallback gradient', () => {
    const first = discoverPosterFallback('Signal Drift');
    const second = discoverPosterFallback('Signal Drift');
    const other = discoverPosterFallback('Other Title');
    expect(first).toBe(second);
    expect(first).toContain('linear-gradient');
    expect(first).toContain('hsl(');
    expect(first).not.toBe(other);
  });

  it('matches discover search case-insensitively across title, year, reason, and overview', () => {
    const item = {
      title: 'Signal Drift',
      year: 2024,
      reason: 'Because you liked sci-fi',
      overview: 'A deep space relay',
    };
    expect(matchesDiscoverSearch(item, '')).toBe(true);
    expect(matchesDiscoverSearch(item, '   ')).toBe(true);
    expect(matchesDiscoverSearch(item, 'signal')).toBe(true);
    expect(matchesDiscoverSearch(item, '2024')).toBe(true);
    expect(matchesDiscoverSearch(item, 'SCI-FI')).toBe(true);
    expect(matchesDiscoverSearch(item, 'relay')).toBe(true);
    expect(matchesDiscoverSearch(item, 'no match')).toBe(false);
  });

  it('maps aiPicks and external DTOs into card items', () => {
    expect(toAiPickCardItem(aiPickItem({ in_library: true }))).toMatchObject({
      aiPickId: 'item-1',
      tmdbId: 101001,
      inLibrary: true,
    });
    expect(
      toExternalCardItem(
        { type: 'tv', title: 'Relay', tmdb_id: 9, overview: 'Show' },
        'trakt',
      ),
    ).toMatchObject({
      id: 'trakt-tv-9',
      tmdbId: 9,
      feedback: null,
      requestState: null,
    });
    expect(
      toExternalCardItem({ type: 'tv', title: 'Relay', tmdb_id: 9 }, 'trakt', new Set(['tv:9'])).requestState,
    ).toBe('requested');
  });

  it('keeps an in-library AI Picks item out of Active while preserving it for History', () => {
    const item = aiPickItem({ active: true, excluded_reason: 'in_library', in_library: true });
    expect(isAiPickActiveItem(item)).toBe(false);
    expect(toAiPickCardItem(item)).toMatchObject({ inLibrary: true, excludedReason: 'in_library' });
  });

  it('derives the In library badge from the exclusion reason', () => {
    const item = aiPickItem({ in_library: false, excluded_reason: 'in_library' });
    expect(toAiPickCardItem(item).inLibrary).toBe(true);
  });

  it('keeps a Trakt-watched AI Picks item out of Active and in the Watched History filter', () => {
    const item = aiPickItem({ active: true, excluded_reason: 'watched_on_trakt', watched_on_trakt: true });
    expect(isAiPickActiveItem(item)).toBe(false);
    expect(matchesHistoryFilter(item, 'watched')).toBe(true);
    expect(toAiPickCardItem(item)).toMatchObject({
      watchedOnTrakt: true,
      excludedReason: 'watched_on_trakt',
      inLibrary: false,
    });
  });

  it('keeps library precedence while retaining Watched filter eligibility', () => {
    const item = aiPickItem({ active: true, excluded_reason: 'in_library', in_library: true, watched_on_trakt: true });
    expect(isAiPickActiveItem(item)).toBe(false);
    expect(matchesHistoryFilter(item, 'watched')).toBe(true);
    expect(toAiPickCardItem(item)).toMatchObject({
      watchedOnTrakt: true,
      excludedReason: 'in_library',
      inLibrary: true,
    });
  });
});
