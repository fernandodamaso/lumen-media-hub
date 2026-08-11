import { DiscoverItem } from './discover.models';
import {
  discoverPosterFallback,
  isDiscoverFeedbackPressed,
  isHermesActiveItem,
  matchesDiscoverSearch,
  matchesHistoryFilter,
  resolveRequestAction,
  toExternalCardItem,
  toHermesCardItem,
} from './discover-format';

function hermesItem(overrides: Partial<DiscoverItem> = {}): DiscoverItem {
  return {
    id: 'item-1',
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
    ...overrides,
  };
}

describe('discover-format', () => {
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
    const liked = hermesItem({ feedback: 'liked', active: false });
    const watched = hermesItem({ id: 'w', feedback: 'watched', active: false });
    const disliked = hermesItem({ id: 'd', feedback: 'disliked', active: false });
    const requested = hermesItem({ id: 'r', request_state: 'requested', active: false });

    expect(matchesHistoryFilter(liked, 'watched')).toBe(true);
    expect(matchesHistoryFilter(watched, 'watched')).toBe(true);
    expect(matchesHistoryFilter(disliked, 'watched')).toBe(false);
    expect(matchesHistoryFilter(requested, 'requested')).toBe(true);
    expect(matchesHistoryFilter(liked, 'requested')).toBe(false);
    expect(matchesHistoryFilter(liked, 'liked')).toBe(true);
    expect(matchesHistoryFilter(liked, 'all')).toBe(true);
  });

  it('removes feedbacked titles from the Active Hermes queue', () => {
    expect(isHermesActiveItem(hermesItem({ active: true, feedback: null }))).toBe(true);
    expect(isHermesActiveItem(hermesItem({ active: true, feedback: 'liked' }))).toBe(false);
    expect(isHermesActiveItem(hermesItem({ active: false, feedback: null }))).toBe(false);
  });

  it('treats liked as pressed for both liked and watched controls', () => {
    expect(isDiscoverFeedbackPressed('liked', 'liked')).toBe(true);
    expect(isDiscoverFeedbackPressed('liked', 'watched')).toBe(true);
    expect(isDiscoverFeedbackPressed('liked', 'disliked')).toBe(false);
    expect(isDiscoverFeedbackPressed('watched', 'watched')).toBe(true);
    expect(isDiscoverFeedbackPressed('watched', 'liked')).toBe(false);
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

  it('maps hermes and external DTOs into card items', () => {
    expect(toHermesCardItem(hermesItem({ in_library: true }))).toMatchObject({
      hermesId: 'item-1',
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

  it('keeps an in-library Hermes item out of Active while preserving it for History', () => {
    const item = hermesItem({ active: true, excluded_reason: 'in_library', in_library: true });
    expect(isHermesActiveItem(item)).toBe(false);
    expect(toHermesCardItem(item)).toMatchObject({ inLibrary: true, excludedReason: 'in_library' });
  });

  it('derives the In library badge from the exclusion reason', () => {
    const item = hermesItem({ in_library: false, excluded_reason: 'in_library' });
    expect(toHermesCardItem(item).inLibrary).toBe(true);
  });
});
