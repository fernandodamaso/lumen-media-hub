import { MediaStackApi, normalizeTorrent, summarizeDownloads } from './media-stack-api';
import { MockMediaStackApi, MOCK_SYNC_FAILED_HERMES_ID } from './mock-media-stack-api';

describe('MockMediaStackApi', () => {
  it('provides deterministic torrents and supports pause/resume all', async () => {
    const api: MediaStackApi = new MockMediaStackApi();
    const initial = await api.listTorrents();
    expect(initial.map((torrent) => torrent.hash)).toEqual(['demo-afterlight', 'demo-blue-hour', 'demo-orbit']);
    expect(initial.filter((torrent) => torrent.state === 'downloading')).toHaveLength(2);

    await api.pauseAll();
    const paused = await api.listTorrents();
    expect(paused.every((torrent) => torrent.state === 'paused' && torrent.dlspeed === 0 && torrent.upspeed === 0)).toBe(true);
    expect(summarizeDownloads(paused.map(normalizeTorrent))).toMatchObject({ downloadRate: 0, uploadRate: 0 });
    await api.resumeAll();
    const resumed = await api.listTorrents();
    expect(resumed.map(({ hash, dlspeed, upspeed }) => ({ hash, dlspeed, upspeed }))).toEqual(initial.map(({ hash, dlspeed, upspeed }) => ({ hash, dlspeed, upspeed })));
  });

  it('provides ordered mixed calendar events and arr library mappings', async () => {
    const api: MediaStackApi = new MockMediaStackApi();
    const events = await api.listCalendarEvents();
    expect(events.map((event) => event.title)).toEqual([
      'Cowboy Bebop',
      'Dune',
      'The Expanse',
      'Night Transit',
    ]);
    expect(events.some((event) => event.kind === 'episode')).toBe(true);
    expect(events.some((event) => event.kind === 'movie')).toBe(true);

    const library = await api.getArrLibrary();
    expect(library.series['cowboy bebop']).toBe('cowboy-bebop');
    expect(library.movies['dune']).toBe('dune-2021');
    expect(library.movies['night transit']).toBeUndefined();
  });

  it('isolates discover fixtures across Hermes and external filters', async () => {
    const api = new MockMediaStackApi();
    const hermes = await api.listHermesRecommendations();
    expect(hermes.ok).toBe(true);
    expect(hermes.items.some((item) => item.id === 'hermes-eligible' && item.active)).toBe(true);
    expect(hermes.items.some((item) => item.id === 'hermes-in-library' && item.in_library)).toBe(true);
    expect(hermes.items.some((item) => item.id === 'hermes-requested' && item.request_state === 'requested')).toBe(true);
    expect(hermes.items.some((item) => item.id === 'hermes-no-tmdb' && item.tmdb_id === 0)).toBe(true);
    expect(hermes.items.some((item) => item.id === MOCK_SYNC_FAILED_HERMES_ID)).toBe(true);
    expect(hermes.items.some((item) => !item.active && item.feedback === 'liked')).toBe(true);

    const jellyseerrTrending = await api.listJellyseerrDiscover('trending');
    const jellyseerrMovies = await api.listJellyseerrDiscover('movies');
    const jellyseerrTv = await api.listJellyseerrDiscover('tv');
    expect(jellyseerrTrending.items.map((item) => item.title)).toEqual(['Trending Ember', 'Trending Tide']);
    expect(jellyseerrMovies.items.map((item) => item.title)).toEqual(['Neon Archive', 'Paper Orbit']);
    expect(jellyseerrTv.items.map((item) => item.title)).toEqual(['Channel Zero Point', 'Late Broadcast']);
    expect(jellyseerrTrending.items.map((item) => item.tmdb_id)).not.toEqual(jellyseerrMovies.items.map((item) => item.tmdb_id));

    const traktMovies = await api.listTraktDiscover('movies');
    const traktShows = await api.listTraktDiscover('shows');
    expect(traktMovies.items.map((item) => item.title)).toEqual(['Trakt Horizon', 'Trakt Meridian']);
    expect(traktShows.items.map((item) => item.title)).toEqual(['Trakt Relay', 'Trakt Cascade']);
  });

  it('keeps feedback mutation isolated from request fields', async () => {
    const api = new MockMediaStackApi();
    const before = (await api.listHermesRecommendations()).items.find((item) => item.id === 'hermes-eligible')!;
    const requestSnapshot = {
      request_state: before.request_state,
      requested_at: before.requested_at,
      jellyseerr_request_id: before.jellyseerr_request_id,
    };

    const result = await api.submitHermesFeedback('hermes-eligible', 'liked');
    expect(result.ok).toBe(true);

    const after = (await api.listHermesRecommendations()).items.find((item) => item.id === 'hermes-eligible')!;
    expect(after.feedback).toBe('liked');
    expect(after.feedback_at).toBeTruthy();
    expect(after.active).toBe(false);
    expect(after.request_state).toBe(requestSnapshot.request_state);
    expect(after.requested_at).toBe(requestSnapshot.requested_at);
    expect(after.jellyseerr_request_id).toBe(requestSnapshot.jellyseerr_request_id);
  });

  it('requestMedia updates request fields without touching feedback', async () => {
    const api = new MockMediaStackApi();
    const before = (await api.listHermesRecommendations()).items.find((item) => item.id === 'hermes-eligible')!;
    expect(before.feedback).toBeNull();

    const result = await api.requestMedia({ mediaType: 'movie', mediaId: 101001, hermesId: 'hermes-eligible' });
    expect(result.ok).toBe(true);
    expect(result.dashboard_state_persisted).toBe(true);

    const after = (await api.listHermesRecommendations()).items.find((item) => item.id === 'hermes-eligible')!;
    expect(after.request_state).toBe('requested');
    expect(after.requested_at).toBeTruthy();
    expect(after.jellyseerr_request_id).toBeTruthy();
    expect(after.feedback).toBeNull();
    expect(after.feedback_at).toBeNull();
  });

  it('simulates sync-failed partial success without writing request_state', async () => {
    const api = new MockMediaStackApi();
    const result = await api.requestMedia({ mediaType: 'tv', mediaId: 101005, hermesId: MOCK_SYNC_FAILED_HERMES_ID });
    expect(result.ok).toBe(true);
    expect(result.dashboard_state_persisted).toBe(false);
    expect(result.partial_success).toBe(true);

    const after = (await api.listHermesRecommendations()).items.find((item) => item.id === MOCK_SYNC_FAILED_HERMES_ID)!;
    expect(after.request_state).toBeNull();
    expect(after.jellyseerr_request_id).toBeTruthy();
  });

  it('requestHermesMore queues once then reports already_pending', async () => {
    const api = new MockMediaStackApi();
    const first = await api.requestHermesMore();
    expect(first).toMatchObject({ ok: true, queued: true, already_pending: false });
    const second = await api.requestHermesMore();
    expect(second).toMatchObject({ ok: true, queued: false, already_pending: true });
    const hermes = await api.listHermesRecommendations();
    expect(hermes.generation_request?.status).toBe('pending');
  });

  it('dedupes external requests by TMDB id and media type', async () => {
    const api = new MockMediaStackApi();
    const first = await api.requestMedia({ mediaType: 'movie', mediaId: 301001 });
    expect(first.ok).toBe(true);
    expect(first.message).toBe('Requested');
    const second = await api.requestMedia({ mediaType: 'movie', mediaId: 301001 });
    expect(second.message).toBe('Already requested');
  });
  it('provides deterministic automation summary with mixed service health', async () => {
    const api = new MockMediaStackApi();
    const summary = await api.getAutomationSummary();
    expect(summary.generatedAt).toBe('2026-07-12T18:00:00Z');
    expect(summary.services?.map((service) => service.id)).toEqual(['sonarr', 'radarr', 'prowlarr', 'sabnzbd']);
    expect(summary.services?.some((service) => service.status === 'down')).toBe(true);
    expect(summary.services?.some((service) => service.status === 'degraded')).toBe(true);
    expect(summary.problems?.some((problem) => problem.severity === 'actionable')).toBe(true);
    expect(summary.preview).toHaveLength(3);
  });
  it('provides a partial automation summary marking preview and problems unavailable', async () => {
    const api = new MockMediaStackApi();
    api.setAutomationScenario('partial');
    const summary = await api.getAutomationSummary();
    expect(summary.services).toHaveLength(1);
    expect(summary.unavailable).toEqual({ preview: true, problems: true });
    expect(summary.preview).toEqual([]);
  });
  it('lists library items with kind filter and defensive copies', async () => {
    const api: MediaStackApi = new MockMediaStackApi();
    const all = await api.listLibraryItems();
    expect(all.filter((item) => item.kind === 'movie').length).toBeGreaterThanOrEqual(3);
    expect(all.filter((item) => item.kind === 'series').length).toBeGreaterThanOrEqual(3);
    expect(all.some((item) => item.artworkState === 'missing')).toBe(true);
    expect(all.some((item) => item.artworkState === 'failed')).toBe(true);

    const movies = await api.listLibraryItems({ kind: 'movie' });
    expect(movies.every((item) => item.kind === 'movie')).toBe(true);

    const first = movies[0];
    first.title = 'Mutated';
    const again = await api.listLibraryItems({ kind: 'movie' });
    expect(again[0].title).not.toBe('Mutated');
  });
});
