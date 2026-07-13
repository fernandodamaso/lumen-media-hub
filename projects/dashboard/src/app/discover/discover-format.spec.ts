import { MediaStackDiscoverItemDto } from '../downloads/media-stack-api';
import {
  matchesHistoryFilter,
  resolveRequestAction,
  toExternalCardItem,
  toHermesCardItem,
} from './discover-format';

function hermesItem(overrides: Partial<MediaStackDiscoverItemDto> = {}): MediaStackDiscoverItemDto {
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
});
